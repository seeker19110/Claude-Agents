"""Nguồn gap R6 cho sàn chất lượng (N2 của `docs/thi-hanh/pe2.md`, ADR gốc 0021 §f + quyết định 3). Chỉ đọc journal.

Tách khỏi `quality_flow` vì module đó đã chạm trần 400 dòng của `orch/` (`test_orch_khuon_loi.py`).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from xagents_core.execution import ExecutionJournal, ExecutionJournalError, RunState

from ..quality_execution import QUALITY_TASK_ID, bindings_from_events
from ..quality_floor import ReleaseQuality
from .quality_flow import journal_path

if TYPE_CHECKING:
    from ..orchestrator import Orchestrator


Row = tuple[str, str | None, str | None, str, frozenset[str]]


def _snapshot(o: Orchestrator, rid: str) -> list[Row]:
    """(run_id, trạng thái `quality:accept`, candidate_sha, blockers, task của run) cho mỗi run chạm RC.

    Mỗi run đọc journal ĐÚNG MỘT lần (ADR gốc 0022, sc-security N5 #1): sau một lần mở lại, đọc trạng thái và
    candidate ở hai lần khác nhau có thể ghép `succeeded` cũ với sha mới, và R6 sẽ cho qua sha chưa ai chấm."""
    tickets = set(o.lead.release_tickets.get(rid, []))
    if not tickets or not o.quality_profiles or not journal_path(o).is_file(): return []
    out: list[Row] = []
    with ExecutionJournal(journal_path(o)) as journal:
        for run_id in sorted({pin["run_id"] for pin in o.quality_profiles.values()}):
            spec = journal.load_spec(run_id)
            tasks = frozenset(t.task_id for t in spec.tasks) if spec is not None else frozenset[str]()
            if spec is None or not tickets & tasks: continue
            events = journal.events(run_id)
            state = RunState.replay(spec, events)
            try:
                cand: str | None = bindings_from_events(events).candidate_sha
            except ExecutionJournalError:
                cand = None
            blockers = state.failures.get(QUALITY_TASK_ID, "")[:300]
            out.append((run_id, state.tasks[QUALITY_TASK_ID].value, cand, blockers, tasks))
    return out


def runs_for_release(o: Orchestrator, rid: str) -> tuple[tuple[str, str | None, str | None], ...]:
    """Cho N2 (R6): (run_id, trạng thái `quality:accept`, candidate_sha) của run có ticket nằm trong RC — chỉ đọc."""
    return tuple(row[:3] for row in _snapshot(o, rid))


def release_quality(o: Orchestrator, rid: str) -> ReleaseQuality:
    """`runs_for_release` + ticket của dự án có profile nằm ngoài mọi run (quyết định 3). Release không chạm dự án có
    profile ⇒ `((), ())` mà không mở journal; journal chưa có ⇒ mọi ticket đó nằm ngoài run (hỏng thì đóng).

    N2.b: mỗi hàng mang `blockers` (lý do `quality:accept` hỏng, `RunState.failures`, cắt ≤300 ký tự), lấy từ
    cùng snapshot với trạng thái và candidate."""
    tickets = o.lead.release_tickets.get(rid, [])
    pinned = [t for t in tickets if t in o.lead.tickets and o.lead.tickets[t].project_id in o.quality_profiles]
    if not pinned: return (), ()
    rows = _snapshot(o, rid)
    covered = frozenset[str]().union(*(row[4] for row in rows))
    return tuple(row[:4] for row in rows), tuple(t for t in pinned if t not in covered)
