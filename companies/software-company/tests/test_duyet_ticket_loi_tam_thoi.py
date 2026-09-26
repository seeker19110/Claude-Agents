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


def test_duyet_escalation_release_chay_lai_luot_qa_hoi_quy_bi_bo(tmp_path):
    """Cùng họ, nhánh RELEASE: security chặn → escalation REL; trong lúc chờ, lượt QA hồi quy staging bị bỏ vì hoãn
    transient quá trần (`unhandled[REL]`). Duyệt = waive + `_rerun_release` (chỉ chạy lại ops `pending_human`) →
    lượt QA không ai chạy lại, release nằm im. Đo được 2026-09-26 (CAMPUS-UNI/REL-007)."""
    from company.events import Envelope
    from company.orchestrator import StepResult
    from test_release_escalation_orchestrator import _blocked_release

    bus = SQLiteBus(tmp_path / "c.sqlite")
    orch = Orchestrator(bus, FakeClient(handler=handler))
    rid, _tid = _blocked_release(orch)
    ev = Envelope(
        topic="release-events",
        key=rid,
        actor="ops",
        payload={"release_id": rid, "env": "staging", "status": "deployed", "version": "0.1.0"},
    )
    bus.publish(ev)
    orch.processed.add(ev.event_id)
    orch._mark_unhandled(ev, "qa", "hoãn transient quá 7200s: transient:qa", StepResult(ev.event_id, ev.topic, ev.key))
    orch.gate.decide(
        rid, "approve", by="human:owner", reason="root_cause: thiếu bằng chứng; decision: approve; hint: giao"
    )
    orch.run()
    assert rid not in orch.unhandled, "lượt QA hồi quy bị bỏ phải được chạy lại"
    assert "event.retried" in [e.payload["action"] for e in bus.replay(topic="audit-log")]
    bus.close()


# ---------- duyệt từ TRƯỚC #354: quyết định đã ghi sổ nhưng event không được chạy lại ----------
# Code trước #354 duyệt xong không chạy lại event bị bỏ, và gate đã đóng — không còn gì mở lại được. Đo được
# 2026-09-26 (CAMPUS-UNI/REL-007): duyệt 15:44, `unhandled[REL-007]` còn nguyên, không gate, không watchdog nào canh
# release. Mở lại bus phải coi quyết định đó là lệnh chạy lại chưa kịp chạy (khuôn `event.retried`).


def _qa_hoi_quy_het_quota(orch, monkeypatch):
    goc = orch.runner.generate

    def gen(agent, env, topic, *a, **k):
        if agent == "qa" and env.topic == "release-events":
            raise TransientError("backend hết quota")
        return goc(agent, env, topic, *a, **k)

    monkeypatch.setattr(orch.runner, "generate", gen)


def _duyet_kieu_cu(orch, monkeypatch, subject, decision="approve"):
    """Hành vi trước #354: duyệt không chạy lại event trong `unhandled`."""
    monkeypatch.setattr(Orchestrator, "_retry_unhandled", lambda *a, **k: False)
    orch.gate.decide(
        subject, decision, by="human:lead", reason="root_cause: hết quota; decision: reopen; hint: chạy lại"
    )
    orch.run()
    monkeypatch.undo()


def _release_mat_luot_qa(tmp_path, monkeypatch):
    from test_orchestrator import _drive_to_plan

    bus = SQLiteBus(tmp_path / "c.sqlite")
    orch = Orchestrator(bus, FakeClient(handler=handler))
    _qa_hoi_quy_het_quota(orch, monkeypatch)
    _drive_to_plan(bus, orch)
    orch.run()
    for eid in list(orch.transient_since):
        orch.transient_since[eid] = time.monotonic() - 3 * 3600
    orch.tick(now=datetime.now(UTC))
    assert "REL-001" in orch.unhandled and orch.gate.pending["REL-001"].kind == "escalation"
    return bus, orch


def test_duyet_release_tu_truoc_354_thi_mo_lai_bus_chay_lai_luot_qa(tmp_path, monkeypatch):
    bus, orch = _release_mat_luot_qa(tmp_path, monkeypatch)
    _duyet_kieu_cu(orch, monkeypatch, "REL-001")
    assert "REL-001" in orch.unhandled and "REL-001" not in orch.gate.pending, "kịch bản: kẹt im lặng như REL-007"
    bus.close()
    bus2 = SQLiteBus(tmp_path / "c.sqlite")
    orch2 = Orchestrator(bus2, FakeClient(handler=handler))
    assert "REL-001" not in orch2.unhandled
    orch2.run()
    g = orch2.gate.pending.get("REL-001")
    assert g is not None and g.kind == "release", "lượt QA hồi quy chạy lại xong → Gate 3 mở"
    bus2.close()
    bus3 = SQLiteBus(tmp_path / "c.sqlite")
    orch3 = Orchestrator(bus3, FakeClient(handler=handler))
    assert "REL-001" not in orch3.unhandled and not orch3.queue, "đã chạy lại rồi thì lần mở sau không chạy nữa"
    bus3.close()


def test_tu_choi_release_tu_truoc_354_thi_mo_lai_bus_khong_chay_lai(tmp_path, monkeypatch):
    bus, orch = _release_mat_luot_qa(tmp_path, monkeypatch)
    _duyet_kieu_cu(orch, monkeypatch, "REL-001", decision="reject")
    bus.close()
    bus2 = SQLiteBus(tmp_path / "c.sqlite")
    orch2 = Orchestrator(bus2, FakeClient(handler=handler))
    bo = orch.unhandled["REL-001"]["event_id"]
    assert "REL-001" in orch2.unhandled and bo in orch2.processed and bo not in {e.event_id for e in orch2.queue}
    bus2.close()


def test_duyet_ticket_tu_truoc_354_thi_mo_lai_bus_giao_lai_viec(tmp_path, monkeypatch):
    bus = SQLiteBus(tmp_path / "c.sqlite")
    orch = Orchestrator(bus, FakeClient(handler=handler))
    tid, _ = _toi_escalation_ticket(bus, orch, monkeypatch)
    _duyet_kieu_cu(orch, monkeypatch, tid)
    assert orch.lead.state[tid] == "dispatched" and tid in orch.unhandled
    bus.close()
    bus2 = SQLiteBus(tmp_path / "c.sqlite")
    orch2 = Orchestrator(bus2, FakeClient(handler=handler))
    orch2.run()
    assert orch2.lead.state[tid] != "dispatched" and tid not in orch2.unhandled
    bus2.close()


def test_duyet_sau_354_roi_mo_lai_bus_khong_chay_lai_lan_hai(tmp_path, monkeypatch):
    bus = SQLiteBus(tmp_path / "c.sqlite")
    orch = Orchestrator(bus, FakeClient(handler=handler))
    tid, _ = _toi_escalation_ticket(bus, orch, monkeypatch)
    orch.gate.decide(tid, "approve", by="human:lead", reason="root_cause: hết quota; decision: reopen; hint: chạy lại")
    orch.run()  # backend vẫn hết quota: lượt chạy lại bị hoãn, ticket còn `dispatched`, `unhandled` đã gỡ
    assert "event.retried" in [e.payload["action"] for e in bus.replay(topic="audit-log")]
    assert orch.lead.state[tid] == "dispatched" and tid not in orch.unhandled
    bus.close()
    bus2 = SQLiteBus(tmp_path / "c.sqlite")
    orch2 = Orchestrator(bus2, FakeClient(handler=handler))
    assert tid not in orch2.unhandled
    cho = [e for e in orch2.queue if e.topic == "tasks" and e.key == tid]
    cho += [e for e, _ in orch2.deferred.values() if e.topic == "tasks" and e.key == tid]
    assert len(cho) == 1, "lượt chạy lại đang chờ đúng một bản, không nhân đôi"
    bus2.close()


def test_duyet_release_cu_ma_du_an_da_ra_rc_moi_thi_khong_chay_lai(tmp_path, monkeypatch):
    """REL-003 (CAMPUS-UNI): duyệt 2026-09-24 15:02, sau đó REL-004/005/007 ra đời — phát lại lần duyệt đó bây giờ là
    deploy một RC cũ đè staging. Dự án đã đi qua lần duyệt thì lần duyệt không còn là lệnh."""
    from company.events import Envelope

    bus, orch = _release_mat_luot_qa(tmp_path, monkeypatch)
    _duyet_kieu_cu(orch, monkeypatch, "REL-001")
    rc = orch.latest("release-candidates", "REL-001")
    bus.publish(
        Envelope(
            topic="release-candidates",
            key="REL-009",
            actor="delivery-lead",
            payload={**rc.payload, "release_id": "REL-009"},
        )
    )
    bus.close()
    bus2 = SQLiteBus(tmp_path / "c.sqlite")
    orch2 = Orchestrator(bus2, FakeClient(handler=handler))
    bo = orch.unhandled["REL-001"]["event_id"]
    assert "REL-001" in orch2.unhandled and bo not in {e.event_id for e in orch2.queue}
    bus2.close()


def test_duyet_ticket_cu_ma_sau_do_ticket_bi_dong_thi_khong_giao_lai(tmp_path, monkeypatch):
    bus = SQLiteBus(tmp_path / "c.sqlite")
    orch = Orchestrator(bus, FakeClient(handler=handler))
    tid, _ = _toi_escalation_ticket(bus, orch, monkeypatch)
    _duyet_kieu_cu(orch, monkeypatch, tid)
    orch.supervisor.escalate_gate(tid, "không hoạt động > 4h", once_key="thu:watchdog")
    orch.run()
    orch.gate.decide(tid, "reject", by="human:lead", reason="root_cause: bỏ việc; decision: close; hint: không làm nữa")
    orch.run()
    assert orch.lead.state[tid] != "dispatched"
    bus.close()
    bus2 = SQLiteBus(tmp_path / "c.sqlite")
    orch2 = Orchestrator(bus2, FakeClient(handler=handler))
    assert not any(e.topic == "tasks" and e.key == tid for e in orch2.queue), "ticket đã đóng thì không giao lại"
    bus2.close()
