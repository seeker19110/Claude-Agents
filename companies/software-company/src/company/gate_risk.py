"""Bậc rủi ro gate do CODE xếp (ADR-0011 §4, giai đoạn 3/5 — `docs/thi-hanh/adr113.md`).

Cùng khuôn với `keeper.risk.risk_tier` (bảng `RiskRule` tra cứu được, không phải chuỗi `if`) nhưng KHÔNG dùng
chung bảng: hai công ty có `GateKind`/miền khác nhau (ADR-0011 §1), và ở đây chưa có object `Signal` mang
ngữ cảnh rủi ro (semver, severity...) như keeper — 12 điểm `gate.request` của company (nay đi qua `request_gate`) chỉ có `kind`,
`subject_id`, `checklist`.

`RISK_RULES` khởi tạo RỖNG **có chủ đích**: bậc rủi ro phải do CODE xếp bằng luật đã qua review, không phải
luật một phiên tự nghĩ ra để "cho có". Bảng rỗng ⇒ `gate_risk_tier` luôn trả `DEFAULT_TIER` ("medium") ⇒
không gate nào tự động qua được, đúng hành vi hôm nay dù cờ `COMPANY_GATE_AUTOAPPROVE` có bật hay không (xem
`request_gate`). Thêm hàng đầu tiên là một PR riêng, tự đứng, tự test, đi qua `sc-security`.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from .gates import GateRequest, gate_autoapprove_enabled

if TYPE_CHECKING:
    from .gate_cli import PersistentGate  # chỉ để chú kiểu: `decide(..., actor=)` là chữ ký của PersistentGate
    # (core `gate_cli.PersistentGate`), không có ở `HumanGate` gốc — nhập thật ở đây sẽ vòng (gate_cli → gate_risk).

RiskTier = Literal["low", "medium", "high"]
DEFAULT_TIER: RiskTier = "medium"

#: Tiền tố `reason` bắt buộc cho mọi quyết định `gate.decide` do code tự động — `company/gate_cli.py._trusted`
#: chỉ tin actor `AUTOAPPROVE_ACTOR` khi `reason` mang đúng tiền tố này (đánh dấu rõ nguồn gốc trong audit-log,
#: phân biệt với một actor giả mạo tên "code" nhưng không đi qua `request_gate`).
AUTOAPPROVE_REASON_PREFIX = "auto-risk:"
#: Actor ghi `gate.decide` khi code tự động qua — actor MỚI, KHÔNG tái dùng `SYSTEM_GATE_ACTOR="orchestrator"`
#: (giữ nguyên phạm vi tin cậy cũ của orchestrator, chỉ cho gate nghiệm thu `UAT-*`; xem `docs/thi-hanh/adr113.md` mục D).
AUTOAPPROVE_ACTOR = "code"


@dataclass(frozen=True)
class GateRiskContext:
    """Ngữ cảnh CÓ THẬT ở mọi điểm gọi `gate.request` — không bịa trường chưa ai đo được.

    `kind: str` (không phải `GateKind`): `GateRequest.kind` kế thừa từ `CoreGateRequest` giữ kiểu `str` (core
    không thu hẹp Literal theo miền của từng công ty — xem `gates.py`), nên trường ở đây khớp đúng kiểu thật."""
    kind: str
    subject_id: str
    checklist: tuple[str, ...]


@dataclass(frozen=True)
class RiskRule:
    """Một hàng của bảng: tên tra cứu được, tier nó gán, và phép thử trên `GateRiskContext`."""
    name: str
    tier: RiskTier
    match: Callable[[GateRiskContext], bool]


# RỖNG có chủ đích — xem docstring module.
RISK_RULES: tuple[RiskRule, ...] = ()


def rules_without(*names: str) -> tuple[RiskRule, ...]:
    """Bảng thiếu đúng những hàng được nêu — dụng cụ ca chiều ngược. Tên không có trong bảng thì NỔ, chứ
    không im lặng trả bảng đầy đủ (bảng đang RỖNG nên MỌI tên đều "không có" — đúng, đây là điểm của ca này:
    chưa có hàng thật nào để "tắt")."""
    known = {r.name for r in RISK_RULES}
    missing = sorted(set(names) - known)
    if missing:
        raise KeyError(f"không có hàng {missing} trong RISK_RULES")
    return tuple(r for r in RISK_RULES if r.name not in names)


def gate_risk_tier(ctx: GateRiskContext, *, rules: tuple[RiskRule, ...] = RISK_RULES) -> RiskTier:
    """Tier của hàng khớp ĐẦU TIÊN; không hàng nào khớp → `DEFAULT_TIER` ("medium", KHÔNG PHẢI "low")."""
    for rule in rules:
        if rule.match(ctx):
            return rule.tier
    return DEFAULT_TIER


def request_gate(gate: PersistentGate, req: GateRequest) -> GateRequest:
    """Thay `gate.request(req)` ở mọi điểm gọi của orchestrator/delivery-lead: mở gate như cũ, rồi — chỉ khi cờ
    `COMPANY_GATE_AUTOAPPROVE` đang bật VÀ đúng một hàng của `RISK_RULES` khớp với tier "low" — code tự đóng
    gate bằng `decide(by=AUTOAPPROVE_ACTOR, enforce=False, reason=<tiền tố>+<tên hàng>)`.

    `enforce=False` chỉ tắt kiểm allowlist `approvers` (allowlist đó dành cho NGƯỜI); four-eyes
    (`created_by == by`) vẫn áp dụng bình thường và không đụng gì vì `AUTOAPPROVE_ACTOR` không trùng bất kỳ
    `created_by` nào của 12 điểm gọi hiện có. `gate_cli.py` (CLI thủ công) và `demo.py` KHÔNG đi qua hàm này —
    chỉ orchestrator/delivery-lead tự động mở gate mới cần tự động qua, gate mở tay qua CLI là hành động người
    đã chủ ý làm."""
    gate.request(req)
    if not gate_autoapprove_enabled():
        return req
    ctx = GateRiskContext(kind=req.kind, subject_id=req.subject_id, checklist=tuple(req.checklist))
    matched = [r for r in RISK_RULES if r.match(ctx)]
    if len(matched) == 1 and matched[0].tier == "low":
        # `actor=AUTOAPPROVE_ACTOR` PHẢI truyền tường minh (sc-security, adr113 2026-09-10): không truyền,
        # `PersistentGate.decide` (core) tự suy `actor` — với subject bắt đầu `UAT-` và `by` không phải người,
        # nó gán `actor=SYSTEM_GATE_ACTOR` ("orchestrator"), khiến envelope khớp NHẦM nhánh `trusted_decision`
        # cũ (actor="orchestrator" + subject UAT-*, không kiểm tiền tố `reason`/cờ) thay vì `trusted_autoapprove`
        # — một gate nghiệm thu tự động qua sẽ bị hiểu lầm thành "khách đã ký nghiệm thu".
        gate.decide(req.subject_id, "approve", by=AUTOAPPROVE_ACTOR, actor=AUTOAPPROVE_ACTOR,
                     reason=f"{AUTOAPPROVE_REASON_PREFIX}{matched[0].name}", enforce=False)
    return req
