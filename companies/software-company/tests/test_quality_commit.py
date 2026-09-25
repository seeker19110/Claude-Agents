"""Durable quality outcomes use the real journal, never a worker's success claim."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta

import pytest
from xagents_core.execution import (
    ExecutionEvent,
    ExecutionEventKind,
    ExecutionJournal,
    ExecutionJournalError,
    RunSpec,
    RunStatus,
    TaskSpec,
    TaskStatus,
)

from company.quality_execution import (
    QUALITY_TASK_ID,
    QualityBindings,
    commit_quality_result,
    compile_execution,
)
from test_product_quality import NOW
from test_product_quality import bundle as bundle
from test_quality_execution import source_result, work_for


def bindings(kwargs):
    return QualityBindings(expected_attempt_id="attempt-1", expected_base_sha="c" * 40,
                           expected_diff_hash="d" * 64, expected_contract_hash=kwargs["expected_contract_hash"],
                           candidate_sha=kwargs["candidate_sha"], context_hash=kwargs["context_hash"],
                           author_principals=kwargs["author_principals"])


def begin(journal, profile):
    spec = compile_execution(profile, work_for(profile))
    journal.register(spec)
    journal.transition(ExecutionEvent(profile.run_id, ExecutionEventKind.RUN_STARTED), expected_count=0)
    for task in spec.tasks:
        count = len(journal.events(profile.run_id))
        journal.transition(ExecutionEvent(profile.run_id, ExecutionEventKind.TASK_STARTED, task.task_id,
                                         payload={"attempt_id": "attempt-1"}), expected_count=count)
        if task.task_id != QUALITY_TASK_ID:
            journal.transition(ExecutionEvent(profile.run_id, ExecutionEventKind.TASK_SUCCEEDED, task.task_id),
                               expected_count=count + 1)
    return len(journal.events(profile.run_id))


def commit(journal, profile, receipts, kwargs, count, *, result=None, event_id="submission-1", now=NOW, pins=None):
    return commit_quality_result(journal, profile, result or source_result(), receipts,
                                 event_id=event_id, expected_count=count, bindings=pins or bindings(kwargs),
                                 trusted_issuers=kwargs["trusted_issuers"], evidence_root=kwargs["evidence_root"], now=now,
                                 approval_lookup=kwargs.get("approval_lookup"))


def commit_no_expected_count(journal, profile, receipts, kwargs, *, result=None, event_id="submission-1",
                              now=NOW, pins=None):
    """Đường mặc định: không truyền `expected_count` — hàm tự lấy `len(history)` làm snapshot."""
    return commit_quality_result(journal, profile, result or source_result(), receipts,
                                 event_id=event_id, bindings=pins or bindings(kwargs),
                                 trusted_issuers=kwargs["trusted_issuers"], evidence_root=kwargs["evidence_root"], now=now)


def test_accepted_result_and_evidence_survive_restart_without_signer_keys(bundle, tmp_path):
    profile, receipts, kwargs = bundle
    path = tmp_path / "run.sqlite"
    with ExecutionJournal(path) as journal:
        count = begin(journal, profile)
        state = commit(journal, profile, receipts, kwargs, count)
        assert state.status is RunStatus.SUCCEEDED
        stored = journal.events(profile.run_id)[-1].payload
        assert stored["result"]["status"] == "succeeded"
        assert stored["bindings"]["expected_attempt_id"] == "attempt-1"
        assert len(stored["receipts"]) == len(receipts)
        assert "key" not in json.dumps(stored)
    with ExecutionJournal(path) as journal:
        assert journal.resume(profile.run_id) == state
        assert journal.events(profile.run_id)[-1].payload == stored


def test_missing_evidence_persists_failure_not_false_completion(bundle, tmp_path):
    profile, _, kwargs = bundle
    with ExecutionJournal(tmp_path / "run.sqlite") as journal:
        count = begin(journal, profile)
        state = commit(journal, profile, [], kwargs, count)
        assert state.status is RunStatus.BLOCKED
        assert "missing" in state.blocked_reason
        assert state.tasks["implementation"] is TaskStatus.SUCCEEDED
        assert journal.events(profile.run_id)[-1].payload["result"]["findings"]


def test_lost_ack_returns_stored_outcome_not_a_new_approval_after_expiry(bundle, tmp_path):
    profile, receipts, kwargs = bundle
    path = tmp_path / "run.sqlite"
    with ExecutionJournal(path) as journal:
        count = begin(journal, profile)
        state = commit(journal, profile, receipts, kwargs, count)
    with ExecutionJournal(path) as journal:
        assert commit(journal, profile, receipts, kwargs, count, now=NOW + timedelta(days=2)) == state
        assert len(journal.events(profile.run_id)) == count + 1
        assert journal.events(profile.run_id)[-1].ts == NOW


def test_same_submission_id_cannot_replace_existing_outcome(bundle, tmp_path):
    profile, receipts, kwargs = bundle
    with ExecutionJournal(tmp_path / "run.sqlite") as journal:
        count = begin(journal, profile)
        commit(journal, profile, receipts, kwargs, count)
        with pytest.raises(ExecutionJournalError, match="collision"):
            commit(journal, profile, [], kwargs, count)
        assert journal.resume(profile.run_id).status is RunStatus.SUCCEEDED


def test_unregistered_or_unbound_workflow_cannot_be_certified(bundle, tmp_path):
    profile, receipts, kwargs = bundle
    with ExecutionJournal(tmp_path / "run.sqlite") as journal:
        with pytest.raises(ExecutionJournalError, match="contract"):
            commit(journal, profile, receipts, kwargs, 0)
        journal.register(work_for(profile))
        with pytest.raises(ExecutionJournalError, match="contract"):
            commit(journal, profile, receipts, kwargs, 0)
        assert journal.events(profile.run_id) == ()


def test_profile_change_cannot_certify_old_plan(bundle, tmp_path):
    profile, receipts, kwargs = bundle
    with ExecutionJournal(tmp_path / "run.sqlite") as journal:
        count = begin(journal, profile)
        changed = profile.model_copy(update={"technology_rationale": "A different decision"})
        with pytest.raises(ExecutionJournalError, match="contract"):
            commit(journal, changed, receipts, kwargs, count)
        assert len(journal.events(profile.run_id)) == count


def test_no_active_attempt_or_wrong_attempt_cannot_commit(bundle, tmp_path):
    profile, receipts, kwargs = bundle
    with ExecutionJournal(tmp_path / "run.sqlite") as journal:
        journal.register(compile_execution(profile, work_for(profile)))
        with pytest.raises(ExecutionJournalError, match="attempt"):
            commit(journal, profile, receipts, kwargs, 0)
        count = begin(journal, profile)
        with pytest.raises(ExecutionJournalError, match="attempt"):
            commit(journal, profile, receipts, kwargs, count,
                   pins=replace(bindings(kwargs), expected_attempt_id="old-attempt"))
        assert len(journal.events(profile.run_id)) == count


def test_state_change_during_assessment_rejected_atomically(bundle, tmp_path, monkeypatch):
    from company import quality_execution

    profile, receipts, kwargs = bundle
    with ExecutionJournal(tmp_path / "run.sqlite") as journal:
        count = begin(journal, profile)
        original = quality_execution.evaluate_result

        def racing_assessment(*args, **kw):
            result = original(*args, **kw)
            journal.transition(ExecutionEvent(profile.run_id, ExecutionEventKind.RUN_CANCELLED), expected_count=count)
            return result

        monkeypatch.setattr(quality_execution, "evaluate_result", racing_assessment)
        with pytest.raises(ExecutionJournalError, match="stale"):
            commit(journal, profile, receipts, kwargs, count)
        assert journal.resume(profile.run_id).status is RunStatus.CANCELLED
        assert len(journal.events(profile.run_id)) == count + 1
        assert all(e.event_id != "submission-1" for e in journal.events(profile.run_id))


def test_failure_retry_preserves_work_and_rejects_late_old_submission(bundle, tmp_path):
    profile, receipts, kwargs = bundle
    with ExecutionJournal(tmp_path / "run.sqlite") as journal:
        count = begin(journal, profile)
        commit(journal, profile, [], kwargs, count)
        journal.transition(ExecutionEvent(profile.run_id, ExecutionEventKind.TASK_RETRIED, QUALITY_TASK_ID),
                           expected_count=count + 1)
        journal.transition(ExecutionEvent(profile.run_id, ExecutionEventKind.TASK_STARTED, QUALITY_TASK_ID,
                                         payload={"attempt_id": "attempt-2"}), expected_count=count + 2)
        with pytest.raises(ExecutionJournalError, match="attempt"):
            commit(journal, profile, receipts, kwargs, count, event_id="late-old")
        state = commit(journal, profile, receipts, kwargs, count + 3, event_id="submission-2",
                       result=replace(source_result(), attempt_id="attempt-2"),
                       pins=replace(bindings(kwargs), expected_attempt_id="attempt-2"))
        assert state.status is RunStatus.SUCCEEDED
        assert state.attempts["implementation"] == 1
        assert state.attempts[QUALITY_TASK_ID] == 2


def test_contract_pin_and_plan_quality_barrier_cannot_be_removed(bundle, tmp_path):
    profile, receipts, kwargs = bundle
    compiled = compile_execution(profile, work_for(profile))
    broken = RunSpec(compiled.run_id, compiled.objective,
                     (*compiled.tasks[:-1], TaskSpec(QUALITY_TASK_ID, "Bogus acceptance")))
    with ExecutionJournal(tmp_path / "run.sqlite") as journal:
        journal.register(broken)
        with pytest.raises(ExecutionJournalError, match="contract"):
            commit(journal, profile, receipts, kwargs, 0)


def test_expected_count_is_optional_and_defaults_to_fresh_history_length(bundle, tmp_path):
    """Không truyền expected_count vẫn commit được: hàm tự soi len(history) làm snapshot của chính nó."""
    profile, receipts, kwargs = bundle
    with ExecutionJournal(tmp_path / "run.sqlite") as journal:
        begin(journal, profile)
        state = commit_no_expected_count(journal, profile, receipts, kwargs)
        assert state.status is RunStatus.SUCCEEDED


def test_expected_count_mismatch_rejected_before_evaluate(bundle, tmp_path, monkeypatch):
    """Truyền expected_count sai lệch với len(history) hiện tại phải hỏng NGAY, trước khi evaluate chạy."""
    from company import quality_execution

    profile, receipts, kwargs = bundle
    with ExecutionJournal(tmp_path / "run.sqlite") as journal:
        count = begin(journal, profile)

        def must_not_run(*_a, **_kw):
            raise AssertionError("evaluate_result must not run when expected_count is already stale")

        monkeypatch.setattr(quality_execution, "evaluate_result", must_not_run)
        with pytest.raises(ExecutionJournalError, match="stale event count"):
            commit(journal, profile, receipts, kwargs, count + 1)
        assert len(journal.events(profile.run_id)) == count


def test_expected_count_matching_still_commits(bundle, tmp_path):
    """Truyền đúng expected_count (khớp len(history)) vẫn chạy bình thường, không bị coi là stale."""
    profile, receipts, kwargs = bundle
    with ExecutionJournal(tmp_path / "run.sqlite") as journal:
        count = begin(journal, profile)
        state = commit(journal, profile, receipts, kwargs, count)
        assert state.status is RunStatus.SUCCEEDED


def test_race_during_evaluate_rejected_even_without_caller_supplied_count(bundle, tmp_path, monkeypatch):
    """CAS phải tự bảo vệ dù caller không truyền expected_count: hàm tự đọc history đầu hàm, trước evaluate,
    và cùng snapshot đó phải khớp lúc transition — chen một event qua connection khác giữa lúc evaluate chạy
    phải làm commit hỏng, không phải âm thầm ghi đè lên state đã đổi."""
    from company import quality_execution

    profile, receipts, kwargs = bundle
    path = tmp_path / "run.sqlite"
    with ExecutionJournal(path) as journal:
        begin(journal, profile)
        original = quality_execution.evaluate_result

        def racing_assessment(*args, **kw):
            result = original(*args, **kw)
            with ExecutionJournal(path) as racer:
                count = len(racer.events(profile.run_id))
                racer.transition(ExecutionEvent(profile.run_id, ExecutionEventKind.RUN_CANCELLED),
                                 expected_count=count)
            return result

        monkeypatch.setattr(quality_execution, "evaluate_result", racing_assessment)
        with pytest.raises(ExecutionJournalError, match="stale"):
            commit_no_expected_count(journal, profile, receipts, kwargs)
        assert journal.resume(profile.run_id).status is RunStatus.CANCELLED
        assert all(e.event_id != "submission-1" for e in journal.events(profile.run_id))


def test_command_receipt_is_serialized_without_raw_output(bundle, tmp_path):
    from xagents_core.execution import EvidenceReceipt

    profile, receipts, kwargs = bundle
    command = EvidenceReceipt.from_output(command="test", cwd="sandbox", exit_code=0,
                                         head_sha=kwargs["candidate_sha"], output=b"private output", duration_ms=1)
    result = replace(source_result(), evidence=(command,))
    with ExecutionJournal(tmp_path / "run.sqlite") as journal:
        count = begin(journal, profile)
        assert commit(journal, profile, receipts, kwargs, count, result=result).status is RunStatus.SUCCEEDED
        payload = journal.events(profile.run_id)[-1].payload
        assert payload["result"]["evidence"][0]["started_at"] == command.started_at.isoformat()
        assert "private output" not in json.dumps(payload)


def test_ket_qua_muon_cua_attempt_cu_bi_tu_choi_khong_danh_failed_attempt_moi(bundle, tmp_path):
    """sc-security N5 #3: bindings đúng attempt mới nhất (CLI/driver đọc từ journal) nhưng kết quả mang attempt cũ
    ⇒ từ chối, KHÔNG ghi gì. Trước đây nó thành finding `wrong_task_or_attempt` và đánh FAILED attempt mới, rồi
    bộ đối chiếu chờ sha mới mãi."""
    profile, receipts, kwargs = bundle
    with ExecutionJournal(tmp_path / "run.sqlite") as journal:
        count = begin(journal, profile)
        commit(journal, profile, [], kwargs, count)
        journal.transition(ExecutionEvent(profile.run_id, ExecutionEventKind.TASK_RETRIED, QUALITY_TASK_ID),
                           expected_count=count + 1)
        journal.transition(ExecutionEvent(profile.run_id, ExecutionEventKind.TASK_STARTED, QUALITY_TASK_ID,
                                         payload={"attempt_id": "attempt-2"}), expected_count=count + 2)
        current = replace(bindings(kwargs), expected_attempt_id="attempt-2")
        with pytest.raises(ExecutionJournalError, match=r"attempt-1.*attempt-2"):
            commit(journal, profile, receipts, kwargs, count + 3, event_id="late-old", pins=current)
        assert len(journal.events(profile.run_id)) == count + 3, "không ghi event nào"
        assert journal.resume(profile.run_id).tasks[QUALITY_TASK_ID] is TaskStatus.RUNNING
        state = commit(journal, profile, receipts, kwargs, count + 3, event_id="submission-2", pins=current,
                       result=replace(source_result(), attempt_id="attempt-2"))
        assert state.status is RunStatus.SUCCEEDED, "attempt mới vẫn nộp được sau khi từ chối kết quả muộn"


def test_sai_task_id_van_la_finding_khong_phai_tu_choi(bundle, tmp_path):
    """Chỉ attempt cũ mới bị từ chối; kết quả sai task cho đúng attempt hiện tại vẫn được chấm FAILED như trước."""
    profile, receipts, kwargs = bundle
    with ExecutionJournal(tmp_path / "run.sqlite") as journal:
        count = begin(journal, profile)
        state = commit(journal, profile, receipts, kwargs, count,
                       result=replace(source_result(), task_id="implementation"))
        assert state.tasks[QUALITY_TASK_ID] is TaskStatus.FAILED
        assert "execution:wrong_task_or_attempt" in state.blocked_reason
