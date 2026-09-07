"""`company.trace` — dòng thời gian một ticket/release/dự án từ intake tới deploy (đặc tả nâng cấp B7).

Kiểm: chủ thể suy từ bus (ticket/release/project); đủ mọi gate và mọi lượt retry của dự án giả; tier/model/token/tool/
gate/chờ có trên dòng; chủ thể không tồn tại → exit 1 kèm thông báo rõ; `--json` ổn định; lệnh không ghi bus.
"""
from __future__ import annotations

import json

import pytest

from company import trace as TR
from company.events import Envelope
from company.orchestrator import main as orch_main
from test_gate_brief import _rows, _scenario, fail_handler


def _audit(bus, actor, action, evidence, **kw):
    bus.publish(Envelope(topic="audit-log", key=actor, actor=actor,
                         payload={"actor": actor, "action": action, "evidence": json.dumps(evidence), **kw}))


def test_ticket_ra_du_gate_va_retry(tmp_path):
    db, bus, orch = _scenario(tmp_path, fail_handler, to="escalation")
    assert orch.lead.state["T1"] == "blocked" and orch.gate.pending["T1"].kind == "escalation"
    n = _rows(db)
    t = TR.trace(bus, "T1", orch.agents)
    assert t["kind"] == "ticket" and t["project_id"] == "P1" and t["tickets"] == ["T1"]
    s = t["summary"]
    kinds = [(g["kind"], g["decision"]) for g in s["gates"]]
    # ADR-0037: gate `plan` không còn — dòng thời gian của ticket đi qua gate spec rồi thẳng tới escalation
    assert ("spec", None) in kinds and ("spec", "approve") in kinds and ("escalation", None) in kinds, \
        f"phải thấy hai gate mở và một gate đã quyết, nhận {kinds}"
    assert ("plan", "approve") not in kinds, "không còn gate plan để mà quyết"
    assert s["gates_opened"] == 2 and s["gates_decided"] == 1
    assert s["task_retries"] == 2, "ticket quay 2 vòng: mốc retry cao nhất phải là 2"
    retries = [r["retry"] for r in t["rows"] if r["topic"] == "tasks"]
    assert retries == [0, 1, 2], retries
    assert s["errors"] >= 3 and any(r["action"] == "invalid_output" for r in t["rows"])
    # intake → deploy: mốc đầu tiên là yêu cầu của người, mốc agent có tier từ registry
    assert t["rows"][0]["topic"] == "research-requests" and t["rows"][0]["actor"] == "human:sales"
    intake = next(r for r in t["rows"] if r["agent"] == "intake" and r["action"] == "produced:research-findings")
    assert intake["tier"] == orch.agents["intake"].model_tier and intake["model"] is not None
    assert all(r["wait_s"] >= 0 for r in t["rows"]) and t["rows"][0]["wait_s"] == 0.0
    # gate quyết ghi ai và lý do
    dec = next(r for r in t["rows"] if r["gate"] and r["gate"]["decision"] == "approve")
    assert dec["gate"]["by"] == "human:po" and dec["action"] == "gate.decide"
    assert _rows(db) == n, "trace không được ghi bus"
    md = TR.render(t)
    assert "# trace T1 (ticket)" in md and "gate escalation T1 mở" in md and "retry=2" in md and "LỖI" in md
    assert "deployed: chưa" in md


def test_release_va_du_an(tmp_path):
    _db, bus, orch = _scenario(tmp_path)
    rel = TR.trace(bus, "REL-001", orch.agents)
    assert rel["kind"] == "release" and rel["tickets"] == ["T1"] and rel["releases"] == ["REL-001"]
    assert rel["summary"]["deployed"], "release đã qua staging/production phải có mốc deployed"
    assert any(r["topic"] == "release-events" and "deployed" in r["note"] for r in rel["rows"])
    assert any(r["gate"] and r["gate"]["subject_id"] == "UAT-REL-001" for r in rel["rows"]), "gate nghiệm thu thuộc release"
    proj = TR.trace(bus, "P1", orch.agents)
    assert proj["kind"] == "project" and "T1" in proj["tickets"] and "REL-001" in proj["releases"]
    assert len(proj["rows"]) >= len(rel["rows"]), "dự án bao trùm release"
    assert proj["summary"]["tokens"] >= rel["summary"]["tokens"]
    md = TR.render(proj)
    assert "deployed: " in md and "chưa" not in md.splitlines()[1]


def test_ticket_khac_cung_du_an_khong_lan_vao(tmp_path):
    _db, bus, orch = _scenario(tmp_path, to="plan")
    orch.run()
    # ticket T9 cùng dự án nhưng không nằm trong câu chuyện của T1
    bus.publish(Envelope(topic="tasks", key="T9", actor="delivery-lead", payload={"ticket_id": "T9", "project_id": "P1", "requirement_id": "REQ-9", "assignee": "backend",
                                  "title": "khác", "acceptance": ["x"], "retry": 0}))
    _audit(bus, "backend", "invalid_output", {"error": "sai schema"}, ticket_id="T9", project_id="P1")
    _audit(bus, "backend", "tools_used", {"turns": 2, "mode": "loop", "calls": {"read_file": 3, "run": 1}}, ticket_id="T1", project_id="P1")
    _audit(bus, "backend", "llm_retry", {"attempts": 2, "notes": ["đi backend b (model m) cho tier standard"]}, ticket_id="T1")
    _audit(bus, "backend", "llm_error", {"error": "hết quota"}, ticket_id="T1")
    _audit(bus, "orchestrator", "once", {"key": "x"}, ticket_id="T1")
    _audit(bus, "orchestrator", "integration.merged", {"release_id": "REL-001", "ticket_id": "T1", "sha": "abc"}, ticket_id="T1")
    t1 = TR.trace(bus, "T1", orch.agents)
    assert not any(r["topic"] == "tasks" and r["actor"] == "delivery-lead" and "T9" in str(r) for r in t1["rows"])
    assert not any(r["error"] == "sai schema" for r in t1["rows"]), "lỗi của T9 không lẫn vào T1"
    assert not any(r["action"] in {"once", "orchestrated"} for r in t1["rows"])
    tools = next(r for r in t1["rows"] if r["action"] == "tools_used")
    assert tools["tools"] == {"read_file": 3, "run": 1}
    assert t1["summary"]["llm_retries"] == 2 and any(r["error"] == "hết quota" for r in t1["rows"])
    md = TR.render(t1)
    assert "tool read_file×3 run×1" in md and "LỖI hết quota" in md and "retry=2" in md
    p = TR.trace(bus, "P1", orch.agents)
    assert any(r["error"] == "sai schema" for r in p["rows"]), "trace dự án thì thấy cả T9"
    assert "T9" in p["tickets"]


def test_khong_ton_tai_va_cli(tmp_path, capsys):
    db, bus, orch = _scenario(tmp_path, fail_handler, to="escalation")
    with pytest.raises(TR.TraceError, match="KHONG-CO"):
        TR.trace(bus, "KHONG-CO", orch.agents)
    assert TR.run(bus, "KHONG-CO", agents=orch.agents) == 1
    err = capsys.readouterr().err
    assert "không có chủ thể 'KHONG-CO'" in err and "tasks: 1" in err and "P1" in err
    # qua orchestrator CLI (bus đã mở, như diagnose) và qua module chỉ đọc
    assert orch_main(["--db", str(db), "trace", "T1"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# trace T1 (ticket)") and "gate spec SPEC-P1 quyết approve by human:po" in out
    assert orch_main(["--db", str(db), "trace", "KHONG-CO"]) == 1
    assert TR.main(["T1", "--db", str(db), "--json"]) == 0
    j = json.loads(capsys.readouterr().out)
    assert j["schema_version"] == 1 and j["subject"] == "T1" and j["summary"]["task_retries"] == 2
    assert TR.main(["T1", "--db", str(tmp_path / "khong.sqlite")]) == 3
    assert "không có bus SQLite" in capsys.readouterr().err


def test_render_cho_thoi_gian_dai_va_tier_mac_dinh(tmp_path):
    _db, bus, _orch = _scenario(tmp_path, to="plan")
    t = TR.trace(bus, "P1")  # agents=None → nạp registry
    assert any(r["tier"] for r in t["rows"])
    assert TR._wait(5) == "+5s" and TR._wait(600) == "+10m" and TR._wait(7200) == "+2.0h"
    assert TR._plan_of("P1", "PLAN-P1-3") and not TR._plan_of("P1", None)
    # payload lạ: tools_used không phải dict, produced không có model → không nổ
    _audit(bus, "backend", "tools_used", {"calls": ["x"]}, project_id="P1")
    _audit(bus, "backend", "produced:pull-requests", {"duration_ms": 5}, project_id="P1", tokens=7, cost_usd=0.01)
    t2 = TR.trace(bus, "P1", _orch.agents)
    last = t2["rows"][-2:]
    assert last[0]["tools"] is None and last[1]["model"] is None and last[1]["tokens"] == 7 and last[1]["agent"] == "backend"
    md = TR.render(t2)
    assert "[?/" not in md and "7 tok $0.0100" in md and "[light/fake-light]" in md and "[light]" in md
    assert TR.trace(bus, "P1", {})["rows"][-1]["agent"] is None, "không có registry thì không đoán agent/tier"
