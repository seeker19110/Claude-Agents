"""Nhãn `source` của `review-results` do CODE quyết, không do model khai.

Nhãn này là IDENTITY CỦA LƯỢT: ROUTE biết chắc ai đang chấm và chấm cái gì, nên nó thuộc nhóm "code điền" của
`CLAUDE.md` ranh giới 1 — cùng hàng với `ticket_id` của review trên release (`review.subject_overridden`) và
`local_checks.verified_by=workspace`.

Vì sao thành module riêng thay vì nằm trong `routes.py`/`orchestrator.py`: `test_orch_khuon_loi.py` giữ hai
trần (thân hàm `orchestrator.py` ≤ 260 dòng, mỗi module `orch/` ≤ 400) — logic mới thuộc về một module của
`orch/`, không phải nhét thêm vào hai file đã kín chỗ.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..events import Envelope
from ..roles import ROLE, SOURCE
from .routes import Route

if TYPE_CHECKING:
    from ..orchestrator import Orchestrator


def source_for(r: Route) -> str | None:
    """Nhãn `source` mà một route `review-results` PHẢI phát — suy từ ROUTE, không hỏi model.

    `security` chấm dưới một nhãn duy nhất. `qa` mang hai nhãn vì nó chấm hai thứ khác nhau và `delivery.py`
    đếm chúng vào hai chỗ khác nhau: một TICKET (`pull-requests` → `reviewer`, review nền của mọi PR) và cả
    một RELEASE (`release-events` → `qa`, hồi quy trên staging). Route không phải `review-results` trả `None`.
    """
    if r.topic_out != "review-results":
        return None
    if r.agent == ROLE.SECURITY:
        return SOURCE.SECURITY
    if r.agent == ROLE.QA:
        return SOURCE.QA if r.topic_in == "release-events" else SOURCE.REVIEWER
    return None


def enforce_source(o: Orchestrator, r: Route, p: dict[str, Any], env: Envelope, agent: str) -> dict[str, Any]:
    """Ghi đè nhãn `source` của một `review-results` bằng nhãn của ROUTE, và để lại vết nếu model khai khác.

    Nhãn là IDENTITY CỦA LƯỢT — cùng nhóm "code điền" với `ticket_id` của review trên release
    (`review.subject_overridden`). Đo 2026-09-13 bằng model thật: khi `security`/`qa` tạm bị gộp làm một agent
    hai pha, 4/18 ca pha `security` khai `reviewer`. Việc gộp đã lùi, nhưng chỗ hở có sẵn từ trước —
    `delivery.py` đếm review THEO NHÃN, nên khai nhầm là ticket rủi ro thiếu review vĩnh viễn, nằm im mà
    `status` không báo gì bất thường.
    """
    src = source_for(r)
    if not src or p.get("source") == src:
        return p
    o._audit("review.source_overridden", {"claimed": p.get("source"), "source": src},
             actor=agent, ticket_id=p.get("ticket_id"), project_id=o.project_for(env))
    return {**p, "source": src}
