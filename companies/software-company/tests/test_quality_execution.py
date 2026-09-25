"""Native execution-kernel integration; synthetic receipts are not product evidence."""
from __future__ import annotations

import json
from dataclasses import replace

import pytest
from xagents_core.execution import (
    ExecutionEvent,
    ExecutionEventKind,
    ExecutionJournal,
    RunSpec,
    RunState,
    RunStatus,
    TaskResult,
    TaskSpec,
    TaskStatus,
    apply_event,
)

from company.quality_execution import QUALITY_TASK_ID, compile_execution, evaluate_result, main
from test_product_quality import SHA, compile_contract, make_profile
from test_product_quality import bundle as bundle


def work_for(profile):
    return RunSpec(profile.run_id, profile.goal, (
        TaskSpec("implementation", "Implement the scoped change", write_scope=("src/**",)),
        TaskSpec("integration", "Integrate and test", dependencies=("implementation",)),
    ))


def source_result():
    return TaskResult(QUALITY_TASK_ID, "attempt-1", TaskStatus.SUCCEEDED, "c" * 40, SHA, "d" * 64)


def expected(kwargs):
    return {**kwargs, "expected_attempt_id": "attempt-1", "expected_base_sha": "c" * 40,
            "expected_diff_hash": "d" * 64}


def test_compile_uses_native_kernel_preserves_work_and_adds_final_quality_barrier():
    profile = make_profile()
    work = work_for(profile)
    spec = compile_execution(profile, work)
    assert type(spec) is RunSpec
    assert spec.tasks[-1].task_id == QUALITY_TASK_ID
    assert spec.tasks[-1].dependencies == ("implementation", "integration")
    assert spec.tasks[-1].write_scope == () and spec.tasks[-1].allowed_tools == ()
    assert spec.tasks[0].write_scope == work.tasks[0].write_scope
    assert spec.tasks[1].dependencies == work.tasks[1].dependencies
    contract = compile_contract(profile)["contract_hash"]
    assert all(f"quality-contract:sha256:{contract}" in task.context_refs for task in spec.tasks)
    assert "goal.traceability" in spec.tasks[-1].acceptance
    assert RunSpec.from_json(spec.to_json()) == spec
    assert compile_execution(profile, work) == spec


def test_result_must_pass_domain_assessor_not_worker_success(bundle):
    profile, receipts, kwargs = bundle
    result = evaluate_result(profile, source_result(), [], **expected(kwargs))
    assert result.status is TaskStatus.FAILED
    assert any("missing" in finding for finding in result.findings)
    assert evaluate_result(profile, source_result(), receipts, **expected(kwargs)).status is TaskStatus.SUCCEEDED


def test_native_journal_restart_keeps_implementation_but_quality_remains_pending(tmp_path):
    profile = make_profile()
    spec = compile_execution(profile, work_for(profile))
    path = tmp_path / "execution.sqlite"
    with ExecutionJournal(path) as journal:
        journal.register(spec)
        journal.register(spec)
        state = journal.resume(spec.run_id)
        for kind, task_id in [
            (ExecutionEventKind.RUN_STARTED, None),
            (ExecutionEventKind.TASK_STARTED, "implementation"),
            (ExecutionEventKind.TASK_SUCCEEDED, "implementation"),
        ]:
            event = ExecutionEvent(spec.run_id, kind, task_id)
            state = apply_event(spec, state, event)
            journal.append(event)
    with ExecutionJournal(path) as reopened:
        restored = reopened.resume(spec.run_id)
        assert restored == state
        assert restored.tasks["implementation"] is TaskStatus.SUCCEEDED
        assert restored.tasks["integration"] is TaskStatus.READY
        assert restored.tasks[QUALITY_TASK_ID] is TaskStatus.PENDING
        assert restored.status is RunStatus.RUNNING


@pytest.mark.parametrize("change", ["run", "goal", "empty", "reserved", "pin"])
def test_compile_rejects_ambiguous_or_duplicate_contract(change):
    profile = make_profile()
    work = work_for(profile)
    if change == "run":
        work = replace(work, run_id="another-run")
    elif change == "goal":
        work = replace(work, objective="Different goal")
    elif change == "empty":
        work = replace(work, tasks=())
    elif change == "reserved":
        work = replace(work, tasks=(TaskSpec("quality:accept", "Collision"),))
    else:
        work = replace(work, tasks=(TaskSpec("task", "Pinned", context_refs=("quality-contract:sha256:old",)),))
    with pytest.raises(ValueError):
        compile_execution(profile, work)


@pytest.mark.parametrize("changes,reason", [
    ({"task_id": "implementation"}, "wrong_task_or_attempt"),
    ({"attempt_id": "old-attempt"}, "wrong_task_or_attempt"),
    ({"base_sha": "e" * 40}, "stale_base_head_or_diff"),
    ({"head_sha": "e" * 40}, "stale_base_head_or_diff"),
    ({"diff_hash": "e" * 64}, "stale_base_head_or_diff"),
    ({"status": TaskStatus.FAILED}, "source_not_succeeded"),
    ({"findings": ("existing blocker",)}, "existing blocker"),
])
def test_kernel_result_fields_cannot_override_pins(bundle, changes, reason):
    profile, receipts, kwargs = bundle
    result = evaluate_result(profile, replace(source_result(), **changes), receipts, **expected(kwargs))
    assert result.status is TaskStatus.FAILED
    assert any(reason in finding for finding in result.findings)


@pytest.mark.parametrize("field,value", [
    ("expected_attempt_id", " "), ("expected_base_sha", "short"),
    ("candidate_sha", "short"), ("expected_diff_hash", "short"),
    ("expected_contract_hash", "short"), ("context_hash", "short"),
])
def test_trusted_pins_must_be_complete(bundle, field, value):
    profile, receipts, kwargs = bundle
    args = {**expected(kwargs), field: value}
    with pytest.raises(ValueError):
        evaluate_result(profile, source_result(), receipts, **args)


def test_unresolved_decision_and_existing_command_failure_are_preserved(bundle):
    from xagents_core.execution import ArtifactRef, DecisionRequest, EvidenceReceipt

    profile, receipts, kwargs = bundle
    command = EvidenceReceipt.from_output(command="test", cwd="sandbox", exit_code=1,
                                          head_sha=SHA, output=b"fixture failure", duration_ms=1)
    artifact = ArtifactRef("fixture:report", "a" * 64)
    source = replace(source_result(), unresolved=(DecisionRequest("D1", "Question", "Missing authority"),),
                     evidence=(command,), artifacts=(artifact,))
    result = evaluate_result(profile, source, receipts, **expected(kwargs))
    assert result.status is TaskStatus.FAILED
    assert "execution:unresolved_decisions" in result.findings
    assert "execution:failed_or_stale_command_evidence" in result.findings
    assert result.evidence == source.evidence and result.artifacts == source.artifacts
    assert result.unresolved == source.unresolved
    passed = replace(command, exit_code=0)
    good = replace(source_result(), evidence=(passed,))
    assert evaluate_result(profile, good, receipts, **expected(kwargs)).status is TaskStatus.SUCCEEDED
    stale = replace(good, evidence=(replace(passed, head_sha="e" * 40),))
    assert evaluate_result(profile, stale, receipts, **expected(kwargs)).status is TaskStatus.FAILED


def test_native_failure_retry_and_completion_after_restart(bundle, tmp_path):
    profile, receipts, kwargs = bundle
    spec = compile_execution(profile, work_for(profile))
    path = tmp_path / "restart.sqlite"
    with ExecutionJournal(path) as journal:
        journal.register(spec)
        state = RunState.initial(spec)
        events = [(ExecutionEventKind.RUN_STARTED, None)]
        for task in spec.tasks:
            events.append((ExecutionEventKind.TASK_STARTED, task.task_id))
            if task.task_id != QUALITY_TASK_ID:
                events.append((ExecutionEventKind.TASK_SUCCEEDED, task.task_id))
        for kind, task_id in events:
            event = ExecutionEvent(spec.run_id, kind, task_id)
            state = apply_event(spec, state, event)
            journal.append(event)
        rejected = evaluate_result(profile, source_result(), [], **expected(kwargs))
        assert rejected.status is TaskStatus.FAILED
        event = ExecutionEvent(spec.run_id, ExecutionEventKind.TASK_FAILED, QUALITY_TASK_ID,
                               payload={"reason": "; ".join(rejected.findings)})
        state = apply_event(spec, state, event)
        journal.append(event)
    with ExecutionJournal(path) as journal:
        state = journal.resume(spec.run_id)
        assert state.status is RunStatus.BLOCKED
        assert state.tasks["implementation"] is TaskStatus.SUCCEEDED
        for kind in (ExecutionEventKind.TASK_RETRIED, ExecutionEventKind.TASK_STARTED):
            event = ExecutionEvent(spec.run_id, kind, QUALITY_TASK_ID)
            state = apply_event(spec, state, event)
            journal.append(event)
        result = replace(source_result(), attempt_id="attempt-2")
        accepted = evaluate_result(profile, result, receipts,
                                   **{**expected(kwargs), "expected_attempt_id": "attempt-2"})
        assert accepted.status is TaskStatus.SUCCEEDED
        event = ExecutionEvent(spec.run_id, ExecutionEventKind.TASK_SUCCEEDED, QUALITY_TASK_ID)
        state = apply_event(spec, state, event)
        journal.append(event)
        assert state.status is RunStatus.SUCCEEDED
        assert state.attempts["implementation"] == 1
        assert state.attempts[QUALITY_TASK_ID] == 2
    with ExecutionJournal(path) as journal:
        assert journal.resume(spec.run_id) == state


def cli_files(tmp_path):
    profile = make_profile()
    profile_path = tmp_path / "profile.json"
    work_path = tmp_path / "work.json"
    profile_path.write_text(profile.model_dump_json(), encoding="utf-8")
    work_path.write_text(work_for(profile).to_json(), encoding="utf-8")
    return profile, profile_path, work_path


def test_cli_plan_register_resume_and_contract_change(tmp_path, capsys):
    profile, profile_path, work_path = cli_files(tmp_path)
    args = [str(profile_path), str(work_path)]
    assert main(["plan", *args]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["execution_spec"]["tasks"][-1]["task_id"] == QUALITY_TASK_ID
    journal_path = tmp_path / "cli.sqlite"
    for _ in range(2):
        assert main(["register", *args, "--journal", str(journal_path)]) == 0
        capsys.readouterr()
    assert main(["status", profile.run_id, "--journal", str(journal_path)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "pending" and status["tasks"][QUALITY_TASK_ID] == "pending"
    assert status["attempts"]["implementation"] == 0
    profile_path.write_text(make_profile(technology_rationale="Another contract version").model_dump_json(), encoding="utf-8")
    assert main(["register", *args, "--journal", str(journal_path)]) == 2
    assert "ExecutionJournalError" in capsys.readouterr().err


@pytest.mark.parametrize("case", ["missing_journal", "missing_run", "corrupt_journal", "invalid_json", "missing_profile"])
def test_cli_errors_never_create_completion(tmp_path, capsys, case):
    profile, profile_path, work_path = cli_files(tmp_path)
    path = tmp_path / "state.sqlite"
    if case == "missing_run":
        with ExecutionJournal(path):
            pass
    elif case == "corrupt_journal":
        path.write_text("not a database", encoding="utf-8")
    if case in {"missing_journal", "missing_run", "corrupt_journal"}:
        args = ["status", profile.run_id, "--journal", str(path)]
    else:
        if case == "invalid_json":
            profile_path.write_text("secret-not-json", encoding="utf-8")
        else:
            profile_path.unlink()
        args = ["plan", str(profile_path), str(work_path)]
    assert main(args) == 2
    output = capsys.readouterr()
    assert not output.out and "no task completion issued" in output.err
    assert "secret-not-json" not in output.err
    if case == "missing_journal":
        assert not path.exists()


def test_adapter_module_entrypoint(tmp_path, monkeypatch, capsys):
    import runpy
    import warnings

    _, profile_path, work_path = cli_files(tmp_path)
    monkeypatch.setattr("sys.argv", ["quality_execution", "plan", str(profile_path), str(work_path)])
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*found in sys.modules.*", category=RuntimeWarning)
        with pytest.raises(SystemExit) as stopped:
            runpy.run_module("company.quality_execution", run_name="__main__", alter_sys=True)
    assert stopped.value.code == 0
    assert "execution_spec" in json.loads(capsys.readouterr().out)
