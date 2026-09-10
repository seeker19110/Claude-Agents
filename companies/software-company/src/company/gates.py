"""Gate của company = cơ chế chung ở `xagents_core.gates` + vốn từ của miền (K3.7).

Cơ chế (sổ `pending`, four-eyes, `due`/`overdue`, allowlist người duyệt) ở core; ở đây chỉ còn `GateKind`,
`Decision` và tên biến môi trường. `COMPANY_GATE_APPROVERS` là thứ MỚI của K3.7: company trước đây không có
allowlist người duyệt (studio đã có từ lâu). Mặc định KHÔNG ĐẶT = danh sách rỗng = hành vi cũ y nguyên
(chỉ four-eyes) — bật lên bằng cách đặt biến, và chỉ khi đó mới có người bị từ chối vì không nằm trong danh sách.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

from xagents_core.gates import GateRequest as CoreGateRequest
from xagents_core.gates import HumanGate as CoreHumanGate
from xagents_core.gates import approvers

# ADR-0037: `plan` KHÔNG còn là gate. Kế hoạch được `_check_plan` (code) chặn rồi dispatch ngay — người ký hai
# gate công đoạn (`spec`, `release`), cộng nghiệm thu của khách và gate bất thường.
GateKind = Literal["spec", "release", "escalation", "acceptance"]
Decision = Literal["approve", "request_changes", "reject", "hold", "rollback", "pending"]

APPROVERS_ENV = "COMPANY_GATE_APPROVERS"  # "human:pm,human:cto" — KHÔNG đặt (mặc định) = ai cũng duyệt được

#: ADR-0011 §4 giai đoạn 3: bật đường "code tự động qua gate rủi ro thấp" (`gate_risk.request_gate`). KHÔNG
#: đặt (mặc định) = TẮT = mọi gate vẫn chờ người y hệt hôm nay, kể cả khi `RISK_RULES` có hàng rồi — bật là
#: một quyết định có chủ ý, ghi ở `docs/HUONG-DAN-VAN-HANH.md`.
AUTOAPPROVE_ENV = "COMPANY_GATE_AUTOAPPROVE"
_AUTOAPPROVE_TRUE = frozenset({"1", "true", "yes"})


def gate_autoapprove_enabled() -> bool:
    """`"1"/"true"/"yes"` (không phân biệt hoa/thường) → bật. Không đặt hoặc bất kỳ giá trị nào khác → tắt."""
    return os.environ.get(AUTOAPPROVE_ENV, "").strip().lower() in _AUTOAPPROVE_TRUE


@dataclass
class GateRequest(CoreGateRequest):
    """Trường y hệt core; lớp riêng để company nói về gate của mình bằng tên của mình."""


def gate_approvers(cfg: Any = None) -> frozenset[str]:
    """Người được duyệt gate: env `COMPANY_GATE_APPROVERS` thắng, sau đó cấu hình `gate.approvers` (nếu có).

    Không đặt biến → rỗng → `HumanGate` chỉ áp four-eyes như trước K3.7."""
    return approvers(APPROVERS_ENV, cfg)


class HumanGate(CoreHumanGate):
    """Không bao giờ tự đi tiếp. Separation of duties: decided_by != created_by."""

    APPROVERS_SOURCE = f"danh sách người duyệt ({APPROVERS_ENV} / gate.approvers)"

    # Thu hẹp kiểu về `GateRequest` của company (core khai lớp cơ sở): nơi gọi vẫn nhận đúng lớp của mình.
    pending: dict[str, GateRequest]  # type: ignore[assignment]
    history: list[GateRequest]  # type: ignore[assignment]
