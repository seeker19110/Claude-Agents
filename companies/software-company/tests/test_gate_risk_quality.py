"""Hai hàng `RISK_RULES` đầu tiên (ADR-0043): gate `release`/`acceptance` tự duyệt khi bằng chứng máy đạt sàn."""
import json
from dataclasses import replace

import pytest

import company.gate_risk as gr
from company.bus import InMemoryBus
from company.gate_cli import PersistentGate
from company.gate_risk import AUTOAPPROVE_ACTOR, AUTOAPPROVE_REASON_PREFIX, RISK_RULES, request_gate
from company.gates import AUTOAPPROVE_ENV, GateRequest
from company.quality_floor import QualityBar, QualityEvidence
from company.roles import LEAD_ACTOR, ROLE

SHA = "d" * 40
OK = {"lint": True, "tests": True, "verified_by": "workspace"}


def _ev(kind="release", **kw) -> QualityEvidence:
    base = QualityEvidence(
        kind=kind, release_id="REL-1", staged_sha=SHA, pr_checks=(("T1", OK),),
        run={"ok": True, "verified_by": "orchestrator", "sha": SHA}, staging_deploy=None,
        qa_verdict="pass", security_verdict=None, needs_security=False, waived=(), had_incident=False,
        release_approved=kind == "acceptance",
        production_deploy={"ok": True, "verified_by": "orchestrator", "sha": SHA} if kind == "acceptance" else None,
    )
    return replace(base, **kw)


def _release_req(sid="REL-1"):
    return GateRequest(kind="release", subject_id=sid, created_by=LEAD_ACTOR, checklist=["tests"])


def _audits(bus, action):
    return [json.loads(e.payload["evidence"]) for e in bus.replay(topic="audit-log")
            if e.payload.get("action") == action]


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv(AUTOAPPROVE_ENV, "1")


def test_bang_co_dung_hai_hang_san_chat_luong():
    assert {r.name for r in RISK_RULES} == {"release-quality-floor", "acceptance-quality-floor"}
    assert all(r.tier == "low" for r in RISK_RULES)


def test_release_dat_san_thi_code_tu_duyet_va_replay_van_tin(on):
    bus = InMemoryBus(); gate = PersistentGate(bus)
    request_gate(gate, _release_req(), evidence=_ev(), bar=QualityBar())
    assert "REL-1" not in gate.pending
    d = _audits(bus, "gate.decide")[-1]
    assert d["by"] == AUTOAPPROVE_ACTOR and d["reason"] == f"{AUTOAPPROVE_REASON_PREFIX}release-quality-floor"
    assert PersistentGate(bus).is_approved("REL-1")  # tiến trình khác dựng lại từ replay: vẫn tin


def test_release_thieu_bang_chung_cho_nguoi_va_ghi_ly_do(on):
    bus = InMemoryBus(); gate = PersistentGate(bus)
    request_gate(gate, _release_req(), evidence=_ev(qa_verdict="fail"), bar=QualityBar())
    assert "REL-1" in gate.pending
    skipped = _audits(bus, "gate.auto_skipped")
    assert skipped and skipped[-1]["subject_id"] == "REL-1" and any("R3" in g for g in skipped[-1]["gaps"])


def test_co_tat_thi_khong_tu_duyet_va_khong_ghi_gi_them(monkeypatch):
    monkeypatch.delenv(AUTOAPPROVE_ENV, raising=False)
    bus = InMemoryBus(); gate = PersistentGate(bus)
    request_gate(gate, _release_req(), evidence=_ev(), bar=QualityBar())
    assert "REL-1" in gate.pending and not _audits(bus, "gate.auto_skipped")


def test_khong_truyen_bang_chung_thi_cho_nguoi(on):
    bus = InMemoryBus(); gate = PersistentGate(bus)
    request_gate(gate, _release_req())
    assert "REL-1" in gate.pending


def test_khong_co_muc_nang_thi_cho_nguoi_hong_thi_dong(on):
    bus = InMemoryBus(); gate = PersistentGate(bus)
    request_gate(gate, _release_req(), evidence=_ev())
    assert "REL-1" in gate.pending


def test_bang_chung_sai_loai_gate_khong_khop(on):
    bus = InMemoryBus(); gate = PersistentGate(bus)
    req = GateRequest(kind="acceptance", subject_id="UAT-REL-1", created_by=ROLE.OPS, checklist=[])
    request_gate(gate, req, evidence=_ev("release"), bar=QualityBar())
    assert "UAT-REL-1" in gate.pending


def test_escalation_khong_bao_gio_tu_duyet_du_bang_chung_dep(on):
    bus = InMemoryBus(); gate = PersistentGate(bus)
    req = GateRequest(kind="escalation", subject_id="REL-1", created_by=LEAD_ACTOR, checklist=[])
    request_gate(gate, req, evidence=replace(_ev(), kind="escalation"), bar=QualityBar())
    assert "REL-1" in gate.pending


def test_nghiem_thu_dat_san_ghi_duoi_actor_code_khong_phai_chu_ky_khach(on):
    bus = InMemoryBus(); gate = PersistentGate(bus)
    req = GateRequest(kind="acceptance", subject_id="UAT-REL-1", created_by=ROLE.OPS, checklist=[])
    request_gate(gate, req, evidence=_ev("acceptance"), bar=QualityBar())
    assert "UAT-REL-1" not in gate.pending
    env = [e for e in bus.replay(topic="audit-log") if e.payload.get("action") == "gate.decide"][-1]
    assert env.actor == AUTOAPPROVE_ACTOR  # không phải "orchestrator" (đường chữ ký khách UAT-*)
    assert json.loads(env.payload["evidence"])["reason"] == f"{AUTOAPPROVE_REASON_PREFIX}acceptance-quality-floor"


def test_chieu_nguoc_bo_hang_release_thi_khong_tu_duyet(on, monkeypatch):
    monkeypatch.setattr(gr, "RISK_RULES", gr.rules_without("release-quality-floor"))
    bus = InMemoryBus(); gate = PersistentGate(bus)
    request_gate(gate, _release_req(), evidence=_ev(), bar=QualityBar())
    assert "REL-1" in gate.pending
