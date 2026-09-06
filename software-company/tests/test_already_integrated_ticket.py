"""Ticket mà code ĐÃ nằm trong nhánh tích hợp nhưng sổ sách còn kẹt `blocked`: duyệt escalation phải đánh dấu XONG,
không giao lại cho agent. Xem `DeliveryLead.mark_done_already_integrated`.

Đo được 2026-09-05/06 (QLKH): sau khi review cấp release chặn vì DPIA, ticket đã merge bị đá về rework; agent chạy
lại, đúng đắn thấy không còn gì để sửa nên không ghi file nào → `invalid_output` → hết retry → `blocked` →
escalation → người duyệt → lặp. QLKH-010 quay 7 vòng; 011/014 vào đúng vòng đó (code cả ba đều đã ở
`company/integration`), chỉ 012 là còn việc thật.
"""
from __future__ import annotations

from company.events import Task
from company.gates import GateRequest
from company.llm import FakeClient
from company.orchestrator import Orchestrator
from company.sqlite_bus import SQLiteBus
from test_orchestrator import handler


def _blocked_ticket(orch, tid="T1", integrated=True):
    orch.lead.tickets[tid] = Task(ticket_id=tid, project_id="P", requirement_id="R1", assignee="backend",
                                  title=tid, acceptance=["a"])
    orch.lead.state[tid] = "blocked"
    if integrated:
        orch.integrated.add(tid)
    orch.gate.request(GateRequest(kind="escalation", subject_id=tid, created_by="supervisor",
                                  checklist=["root_cause", "decision:reopen|close", "hint"]))
    return tid


def test_ticket_da_tich_hop_thi_duyet_escalation_danh_dau_xong_khong_giao_lai(tmp_path):
    bus = SQLiteBus(tmp_path / "c.sqlite")
    client = FakeClient(handler=handler)
    orch = Orchestrator(bus, client, repo=None)
    tid = _blocked_ticket(orch)

    orch.gate.decide(tid, "approve", by="human:lead", reason="d")
    res = orch.run()

    assert orch.lead.state[tid] == "merged", "code đã ở nhánh tích hợp → đánh dấu xong, không quay lại vòng làm"
    assert any(a == f"already_integrated:{tid}" for r in res for a in r.actions), [r.actions for r in res]
    assert not [c for c in client.calls if "backend" in c["system"][:40]], "KHÔNG được gọi agent làm lại việc đã merge"
    acts = [e.payload["action"] for e in bus.replay(topic="audit-log")]
    assert "ticket.already_integrated" in acts and "invalid_output" not in acts
    assert not [e for e in bus.replay(topic="tasks") if e.key == tid], "không phát task mới cho ticket đã xong"

    orch.lead.mark_done_already_integrated(tid)  # idempotent: gọi lại trên ticket đã `merged` không đổi gì
    assert orch.lead.state[tid] == "merged"


def test_ticket_chua_tich_hop_van_duoc_giao_lai_nhu_cu(tmp_path):
    """Chiều ngược: ticket CHƯA vào nhánh tích hợp (còn việc thật) vẫn `reopen` → phát task mới như trước."""
    bus = SQLiteBus(tmp_path / "c.sqlite")
    orch = Orchestrator(bus, FakeClient(handler=handler), repo=None)
    tid = _blocked_ticket(orch, tid="T2", integrated=False)

    orch.gate.decide(tid, "approve", by="human:lead", reason="làm lại đi")
    res = orch.run()

    assert any(a == f"reopen:{tid}" for r in res for a in r.actions), [r.actions for r in res]
    assert not any(a.startswith("already_integrated:") for r in res for a in r.actions)
    tasks = [e for e in bus.replay(topic="tasks") if e.key == tid]
    assert tasks and tasks[-1].payload["hint"] == "làm lại đi", "vẫn phát task mới kèm hint của người duyệt"


def test_danh_dau_xong_song_sot_qua_restart_bus(tmp_path):
    bus = SQLiteBus(tmp_path / "c.sqlite")
    orch = Orchestrator(bus, FakeClient(handler=handler), repo=None)
    tid = _blocked_ticket(orch, tid="T3")
    orch.gate.decide(tid, "approve", by="human:lead", reason="d")
    orch.run()
    assert orch.lead.state[tid] == "merged"
    bus.close()

    o2 = Orchestrator(SQLiteBus(tmp_path / "c.sqlite"), FakeClient(handler=handler), repo=None)
    assert o2.lead.state.get(tid) != "blocked", "mở lại bus không được kéo ticket đã xong về `blocked` lần nữa"
