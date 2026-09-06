"""ADR-0030 — sổ Ruling: quyết định agent tự đưa ra thay vì dừng chờ người phải (1) vào được mọi topic qua schema,
(2) thành audit `ruling` bền trên bus, (3) đọc lại được sau restart, (4) hiện trong `status` và mọi hồ sơ gate.

Chiều đo ngược: payload KHÔNG có `rulings` → không có audit nào; ruling thiếu `decision` → bị bỏ qua, không ném."""
from __future__ import annotations

import json

from company.events import Envelope, Ruling, Task
from company.gate_brief import build, render_md
from company.llm import FakeClient
from company.orchestrator import ENGINEERING, Orchestrator
from company.sqlite_bus import SQLiteBus
from test_orchestrator import handler

RUL = [{"decision": "dùng SQLite in-memory cho devserver", "why": "spec không chốt DB thật; ADR chưa có người ký",
        "cost_if_wrong": "đổi adapter repository, ~0.5 ngày, không mất dữ liệu vì chưa có production"}]


def _handler_co_ruling(system, user):
    """Backend trả PR kèm ruling; agent khác giữ nguyên."""
    out = handler(system, user)
    if any(a in system[:60] for a in ENGINEERING) and isinstance(out, dict) and "ticket_id" in out:
        return {**out, "rulings": RUL}
    return out


def _orch(tmp_path, h=_handler_co_ruling):
    bus = SQLiteBus(tmp_path / "c.sqlite")
    orch = Orchestrator(bus, FakeClient(handler=h))
    return bus, orch


def _dispatch(bus, orch, tid="T1"):
    orch.lead.tickets[tid] = Task(ticket_id=tid, project_id="P", requirement_id="R1", assignee="backend", title=tid, acceptance=["a"])
    orch.lead.state[tid] = "dispatched"
    bus.publish(Envelope(topic="tasks", key=tid, actor="delivery-lead", payload=orch.lead.tickets[tid].model_dump()))


def test_ruling_vao_audit_va_doc_lai_duoc(tmp_path):
    bus, orch = _orch(tmp_path)
    _dispatch(bus, orch)
    orch.run()
    rows = [e for e in bus.replay(topic="audit-log") if e.payload["action"] == "ruling"]
    assert len(rows) == 1 and rows[0].payload["actor"] == "backend" and rows[0].payload["ticket_id"] == "T1"
    d = json.loads(rows[0].payload["evidence"])
    assert d["decision"] == RUL[0]["decision"] and d["topic"] == "pull-requests" and d["key"] == "T1" and d["event_id"]
    r = orch.rulings()
    assert len(r) == 1 and r[0]["by"] == "backend" and r[0]["cost_if_wrong"].startswith("đổi adapter")
    assert orch.rulings(ticket_id="T1") and not orch.rulings(ticket_id="T9") and orch.rulings(project_id="P")
    assert orch.status()["rulings"] == 1


def test_ruling_song_sot_qua_restart_vi_so_nam_tren_bus(tmp_path):
    bus, orch = _orch(tmp_path)
    _dispatch(bus, orch); orch.run()
    o2 = Orchestrator(SQLiteBus(tmp_path / "c.sqlite"), FakeClient(handler=handler))
    assert len(o2.rulings()) == 1 and o2.status()["rulings"] == 1


def test_khong_co_rulings_thi_khong_co_audit(tmp_path):
    bus, orch = _orch(tmp_path, handler)
    _dispatch(bus, orch); orch.run()
    assert not [e for e in bus.replay(topic="audit-log") if e.payload["action"] == "ruling"]
    assert orch.status()["rulings"] == 0


def test_ruling_thieu_decision_bi_bo_qua_khong_nem(tmp_path):
    def h(system, user):
        out = handler(system, user)
        if isinstance(out, dict) and "ticket_id" in out and "branch" in out:
            return {**out, "rulings": [{"decision": "", "why": "x", "cost_if_wrong": "y"}, "rác"]}
        return out
    bus, orch = _orch(tmp_path, h)
    _dispatch(bus, orch); orch.run()
    assert orch.rulings() == []


def test_ho_so_gate_mang_so_ruling(tmp_path):
    bus, orch = _orch(tmp_path)
    _dispatch(bus, orch); orch.run()
    # mở một gate escalation cho ticket để có hồ sơ (kind bất kỳ đều mang mục Sổ Ruling)
    from company.gates import GateRequest
    orch.gate.request(GateRequest(kind="escalation", subject_id="T1", created_by="supervisor", checklist=["root_cause"]))
    b = build(orch, "T1")
    assert b["extra"]["rulings"] and b["extra"]["rulings"][0]["decision"] == RUL[0]["decision"]
    md = render_md(b)
    assert "Sổ Ruling — agent đã tự quyết 1 việc" in md and "sai thì: đổi adapter" in md


def test_ho_so_gate_khong_ruling_noi_ro(tmp_path):
    bus, orch = _orch(tmp_path, handler)
    _dispatch(bus, orch); orch.run()
    from company.gates import GateRequest
    orch.gate.request(GateRequest(kind="escalation", subject_id="T1", created_by="supervisor", checklist=["root_cause"]))
    md = render_md(build(orch, "T1"))
    assert "tự quyết 0 việc" in md and "chưa có ruling nào" in md


def test_schema_moi_topic_deu_nhan_rulings_va_bat_buoc_ba_phan():
    from company.bus import InMemoryBus
    bus = InMemoryBus()
    ok = Ruling(decision="a", why="b", cost_if_wrong="c").model_dump()
    bus.publish(Envelope(topic="tasks", key="T1", actor="delivery-lead",
                         payload={**Task(ticket_id="T1", project_id="P", requirement_id="R1", assignee="backend", title="t",
                                         acceptance=["a"]).model_dump(), "rulings": [ok]}))
    import pytest

    from company.bus import BusError
    with pytest.raises(BusError):
        bus.publish(Envelope(topic="tasks", key="T2", actor="delivery-lead",
                             payload={**Task(ticket_id="T2", project_id="P", requirement_id="R1", assignee="backend", title="t",
                                             acceptance=["a"]).model_dump(), "rulings": [{"decision": "a"}]}))


def test_cli_rulings_in_so(tmp_path, capsys):
    bus, orch = _orch(tmp_path)
    _dispatch(bus, orch); orch.run()
    from company.orchestrator import main
    assert main(["--db", str(tmp_path / "c.sqlite"), "rulings", "--ticket", "T1"]) == 0
    out = capsys.readouterr().out
    assert "dùng SQLite in-memory" in out and "sai thì:" in out and "(1 ruling)" in out
