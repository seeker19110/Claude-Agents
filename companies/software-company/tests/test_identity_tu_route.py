"""`ticket_id` của đầu ra do ROUTE quyết khi đầu vào thuộc về một ticket (sc-security 2026-09-23, lỗ còn mở ở
ADR-0043): route PR trước đây không ghi đè `ticket_id` model khai, nên QA duyệt PR của T1 ghi được một review
cho `REL-x` hay cho ticket khác — cùng khuôn `review.subject_overridden` (release) và `review.source_overridden`."""
from __future__ import annotations

from company.bus import InMemoryBus
from company.llm import FakeClient
from company.orchestrator import Orchestrator
from company.roles import ROLE

GIA = "REL-GIA"


def test_review_pr_khai_ticket_khac_bi_ghi_de_ve_ticket_cua_route() -> None:
    from test_orchestrator import _agent_of, _drive_to_plan, handler

    def khai_sai(system, user):
        out = handler(system, user)
        if _agent_of(system) in {ROLE.QA, ROLE.SECURITY} and isinstance(out, dict) and "verdict" in out:
            return {**out, "ticket_id": GIA}
        return out

    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=khai_sai))
    _drive_to_plan(bus, orch); orch.run()
    reviews = [e for e in bus.replay(topic="review-results")]
    assert reviews, "kịch bản phải có review thì mới đo được"
    assert all(e.payload["ticket_id"] != GIA and e.key != GIA for e in reviews), \
        [(e.key, e.payload["ticket_id"]) for e in reviews]
    pr_of = {e.event_id: e.key for e in bus.replay(topic="pull-requests")}
    tu_pr = [e for e in reviews if e.causation_id in pr_of]
    assert tu_pr and all(e.payload["ticket_id"] == pr_of[e.causation_id] for e in tu_pr)
    audits = [e for e in bus.replay(topic="audit-log") if e.payload.get("action") == "output.subject_overridden"]
    assert audits, "ghi đè lời khai của model phải để lại vết"
