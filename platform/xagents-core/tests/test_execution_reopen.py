"""ADR gốc 0022 phương án (a): `task.reopened` mở lại task đã SUCCEEDED mà RunSpec khai `reopenable` (chỉ task lá).

Mỗi điều kiện có một ca từ chối riêng; ca thuận kiểm cả run SUCCEEDED → RUNNING và attempt kế tiếp. Byte của
RunSpec không `reopenable` được ghim bằng chuỗi chụp từ code trước N5 (`main@1261080`)."""
from __future__ import annotations

import pytest

from xagents_core.execution import (
    Complexity,
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

K = ExecutionEventKind
SPEC = RunSpec(run_id="R", objective="x",
               tasks=(TaskSpec("A", "a"), TaskSpec("Q", "q", dependencies=("A",), reopenable=True)))
LEGACY = RunSpec(run_id="R", objective="x", tasks=(TaskSpec("A", "a"), TaskSpec("Q", "q", dependencies=("A",))))
# RunSpec.to_json chụp bằng code trước N5 (main@1261080): spec không reopenable phải giữ ĐÚNG byte này.
PRE_N5_JSON = (
    '{"objective": "x", "run_id": "R", "tasks": [{"acceptance": ["ok"], "allowed_tools": [], "complexity": "c2", '
    '"context_refs": [], "dependencies": [], "objective": "a", "task_id": "A", "write_scope": []}, '
    '{"acceptance": [], "allowed_tools": [], "complexity": "c3", "context_refs": [], "dependencies": ["A"], '
    '"objective": "q", "task_id": "Q", "write_scope": []}]}'
)


def _ev(kind: ExecutionEventKind, task_id: str | None = None, **payload: object) -> ExecutionEvent:
    return ExecutionEvent(run_id="R", kind=kind, task_id=task_id, payload=dict(payload))


def _done() -> RunState:
    return RunState.replay(SPEC, (
        _ev(K.RUN_STARTED), _ev(K.TASK_STARTED, "A"), _ev(K.TASK_SUCCEEDED, "A"),
        _ev(K.TASK_STARTED, "Q"), _ev(K.TASK_SUCCEEDED, "Q"),
    ))


def test_mo_lai_sink_da_xong_dua_task_ve_ready_va_run_ve_running() -> None:
    state = _done()
    assert state.status is RunStatus.SUCCEEDED
    state = apply_event(SPEC, state, _ev(K.TASK_REOPENED, "Q", reason="candidate đổi X → Y"))
    assert state.status is RunStatus.RUNNING
    assert state.tasks == {"A": TaskStatus.SUCCEEDED, "Q": TaskStatus.READY}
    assert state.attempts["Q"] == 1, "mở lại không tính là một attempt"
    state = apply_event(SPEC, state, _ev(K.TASK_STARTED, "Q"))
    state = apply_event(SPEC, state, _ev(K.TASK_SUCCEEDED, "Q"))
    assert state.status is RunStatus.SUCCEEDED and state.attempts["Q"] == 2


def test_mo_lai_tu_choi_task_khong_khai_reopenable() -> None:
    with pytest.raises(ExecutionTransitionError, match="reopenable"):
        apply_event(SPEC, _done(), _ev(K.TASK_REOPENED, "A", reason="x"))
    legacy = RunState.replay(LEGACY, (_ev(K.RUN_STARTED), _ev(K.TASK_STARTED, "A"), _ev(K.TASK_SUCCEEDED, "A"),
                                      _ev(K.TASK_STARTED, "Q"), _ev(K.TASK_SUCCEEDED, "Q")))
    with pytest.raises(ExecutionTransitionError, match="reopenable"):
        apply_event(LEGACY, legacy, _ev(K.TASK_REOPENED, "Q", reason="lá nhưng không khai"))


def test_reopenable_chi_cho_task_la() -> None:
    with pytest.raises(ValueError, match="reopenable"):
        RunSpec(run_id="R", objective="x",
                tasks=(TaskSpec("A", "a", reopenable=True), TaskSpec("B", "b", dependencies=("A",))))


def test_retried_tren_succeeded_van_bi_tu_choi() -> None:
    with pytest.raises(ExecutionTransitionError, match="run phải BLOCKED"):
        apply_event(SPEC, _done(), _ev(K.TASK_RETRIED, "Q"))


def test_byte_runspec_khong_reopenable_giu_nguyen_va_round_trip() -> None:
    old = RunSpec(run_id="R", objective="x", tasks=(
        TaskSpec("A", "a", acceptance=("ok",)), TaskSpec("Q", "q", dependencies=("A",), complexity=Complexity.C3)))
    assert old.to_json() == PRE_N5_JSON
    assert RunSpec.from_json(PRE_N5_JSON) == old
    new = RunSpec.from_json(SPEC.to_json())
    assert new == SPEC and new.tasks[1].reopenable and '"reopenable": true' in SPEC.to_json()
    assert SPEC.to_json().count("reopenable") == 1, "chỉ task mang cờ mới có khoá"


def test_mo_lai_tu_choi_task_chua_succeeded() -> None:
    state = RunState.replay(SPEC, (_ev(K.RUN_STARTED), _ev(K.TASK_STARTED, "A"), _ev(K.TASK_SUCCEEDED, "A"),
                                   _ev(K.TASK_STARTED, "Q")))
    with pytest.raises(ExecutionTransitionError, match="task phải SUCCEEDED"):
        apply_event(SPEC, state, _ev(K.TASK_REOPENED, "Q", reason="x"))


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_mo_lai_bat_buoc_co_ly_do(reason: str | None) -> None:
    payload = {} if reason is None else {"reason": reason}
    with pytest.raises(ExecutionTransitionError, match="reason"):
        apply_event(SPEC, _done(), _ev(K.TASK_REOPENED, "Q", **payload))


def test_mo_lai_tu_choi_run_cancelled_va_run_blocked() -> None:
    spec = RunSpec(run_id="R", objective="x", tasks=(TaskSpec("A", "a", reopenable=True), TaskSpec("B", "b")))
    blocked = RunState.replay(spec, (_ev(K.RUN_STARTED), _ev(K.TASK_STARTED, "A"), _ev(K.TASK_SUCCEEDED, "A"),
                                     _ev(K.TASK_STARTED, "B"), _ev(K.TASK_FAILED, "B", reason="b hỏng")))
    with pytest.raises(ExecutionTransitionError, match="run phải RUNNING hoặc SUCCEEDED"):
        apply_event(spec, blocked, _ev(K.TASK_REOPENED, "A", reason="x"))
    with pytest.raises(ExecutionTransitionError, match="task không tồn tại"):
        apply_event(SPEC, _done(), _ev(K.TASK_REOPENED, "Z", reason="x"))
    cancelled = RunState.replay(spec, (_ev(K.RUN_STARTED), _ev(K.TASK_STARTED, "A"), _ev(K.TASK_SUCCEEDED, "A"),
                                       _ev(K.RUN_CANCELLED)))
    with pytest.raises(ExecutionTransitionError, match="run phải RUNNING hoặc SUCCEEDED"):
        apply_event(spec, cancelled, _ev(K.TASK_REOPENED, "A", reason="x"))


def test_run_da_mo_lai_thi_cancel_duoc_va_journal_replay_giu_lich_su(tmp_path) -> None:
    with ExecutionJournal(tmp_path / "j.sqlite") as journal:
        journal.register(SPEC)
        history = [_ev(K.RUN_STARTED), _ev(K.TASK_STARTED, "A"), _ev(K.TASK_SUCCEEDED, "A"),
                   _ev(K.TASK_STARTED, "Q"), _ev(K.TASK_SUCCEEDED, "Q"), _ev(K.TASK_REOPENED, "Q", reason="sha mới")]
        for n, event in enumerate(history):
            journal.transition(event, expected_count=n)
        assert journal.resume("R").tasks["Q"] is TaskStatus.READY
        state = journal.transition(_ev(K.RUN_CANCELLED), expected_count=len(history))
        assert state.status is RunStatus.CANCELLED
        assert [e.kind for e in journal.events("R")][-2:] == [K.TASK_REOPENED, K.RUN_CANCELLED]


def test_mo_lai_gui_lai_cung_id_thi_ack_khac_payload_thi_collision(tmp_path) -> None:
    with ExecutionJournal(tmp_path / "j.sqlite") as journal:
        journal.register(SPEC)
        history = [_ev(K.RUN_STARTED), _ev(K.TASK_STARTED, "A"), _ev(K.TASK_SUCCEEDED, "A"),
                   _ev(K.TASK_STARTED, "Q"), _ev(K.TASK_SUCCEEDED, "Q")]
        for n, event in enumerate(history):
            journal.transition(event, expected_count=n)
        reopen = ExecutionEvent(run_id="R", kind=K.TASK_REOPENED, task_id="Q", payload={"reason": "sha mới"},
                                event_id="R:quality:reopen:1")
        journal.transition(reopen, expected_count=5)
        assert journal.transition(reopen, expected_count=5).tasks["Q"] is TaskStatus.READY, "gửi lại ⇒ ACK"
        with pytest.raises(ExecutionJournalError, match="collision"):
            journal.transition(ExecutionEvent(run_id="R", kind=K.TASK_REOPENED, task_id="Q",
                                              payload={"reason": "khác"}, event_id="R:quality:reopen:1"),
                               expected_count=6)
