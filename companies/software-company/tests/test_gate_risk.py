"""Bậc rủi ro gate do CODE xếp (ADR-0011 §4, giai đoạn 3/5 — docs/thi-hanh/adr113.md gói `adr113-a`).

`RISK_RULES` khởi tạo RỖNG có chủ đích: chưa có luật cứng nào qua review để tự động qua gate. Test ở đây chứng
minh CƠ CHẾ tra bảng đúng (qua rule giả truyền bằng tham số `rules=`), không chứng minh có luật thật nào."""
import json

import pytest

from company.bus import InMemoryBus
from company.events import AuditLog, Envelope
from company.gate_cli import PersistentGate, trusted_autoapprove
from company.gate_risk import (
    AUTOAPPROVE_ACTOR,
    AUTOAPPROVE_REASON_PREFIX,
    GateRiskContext,
    RiskRule,
    gate_risk_tier,
    request_gate,
    rules_without,
)
from company.gates import AUTOAPPROVE_ENV, GateRequest, gate_autoapprove_enabled


def _ctx(kind="release", subject_id="REL-1", checklist=("tests",)):
    return GateRiskContext(kind=kind, subject_id=subject_id, checklist=checklist)


def test_bang_rong_moi_gate_deu_medium():
    for kind in ("spec", "release", "escalation", "acceptance"):
        assert gate_risk_tier(_ctx(kind=kind)) == "medium"


def test_rule_gia_khop_tra_dung_tier():
    rule = RiskRule(name="doc-only", tier="low", match=lambda c: c.kind == "release")
    assert gate_risk_tier(_ctx(kind="release"), rules=(rule,)) == "low"
    assert gate_risk_tier(_ctx(kind="spec"), rules=(rule,)) == "medium"


def test_rules_without_ten_la_no():
    with pytest.raises(KeyError):
        rules_without("khong-ton-tai")


def test_rules_without_khong_ten_nao_tra_bang_hien_co():
    assert rules_without() == ()  # bảng đang rỗng: không tên nào cần bỏ, kết quả là chính bảng hiện có


def test_rules_without_bang_rong_ném_vi_khong_co_gi_de_bo():
    with pytest.raises(KeyError):
        rules_without("bat-ky-ten-nao")


# ---------- cờ COMPANY_GATE_AUTOAPPROVE (mặc định TẮT) ----------

def test_co_mac_dinh_tat(monkeypatch):
    monkeypatch.delenv(AUTOAPPROVE_ENV, raising=False)
    assert gate_autoapprove_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "Yes"])
def test_co_bat(monkeypatch, val):
    monkeypatch.setenv(AUTOAPPROVE_ENV, val)
    assert gate_autoapprove_enabled() is True


@pytest.mark.parametrize("val", ["0", "", "no", "rac"])
def test_co_gia_tri_la_van_tat(monkeypatch, val):
    monkeypatch.setenv(AUTOAPPROVE_ENV, val)
    assert gate_autoapprove_enabled() is False


# ---------- request_gate: nối bậc rủi ro vào runtime ----------

def test_request_gate_co_tat_khong_tu_dong_qua(monkeypatch):
    """Cờ tắt (mặc định) → dù có rule giả khớp `low`, gate vẫn `pending` — chỉ test cơ chế nối, không sửa RISK_RULES thật."""
    monkeypatch.delenv(AUTOAPPROVE_ENV, raising=False)
    bus = InMemoryBus(); gate = PersistentGate(bus)
    req = GateRequest(kind="release", subject_id="REL-1", created_by="delivery-lead", checklist=["tests"])
    request_gate(gate, req)
    assert "REL-1" in gate.pending


def test_request_gate_bang_that_rong_khong_tu_dong_qua_gi(monkeypatch):
    monkeypatch.setenv(AUTOAPPROVE_ENV, "1")
    bus = InMemoryBus(); gate = PersistentGate(bus)
    req = GateRequest(kind="release", subject_id="REL-2", created_by="delivery-lead", checklist=["tests"])
    request_gate(gate, req)
    assert "REL-2" in gate.pending  # RISK_RULES đang rỗng thật trong repo


def test_request_gate_bat_va_rule_gia_khop_low_tu_dong_qua(monkeypatch):
    monkeypatch.setenv(AUTOAPPROVE_ENV, "1")
    import company.gate_risk as gr

    monkeypatch.setattr(gr, "RISK_RULES", (RiskRule(name="fake-low", tier="low", match=lambda c: True),))
    bus = InMemoryBus(); gate = PersistentGate(bus)
    req = GateRequest(kind="release", subject_id="REL-3", created_by="delivery-lead", checklist=["tests"])
    gr.request_gate(gate, req)
    assert "REL-3" not in gate.pending
    assert PersistentGate(bus).is_approved("REL-3")
    done = next(g for g in gate.history if g.subject_id == "REL-3")
    assert done.decided_by == AUTOAPPROVE_ACTOR
    assert done.reason.startswith(AUTOAPPROVE_REASON_PREFIX)


def test_request_gate_bat_rule_gia_khop_medium_khong_tu_dong_qua(monkeypatch):
    monkeypatch.setenv(AUTOAPPROVE_ENV, "1")
    import company.gate_risk as gr

    monkeypatch.setattr(gr, "RISK_RULES", (RiskRule(name="fake-medium", tier="medium", match=lambda c: True),))
    bus = InMemoryBus(); gate = PersistentGate(bus)
    req = GateRequest(kind="release", subject_id="REL-4", created_by="delivery-lead", checklist=["tests"])
    gr.request_gate(gate, req)
    assert "REL-4" in gate.pending


def test_request_gate_hai_rule_cung_khop_khong_tu_dong_qua(monkeypatch):
    monkeypatch.setenv(AUTOAPPROVE_ENV, "1")
    import company.gate_risk as gr

    monkeypatch.setattr(gr, "RISK_RULES", (
        RiskRule(name="a", tier="low", match=lambda c: True),
        RiskRule(name="b", tier="low", match=lambda c: True),
    ))
    bus = InMemoryBus(); gate = PersistentGate(bus)
    req = GateRequest(kind="release", subject_id="REL-5", created_by="delivery-lead", checklist=["tests"])
    gr.request_gate(gate, req)
    assert "REL-5" in gate.pending


def test_request_gate_gate_uat_actor_phai_la_code_khong_phai_orchestrator(monkeypatch):
    """sc-security (adr113, 2026-09-10): `gate.decide` không truyền `actor=` thì core tự suy `actor` — với
    subject bắt đầu `UAT-` và `by` không phải người, core gán `actor=SYSTEM_GATE_ACTOR` ("orchestrator")
    (`xagents_core/gate_cli.py::decide`). Envelope khi đó khớp NHÁNH CŨ `trusted_decision` (actor="orchestrator"
    + subject UAT-*) mà KHÔNG kiểm tiền tố `reason` hay cờ `COMPANY_GATE_AUTOAPPROVE` lúc replay — một gate
    nghiệm thu (`acceptance`, subject `UAT-*`) tự động qua bởi code sẽ bị hiểu nhầm thành "khách đã ký". Bắt
    buộc `request_gate` truyền `actor=AUTOAPPROVE_ACTOR` tường minh."""
    monkeypatch.setenv(AUTOAPPROVE_ENV, "1")
    import company.gate_risk as gr

    monkeypatch.setattr(gr, "RISK_RULES", (RiskRule(name="fake-low", tier="low", match=lambda c: True),))
    bus = InMemoryBus(); gate = PersistentGate(bus)
    req = GateRequest(kind="acceptance", subject_id="UAT-REL-1", created_by="ops", checklist=["signed_by"])
    gr.request_gate(gate, req)
    env = next(e for e in bus.replay(topic="audit-log")
               if e.payload.get("action") == "gate.decide" and json.loads(e.payload["evidence"])["subject_id"] == "UAT-REL-1")
    assert env.actor == AUTOAPPROVE_ACTOR, f"actor phải là {AUTOAPPROVE_ACTOR!r}, không phải {env.actor!r} (SYSTEM_GATE_ACTOR)"


def test_trusted_autoapprove_tu_choi_ten_hang_khong_ton_tai_trong_risk_rules(monkeypatch):
    """sc-security (adr113, 2026-09-10): `trusted_autoapprove` trước đây chỉ kiểm tiền tố `reason`, không đối
    chiếu TÊN hàng với `RISK_RULES` hiện có — một envelope actor="code" (nay bus cho publish) với
    reason="auto-risk:<tên bịa>" vẫn được tin nếu cờ bật, bất kể hàng đó có tồn tại hay không."""
    monkeypatch.setenv(AUTOAPPROVE_ENV, "1")
    import company.gate_risk as gr

    monkeypatch.setattr(gr, "RISK_RULES", (RiskRule(name="ten-that", tier="low", match=lambda c: True),))
    env = _fake_code_decide_log("REL-10", reason=f"{AUTOAPPROVE_REASON_PREFIX}ten-bia-khong-co-that")
    assert trusted_autoapprove(env) is None


def test_request_gate_replay_ben_vung(monkeypatch):
    """Mở lại bus (tiến trình khác) sau khi đã auto-approve → dựng lại đúng trạng thái đã đóng, không đóng lại lần hai."""
    monkeypatch.setenv(AUTOAPPROVE_ENV, "1")
    import company.gate_risk as gr

    monkeypatch.setattr(gr, "RISK_RULES", (RiskRule(name="fake-low", tier="low", match=lambda c: True),))
    bus = InMemoryBus(); gate = PersistentGate(bus)
    req = GateRequest(kind="release", subject_id="REL-6", created_by="delivery-lead", checklist=["tests"])
    gr.request_gate(gate, req)
    reopened = PersistentGate(bus)
    assert PersistentGate(bus).is_approved("REL-6")
    assert reopened.pending == {}
    assert sum(1 for g in reopened.history if g.subject_id == "REL-6") == 1


# ---------- chiều ngược: actor "code" giả mạo KHÔNG đi qua request_gate ----------

def _fake_code_decide_log(sid, reason, *, by=AUTOAPPROVE_ACTOR, actor=AUTOAPPROVE_ACTOR):
    ev = json.dumps({"subject_id": sid, "decision": "approve", "by": by, "reason": reason})
    return Envelope(topic="audit-log", key=actor, actor=actor,
                     payload=AuditLog(actor=by, action="gate.decide", evidence=ev).model_dump())


def test_actor_code_thieu_tien_to_reason_khong_duoc_tin(monkeypatch):
    monkeypatch.setenv(AUTOAPPROVE_ENV, "1")
    env = _fake_code_decide_log("REL-7", reason="tôi tự soạn lý do, không qua request_gate")
    assert trusted_autoapprove(env) is None


def test_actor_code_co_tat_khong_duoc_tin_du_dung_tien_to(monkeypatch):
    monkeypatch.delenv(AUTOAPPROVE_ENV, raising=False)
    env = _fake_code_decide_log("REL-8", reason=f"{AUTOAPPROVE_REASON_PREFIX}fake-low")
    assert trusted_autoapprove(env) is None


def test_actor_code_evidence_hong_khong_duoc_tin(monkeypatch):
    monkeypatch.setenv(AUTOAPPROVE_ENV, "1")
    env = Envelope(topic="audit-log", key=AUTOAPPROVE_ACTOR, actor=AUTOAPPROVE_ACTOR,
                    payload=AuditLog(actor=AUTOAPPROVE_ACTOR, action="gate.decide", evidence="{not json").model_dump())
    assert trusted_autoapprove(env) is None


def test_actor_code_gia_mao_khong_dong_duoc_gate_that(monkeypatch):
    """Bản ghi bị chèn thẳng lên bus (mô phỏng log bị sửa tay hoặc bus bị lách), không qua `request_gate` —
    dù đúng actor "code" và cờ bật, thiếu tiền tố `reason` thì gate vẫn `pending`."""
    monkeypatch.setenv(AUTOAPPROVE_ENV, "1")
    bus = InMemoryBus(); gate = PersistentGate(bus)
    gate.request(GateRequest(kind="release", subject_id="REL-9", created_by="delivery-lead", checklist=["tests"]))
    env = _fake_code_decide_log("REL-9", reason="không có tiền tố")
    bus._log.append(env); bus._notify(bus._subs, env)  # đi vòng qua ACL publish, mô phỏng log bị sửa tay
    assert "REL-9" in PersistentGate(bus).pending


# ---------- nhánh chưa đi trong trusted_autoapprove (đo coverage 2026-09-12) ----------

def test_trusted_autoapprove_bo_qua_topic_khac_audit_log():
    env = Envelope(topic="tasks", key="code", actor=AUTOAPPROVE_ACTOR, payload={"action": "gate.decide"})
    assert trusted_autoapprove(env) is None


def test_trusted_autoapprove_bo_qua_action_khac_gate_decide(monkeypatch):
    monkeypatch.setenv(AUTOAPPROVE_ENV, "1")
    env = Envelope(topic="audit-log", key=AUTOAPPROVE_ACTOR, actor=AUTOAPPROVE_ACTOR,
                    payload=AuditLog(actor=AUTOAPPROVE_ACTOR, action="gate.request", evidence="{}").model_dump())
    assert trusted_autoapprove(env) is None


def test_trusted_autoapprove_evidence_khong_phai_dict(monkeypatch):
    monkeypatch.setenv(AUTOAPPROVE_ENV, "1")
    env = Envelope(topic="audit-log", key=AUTOAPPROVE_ACTOR, actor=AUTOAPPROVE_ACTOR,
                    payload=AuditLog(actor=AUTOAPPROVE_ACTOR, action="gate.decide", evidence="[1, 2, 3]").model_dump())
    assert trusted_autoapprove(env) is None


def test_trusted_autoapprove_subject_id_rong(monkeypatch):
    monkeypatch.setenv(AUTOAPPROVE_ENV, "1")
    ev = json.dumps({"subject_id": "", "decision": "approve", "by": AUTOAPPROVE_ACTOR,
                      "reason": f"{AUTOAPPROVE_REASON_PREFIX}fake-low"})
    env = Envelope(topic="audit-log", key=AUTOAPPROVE_ACTOR, actor=AUTOAPPROVE_ACTOR,
                    payload=AuditLog(actor=AUTOAPPROVE_ACTOR, action="gate.decide", evidence=ev).model_dump())
    assert trusted_autoapprove(env) is None


def test_trusted_autoapprove_by_khac_actor_code(monkeypatch):
    monkeypatch.setenv(AUTOAPPROVE_ENV, "1")
    env = _fake_code_decide_log("REL-11", reason=f"{AUTOAPPROVE_REASON_PREFIX}fake-low", by="human:ai-mao-danh")
    assert trusted_autoapprove(env) is None


def test_trusted_autoapprove_decision_khong_phai_chuoi(monkeypatch):
    monkeypatch.setenv(AUTOAPPROVE_ENV, "1")
    ev = json.dumps({"subject_id": "REL-12", "decision": 123, "by": AUTOAPPROVE_ACTOR,
                      "reason": f"{AUTOAPPROVE_REASON_PREFIX}fake-low"})
    env = Envelope(topic="audit-log", key=AUTOAPPROVE_ACTOR, actor=AUTOAPPROVE_ACTOR,
                    payload=AuditLog(actor=AUTOAPPROVE_ACTOR, action="gate.decide", evidence=ev).model_dump())
    assert trusted_autoapprove(env) is None
