"""Quyết định gate chỉ đến từ người: `audit-log` là topic mở, nên `gate.decide` phải được kiểm actor của envelope
chứ không chỉ tin `evidence.by` (rà soát bảo mật 2026-09-04)."""
import json

import pytest

from company.bus import InMemoryBus, PermissionDenied
from company.events import AuditLog, Envelope
from company.gate_cli import PersistentGate, trusted_decision
from company.gates import GateRequest
from company.orchestrator import main as orch_main


def _decide_log(bus, actor, by, sid="PLAN-1", decision="approve", enforce=True):
    ev = json.dumps({"subject_id": sid, "decision": decision, "by": by})
    env = Envelope(topic="audit-log", key=actor, actor=actor,
                   payload=AuditLog(actor=by, action="gate.decide", evidence=ev).model_dump())
    if enforce: return bus.publish(env)
    bus._log.append(env); bus._notify(bus._subs, env); return env  # đi vòng qua bus (mô phỏng log bị sửa tay)


def test_agent_khong_ghi_duoc_gate_decide_len_bus():
    bus = InMemoryBus(); gate = PersistentGate(bus)
    gate.request(GateRequest(kind="plan", subject_id="PLAN-1", created_by="delivery-lead", checklist=["tickets"]))
    with pytest.raises(PermissionDenied):
        _decide_log(bus, actor="delivery-lead", by="human:pm")
    assert "PLAN-1" in gate.pending
    assert any(e.payload.get("action") == "publish_denied" for e in bus.replay(topic="audit-log"))


def test_ban_ghi_gate_decide_gia_trong_log_khong_dong_gate():
    """Log đã có một dòng gate.decide mà actor không phải người (hoặc không trùng `by`): replay bỏ qua."""
    bus = InMemoryBus(); gate = PersistentGate(bus)
    gate.request(GateRequest(kind="plan", subject_id="PLAN-1", created_by="delivery-lead", checklist=["tickets"]))
    _decide_log(bus, actor="delivery-lead", by="human:pm", enforce=False)   # agent giả danh
    _decide_log(bus, actor="human:dev", by="human:pm", enforce=False)       # người này ký tên người khác
    assert "PLAN-1" in gate.pending
    assert "PLAN-1" in PersistentGate(bus).pending  # dựng lại từ replay cũng không tin
    gate.decide("PLAN-1", "approve", by="human:pm")
    assert PersistentGate(bus).is_approved("PLAN-1")


def test_trusted_decision_chi_tin_nguoi_hoac_orchestrator_dong_gate_nghiem_thu():
    ok = _decide_log(InMemoryBus(enforce_owners=False), actor="human:pm", by="human:pm")
    assert trusted_decision(ok)["subject_id"] == "PLAN-1"
    uat = _decide_log(InMemoryBus(enforce_owners=False), actor="orchestrator", by="chị Lan (PO)", sid="UAT-REL-1")
    assert trusted_decision(uat)["decision"] == "approve"
    plan_by_orch = _decide_log(InMemoryBus(enforce_owners=False), actor="orchestrator", by="human:pm")
    assert trusted_decision(plan_by_orch) is None  # orchestrator không được duyệt plan/release thay người
    hong = Envelope(topic="audit-log", key="human:pm", actor="human:pm",
                    payload=AuditLog(actor="human:pm", action="gate.decide", evidence="{not json").model_dump())
    assert trusted_decision(hong) is None
    assert trusted_decision(Envelope(topic="audit-log", key="x", actor="human:pm",
                                     payload=AuditLog(actor="human:pm", action="gate.request", evidence="{}").model_dump())) is None


def test_cli_publish_tu_choi_actor_khong_phai_nguoi(tmp_path, capsys):
    db = str(tmp_path / "c.sqlite"); f = tmp_path / "d.json"
    f.write_text(json.dumps({"actor": "x", "action": "gate.decide", "evidence": "{}"}), encoding="utf-8")
    assert orch_main(["--db", db, "publish", "audit-log", str(f), "--actor", "delivery-lead", "--key", "k"]) == 2
    assert "human:" in capsys.readouterr().err


def test_subagent_actor_khong_dong_duoc_gate():
    """I2 (đặc tả trợ lý kiểm duyệt §8.4): kể cả khi một trợ lý `sc-*` có cách ghi được `gate.decide` lên bus, quyết
    định đó không được tin — gate vẫn `pending`. Trợ lý chuẩn bị bằng chứng, người ký."""
    bus = InMemoryBus(); gate = PersistentGate(bus)
    gate.request(GateRequest(kind="escalation", subject_id="T1", created_by="supervisor", checklist=["hint"]))
    with pytest.raises(PermissionDenied):  # đường thẳng: bus chặn ngay
        _decide_log(bus, actor="sc-qa-debugger", by="sc-qa-debugger", sid="T1")
    for actor, by in (("sc-qa-debugger", "sc-qa-debugger"), ("sc-gate-escalation", "human:lead")):
        env = _decide_log(bus, actor=actor, by=by, sid="T1", enforce=False)  # đường vòng: log bị chèn tay
        assert trusted_decision(env) is None
    assert "T1" in gate.pending and "T1" in PersistentGate(bus).pending
    gate.decide("T1", "approve", by="human:lead", reason="mock thiếu header X-Idempotency-Key")
    assert PersistentGate(bus).is_approved("T1")
