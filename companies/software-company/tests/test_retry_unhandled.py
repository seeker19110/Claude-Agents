"""Agent lỗi trên event KHÔNG phải ticket (change-request...) → escalation → duyệt phải chạy LẠI event đó.

Trước đây `_on_escalation_decided` rơi xuống nhánh ticket: "reopen" một ticket không tồn tại, event không bao giờ
chạy lại, hàng đợi rỗng. Đo được 2026-09-06 (CR-DEV-001): delivery-lead lỗi error_max_structured_output_retries,
duyệt escalation xong không có gì xảy ra, phải phát lại CR bằng tay.
"""
from __future__ import annotations

from company.bus import InMemoryBus
from company.events import Envelope
from company.llm import FakeClient, LLMError
from company.orchestrator import Orchestrator
from company.sqlite_bus import SQLiteBus
from test_orchestrator import _agent_of, _inp, _product_phase, handler

CR = {"change_id": "CR-1", "project_id": "P1", "requested_by": "human:po", "description": "đổi phạm vi", "decision": "pending"}


def _flaky_lead(fail_times: int):
    n = {"k": 0}
    def h(system, user):
        a, p = _agent_of(system), _inp(user)
        if a == "product" and _product_phase(system) == "plan" and p.get("decision") == "pending":
            n["k"] += 1
            if n["k"] <= fail_times: raise LLMError("claude -p thoát mã 1 (error_max_structured_output_retries)")
        return handler(system, user)
    return h


def _impacts(bus):
    return [e for e in bus.replay(topic="audit-log") if e.payload["action"] == "change.impact"]


def test_duyet_escalation_cua_change_request_loi_thi_chay_lai_event():
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=_flaky_lead(1)))
    bus.publish(Envelope(topic="change-requests", key="CR-1", actor="human:po", payload=CR)); orch.run()
    assert not _impacts(bus) and orch.unhandled["CR-1"]["agent"] == "product"
    assert orch.gate.pending["CR-1"].kind == "escalation"
    orch.gate.decide("CR-1", "approve", by="human:lead", reason="lỗi model, thử lại"); orch.run()
    assert len(_impacts(bus)) == 1, "duyệt = event chạy lại và lần này `product` ước lượng được"
    assert "CR-1" not in orch.unhandled and not orch.queue
    acts = [e.payload["action"] for e in bus.replay(topic="audit-log")]
    assert "event.retried" in acts


def test_tu_choi_thi_bo_event_khong_chay_lai():
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=_flaky_lead(9)))
    bus.publish(Envelope(topic="change-requests", key="CR-1", actor="human:po", payload=CR)); orch.run()
    orch.gate.decide("CR-1", "reject", by="human:lead", reason="CR sai"); orch.run()
    assert "CR-1" not in orch.unhandled and not _impacts(bus)
    assert "event.abandoned" in [e.payload["action"] for e in bus.replay(topic="audit-log")]


def test_mo_lai_bus_van_nho_event_loi_va_thu_lai_duoc(tmp_path):
    h = _flaky_lead(1)
    bus = SQLiteBus(tmp_path / "c.sqlite"); orch = Orchestrator(bus, FakeClient(handler=h))
    bus.publish(Envelope(topic="change-requests", key="CR-1", actor="human:po", payload=CR)); orch.run()
    bus.close()
    bus2 = SQLiteBus(tmp_path / "c.sqlite"); orch2 = Orchestrator(bus2, FakeClient(handler=h))
    assert "CR-1" in orch2.unhandled, "trạng thái không chỉ sống trong RAM"
    orch2.gate.decide("CR-1", "approve", by="human:lead", reason="thử lại sau restart"); orch2.run()
    assert len(_impacts(bus2)) == 1
    bus2.close()
    bus3 = SQLiteBus(tmp_path / "c.sqlite"); orch3 = Orchestrator(bus3, FakeClient(handler=h))
    assert "CR-1" not in orch3.unhandled, "event.retried đã xoá khỏi sổ"


def test_retry_unhandled_khong_co_gi_de_chay():
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler))
    assert orch._retry_unhandled("CR-404", "human:lead", "x") is False
    orch.unhandled["CR-9"] = {"topic": "change-requests", "event_id": "khong-co", "agent": "product"}
    assert orch._retry_unhandled("CR-9", "human:lead", "x") is False


def _lead_empty_plan_once():
    n = {"k": 0}
    def h(system, user):
        a, p = _agent_of(system), _inp(user)
        if a == "product" and _product_phase(system) == "plan" and p.get("decision") != "pending":
            n["k"] += 1
            if n["k"] == 1: return {"items": []}  # kế hoạch rỗng → plan_rejected
        return handler(system, user)
    return h


def test_duyet_escalation_plan_rong_thi_lap_lai_ke_hoach():
    """`plan_rejected` mở gate escalation subject=project; duyệt phải chạy lại event nguồn để delivery-lead lập lại —
    trước đây rơi xuống nhánh ticket ("reopen" ticket ma), không gì xảy ra (CR-STAGE-001, 2026-09-06)."""
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=_lead_empty_plan_once()))
    bus.publish(Envelope(topic="research-requests", key="P1", actor="human:sales", payload={"project_id": "P1", "description": "app"}))
    orch.run()
    bus.publish(Envelope(topic="clarification-answers", key="P1", actor="human:po",
                         payload={"project_id": "P1", "answers": [{"question_id": "Q1", "answer": "a"}]}))
    orch.run(); orch.gate.decide("SPEC-P1", "approve", by="human:po"); orch.run()
    assert orch.gate.pending["P1"].kind == "escalation" and "P1" in orch.unhandled and not orch.plans
    acts = [e.payload["action"] for e in bus.replay(topic="audit-log")]
    assert "plan_rejected" in acts
    orch.gate.decide("P1", "approve", by="human:lead", reason="lập lại"); orch.run()
    assert "PLAN-P1-1" in orch.plans and orch.lead.tickets, "duyệt = `product` lập lại và ticket được giao ngay (ADR-0037)"
    assert "P1" not in orch.unhandled


def test_mo_lai_bus_van_nho_plan_rejected(tmp_path):
    bus = SQLiteBus(tmp_path / "c.sqlite"); orch = Orchestrator(bus, FakeClient(handler=_lead_empty_plan_once()))
    bus.publish(Envelope(topic="research-requests", key="P1", actor="human:sales", payload={"project_id": "P1", "description": "app"}))
    orch.run()
    bus.publish(Envelope(topic="clarification-answers", key="P1", actor="human:po",
                         payload={"project_id": "P1", "answers": [{"question_id": "Q1", "answer": "a"}]}))
    orch.run(); orch.gate.decide("SPEC-P1", "approve", by="human:po"); orch.run()
    assert "P1" in orch.unhandled
    bus.close(); bus2 = SQLiteBus(tmp_path / "c.sqlite"); orch2 = Orchestrator(bus2, FakeClient(handler=handler))
    assert orch2.unhandled["P1"]["topic"] == "approved-specs"
