"""ADR-0043 nối vào vòng thật: orchestrator + deploy giả, cờ bật → gate release tự duyệt khi bằng chứng máy đủ,
thiếu một mảnh thì chờ người kèm `gate.auto_skipped`. Dùng chung harness của `test_deploy_release_fsm.py`."""
from __future__ import annotations

import json

import pytest

from company.events import Envelope
from company.gate_risk import AUTOAPPROVE_ACTOR
from company.gates import AUTOAPPROVE_ENV
from company.sqlite_bus import SQLiteBus
from test_deploy_release_fsm import RUNTIME, _fake_deploy, _orch, _rel, _repo

OK_LC = {"lint": True, "tests": True, "verified_by": "workspace"}


def _audits(bus, action):
    return [json.loads(e.payload["evidence"]) for e in bus.replay(topic="audit-log") if e.payload.get("action") == action]


def _seed_pr(tmp_path, lc):
    """PR của T1 lên bus TRƯỚC khi orchestrator dựng (không đi qua handler `_on_pr` của vòng sống)."""
    bus = SQLiteBus(tmp_path / "c.sqlite")
    bus.publish(Envelope(topic="pull-requests", key="T1", actor="builder",
                         payload={"ticket_id": "T1", "branch": "ticket/T1", "pr_ref": "x", "local_checks": lc,
                                  "project_id": "P"}))
    bus.close()


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv(AUTOAPPROVE_ENV, "1")


def _decided_by(bus, sid):
    return [d["by"] for d in _audits(bus, "gate.decide") if d["subject_id"] == sid]


def test_release_du_bang_chung_may_tu_duyet_va_len_production(tmp_path, monkeypatch, on):
    _seed_pr(tmp_path, OK_LC)
    fn, _ = _fake_deploy(monkeypatch)
    bus, orch = _orch(tmp_path, _repo(tmp_path), deploy_fn=fn, runtime=RUNTIME)
    orch.lead.state["T1"] = "approved"
    orch.run()
    assert _decided_by(bus, "REL-001") == [AUTOAPPROVE_ACTOR], _audits(bus, "gate.auto_skipped")
    orch.run()
    assert _rel(bus, "production") and _rel(bus, "production")[-1]["status"] == "deployed"


def test_pr_test_do_thi_cho_nguoi_va_noi_vi_sao(tmp_path, monkeypatch, on):
    _seed_pr(tmp_path, {**OK_LC, "tests": False})
    fn, _ = _fake_deploy(monkeypatch)
    bus, orch = _orch(tmp_path, _repo(tmp_path), deploy_fn=fn, runtime=RUNTIME)
    orch.lead.state["T1"] = "approved"
    orch.run()
    assert "REL-001" in orch.gate.pending and not _decided_by(bus, "REL-001")
    gaps = [g for d in _audits(bus, "gate.auto_skipped") if d["subject_id"] == "REL-001" for g in d["gaps"]]
    assert any(g.startswith("R1") for g in gaps)


def test_du_an_nang_release_human_thi_cho_nguoi(tmp_path, monkeypatch, on):
    _seed_pr(tmp_path, OK_LC)
    fn, _ = _fake_deploy(monkeypatch)
    _bus, orch = _orch(tmp_path, _repo(tmp_path), deploy_fn=fn, runtime=RUNTIME)
    orch.lead.state["T1"] = "approved"
    orch.gate._log("human:pm", "quality.bar_set", {"project_id": "P", "bar": {"release": "human"}, "by": "human:pm"},
                   by="human:pm")
    orch.run()
    assert "REL-001" in orch.gate.pending


def test_co_tat_thi_hanh_vi_cu(tmp_path, monkeypatch):
    monkeypatch.delenv(AUTOAPPROVE_ENV, raising=False)
    _seed_pr(tmp_path, OK_LC)
    fn, _ = _fake_deploy(monkeypatch)
    bus, orch = _orch(tmp_path, _repo(tmp_path), deploy_fn=fn, runtime=RUNTIME)
    orch.lead.state["T1"] = "approved"
    orch.run()
    assert "REL-001" in orch.gate.pending and not _audits(bus, "gate.auto_skipped")
