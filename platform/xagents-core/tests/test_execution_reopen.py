"""ADR gốc 0022: `task.reopened` mở lại một task SINK đã SUCCEEDED (candidate đổi sau nghiệm thu).

Mỗi điều kiện của ADR §a có một ca từ chối riêng; ca thuận kiểm cả run SUCCEEDED → RUNNING và attempt kế tiếp."""
from __future__ import annotations

import pytest

from xagents_core.execution import (
    ExecutionEvent,
    ExecutionEventKind,
    ExecutionJournal,
    ExecutionTransitionError,
    RunSpec,
    RunState,
    RunStatus,
    TaskSpec,
    TaskStatus,
    apply_event,
)

K = ExecutionEventKind
SPEC = RunSpec(run_id="R", objective="x", tasks=(TaskSpec("A", "a"), TaskSpec("Q", "q", dependencies=("A",))))


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


def test_mo_lai_tu_choi_task_co_task_ha_nguon() -> None:
    with pytest.raises(ExecutionTransitionError, match="sink"):
        apply_event(SPEC, _done(), _ev(K.TASK_REOPENED, "A", reason="x"))


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
    spec = RunSpec(run_id="R", objective="x", tasks=(TaskSpec("A", "a"), TaskSpec("B", "b")))
    blocked = RunState.replay(spec, (_ev(K.RUN_STARTED), _ev(K.TASK_STARTED, "A"), _ev(K.TASK_SUCCEEDED, "A"),
                                     _ev(K.TASK_STARTED, "B"), _ev(K.TASK_FAILED, "B", reason="b hỏng")))
    with pytest.raises(ExecutionTransitionError, match="run phải RUNNING hoặc SUCCEEDED"):
        apply_event(spec, blocked, _ev(K.TASK_REOPENED, "A", reason="x"))
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
