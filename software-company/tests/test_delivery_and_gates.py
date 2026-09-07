from datetime import UTC

import pytest

from company.bus import InMemoryBus
from company.delivery import DeliveryLead
from company.events import Envelope, PullRequest, ReviewResult, Task
from company.gates import GateRequest, HumanGate


def _setup():
    bus = InMemoryBus(); gate = HumanGate(); lead = DeliveryLead(bus, gate)
    return bus, gate, lead

def _task(**kw): return Task(ticket_id="T1", project_id="P", requirement_id="R1", assignee="backend", title="x", acceptance=["a"], **kw)
def _pr(bus): bus.publish(Envelope(topic="pull-requests", key="T1", actor="backend", payload=PullRequest(ticket_id="T1", branch="b", pr_ref="#1", local_checks={"lint": True}).model_dump()))
def _rev(bus, src, verdict, rc=None): bus.publish(Envelope(topic="review-results", key="T1", actor=src, payload=ReviewResult(ticket_id="T1", source=src, verdict=verdict, root_cause=rc).model_dump()))

def test_dispatch_tu_choi_plan_chua_check():
    """ADR-0037: gate `plan` biến mất nhưng guard KHÔNG biến mất — chỉ đổi nguồn sự thật. Plan chưa qua
    `_check_plan` (không có trong `plans_ok`) thì `dispatch` vẫn `PermissionError`."""
    _, _, lead = _setup()
    with pytest.raises(PermissionError, match="plan chưa qua _check_plan"):
        lead.dispatch(_task(), "PLAN")
    lead.plans_ok.add("PLAN")
    assert lead.dispatch(_task(), "PLAN").ticket_id == "T1", "vào plans_ok rồi thì giao được"

def test_four_eyes():
    _, gate, _ = _setup()
    gate.request(GateRequest(kind="spec", subject_id="SPEC-P", checklist=[], created_by="spec-writer"))
    with pytest.raises(PermissionError):
        gate.decide("SPEC-P", "approve", by="spec-writer")

def test_happy_path_to_release_gate():
    bus, gate, lead = _setup(); lead.plans_ok.add("PLAN")
    lead.dispatch(_task(), "PLAN"); _pr(bus); _rev(bus, "reviewer", "pass"); _rev(bus, "qa", "pass")
    assert lead.state["T1"] == "approved" and lead.releases == ["REL-001"]
    assert "REL-001" not in gate.pending, "gate 3 chỉ xin sau khi QA staging pass (ADR-0006)"

def test_fail_retries_with_hint_then_blocks():
    bus, _gate, lead = _setup(); lead.plans_ok.add("PLAN")
    lead.dispatch(_task(), "PLAN")
    for i in range(2):
        _pr(bus); _rev(bus, "reviewer", "fail", rc=f"bug{i}")
    assert lead.state["T1"] == "dispatched" and lead.tickets["T1"].retry == 2 and lead.tickets["T1"].hint == "bug1"
    _pr(bus); _rev(bus, "reviewer", "fail", rc="bug2")
    assert lead.state["T1"] == "blocked"

def test_security_review_required_when_risk_tags():
    """ADR-0003: reviewer + qa pass chưa đủ nếu ticket có risk_tags; cần thêm security."""
    bus, _gate, lead = _setup(); lead.plans_ok.add("PLAN")
    lead.dispatch(_task(risk_tags=["payment"]), "PLAN"); _pr(bus)
    _rev(bus, "reviewer", "pass"); _rev(bus, "qa", "pass")
    assert lead.state["T1"] == "in_review" and lead.releases == []
    _rev(bus, "security", "pass")
    assert lead.state["T1"] == "approved" and lead.releases == ["REL-001"]

def test_security_block_requests_changes_with_hint():
    bus, _gate, lead = _setup(); lead.plans_ok.add("PLAN")
    lead.dispatch(_task(risk_tags=["auth"]), "PLAN"); _pr(bus)
    _rev(bus, "reviewer", "pass"); _rev(bus, "qa", "pass")
    bus.publish(Envelope(topic="review-results", key="T1", actor="security", payload=ReviewResult(
        ticket_id="T1", source="security", verdict="block",
        findings=[{"level": "block", "text": "JWT không kiểm tra exp", "location": "auth.py:42"}]).model_dump()))
    assert lead.state["T1"] == "dispatched" and lead.tickets["T1"].retry == 1
    assert "JWT" in lead.tickets["T1"].hint

def test_security_not_required_without_risk_tags():
    _, _, lead = _setup()
    lead.tickets["T1"] = _task()
    assert lead.required_reviews("T1") == {"reviewer"}, "ADR-0021: ticket thường chỉ reviewer ở lượt PR"
    lead.tickets["T1"] = _task(risk_tags=["pii"])
    assert lead.required_reviews("T1") == {"reviewer", "qa", "security"}

def test_budget_must_cover_estimate_times_factor():
    """skill cost-estimation: budget_tokens ≥ estimate_tokens × 1.5."""
    _, _g, lead = _setup(); lead.plans_ok.add("PLAN")
    with pytest.raises(ValueError):
        lead.dispatch(_task(estimate_tokens=100_000, budget_tokens=120_000), "PLAN")
    lead.dispatch(_task(estimate_tokens=80_000, budget_tokens=120_000), "PLAN")
    assert lead.state["T1"] == "dispatched"

def test_human_hint_bao_loi_khi_trang_thai_khong_can_thiep_duoc():
    _, _g, lead = _setup(); lead.plans_ok.add("PLAN")
    lead.dispatch(_task(), "PLAN")
    nt = lead.human_hint("T1", "gợi ý")   # dispatched: hợp lệ, phát lại task ngay nên state về "dispatched"
    assert lead.state["T1"] == "dispatched" and nt.hint == "gợi ý"
    with pytest.raises(ValueError, match="không can thiệp được"):
        lead.human_hint("T2-khong-ton-tai", "x")

def test_rework_bao_loi_ngoai_dispatched_hoac_in_progress():
    bus, _gate, lead = _setup(); lead.plans_ok.add("PLAN")
    lead.dispatch(_task(), "PLAN"); _pr(bus)
    with pytest.raises(ValueError, match="rework chỉ từ dispatched/in_progress"):
        lead.rework("T1", "test fail")   # đã ở in_review, không phải dispatched/in_progress

def test_reopen_bao_loi_ngoai_blocked_hoac_escalated():
    _, _g, lead = _setup(); lead.plans_ok.add("PLAN")
    lead.dispatch(_task(), "PLAN")
    with pytest.raises(ValueError, match="chỉ mở lại ticket blocked/escalated"):
        lead.reopen("T1", "x")   # đang dispatched, chưa blocked

def test_reopen_mo_lai_ticket_blocked_va_dem_lai_retry():
    bus, _gate, lead = _setup(); lead.plans_ok.add("PLAN")
    lead.dispatch(_task(), "PLAN")
    for i in range(3):
        _pr(bus); _rev(bus, "reviewer", "fail", rc=f"bug{i}")
    assert lead.state["T1"] == "blocked"
    nt = lead.reopen("T1", "đã sửa hạ tầng")
    assert lead.state["T1"] == "dispatched" and nt.retry == 0 and nt.hint == "đã sửa hạ tầng"

def test_replay_nuot_loi_nghiep_vu_khong_lam_sap_viec_dung_lai_log():
    """`replay` dựng lại trạng thái từ log: một sự kiện log cũ gây lỗi nghiệp vụ (ValueError/PermissionError/KeyError,
    ở đây là `_on_review` KeyError vì review đến trước khi ticket từng dispatch) không được ném ra ngoài."""
    _, _, lead = _setup()
    # PR cho ticket chưa từng dispatch (không ở draft→in_review hợp lệ): `_on_pr`→`_set` ném ValueError chuyển
    # trạng thái sai — trên đường chạy thật đó là lỗi thật, nhưng khi khôi phục từ log thì event đã xảy ra rồi.
    ev = Envelope(topic="pull-requests", key="T-chua-tung-dispatch", actor="backend",
                 payload=PullRequest(ticket_id="T-chua-tung-dispatch", branch="b", pr_ref="#1",
                                     local_checks={"lint": True}).model_dump())
    lead.replay(ev)   # không được ném lỗi ra ngoài
    assert lead.replaying is False
    assert "T-chua-tung-dispatch" not in lead.tickets


def test_on_release_candidate_bo_qua_version_hong_khong_sap():
    """Log cũ có `version` không phải `X.Y.Z` hợp lệ (vd. rỗng hoặc chữ) thì bỏ qua, không ném lỗi lên trên."""
    bus, _gate, lead = _setup(); lead.plans_ok.add("PLAN")
    lead.dispatch(_task(), "PLAN"); _pr(bus); _rev(bus, "reviewer", "pass"); _rev(bus, "qa", "pass")
    assert lead.versions.get("P") is None or isinstance(lead.versions.get("P"), tuple)
    bus.publish(Envelope(topic="release-candidates", key="REL-002", actor="delivery-lead",
                         payload={"release_id": "REL-002", "project_id": "P", "tickets": ["T1"], "version": "khong-phai-so"}))
    assert "REL-002" not in lead.versions
    assert lead.release_tickets["REL-002"] == ["T1"]


def test_gate_timeouts():
    from datetime import datetime, timedelta
    gate = HumanGate(); gate.request(GateRequest(kind="spec", subject_id="S", checklist=[]))
    now = datetime.now(UTC)
    assert gate.due(now + timedelta(hours=13)) == (["S"], [])
    assert gate.due(now + timedelta(hours=25)) == ([], ["S"])
