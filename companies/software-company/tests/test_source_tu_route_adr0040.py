"""ADR-0040 hệ quả: nhãn `source` của `review-results` do CODE điền từ ROUTE, không phải model khai.

Đo được khi chạy `make eval-record AGENT=qa` bằng model thật ngay sau khi gộp (2026-09-13): 4/18 ca hỏng vì
model ở pha `security` vẫn khai `source: reviewer` — một agent đội hai pha thì cái nhãn phân biệt hai pha là
thứ đầu tiên nó lẫn. Hậu quả không phải "sai một chữ": `delivery.py` đếm review THEO NHÃN, nên ticket rủi ro
không bao giờ đủ `security` và nằm im.

Nhãn ấy là IDENTITY CỦA LƯỢT — ROUTE biết chắc (pha + topic vào), nên nó thuộc nhóm "code điền" cùng hàng với
`ticket_id` của review trên release (`review.subject_overridden`) và `local_checks.verified_by`.
"""
from __future__ import annotations

import pytest

from company.orch.routes import ROUTES, THREAT_ROUTE, source_for
from company.roles import SOURCE


def _route(topic_in: str, phase: str):
    return next(r for r in ROUTES if r.topic_in == topic_in and r.topic_out == "review-results" and r.phase == phase)


@pytest.mark.parametrize(("topic_in", "phase", "mong_doi"), [
    ("pull-requests", "security", SOURCE.SECURITY),   # deep-review ticket rủi ro
    ("pull-requests", "review", SOURCE.REVIEWER),     # chấm code một ticket
    ("release-events", "review", SOURCE.QA),          # hồi quy cả release trên staging
    ("release-candidates", "security", SOURCE.SECURITY),  # release-check
])
def test_source_suy_duoc_tu_route(topic_in: str, phase: str, mong_doi: str) -> None:
    assert source_for(_route(topic_in, phase)) == mong_doi


def test_threat_route_la_security() -> None:
    assert source_for(THREAT_ROUTE) == SOURCE.SECURITY


def test_route_khong_phai_review_thi_khong_co_source() -> None:
    khac = next(r for r in ROUTES if r.topic_out != "review-results")
    assert source_for(khac) is None


def test_moi_route_review_results_deu_suy_duoc_source() -> None:
    """Thêm một route `review-results` mà quên khai pha ⇒ code không điền được ⇒ lại rơi vào tay model."""
    thieu = [(r.topic_in, r.phase) for r in (*ROUTES, THREAT_ROUTE)
             if r.topic_out == "review-results" and source_for(r) is None]
    assert thieu == [], f"route review-results không suy được `source`: {thieu}"


def test_code_ghi_de_nhan_model_khai_sai() -> None:
    """Model ở pha `security` khai `reviewer` → event publish ra vẫn phải mang `security`, kèm audit."""
    from company.bus import InMemoryBus
    from company.llm import FakeClient
    from company.orchestrator import Orchestrator
    from test_orchestrator import _agent_of, _drive_to_plan, _qa_phase, handler

    def khai_sai(system, user):
        out = handler(system, user)
        # pha `security` nhưng khai nhãn của pha `review` — đúng lỗi model thật mắc 4/18 ca.
        if _agent_of(system) == "qa" and _qa_phase(system) == "security" and isinstance(out, dict) and "source" in out:
            return {**out, "source": SOURCE.REVIEWER}
        return out

    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=khai_sai))
    _drive_to_plan(bus, orch); orch.run()
    reviews = [e for e in bus.replay(topic="review-results") if e.payload.get("ticket_id") == "T2"]
    assert any(e.payload["source"] == SOURCE.SECURITY for e in reviews), \
        f"nhãn phải do ROUTE quyết, nhận: {[e.payload['source'] for e in reviews]}"
    audits = [e for e in bus.replay(topic="audit-log") if e.payload.get("action") == "review.source_overridden"]
    assert audits, "ghi đè phải để lại vết trong audit-log"
