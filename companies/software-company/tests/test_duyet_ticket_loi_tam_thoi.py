"""Ticket `dispatched` mà lượt giao việc bị bỏ vì hoãn `transient:` quá trần → escalation subject=ticket → duyệt
phải chạy LẠI đúng event `tasks` đã lỗi.

Trước đây `_on_escalation_decided` chỉ chạy lại `unhandled` khi subject KHÔNG phải ticket; subject là ticket thì rơi
xuống nhánh ticket: state `dispatched` không `reopen`, chỉ `resume` — không gì chạy, ticket nằm im tới watchdog
"không hoạt động > 4h" mở gate mới cho cùng việc. Đo được 2026-09-26 (CAMPUS-UNI/TCK-012, TCK-015): backend hết
quota 13:13–13:43, duyệt 15:43, gate mở lại 15:48 ngay sau restart.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from company.bus import InMemoryBus
from company.llm import FakeClient, TransientError
from company.orchestrator import Orchestrator
from company.sqlite_bus import SQLiteBus
from test_orchestrator import _drive_to_spec_gate, handler


def _het_quota_builder(orch, monkeypatch):
    goc = orch.runner.generate
    trang_thai = {"het": True}

    def gen(agent, env, topic, *a, **k):
        if trang_thai["het"] and agent == "builder":
            raise TransientError("backend hết quota")
        return goc(agent, env, topic, *a, **k)

    monkeypatch.setattr(orch.runner, "generate", gen)
    return trang_thai


def _toi_escalation_ticket(bus, orch, monkeypatch):
    _drive_to_spec_gate(bus, orch)
    quota = _het_quota_builder(orch, monkeypatch)
    orch.gate.decide("SPEC-P1", "approve", by="human:po")
    orch.run()
    for eid in list(orch.transient_since):
        orch.transient_since[eid] = time.monotonic() - 3 * 3600
    orch.tick(now=datetime.now(UTC))
    tid = next(s for s, r in orch.gate.pending.items() if r.kind == "escalation" and s in orch.lead.tickets)
    assert orch.lead.state[tid] == "dispatched" and tid in orch.unhandled
    return tid, quota


def test_duyet_escalation_ticket_loi_tam_thoi_thi_giao_lai_viec(monkeypatch):
    bus = InMemoryBus()
    orch = Orchestrator(bus, FakeClient(handler=handler))
    tid, quota = _toi_escalation_ticket(bus, orch, monkeypatch)
    quota["het"] = False
    orch.gate.decide(tid, "approve", by="human:lead", reason="root_cause: hết quota; decision: reopen; hint: chạy lại")
    orch.run()
    assert orch.lead.state[tid] != "dispatched", "builder phải chạy lại event `tasks` đã lỗi và nộp PR"
    assert tid not in orch.unhandled
    assert "event.retried" in [e.payload["action"] for e in bus.replay(topic="audit-log")]


def test_restart_giua_loi_va_duyet_van_giao_lai_viec(tmp_path, monkeypatch):
    bus = SQLiteBus(tmp_path / "c.sqlite")
    orch = Orchestrator(bus, FakeClient(handler=handler))
    tid, _ = _toi_escalation_ticket(bus, orch, monkeypatch)
    bus.close()
    bus2 = SQLiteBus(tmp_path / "c.sqlite")
    orch2 = Orchestrator(bus2, FakeClient(handler=handler))
    orch2.gate.decide(tid, "approve", by="human:lead", reason="root_cause: hết quota; decision: reopen; hint: chạy lại")
    orch2.run()
    assert orch2.lead.state[tid] != "dispatched" and tid not in orch2.unhandled
    bus2.close()
