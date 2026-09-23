"""Bậc rủi ro gate do CODE xếp (ADR-0011 §4, giai đoạn 3/5 — `docs/thi-hanh/adr113.md`).

Cùng khuôn với `keeper.risk.risk_tier` (bảng `RiskRule` tra cứu được, không phải chuỗi `if`) nhưng KHÔNG dùng
chung bảng: hai công ty có `GateKind`/miền khác nhau (ADR-0011 §1), và ở đây chưa có object `Signal` mang
ngữ cảnh rủi ro (semver, severity...) như keeper — 12 điểm `gate.request` của company (nay đi qua `request_gate`) chỉ có `kind`,
`subject_id`, `checklist`.

`RISK_RULES` khởi tạo RỖNG có chủ đích (2026-09-10): bậc rủi ro phải do CODE xếp bằng luật đã qua review, không
phải luật một phiên tự nghĩ ra để "cho có". Hai hàng đầu tiên vào từ ADR-0043 (`release-quality-floor`,
`acceptance-quality-floor`): cả hai chỉ khớp khi nơi gọi truyền bằng chứng máy + mức nâng của dự án và
`quality_floor.floor_gaps` trả rỗng. Không bằng chứng ⇒ không hàng nào khớp ⇒ `DEFAULT_TIER` ("medium") ⇒ người.
Thêm/bớt hàng là PR riêng, test đỏ trước, đi qua `sc-security`.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from .gates import GateRequest, gate_autoapprove_enabled
from .quality_floor import QualityBar, QualityEvidence, floor_gaps

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
    không thu hẹp Literal theo miền của từng công ty — xem `gates.py`), nên trường ở đây khớp đúng kiểu thật.

    `created_by` và `seq` vào đây vì ba trường đầu không đủ để viết một luật đáng tin:
    - `created_by` — cùng `kind="escalation"` và cùng `checklist` nhưng `supervisor` mở (ticket blocked) là
      chuyện khác hẳn `ops` mở (release hỏng) hay `delivery-lead` mở (review release fail). Không phân biệt
      được người mở thì luật nào cũng vơ cả ba vào một rọ.
    - `seq` — thế hệ gate do `HumanGate.request()` gán (không phải người gọi điền). Đây là thứ DUY NHẤT cho
      phép diễn đạt "chỉ tự động lần đầu, lần hai phải có người"; thiếu cap đó thì một luật auto-approve thành
      vòng lặp tự duyệt chính mình.
    Cả hai đều đã có sẵn ở mọi điểm mở gate — không bịa trường chưa ai đo được."""
    kind: str
    subject_id: str
    checklist: tuple[str, ...]
    created_by: str | None = None
    seq: int = 0
    #: ADR-0043: bằng chứng máy + mức nâng của dự án. Chỉ gate `release`/`acceptance` truyền; `None` ⇒ không luật
    #: sàn chất lượng nào khớp ⇒ người (thiếu bằng chứng → người, thiếu mức nâng → hỏng thì đóng).
    evidence: QualityEvidence | None = None
    bar: QualityBar | None = None


@dataclass(frozen=True)
class RiskRule:
    """Một hàng của bảng: tên tra cứu được, tier nó gán, và phép thử trên `GateRiskContext`."""
    name: str
    tier: RiskTier
    match: Callable[[GateRiskContext], bool]
    #: Loại gate duy nhất hàng này được đóng (`gate_cli.trusted_autoapprove` kiểm lúc replay). `None` = không ràng
    #: buộc — chỉ cho hàng giả trong test; hàng thật của bảng luôn khai.
    kind: str | None = None


def gaps_of(ctx: GateRiskContext) -> list[str] | None:
    """Khoảng trống so với sàn (ADR-0043), hoặc `None` khi ngữ cảnh không mang bằng chứng/mức nâng hay bằng chứng
    không cùng loại với gate — tức là không có gì để chấm, không phải "đạt"."""
    if ctx.evidence is None or ctx.bar is None or ctx.evidence.kind != ctx.kind:
        return None
    return floor_gaps(ctx.evidence, ctx.bar)


def _meets_floor(kind: str) -> Callable[[GateRiskContext], bool]:
    return lambda c: c.kind == kind and gaps_of(c) == []


# ADR-0043: hai hàng đầu tiên, cùng một sàn cứng trong `quality_floor.floor_gaps`. Thêm/bớt hàng là PR + test đỏ
# trước + `sc-security` (docstring module).
RISK_RULES: tuple[RiskRule, ...] = (
    RiskRule(name="release-quality-floor", tier="low", match=_meets_floor("release"), kind="release"),
    RiskRule(name="acceptance-quality-floor", tier="low", match=_meets_floor("acceptance"), kind="acceptance"),
)


def context_of(req: GateRequest, *, evidence: QualityEvidence | None = None,
               bar: QualityBar | None = None) -> GateRiskContext:
    """`GateRequest` → `GateRiskContext`. Một chỗ dựng duy nhất, nên thêm trường về sau chỉ sửa ở đây.

    Đọc SAU khi `HumanGate.request()` chạy thì `seq` mới là thế hệ thật (trước đó nó là 0 mặc định)."""
    return GateRiskContext(kind=req.kind, subject_id=req.subject_id, checklist=tuple(req.checklist),
                           created_by=req.created_by, seq=req.seq, evidence=evidence, bar=bar)


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


def request_gate(gate: PersistentGate, req: GateRequest, *, evidence: QualityEvidence | None = None,
                 bar: QualityBar | None = None) -> GateRequest:
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
    ctx = context_of(req, evidence=evidence, bar=bar)  # sau `gate.request(req)`: `seq` đã là thế hệ thật
    matched = [r for r in RISK_RULES if r.match(ctx)]
    gaps = gaps_of(ctx)
    if gaps:
        # ADR-0043: người ký phải thấy VÌ SAO máy không tự ký — không thì "tự duyệt" chỉ tồn tại trên giấy mà không
        # ai đếm được khoảng trống nào chặn nó.
        gate._log(AUTOAPPROVE_ACTOR, "gate.auto_skipped", {"subject_id": req.subject_id, "kind": req.kind, "gaps": gaps})
    if len(matched) == 1 and matched[0].tier == "low":
        # `actor=AUTOAPPROVE_ACTOR` PHẢI truyền tường minh (sc-security, adr113 2026-09-10): không truyền,
        # `PersistentGate.decide` (core) tự suy `actor` — với subject bắt đầu `UAT-` và `by` không phải người,
        # nó gán `actor=SYSTEM_GATE_ACTOR` ("orchestrator"), khiến envelope khớp NHẦM nhánh `trusted_decision`
        # cũ (actor="orchestrator" + subject UAT-*, không kiểm tiền tố `reason`/cờ) thay vì `trusted_autoapprove`
        # — một gate nghiệm thu tự động qua sẽ bị hiểu lầm thành "khách đã ký nghiệm thu".
        gate.decide(req.subject_id, "approve", by=AUTOAPPROVE_ACTOR, actor=AUTOAPPROVE_ACTOR,
                     reason=f"{AUTOAPPROVE_REASON_PREFIX}{matched[0].name}", enforce=False)
    return req
