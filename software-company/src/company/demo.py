"""Chạy thử vòng đời đầy đủ bằng logic xác định (không gọi LLM).

TCK-1: ticket thường → reviewer + qa pass là đủ.
TCK-2: ticket có risk_tags → phải chờ thêm `security` (ADR-0003); phụ thuộc TCK-1 nên chờ ở `waiting` (ADR-0006).
Release: candidate → staging → QA hồi quy → gate release → production → khách nghiệm thu → closed.
"""
from __future__ import annotations

import sys
from typing import Any

from .blackboard import Blackboard
from .bus import InMemoryBus
from .delivery import DeliveryLead
from .events import AcceptanceResult, AuditLog, Envelope, PullRequest, ReviewResult, Task
from .gates import GateRequest, HumanGate
from .roles import ROLE, SOURCE
from .supervisor import Supervisor


def _pr(bus: InMemoryBus, tid: str, actor: str) -> None:
    bus.publish(Envelope(topic="pull-requests", key=tid, actor=actor, payload=PullRequest(
        ticket_id=tid, branch=f"ticket/{tid}", pr_ref="#1",
        local_checks={"lint": True, "tests": True, "coverage": 0.86}).model_dump()))


def _review(bus: InMemoryBus, tid: Any, source: Any, actor: str, **kw) -> None:
    bus.publish(Envelope(topic="review-results", key=tid, actor=actor,
                         payload=ReviewResult(ticket_id=tid, source=source, verdict="pass", **kw).model_dump()))


def _release_event(bus: InMemoryBus, rid: str, env: str, status: str) -> None:
    bus.publish(Envelope(topic="release-events", key=rid, actor=ROLE.OPS,
                         payload={"release_id": rid, "version": "1.0.0", "env": env, "status": status}))


def run() -> None:
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")  # Windows console cp1252
    bus = InMemoryBus(); bb = Blackboard(bus); gate = HumanGate(); sup = Supervisor(bus)
    lead = DeliveryLead(bus, gate)
    bb.write(ROLE.LEAD, "architecture", "docs/c4.md", "C4 L1-L2")
    bb.write(ROLE.LEAD, "api-contract", "openapi.yaml", "v1")
    bb.write(ROLE.SECURITY, "threat-model", "docs/threat-model.md", "v1: T-01..T-06")
    bb.write(ROLE.OPS, "contract", "docs/sow.md", "SOW + kịch bản UAT map Must")
    # ADR-0037: người ký gate SPEC; kế hoạch không còn gate — `_check_plan` của orchestrator cho phép giao ticket
    # bằng cách ghi plan_id vào `lead.plans_ok` (ở đây gọi tay vì demo không chạy orchestrator).
    gate.request(GateRequest(kind="spec", subject_id="SPEC-P1", checklist=["prd", "acceptance-criteria", "ux-flow", "risks"],
                             created_by=ROLE.PRODUCT))
    gate.decide("SPEC-P1", "approve", by="human:pm")
    lead.plans_ok.add("PLAN-1")

    t1 = Task(ticket_id="TCK-1", project_id="P1", requirement_id="REQ-1", assignee=ROLE.BACKEND,
              title="GET /orders/{id}", acceptance=["Given ... When ... Then ..."],
              estimate_tokens=6_000, budget_tokens=10_000)
    t2 = Task(ticket_id="TCK-2", project_id="P1", requirement_id="REQ-2", assignee=ROLE.BACKEND,
              title="POST /payments", acceptance=["Given ... When ... Then ..."], depends_on=["TCK-1"], priority=1,
              estimate_tokens=20_000, budget_tokens=30_000, risk_tags=["payment", "pii"])
    lead.dispatch(t1, "PLAN-1"); lead.dispatch(t2, "PLAN-1")
    print("sau dispatch:", lead.state["TCK-1"], "/", lead.state["TCK-2"], "| waiting:", lead.waiting())

    bus.publish(Envelope(topic="audit-log", key=ROLE.BACKEND, actor=ROLE.BACKEND,
                         payload=AuditLog(actor=ROLE.BACKEND, action="code", ticket_id="TCK-1", tokens=8_500).model_dump()))
    _pr(bus, "TCK-1", ROLE.BACKEND)
    _review(bus, "TCK-1", SOURCE.REVIEWER, ROLE.REVIEWER)
    _review(bus, "TCK-1", SOURCE.QA, ROLE.QA, metrics={"mutation": 0.74})
    print("TCK-1 approved → TCK-2 tự dispatch:", lead.state["TCK-1"], "/", lead.state["TCK-2"])

    _pr(bus, "TCK-2", ROLE.BACKEND)
    _review(bus, "TCK-2", SOURCE.REVIEWER, ROLE.REVIEWER)
    _review(bus, "TCK-2", SOURCE.QA, ROLE.QA)
    state_before_security = lead.state["TCK-2"]
    _review(bus, "TCK-2", SOURCE.SECURITY, ROLE.SECURITY, metrics={"dast_high": 0, "license_violations": 0})
    print("TCK-2:", state_before_security, "->", lead.state["TCK-2"], "| required:", sorted(lead.required_reviews("TCK-2")))

    rid = lead.releases[0]
    _release_event(bus, rid, "staging", "deployed")
    _review(bus, rid, SOURCE.QA, ROLE.QA, metrics={"p95_ms": 212, "axe_critical": 0})
    print(f"{rid}: staging deployed, QA pass → gate release pending:", rid in gate.pending, "| TCK-1:", lead.state["TCK-1"])
    gate.decide(rid, "approve", by="human:release-manager")
    _release_event(bus, rid, "production", "deployed")
    bus.publish(Envelope(topic="acceptance-results", key=rid, actor=ROLE.OPS, payload=AcceptanceResult(
        release_id=rid, project_id="P1", verdict="accepted", signed_by="customer:po").model_dump()))
    print(f"{rid}: production + khách nghiệm thu → TCK-1:", lead.state["TCK-1"])

    print("releases:", lead.releases, "| gate pending:", list(gate.pending))
    print("supervisor actions:", [(a.target, a.action) for a in sup.actions])
    print("sprint report:", sup.sprint_report()["tickets"]["TCK-1"])
    print("events:", len(bus))


if __name__ == "__main__":
    run()
