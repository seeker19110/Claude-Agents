"""Nhãn `source` của `review-results` do CODE điền từ ROUTE, không phải model khai.

Đo được 2026-09-13 bằng model thật: khi `security` và `qa` tạm bị gộp làm một agent hai pha, 4/18 ca pha
`security` khai `source: reviewer`. Việc gộp đã được lùi, nhưng phép đo ấy chỉ ra một chỗ hở có sẵn từ trước:
nhãn này luôn do MODEL khai, trong khi nó là IDENTITY CỦA LƯỢT mà ROUTE biết chắc.

Khai sai nhãn không phải "sai một chữ": `delivery.py` đếm review THEO NHÃN (`required_reviews`), nên một lượt
`security` khai nhầm `reviewer` là ticket rủi ro không bao giờ đủ review — nó nằm im, `status` không báo gì.

Vì thế nhãn thuộc nhóm "code điền" của `CLAUDE.md` ranh giới 1, cùng hàng với `ticket_id` của review trên
release (`review.subject_overridden`) và `local_checks.verified_by=workspace`.
"""
from __future__ import annotations

import pytest

from company.bus import InMemoryBus
from company.llm import FakeClient
from company.orch.routes import ROUTES, THREAT_ROUTE, source_for
from company.orchestrator import Orchestrator
from company.roles import ROLE, SOURCE


def _route(topic_in: str, agent: str):
    return next(r for r in ROUTES if r.topic_in == topic_in and r.topic_out == "review-results" and r.agent == agent)


@pytest.mark.parametrize(("topic_in", "agent", "mong_doi"), [
    ("pull-requests", ROLE.SECURITY, SOURCE.SECURITY),      # deep-review ticket rủi ro
    ("release-candidates", ROLE.SECURITY, SOURCE.SECURITY),  # release-check
    ("pull-requests", ROLE.QA, SOURCE.REVIEWER),             # chấm code một ticket
    ("release-events", ROLE.QA, SOURCE.QA),                  # hồi quy cả release trên staging
])
def test_source_suy_duoc_tu_route(topic_in: str, agent: str, mong_doi: str) -> None:
    assert source_for(_route(topic_in, agent)) == mong_doi


def test_threat_route_la_security() -> None:
    assert source_for(THREAT_ROUTE) == SOURCE.SECURITY


def test_route_khong_phai_review_thi_khong_co_source() -> None:
    assert source_for(next(r for r in ROUTES if r.topic_out != "review-results")) is None


def test_moi_route_review_results_deu_suy_duoc_source() -> None:
    """Thêm route `review-results` mà `source_for` không suy được ⇒ nhãn lại rơi vào tay model."""
    thieu = [(r.topic_in, r.agent) for r in (*ROUTES, THREAT_ROUTE)
             if r.topic_out == "review-results" and source_for(r) is None]
    assert thieu == [], f"route review-results không suy được `source`: {thieu}"


def test_code_ghi_de_nhan_model_khai_sai() -> None:
    """`security` khai nhãn `reviewer` → event publish ra vẫn mang `security`, và để lại vết trong audit-log."""
    from test_orchestrator import _agent_of, _drive_to_plan, handler

    def khai_sai(system, user):
        out = handler(system, user)
        if _agent_of(system) == ROLE.SECURITY and isinstance(out, dict) and out.get("source") == SOURCE.SECURITY:
            return {**out, "source": SOURCE.REVIEWER}
        return out

    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=khai_sai))
    _drive_to_plan(bus, orch); orch.run()
    nhan = [e.payload["source"] for e in bus.replay(topic="review-results") if e.payload.get("ticket_id") == "T2"]
    assert SOURCE.SECURITY in nhan, f"nhãn phải do ROUTE quyết, nhận: {nhan}"
    audits = [e for e in bus.replay(topic="audit-log") if e.payload.get("action") == "review.source_overridden"]
    assert audits, "ghi đè lời khai của model phải để lại vết"
