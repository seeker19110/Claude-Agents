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
from test_orchestrator import _agent_of, _inp, handler

CR = {"change_id": "CR-1", "project_id": "P1", "requested_by": "human:po", "description": "đổi phạm vi", "decision": "pending"}


def _flaky_lead(fail_times: int):
    n = {"k": 0}
    def h(system, user):
        a, p = _agent_of(system), _inp(user)
        if a == "delivery-lead" and p.get("decision") == "pending":
            n["k"] += 1
            if n["k"] <= fail_times: raise LLMError("claude -p thoát mã 1 (error_max_structured_output_retries)")
        return handler(system, user)
    return h


def _impacts(bus):
    return [e for e in bus.replay(topic="audit-log") if e.payload["action"] == "change.impact"]


def test_duyet_escalation_cua_change_request_loi_thi_chay_lai_event():
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=_flaky_lead(1)))
    bus.publish(Envelope(topic="change-requests", key="CR-1", actor="human:po", payload=CR)); orch.run()
    assert not _impacts(bus) and orch.unhandled["CR-1"]["agent"] == "delivery-lead"
    assert orch.gate.pending["CR-1"].kind == "escalation"
    orch.gate.decide("CR-1", "approve", by="human:lead", reason="lỗi model, thử lại"); orch.run()
    assert len(_impacts(bus)) == 1, "duyệt = event chạy lại và lần này delivery-lead ước lượng được"
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
    orch.unhandled["CR-9"] = {"topic": "change-requests", "event_id": "khong-co", "agent": "delivery-lead"}
    assert orch._retry_unhandled("CR-9", "human:lead", "x") is False
