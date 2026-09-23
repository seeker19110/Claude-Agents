"""`GateRiskContext` mang thêm `created_by` và `seq` — hai trường CÓ THẬT ở mọi điểm mở gate.

Vì sao cần: `RISK_RULES` đang rỗng và hàng đầu tiên chưa viết được, không phải vì thiếu cơ chế mà vì ngữ cảnh
quá nghèo. Ba trường cũ (`kind`, `subject_id`, `checklist`) không trả lời được hai câu mà mọi luật đáng tin đều
phải hỏi:

- **Ai mở gate này?** `escalation` do `supervisor` mở (ticket blocked) khác hẳn `escalation` do `ops` mở
  (release hỏng) hay do `delivery-lead` mở (review release fail) — cùng một `kind`, cùng một `checklist`.
- **Đây là lần thứ mấy?** `seq` là bộ đếm thế hệ do `HumanGate.request()` gán. Không có nó thì không luật nào
  diễn đạt được "chỉ tự động lần đầu, lần hai phải có người" — mà cái cap ấy là điều kiện để một luật
  auto-approve không biến thành vòng lặp tự duyệt.

ADR này KHÔNG thêm hàng luật nào và KHÔNG đổi hành vi: `RISK_RULES` vẫn rỗng, `gate_risk_tier` vẫn luôn trả
`DEFAULT_TIER`, không gate nào tự qua. Chỉ mở đường để hàng đầu tiên viết được bằng dữ liệu đã đo, đúng yêu cầu
"không bịa trường chưa ai đo được" của `gate_risk.py`.
"""
from __future__ import annotations

from company.bus import InMemoryBus
from company.gate_cli import PersistentGate
from company.gate_risk import DEFAULT_TIER, RISK_RULES, GateRiskContext, context_of, gate_risk_tier
from company.gates import GateRequest
from company.roles import ROLE


def test_context_mang_created_by_va_seq() -> None:
    ctx = GateRiskContext(kind="escalation", subject_id="T1", checklist=("root_cause",),
                          created_by=ROLE.SUPERVISOR, seq=2)
    assert ctx.created_by == ROLE.SUPERVISOR and ctx.seq == 2


def test_context_of_lay_dung_tu_gate_request() -> None:
    """`seq` do `HumanGate.request()` gán chứ không phải người gọi điền — nên phải đọc SAU khi request."""
    gate = PersistentGate(InMemoryBus())
    req = GateRequest(kind="escalation", subject_id="T1", created_by=ROLE.SUPERVISOR, checklist=["root_cause"])
    gate.request(req)
    ctx = context_of(req)
    assert ctx.kind == "escalation" and ctx.subject_id == "T1"
    assert ctx.created_by == ROLE.SUPERVISOR
    assert ctx.seq == req.seq >= 1, "seq phải là thế hệ thật do gate gán"
    assert ctx.checklist == ("root_cause",)


def test_seq_tang_qua_moi_the_he_cua_cung_subject() -> None:
    """Cùng một ticket mở gate nhiều lần trong đời — luật 'chỉ lần đầu' dựa vào đúng con số này."""
    gate = PersistentGate(InMemoryBus())
    seqs = []
    for _ in range(3):
        req = GateRequest(kind="escalation", subject_id="T1", created_by=ROLE.SUPERVISOR, checklist=["root_cause"])
        gate.request(req)
        seqs.append(context_of(req).seq)
    assert seqs == sorted(set(seqs)) and len(set(seqs)) == 3, f"seq phải phân biệt được ba thế hệ: {seqs}"


def test_created_by_thieu_thi_la_none_khong_no() -> None:
    """`GateRequest.created_by` khai `str | None`; ngữ cảnh phải chịu được None chứ không đổ vỡ lúc mở gate."""
    req = GateRequest(kind="spec", subject_id="SPEC-P1", checklist=[])
    assert context_of(req).created_by is None


def test_khong_bang_chung_thi_hanh_vi_khong_doi() -> None:
    """Bảng có hàng từ ADR-0043, nhưng mọi hàng đòi bằng chứng: ngữ cảnh không mang bằng chứng vẫn chờ người."""
    assert RISK_RULES
    ctx = context_of(GateRequest(kind="escalation", subject_id="T1", created_by=ROLE.SUPERVISOR, checklist=[]))
    assert gate_risk_tier(ctx) == DEFAULT_TIER != "low"
