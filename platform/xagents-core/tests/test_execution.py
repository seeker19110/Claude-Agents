"""Execution harness kernel: contract, state machine, evidence và durable journal (ADR-0017).

Các ca ở đây cố ý kiểm tra cả chiều thuận lẫn chiều ngược. Harness sẽ trở thành lớp thi hành dưới phiên chính,
nên một transition sai ở đây có thể làm task chạy hai lần hoặc tuyên bố xong khi chưa đủ bằng chứng.
"""
from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

from xagents_core.execution import (
    Complexity,
    EvidenceReceipt,
    ExecutionEvent,
    ExecutionEventKind,
    ExecutionJournal,
    ExecutionJournalError,
    ExecutionTransitionError,
    RunSpec,
    RunState,
    RunStatus,
    TaskSpec,
    TaskStatus,
    apply_event,
)


def _spec(run_id: str = "RUN-1") -> RunSpec:
    return RunSpec(
        run_id=run_id,
        objective="xây tính năng",
        tasks=(
            TaskSpec(task_id="A", objective="nền", complexity=Complexity.C2),
            TaskSpec(task_id="B", objective="ghép", dependencies=("A",), complexity=Complexity.C3),
        ),
    )


def _event(
    kind: ExecutionEventKind,
    task_id: str | None = None,
    run_id: str = "RUN-1",
    **payload: object,
) -> ExecutionEvent:
    return ExecutionEvent(run_id=run_id, kind=kind, task_id=task_id, payload=dict(payload))


def test_task_khong_duoc_phu_thuoc_chinh_no() -> None:
    with pytest.raises(ValueError, match="phụ thuộc chính nó"):
        TaskSpec(task_id="A", objective="x", dependencies=("A",))


def test_run_spec_tu_choi_task_id_trung() -> None:
    task = TaskSpec(task_id="A", objective="x")
    with pytest.raises(ValueError, match="task_id trùng"):
        RunSpec(run_id="R", objective="x", tasks=(task, task))


def test_run_spec_tu_choi_dependency_khong_ton_tai() -> None:
    task = TaskSpec(task_id="A", objective="x", dependencies=("MISSING",))
    with pytest.raises(ValueError, match="dependency không tồn tại"):
        RunSpec(run_id="R", objective="x", tasks=(task,))


def test_run_spec_tu_choi_chu_trinh() -> None:
    a = TaskSpec(task_id="A", objective="x", dependencies=("B",))
    b = TaskSpec(task_id="B", objective="x", dependencies=("A",))
    with pytest.raises(ValueError, match="chu trình"):
        RunSpec(run_id="R", objective="x", tasks=(a, b))


def test_state_ban_dau_chi_task_khong_phu_thuoc_la_ready() -> None:
    state = RunState.initial(_spec())
    assert state.status is RunStatus.PENDING
    assert state.tasks == {"A": TaskStatus.READY, "B": TaskStatus.PENDING}
    assert state.attempts == {"A": 0, "B": 0}
    assert state.blocked_reason == ""


def test_run_started_chuyen_run_sang_running() -> None:
    spec = _spec()
    state = apply_event(spec, RunState.initial(spec), _event(ExecutionEventKind.RUN_STARTED))
    assert state.status is RunStatus.RUNNING
    with pytest.raises(ExecutionTransitionError, match="run_started"):
        apply_event(spec, state, _event(ExecutionEventKind.RUN_STARTED))


def test_event_khong_duoc_di_vao_run_khac() -> None:
    spec = _spec()
    with pytest.raises(ExecutionTransitionError, match="run khác"):
        apply_event(spec, RunState.initial(spec), _event(ExecutionEventKind.RUN_STARTED, run_id="RUN-2"))

    state_run_2 = RunState.initial(_spec("RUN-2"))
    with pytest.raises(ExecutionTransitionError, match="run khác"):
        apply_event(spec, state_run_2, _event(ExecutionEventKind.RUN_STARTED, run_id="RUN-2"))


def test_task_event_bat_buoc_task_id_hop_le() -> None:
    spec = _spec()
    state = apply_event(spec, RunState.initial(spec), _event(ExecutionEventKind.RUN_STARTED))
    with pytest.raises(ExecutionTransitionError, match="thiếu task_id"):
        apply_event(spec, state, _event(ExecutionEventKind.TASK_STARTED))
    with pytest.raises(ExecutionTransitionError, match="task không tồn tại"):
        apply_event(spec, state, _event(ExecutionEventKind.TASK_STARTED, "NOPE"))


def test_task_started_chi_khi_run_dang_running() -> None:
    spec = _spec()
    with pytest.raises(ExecutionTransitionError, match="run phải RUNNING"):
        apply_event(spec, RunState.initial(spec), _event(ExecutionEventKind.TASK_STARTED, "A"))


def test_task_started_chi_khi_task_ready() -> None:
    spec = _spec()
    state = apply_event(spec, RunState.initial(spec), _event(ExecutionEventKind.RUN_STARTED))
    with pytest.raises(ExecutionTransitionError, match="task phải READY"):
        apply_event(spec, state, _event(ExecutionEventKind.TASK_STARTED, "B"))
    with pytest.raises(ExecutionTransitionError, match="task_succeeded: task phải RUNNING"):
        apply_event(spec, state, _event(ExecutionEventKind.TASK_SUCCEEDED, "A"))
    with pytest.raises(ExecutionTransitionError, match="task_failed: task phải RUNNING"):
        apply_event(spec, state, _event(ExecutionEventKind.TASK_FAILED, "A"))


def test_task_succeeded_mo_khoa_dependency_va_ket_thuc_run() -> None:
    spec = RunSpec(
        run_id="RUN-1",
        objective="x",
        tasks=(
            TaskSpec("A", "a"),
            TaskSpec("B", "b", dependencies=("A",)),
            TaskSpec("C", "c", dependencies=("A", "B")),
        ),
    )
    state = RunState.replay(
        spec,
        (
            _event(ExecutionEventKind.RUN_STARTED),
            _event(ExecutionEventKind.TASK_STARTED, "A"),
            _event(ExecutionEventKind.TASK_SUCCEEDED, "A"),
        ),
    )
    assert state.status is RunStatus.RUNNING
    assert state.tasks == {
        "A": TaskStatus.SUCCEEDED,
        "B": TaskStatus.READY,
        "C": TaskStatus.PENDING,
    }
    assert state.attempts["A"] == 1

    state = apply_event(spec, state, _event(ExecutionEventKind.TASK_STARTED, "B"))
    state = apply_event(spec, state, _event(ExecutionEventKind.TASK_SUCCEEDED, "B"))
    assert state.tasks["C"] is TaskStatus.READY
    state = apply_event(spec, state, _event(ExecutionEventKind.TASK_STARTED, "C"))
    state = apply_event(spec, state, _event(ExecutionEventKind.TASK_SUCCEEDED, "C"))
    assert state.status is RunStatus.SUCCEEDED


def test_task_failed_block_run_va_retry_tiep_tuc_duoc() -> None:
    spec = _spec()
    state = RunState.replay(
        spec,
        (
            _event(ExecutionEventKind.RUN_STARTED),
            _event(ExecutionEventKind.TASK_STARTED, "A"),
            _event(ExecutionEventKind.TASK_FAILED, "A", reason="test đỏ"),
        ),
    )
    assert state.status is RunStatus.BLOCKED
    assert state.tasks["A"] is TaskStatus.FAILED
    assert state.blocked_reason == "test đỏ"

    state = apply_event(spec, state, _event(ExecutionEventKind.TASK_RETRIED, "A"))
    assert state.status is RunStatus.RUNNING
    assert state.tasks["A"] is TaskStatus.READY
    assert state.blocked_reason == ""
    state = apply_event(spec, state, _event(ExecutionEventKind.TASK_STARTED, "A"))
    assert state.attempts["A"] == 2


def test_retry_chi_khi_run_blocked() -> None:
    spec = _spec()
    state = apply_event(spec, RunState.initial(spec), _event(ExecutionEventKind.RUN_STARTED))
    with pytest.raises(ExecutionTransitionError, match="run phải BLOCKED"):
        apply_event(spec, state, _event(ExecutionEventKind.TASK_RETRIED, "A"))


def test_retry_chi_task_da_failed() -> None:
    spec = _spec()
    state = RunState.replay(
        spec,
        (
            _event(ExecutionEventKind.RUN_STARTED),
            _event(ExecutionEventKind.TASK_STARTED, "A"),
            _event(ExecutionEventKind.TASK_FAILED, "A"),
        ),
    )
    with pytest.raises(ExecutionTransitionError, match="task phải FAILED"):
        apply_event(spec, state, _event(ExecutionEventKind.TASK_RETRIED, "B"))


def test_retry_mot_task_khong_mo_run_khi_con_task_failed_khac() -> None:
    spec = RunSpec(
        run_id="RUN-1",
        objective="x",
        tasks=(TaskSpec("A", "a"), TaskSpec("B", "b")),
    )
    state = RunState.replay(
        spec,
        (
            _event(ExecutionEventKind.RUN_STARTED),
            _event(ExecutionEventKind.TASK_STARTED, "A"),
            _event(ExecutionEventKind.TASK_STARTED, "B"),
            _event(ExecutionEventKind.TASK_FAILED, "A", reason="a hỏng"),
            _event(ExecutionEventKind.TASK_FAILED, "B", reason="b hỏng"),
        ),
    )
    assert state.status is RunStatus.BLOCKED
    assert state.blocked_reason == "A: a hỏng; B: b hỏng"

    state = apply_event(spec, state, _event(ExecutionEventKind.TASK_RETRIED, "A"))
    assert state.status is RunStatus.BLOCKED
    assert state.blocked_reason == "b hỏng"

    state = apply_event(spec, state, _event(ExecutionEventKind.TASK_RETRIED, "B"))
    assert state.status is RunStatus.RUNNING
    assert state.blocked_reason == ""


def test_cancel_giu_task_da_xong_va_huy_task_con_lai() -> None:
    spec = RunSpec(
        run_id="RUN-1",
        objective="x",
        tasks=(TaskSpec("A", "a"), TaskSpec("B", "b")),
    )
    state = RunState.replay(
        spec,
        (
            _event(ExecutionEventKind.RUN_STARTED),
            _event(ExecutionEventKind.TASK_STARTED, "A"),
            _event(ExecutionEventKind.TASK_SUCCEEDED, "A"),
            _event(ExecutionEventKind.RUN_CANCELLED),
        ),
    )
    assert state.status is RunStatus.CANCELLED
    assert state.tasks == {"A": TaskStatus.SUCCEEDED, "B": TaskStatus.CANCELLED}


def test_cancel_khong_duoc_ap_dung_cho_run_terminal() -> None:
    spec = RunSpec(run_id="RUN-1", objective="x", tasks=(TaskSpec("A", "a"),))
    state = RunState.replay(
        spec,
        (
            _event(ExecutionEventKind.RUN_STARTED),
            _event(ExecutionEventKind.TASK_STARTED, "A"),
            _event(ExecutionEventKind.TASK_SUCCEEDED, "A"),
        ),
    )
    with pytest.raises(ExecutionTransitionError, match="run terminal"):
        apply_event(spec, state, _event(ExecutionEventKind.RUN_CANCELLED))


def test_evidence_receipt_hash_output_va_passed_theo_exit_code() -> None:
    ok = EvidenceReceipt.from_output(
        command="pytest -q",
        cwd="/repo",
        exit_code=0,
        head_sha="abc",
        output=b"2 passed\n",
        duration_ms=12.5,
    )
    bad = EvidenceReceipt.from_output(
        command="pytest -q",
        cwd="/repo",
        exit_code=1,
        head_sha="abc",
        output=b"1 failed\n",
        duration_ms=4.0,
    )
    assert ok.passed and not bad.passed
    assert ok.output_sha256 == hashlib.sha256(b"2 passed\n").hexdigest()


def test_execution_event_json_roundtrip_giu_nguyen_identity() -> None:
    event = ExecutionEvent(
        run_id="RUN-1",
        kind=ExecutionEventKind.TASK_FAILED,
        task_id="A",
        payload={"reason": "x"},
        event_id="evt-1",
        ts=datetime(2026, 9, 24, 15, 0, tzinfo=UTC),
    )
    assert ExecutionEvent.from_json(event.to_json()) == event
    run_event = ExecutionEvent(run_id="RUN-1", kind=ExecutionEventKind.RUN_STARTED)
    assert ExecutionEvent.from_json(run_event.to_json()).task_id is None


def test_journal_dong_mo_lai_van_replay_duoc_run(tmp_path) -> None:
    spec = _spec()
    path = tmp_path / "journal.sqlite"
    with ExecutionJournal(path) as journal:
        journal._append_unchecked(_event(ExecutionEventKind.RUN_STARTED))
        journal._append_unchecked(_event(ExecutionEventKind.TASK_STARTED, "A"))
        journal._append_unchecked(_event(ExecutionEventKind.RUN_STARTED, run_id="RUN-OTHER"))
        assert len(journal.events("RUN-1")) == 2

    with ExecutionJournal(path) as journal:
        state = journal.replay(spec)
        assert state.status is RunStatus.RUNNING
        assert state.tasks["A"] is TaskStatus.RUNNING
        assert state.attempts["A"] == 1


def test_journal_tu_choi_event_id_trung(tmp_path) -> None:
    event = ExecutionEvent(run_id="RUN-1", kind=ExecutionEventKind.RUN_STARTED, event_id="same")
    with ExecutionJournal(tmp_path / "journal.sqlite") as journal:
        journal._append_unchecked(event)
        with pytest.raises(ExecutionJournalError, match="event_id trùng"):
            journal._append_unchecked(event)


def test_journal_mot_connection_ghi_duoc_tu_nhieu_worker_thread(tmp_path) -> None:
    with ExecutionJournal(tmp_path / "journal.sqlite") as journal:
        events = [
            ExecutionEvent(
                run_id="RUN-1",
                kind=ExecutionEventKind.TASK_STARTED,
                task_id=f"T{i}",
            )
            for i in range(12)
        ]
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(journal._append_unchecked, events))
        assert {event.event_id for event in journal.events("RUN-1")} == {
            event.event_id for event in events
        }


def test_journal_luu_runspec_de_resume_sau_khi_mat_context(tmp_path) -> None:
    path = tmp_path / "journal.sqlite"
    spec = _spec()
    with ExecutionJournal(path) as journal:
        journal.register(spec)
        journal.register(spec)
        journal._append_unchecked(_event(ExecutionEventKind.RUN_STARTED))
        journal._append_unchecked(_event(ExecutionEventKind.TASK_STARTED, "A"))
        conflict = RunSpec(
            run_id="RUN-1",
            objective="khác",
            tasks=(TaskSpec("X", "x"),),
        )
        with pytest.raises(ExecutionJournalError, match="RunSpec khác"):
            journal.register(conflict)

    with ExecutionJournal(path) as journal:
        assert journal.load_spec("MISSING") is None
        assert journal.load_spec("RUN-1") == spec
        state = journal.resume("RUN-1")
        assert state.status is RunStatus.RUNNING
        assert state.tasks["A"] is TaskStatus.RUNNING
        with pytest.raises(ExecutionJournalError, match="chưa đăng ký"):
            journal.resume("MISSING")


def test_append_phat_deprecation_warning_nhung_van_ghi(tmp_path) -> None:
    """`append` là alias legacy: vẫn ghi được, nhưng phải la làng để không ai còn coi nó là đường ghi chính."""
    event = _event(ExecutionEventKind.RUN_STARTED)
    with ExecutionJournal(tmp_path / "journal.sqlite") as journal:
        with pytest.warns(DeprecationWarning, match="transition"):
            journal.append(event)
        assert journal.events("RUN-1") == (event,)


def test_append_unchecked_khong_phat_warning(tmp_path) -> None:
    """Đường ghi nội bộ (`_append_unchecked`) không được tự cảnh báo về chính nó."""
    import warnings

    event = _event(ExecutionEventKind.RUN_STARTED)
    with ExecutionJournal(tmp_path / "journal.sqlite") as journal:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            journal._append_unchecked(event)
        assert journal.events("RUN-1") == (event,)
