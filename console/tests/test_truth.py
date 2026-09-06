"""truth.py: sự thật giao hàng suy từ log — mỗi bậc phễu, quyết định chờ áp, bế tắc im lặng, bằng chứng bị cắt.

Dựng Envelope thật của software-company và dùng `HumanGate` thật; DeliveryLead thay bằng stub mang đúng các
trường `Truth` đọc (state, tickets, releases, release_tickets, release_reviews, release_waived) để đặt được từng
tình huống mà không phải diễn lại cả vòng đời.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from company.events import AuditLog, Envelope, ReviewResult, Task
from company.gates import GateRequest, HumanGate

from console.collect import COMPANY, collect
from console.truth import FUNNEL, Truth, gate_effect

NOW = datetime(2026, 9, 6, 4, 0, tzinfo=UTC)


def audit(actor: str, action: str, ev: dict | None = None, *, ts: datetime = NOW, **fields) -> Envelope:
    p = AuditLog(actor=actor, action=action, evidence=json.dumps(ev, ensure_ascii=False) if ev is not None else None, **fields)
    return Envelope(topic="audit-log", key=actor, actor=actor, ts=ts, payload=p.model_dump())


def rel_event(rid: str, env: str, status: str, *, ts: datetime = NOW, **extra) -> Envelope:
    return Envelope(topic="release-events", key=rid, actor="release-engineer", ts=ts,
                    payload={"release_id": rid, "version": "1.0.0", "env": env, "status": status, **extra})


def rc(rid: str, tickets: list[str], version: str = "1.0.0") -> Envelope:
    return Envelope(topic="release-candidates", key=rid, actor="delivery-lead", ts=NOW,
                    payload={"release_id": rid, "project_id": "P1", "tickets": tickets, "version": version})


def review(rid: str, source: str, verdict: str, *, ts: datetime = NOW) -> Envelope:
    r = ReviewResult(ticket_id=rid, source=source, verdict=verdict)
    return Envelope(topic="review-results", key=rid, actor="qa-debugger", ts=ts, payload=r.model_dump())


def lead_stub(**over):
    base = {"state": {}, "tickets": {}, "releases": [], "release_tickets": {}, "release_reviews": {}, "release_waived": {}}
    return SimpleNamespace(**{**base, **over})


def test_hieu_qua_duyet_theo_loai_gate() -> None:
    assert "GIAO HÀNG" in gate_effect("release", "REL-1")
    assert "KHÔNG deploy" in gate_effect("escalation", "REL-1")
    assert "mở lại ticket" in gate_effect("escalation", "T1")
    assert "giao ticket" in gate_effect("plan", "PLAN-1")
    assert "threat model" in gate_effect("spec", "SPEC-1")
    assert "nghiệm thu" in gate_effect("acceptance", "UAT-1")
    assert gate_effect("publish", "PUB-1") == ""


def test_pheu_release_moi_bac_mot_rc() -> None:
    """12 RC, mỗi RC một bậc; `delivery` đếm đúng và `next` nói đúng việc kế tiếp."""
    gate = HumanGate()
    tickets = {f"REL-{i:03d}": [f"T{i}"] for i in range(1, 13)}
    lead = lead_stub(releases=list(tickets), release_tickets=tickets,
                     release_reviews={"REL-007": {"qa": ReviewResult(ticket_id="REL-007", source="qa", verdict="fail")},
                                      "REL-008": {"qa": ReviewResult(ticket_id="REL-008", source="qa", verdict="pass")}})
    gate.request(GateRequest(kind="release", subject_id="REL-008", created_by="delivery-lead", checklist=["tests"]))
    for rid in ("REL-009", "REL-010", "REL-011", "REL-012"):
        gate.request(GateRequest(kind="release", subject_id=rid, created_by="delivery-lead", checklist=["tests"]))
        gate.decide(rid, "approve", by="human:lead")
    gate.request(GateRequest(kind="escalation", subject_id="REL-005", created_by="delivery-lead", checklist=["root_cause"]))
    envs = [rc(rid, t) for rid, t in tickets.items()] + [
        audit("orchestrator", "delivery.done", {"release_id": "REL-001", "tag": "v1.0.0", "sha": "abc1234", "detail": "pushed"}),
        rel_event("REL-001", "production", "deployed"),
        audit("orchestrator", "release.void", {"release_id": "REL-002", "ticket_id": "T2", "reason": "ticket đang dispatched"}),
        rel_event("REL-004", "staging", "failed"),
        rel_event("REL-005", "staging", "pending_human", summary="Dừng: gate_release=false"),
        rel_event("REL-006", "staging", "deployed"),
        rel_event("REL-007", "staging", "deployed"),
        rel_event("REL-008", "staging", "deployed"),
        rel_event("REL-009", "staging", "deployed"),
        rel_event("REL-010", "production", "failed"),
        rel_event("REL-011", "production", "pending_human", runbook_ref="infra/x.md"),
        rel_event("REL-012", "production", "deployed"),
        audit("orchestrator", "release.staged", {"release_id": "REL-006", "sha": "d16289b72405c43ecf3e08ef2a70b1ea1c0922e2", "branch": "company/integration"}),
    ]
    tr = Truth(envs, lead, gate, NOW)
    d = tr.delivery()
    stages = {r["id"]: r["stage"] for r in d["releases"]}
    assert stages == {"REL-001": "delivered", "REL-002": "void", "REL-003": "rc", "REL-004": "staging_failed",
                      "REL-005": "staging_pending_human", "REL-006": "staging_deployed", "REL-007": "qa_failed",
                      "REL-008": "gate3", "REL-009": "gate3_approved", "REL-010": "production_failed",
                      "REL-011": "production_pending_human", "REL-012": "production"}
    assert d["releases_total"] == 12 and d["releases_live"] == 11 and d["void"] == 1
    assert d["production"] == 2 and d["delivered"] == 1 and d["latest_tag"] == "v1.0.0" and d["latest_release"] == "REL-001"
    assert d["integration_sha"] == "d16289b" and d["integrated_tickets"] == 0
    assert [f["stage"] for f in d["funnel"]] == [k for k, _ in FUNNEL]
    assert sum(f["n"] for f in d["funnel"]) == 12 and dict((f["stage"], f["ids"]) for f in d["funnel"])["gate3"] == ["REL-008"]
    by_id = {r["id"]: r for r in d["releases"]}
    assert by_id["REL-006"]["sha"] == "d16289b" and by_id["REL-008"]["gate"] == "release" and by_id["REL-005"]["gate"] == "escalation"
    assert by_id["REL-011"]["runbook"] == "infra/x.md" and by_id["REL-005"]["summary"].startswith("Dừng")
    assert by_id["REL-001"]["next"] == "" and "trùng" in by_id["REL-002"]["next"]
    assert "release-engineer" in by_id["REL-003"]["next"] and "qa-debugger" in by_id["REL-006"]["next"]
    assert "Gate 3" in by_id["REL-008"]["next"] and "lượt production" in by_id["REL-009"]["next"]
    assert "nghiệm thu" in by_id["REL-012"]["next"]
    assert "escalation" in by_id["REL-005"]["next"], "RC có gate chờ thì nói chờ người quyết gate đó"
    assert "KHÔNG gate nào mở" in by_id["REL-011"]["next"], "agent tự dừng mà không gate: nói thẳng là không ai được hỏi"
    assert "QA chặn" in by_id["REL-007"]["next"] and "làm lại" in by_id["REL-004"]["next"] and "làm lại" in by_id["REL-010"]["next"]


def test_qa_bi_waive_thi_khong_con_la_qa_failed() -> None:
    gate = HumanGate()
    lead = lead_stub(releases=["REL-1"], release_tickets={"REL-1": ["T1"]},
                     release_reviews={"REL-1": {"qa": ReviewResult(ticket_id="REL-1", source="qa", verdict="fail")}},
                     release_waived={"REL-1": {"qa"}})
    tr = Truth([rc("REL-1", ["T1"]), rel_event("REL-1", "staging", "deployed")], lead, gate, NOW)
    assert tr.releases()[0]["stage"] == "staging_deployed"


def test_rollback_o_production_va_staging_la_that_bai() -> None:
    lead = lead_stub(releases=["REL-1", "REL-2"], release_tickets={"REL-1": ["T1"], "REL-2": ["T2"]})
    tr = Truth([rc("REL-1", ["T1"]), rel_event("REL-1", "production", "rolled_back"),
                rc("REL-2", ["T2"]), rel_event("REL-2", "staging", "rolled_back")], lead, HumanGate(), NOW)
    assert [r["stage"] for r in tr.releases()] == ["production_failed", "staging_failed"]


def test_quyet_dinh_da_ky_chua_ap_dung() -> None:
    """gate.decide nằm trong log mà chưa có `orchestrated` cho nó = người đã ký, máy chưa áp."""
    gate = HumanGate()
    gate.request(GateRequest(kind="release", subject_id="REL-1", created_by="delivery-lead", checklist=[]))
    applied = audit("human:lead", "gate.decide", {"subject_id": "PLAN-1", "decision": "approve", "by": "human:lead"},
                    ts=NOW - timedelta(minutes=30))
    waiting = audit("human:lead", "gate.decide", {"subject_id": "REL-1", "decision": "approve", "by": "human:lead",
                                                  "reason": "đủ điều kiện"}, ts=NOW - timedelta(minutes=12))
    envs = [applied, waiting,
            audit("orchestrator", "orchestrated", {"event_id": applied.event_id, "topic": "audit-log", "actions": []})]
    pend = Truth(envs, lead_stub(), gate, NOW).pending_decisions()
    assert pend == [{"id": "REL-1", "decision": "approve", "by": "human:lead", "kind": "release", "minutes": 12,
                     "reason": "đủ điều kiện"}]


def test_hang_doi_va_event_dau_hang() -> None:
    t0 = NOW - timedelta(minutes=9)
    task = Task(ticket_id="T1", project_id="P1", requirement_id="R1", assignee="backend", title="x", acceptance=["ok"],
                estimate_tokens=1, budget_tokens=2)
    e_task = Envelope(topic="tasks", key="T1", actor="delivery-lead", ts=t0, payload=task.model_dump())
    e_done = Envelope(topic="tasks", key="T0", actor="delivery-lead", ts=t0 - timedelta(minutes=1), payload={**task.model_dump(), "ticket_id": "T0"})
    ctx = Envelope(topic="shared-context", key="P1/prd", actor="spec-writer", ts=NOW,
                   payload={"namespace": "prd", "version": 1, "content_ref": "x", "summary": "y", "project_id": "P1"})
    envs = [e_done, e_task, ctx, audit("orchestrator", "orchestrated", {"event_id": e_done.event_id, "topic": "tasks", "actions": []},
                                        ts=NOW - timedelta(minutes=3))]
    run = Truth(envs, lead_stub(), HumanGate(), NOW).running()
    assert run == {"queue": 1, "head": {"topic": "tasks", "key": "T1", "minutes": 9}, "last_event_minutes": 3, "topics": ["tasks"]}
    assert Truth([], lead_stub(), HumanGate(), NOW).running() == {"queue": 0, "head": None, "last_event_minutes": None, "topics": []}


def test_be_tac_im_lang() -> None:
    """Ticket kẹt không gate, RC agent tự dừng không gate, và hàng đợi rỗng trong khi việc chưa xong."""
    gate = HumanGate()
    gate.request(GateRequest(kind="escalation", subject_id="T3", created_by="supervisor", checklist=[]))
    lead = lead_stub(state={"T1": "merged", "T2": "blocked", "T3": "escalated", "T4": "in_review"},
                     releases=["REL-1", "REL-2"], release_tickets={"REL-1": ["T1"], "REL-2": ["T2"]})
    envs = [rc("REL-1", ["T1"]), rel_event("REL-1", "production", "pending_human"),
            rc("REL-2", ["T2"]), rel_event("REL-2", "staging", "deployed"),
            audit("orchestrator", "integration.merged", {"ticket_id": "T2", "sha": "b1b3e4b7", "branch": "company/integration"})]
    processed = [audit("orchestrator", "orchestrated", {"event_id": e.event_id, "topic": e.topic, "actions": []}) for e in envs]
    dl = Truth(envs + processed, lead, gate, NOW).deadlocks()
    kinds = [(d["kind"], d["id"]) for d in dl]
    assert kinds == [("ticket", "T2"), ("release", "REL-1")], "T3 escalated NHƯNG có gate chờ → không phải bế tắc; còn gate chờ → không idle"
    assert dl[0]["integrated"] is True, "kẹt sổ sách: code đã ở integration — phải phân biệt với chưa làm"
    assert "không ai được hỏi" in dl[0]["why"] and "KHÔNG gate nào mở" in dl[1]["why"]
    # Không gate nào, hàng đợi rỗng, việc chưa xong → idle: không có gì tự chạy tiếp
    idle = Truth(envs + processed, lead_stub(state={"T4": "in_review", "T5": "dispatched"}, releases=["REL-2"],
                                             release_tickets={"REL-2": ["T4"]}), HumanGate(), NOW).deadlocks()
    assert [d["kind"] for d in idle] == ["idle"]
    assert "2 ticket chưa xong" in idle[0]["why"] and "1 release chưa giao" in idle[0]["why"]
    # Có gate chờ thì không idle; ticket/RC bình thường không phải bế tắc
    gate2 = HumanGate(); gate2.request(GateRequest(kind="release", subject_id="REL-2", created_by="delivery-lead", checklist=[]))
    lead2 = lead_stub(state={"T4": "in_review"}, releases=["REL-2"], release_tickets={"REL-2": ["T4"]})
    assert Truth([rc("REL-2", ["T4"]), rel_event("REL-2", "staging", "deployed")], lead2, gate2, NOW).deadlocks() == []


def test_ticket_extra_va_review_trimmed() -> None:
    gate = HumanGate()
    gate.request(GateRequest(kind="escalation", subject_id="T1", created_by="supervisor", checklist=[]))
    task = Task(ticket_id="T1", project_id="P1", requirement_id="R1", assignee="backend", title="x", acceptance=["ok"],
                estimate_tokens=1, budget_tokens=2, hint="máy", human_hint="người: sửa authz")
    lead = lead_stub(tickets={"T1": task}, state={"T1": "escalated"})
    rv = review("T1", "security", "block", ts=NOW)
    prod = audit("security-engineer", "produced:review-results", {"event": rv.event_id, "duration_ms": 60_000}, ts=NOW)
    cut = audit("security-engineer", "context_trimmed", {"max_input_chars": 70000, "trimmed_payload": 804,
                                                          "trimmed_context": {"api-contract": 13170}}, ts=NOW - timedelta(seconds=40))
    too_old = audit("security-engineer", "context_trimmed", {"trimmed_context": {"prd": 1}}, ts=NOW - timedelta(minutes=10))
    other = audit("reviewer", "context_trimmed", {"trimmed_context": {"prd": 1}}, ts=NOW - timedelta(seconds=10))
    empty = audit("security-engineer", "context_trimmed", {"trimmed_payload": 0, "trimmed_context": {}}, ts=NOW - timedelta(seconds=50))
    tr = Truth([rv, prod, too_old, other, cut, audit("orchestrator", "integration.merged", {"ticket_id": "T1", "sha": "abcdef012"})],
               lead, gate, NOW)
    assert tr.ticket_extra("T1") == {"integrated": True, "sha": "abcdef0", "human_hint": "người: sửa authz", "hint": "máy",
                                     "gate": "escalation"}
    assert tr.ticket_extra("T9") == {"integrated": False, "sha": None, "human_hint": "", "hint": "", "gate": None}
    assert tr.review_trimmed(rv) == "cắt api-contract 13.170 ký tự, payload 804 ký tự"
    assert Truth([rv], lead, gate, NOW).review_trimmed(rv) == "", "không có audit produced → không biết → không nói"
    assert Truth([rv, prod, empty], lead, gate, NOW).review_trimmed(rv) == "", "bản ghi cắt rỗng → không có gì để phơi"


def test_evidence_hong_khong_nem() -> None:
    bad = Envelope(topic="audit-log", key="x", actor="orchestrator", ts=NOW,
                   payload=AuditLog(actor="orchestrator", action="orchestrated", evidence="{không phải json").model_dump())
    lst = Envelope(topic="audit-log", key="x", actor="orchestrator", ts=NOW,
                   payload=AuditLog(actor="orchestrator", action="delivery.done", evidence="[1,2]").model_dump())
    tr = Truth([bad, lst], lead_stub(), HumanGate(), NOW)
    assert tr.processed == set() and tr.delivered == {}


def test_collect_mang_khoi_su_that_va_hieu_qua_gate(company_db: Path, studio_db: Path, tmp_path: Path) -> None:
    s = collect(company_db, studio_db, gateway_url="http://127.0.0.1:9")
    assert s["delivery"]["releases_total"] == 0 and s["delivery"]["production"] == 0
    # conftest ký SPEC-1 nhưng không có `orchestrated` cho quyết định đó → đúng là "người đã ký, máy chưa áp"
    assert [(d["id"], d["kind"]) for d in s["pending_decisions"]] == [("SPEC-1", "spec")] and s["running"]["queue"] >= 1
    assert isinstance(s["deadlocks"], list)
    plan = next(g for g in s["gates"] if g["id"] == "PLAN-1")
    assert "giao ticket" in plan["effect"]
    pub = next(g for g in s["gates"] if g["id"] == "PUB-vid-042")
    assert pub["effect"] == ""
    t = s["tickets"][0]
    assert t["integrated"] is False and t["human_hint"] == "" and t["gate"] is None
    assert s["reviews"][0]["trim"] == "" and len(s["reviews"][0]["at"]) == 5
    dead = collect(tmp_path / "khong-co.sqlite", studio_db, gateway_url="http://127.0.0.1:9")
    assert dead["delivery"] is None and dead["running"] is None and dead["pending_decisions"] == [] and dead["deadlocks"] == []
    assert COMPANY in dead["sources"]
