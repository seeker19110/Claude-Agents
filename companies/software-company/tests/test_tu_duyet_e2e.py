"""ADR-0043 nối vào vòng thật: orchestrator + deploy giả, cờ bật → gate release tự duyệt khi bằng chứng máy đủ,
thiếu một mảnh thì chờ người kèm `gate.auto_skipped`. Dùng chung harness của `test_deploy_release_fsm.py`."""
from __future__ import annotations

import json

import pytest

from company.events import Envelope
from company.gate_risk import AUTOAPPROVE_ACTOR
from company.gates import AUTOAPPROVE_ENV
from company.llm import FakeClient
from company.orchestrator import Orchestrator
from company.sqlite_bus import SQLiteBus
from test_deploy_release_fsm import RUNTIME, _fake_deploy, _orch, _rel, _repo
from test_orchestrator import handler

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


# ---------- nghiệm thu (ADR-0043 §3) ----------

def _tu_duyet_toi_nghiem_thu(tmp_path, monkeypatch):
    _seed_pr(tmp_path, OK_LC)
    fn, _ = _fake_deploy(monkeypatch)
    bus, orch = _orch(tmp_path, _repo(tmp_path), deploy_fn=fn, runtime=RUNTIME)
    orch.lead.state["T1"] = "approved"
    orch.run(); orch.run(); orch.run()
    return bus, orch


def test_nghiem_thu_tu_duyet_dong_ticket_ma_khong_gia_chu_ky_khach(tmp_path, monkeypatch, on):
    bus, orch = _tu_duyet_toi_nghiem_thu(tmp_path, monkeypatch)
    assert _decided_by(bus, "UAT-REL-001") == [AUTOAPPROVE_ACTOR], _audits(bus, "gate.auto_skipped")
    assert orch.lead.state["T1"] == "closed"
    assert [d["release_id"] for d in _audits(bus, "acceptance.auto")] == ["REL-001"]
    assert not list(bus.replay(topic="acceptance-results")), "máy không bao giờ ghi vào topic chữ ký của khách"


def test_nghiem_thu_tu_duyet_song_qua_restart(tmp_path, monkeypatch, on):
    """Mở lại bus: không có `acceptance-results` nào để replay, nên `_rehydrate` phải áp lại `acceptance.auto`.
    (Harness gán `T1` thẳng vào RAM nên orchestrator mới không biết T1 — đo đúng lời gọi đóng ticket khi replay.)"""
    from company.delivery import DeliveryLead
    bus, orch = _tu_duyet_toi_nghiem_thu(tmp_path, monkeypatch)
    assert orch.lead.state["T1"] == "closed"
    bus.close()
    calls: list[tuple[str, bool]] = []
    goc = DeliveryLead.close_accepted
    def ghi(self, rid):
        calls.append((rid, self.replaying)); return goc(self, rid)
    monkeypatch.setattr(DeliveryLead, "close_accepted", ghi)
    Orchestrator(SQLiteBus(tmp_path / "c.sqlite"), FakeClient(handler=handler), repo=orch.repo)
    assert calls == [("REL-001", True)]


def test_khach_tu_choi_sau_khi_may_nghiem_thu_thi_mo_escalation_cho_nguoi(tmp_path, monkeypatch, on):
    bus, orch = _tu_duyet_toi_nghiem_thu(tmp_path, monkeypatch)
    bus.publish(Envelope(topic="acceptance-results", key="REL-001", actor="ops",
                         payload={"release_id": "REL-001", "project_id": "P", "verdict": "rejected",
                                  "signed_by": "khach:an", "findings": [{"level": "block", "text": "sai màu"}]}))
    orch.run()
    g = orch.gate.pending.get("REL-001")
    assert g is not None and g.kind == "escalation"
    assert [d["release_id"] for d in _audits(bus, "acceptance.overridden")] == ["REL-001"]


def test_du_an_nang_acceptance_human_thi_cho_khach_ky(tmp_path, monkeypatch, on):
    _seed_pr(tmp_path, OK_LC)
    fn, _ = _fake_deploy(monkeypatch)
    bus, orch = _orch(tmp_path, _repo(tmp_path), deploy_fn=fn, runtime=RUNTIME)
    orch.lead.state["T1"] = "approved"
    orch.gate._log("human:pm", "quality.bar_set", {"project_id": "P", "bar": {"acceptance": "human"}, "by": "human:pm"},
                   by="human:pm")
    orch.run()
    assert _decided_by(bus, "REL-001") == [AUTOAPPROVE_ACTOR], "release vẫn tự duyệt: mức nâng chỉ chặn nghiệm thu"
    assert "UAT-REL-001" in orch.gate.pending and orch.lead.state["T1"] == "released"


def test_khach_tu_choi_lan_hai_khong_mo_escalation_trung_va_khach_dong_y_thi_khong_mo(tmp_path, monkeypatch, on):
    bus, orch = _tu_duyet_toi_nghiem_thu(tmp_path, monkeypatch)

    def ky(verdict):
        bus.publish(Envelope(topic="acceptance-results", key="REL-001", actor="ops",
                             payload={"release_id": "REL-001", "project_id": "P", "verdict": verdict,
                                      "signed_by": "khach:an"}))
        orch.run()

    ky("accepted")
    assert "REL-001" not in orch.gate.pending and not _audits(bus, "acceptance.overridden")
    ky("rejected"); ky("rejected")
    assert len(_audits(bus, "acceptance.overridden")) == 1
    esc = [e for e in bus.replay(topic="audit-log") if e.payload.get("action") == "gate.request"
           and '"escalation"' in e.payload["evidence"] and '"REL-001"' in e.payload["evidence"]]
    assert len(esc) == 1 and orch.gate.pending["REL-001"].kind == "escalation"
