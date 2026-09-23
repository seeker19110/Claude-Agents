"""Thu bằng chứng cho sàn chất lượng từ bus (ADR-0043 §1): chỉ nguồn do máy sinh, đúng release, đúng sha."""
import json

from company.bus import InMemoryBus
from company.events import AuditLog, Envelope
from company.gates import GateRequest
from company.quality_floor import collect_evidence

SHA = "f" * 40
OK_LC = {"lint": True, "tests": True, "verified_by": "workspace"}


def _pub(bus, topic, key, payload, actor="orchestrator", causation_id=None):
    return bus.publish(Envelope(topic=topic, key=key, actor=actor, payload=payload, causation_id=causation_id))


def _audit(bus, action, ev):
    _pub(bus, "audit-log", "orchestrator",
         AuditLog(actor="orchestrator", action=action, evidence=json.dumps(ev)).model_dump())


def _pr(bus, tid, lc):
    _pub(bus, "pull-requests", tid, {"ticket_id": tid, "branch": f"ticket/{tid}", "pr_ref": "x", "local_checks": lc})


def _review(bus, rid, source, verdict, cause, run=None):
    p = {"ticket_id": rid, "source": source, "verdict": verdict}
    if run is not None:
        p["evidence"] = {"run": run}
    _pub(bus, "review-results", rid, p, actor=source, causation_id=cause)


def _rel_event(bus, rid, env, status, deploy):
    return _pub(bus, "release-events", rid, {"release_id": rid, "version": "1.0.0", "env": env, "status": status,
                                     "evidence": {"deploy": deploy}})


def _rc(bus, rid):
    return _pub(bus, "release-candidates", rid, {"release_id": rid, "project_id": "P", "tickets": ["T1"],
                                                "version": "1.0.0", "notes": "rc"}, actor="delivery-lead")


RUN = {"ok": True, "verified_by": "orchestrator", "sha": SHA}


def _full(bus, rid="REL-1"):
    rc = _rc(bus, rid)
    _audit(bus, "release.staged", {"release_id": rid, "sha": SHA})
    _pr(bus, "T1", {"lint": False, "tests": False, "verified_by": "workspace"})  # PR cũ, đã bị thay
    _pr(bus, "T1", OK_LC)
    st = _rel_event(bus, rid, "staging", "deployed", {"ok": True, "verified_by": "orchestrator", "sha": SHA})
    _audit(bus, "regression.run", {"release_id": rid, "ok": False, "verified_by": "orchestrator", "sha": SHA})
    _audit(bus, "regression.run", {"release_id": rid, **RUN})
    _review(bus, rid, "qa", "fail", st.event_id)
    _review(bus, rid, "qa", "pass", st.event_id)
    _review(bus, rid, "security", "pass", rc.event_id)


def test_thu_dung_ban_moi_nhat_cua_moi_nguon():
    bus = InMemoryBus(enforce_owners=False); _full(bus)
    ev = collect_evidence(bus, "release", "REL-1", tickets=["T1"], needs_security=True, waived=(), history=[])
    assert ev.kind == "release" and ev.staged_sha == SHA
    assert ev.pr_checks == (("T1", OK_LC),)
    assert ev.qa_verdict == "pass" and ev.run == RUN
    assert ev.security_verdict == "pass" and ev.needs_security is True
    assert ev.staging_deploy == {"ok": True, "verified_by": "orchestrator", "sha": SHA}
    assert ev.production_deploy is None and ev.release_approved is False and ev.had_incident is False


def test_thieu_nguon_thi_la_none_khong_bia():
    bus = InMemoryBus(enforce_owners=False)
    ev = collect_evidence(bus, "release", "REL-9", tickets=["T7"], needs_security=False, waived=("qa",), history=[])
    assert ev.staged_sha is None and ev.pr_checks == (("T7", None),) and ev.run is None
    assert ev.qa_verdict is None and ev.staging_deploy is None and ev.waived == ("qa",)


def test_release_khac_va_env_khac_khong_lan_vao():
    bus = InMemoryBus(enforce_owners=False); _full(bus, "REL-2")
    _audit(bus, "release.deploy", {"release_id": "REL-1", "sha": "0" * 40})  # action khác: không phải staged
    _rel_event(bus, "REL-1", "staging", "deploy_failed", {"ok": False, "verified_by": "orchestrator"})
    ev = collect_evidence(bus, "release", "REL-1", tickets=[], needs_security=False, waived=(), history=[])
    assert ev.staged_sha is None and ev.staging_deploy is None and ev.qa_verdict is None


def test_nghiem_thu_doc_production_va_gate_release_da_duyet():
    bus = InMemoryBus(enforce_owners=False); _full(bus)
    _rel_event(bus, "REL-1", "production", "deployed", {"ok": True, "verified_by": "orchestrator", "sha": SHA})
    rel = GateRequest(kind="release", subject_id="REL-1", created_by="delivery-lead", checklist=[], decision="approve")
    ev = collect_evidence(bus, "acceptance", "REL-1", tickets=["T1"], needs_security=False, waived=(), history=[rel])
    assert ev.kind == "acceptance" and ev.release_approved is True
    assert ev.production_deploy == {"ok": True, "verified_by": "orchestrator", "sha": SHA}
    assert ev.had_incident is False


def test_escalation_hay_quyet_dinh_khac_approve_la_su_co():
    bus = InMemoryBus(enforce_owners=False)
    for g in (GateRequest(kind="escalation", subject_id="REL-1", checklist=[], decision="approve"),
              GateRequest(kind="release", subject_id="REL-1", checklist=[], decision="reject"),
              GateRequest(kind="acceptance", subject_id="UAT-REL-1", checklist=[], decision="reject")):
        ev = collect_evidence(bus, "release", "REL-1", tickets=[], needs_security=False, waived=(), history=[g])
        assert ev.had_incident is True, g
    other = GateRequest(kind="escalation", subject_id="REL-2", checklist=[], decision="approve")
    pending = GateRequest(kind="release", subject_id="REL-1", checklist=[])
    ev = collect_evidence(bus, "release", "REL-1", tickets=[], needs_security=False, waived=(), history=[other, pending])
    assert ev.had_incident is False


def test_evidence_audit_hong_bi_bo_qua():
    bus = InMemoryBus(enforce_owners=False)
    _pub(bus, "audit-log", "orchestrator",
         AuditLog(actor="orchestrator", action="release.staged", evidence="{hỏng").model_dump())
    _audit(bus, "release.staged", {"release_id": "REL-1", "sha": 123})
    _pub(bus, "release-events", "REL-1", {"release_id": "REL-1", "version": "1.0.0", "env": "staging",
                                          "status": "deployed", "evidence": {}})  # deployed mà không có deploy
    _pub(bus, "audit-log", "orchestrator",
         AuditLog(actor="orchestrator", action="regression.run", evidence="[1]").model_dump())
    ev = collect_evidence(bus, "release", "REL-1", tickets=[], needs_security=False, waived=(), history=[])
    assert ev.staged_sha is None and ev.staging_deploy is None and ev.run is None


def test_staged_do_agent_ghi_khong_duoc_tin():
    bus = InMemoryBus(enforce_owners=False)
    _pub(bus, "audit-log", "ops", AuditLog(actor="ops", action="release.staged",
                                           evidence=json.dumps({"release_id": "REL-1", "sha": SHA})).model_dump(),
         actor="ops")
    ev = collect_evidence(bus, "release", "REL-1", tickets=[], needs_security=False, waived=(), history=[])
    assert ev.staged_sha is None


def test_review_khong_do_su_kien_cua_release_sinh_ra_bi_bo_qua():
    """sc-security 2026-09-23: QA duyệt PR có thể tự khai `ticket_id=REL-x` + `verdict=pass` (route PR không ghi
    đè identity). Verdict release chỉ tính khi review là PHẢN HỒI cho `release-events` (QA) / `release-candidates`
    (security) của chính release đó."""
    bus = InMemoryBus(enforce_owners=False)
    rc = _rc(bus, "REL-1")
    pr = _pub(bus, "pull-requests", "T1", {"ticket_id": "T1", "branch": "b", "pr_ref": "x", "local_checks": OK_LC})
    _review(bus, "REL-1", "qa", "pass", pr.event_id)
    _review(bus, "REL-1", "security", "pass", pr.event_id)
    _review(bus, "REL-1", "qa", "pass", rc.event_id)  # QA không chấm release trên release-candidates
    _review(bus, "REL-1", "security", "pass", None)
    ev = collect_evidence(bus, "release", "REL-1", tickets=[], needs_security=True, waived=(), history=[])
    assert ev.qa_verdict is None and ev.security_verdict is None


def test_evidence_run_do_model_khai_trong_review_khong_duoc_dung():
    """`run` chỉ lấy từ audit `regression.run` do orchestrator ghi, không từ `review-results.evidence.run`."""
    bus = InMemoryBus(enforce_owners=False)
    st = _rel_event(bus, "REL-1", "staging", "deployed", {})
    _review(bus, "REL-1", "qa", "pass", st.event_id, run=RUN)
    _pub(bus, "audit-log", "qa", AuditLog(actor="qa", action="regression.run",
                                          evidence=json.dumps({"release_id": "REL-1", **RUN})).model_dump(), actor="qa")
    ev = collect_evidence(bus, "release", "REL-1", tickets=[], needs_security=False, waived=(), history=[])
    assert ev.qa_verdict == "pass" and ev.run is None
