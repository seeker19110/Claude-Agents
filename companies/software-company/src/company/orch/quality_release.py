"""Nguồn gap R6 cho sàn chất lượng (N2 của `docs/thi-hanh/pe2.md`, ADR gốc 0021 §f + quyết định 3). Chỉ đọc journal.

Tách khỏi `quality_flow` vì module đó đã chạm trần 400 dòng của `orch/` (`test_orch_khuon_loi.py`).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from xagents_core.execution import ExecutionJournal

from ..quality_floor import ReleaseQuality
from .quality_flow import journal_path, runs_for_release

if TYPE_CHECKING:
    from ..orchestrator import Orchestrator


def release_quality(o: Orchestrator, rid: str) -> ReleaseQuality:
    """`runs_for_release` + ticket của dự án có profile nằm ngoài mọi run (quyết định 3). Release không chạm dự án có
    profile ⇒ `((), ())` mà không mở journal; journal chưa có ⇒ mọi ticket đó nằm ngoài run (hỏng thì đóng)."""
    tickets = o.lead.release_tickets.get(rid, [])
    pinned = [t for t in tickets if t in o.lead.tickets and o.lead.tickets[t].project_id in o.quality_profiles]
    if not pinned: return (), ()
    runs = runs_for_release(o, rid)
    covered: set[str] = set()
    if runs:
        with ExecutionJournal(journal_path(o)) as journal:
            for run_id, _status, _sha in runs:
                spec = journal.load_spec(run_id)
                covered |= {t.task_id for t in spec.tasks} if spec is not None else set()
    return runs, tuple(t for t in pinned if t not in covered)
