"""`audit-log` là topic mở: `_rehydrate` dựng lại trạng thái từ nó sau restart, nên một dòng mang tên action đúng
nhưng do SAI người ghi là lệnh giả (sc-security 2026-09-23, lỗ để ngỏ ở ADR-0043). Hai lớp:

1. Route `change-requests → product → audit-log` publish payload của MODEL — model tự chọn `action`. Nội dung
   change request đến từ khách (injection được), nên model có thể viết `plan.proposed`/`ticket.blocked`/...
   Code ép `action="change.impact"` và `actor` payload = agent (như `source`/`ticket_id` của review).
2. `_rehydrate` chỉ áp một action khi `env.actor` (bus kiểm) là người ghi thật của action đó — không tin tên
   action, không tin `actor` tự khai trong payload."""
from __future__ import annotations

import json

import pytest

from company.bus import InMemoryBus
from company.events import AuditLog, Envelope
from company.llm import FakeClient
from company.orchestrator import Orchestrator
from company.roles import LEAD_ACTOR, ROLE
from company.sqlite_bus import SQLiteBus
from test_orchestrator import handler


def _forged(env_actor: str, action: str, ev: dict, payload_actor: str = "orchestrator") -> Envelope:
    return Envelope(topic="audit-log", key=env_actor, actor=env_actor,
                    payload=AuditLog(actor=payload_actor, action=action, ticket_id=ev.get("ticket_id"),
                                     evidence=json.dumps(ev)).model_dump())


FORGED = [
    ("orchestrated", {"event_id": "E-GIA", "topic": "tasks", "actions": []}),
    ("once", {"key": "uat:REL-9:x"}),
    ("plan.proposed", {"plan_id": "PLAN-GIA", "project_id": "P9", "tickets": []}),
    ("delivery.done", {"release_id": "REL-9", "sha": "0" * 40, "tag": "v9"}),
    ("ticket.blocked", {"ticket_id": "T9"}),
    ("ticket.already_integrated", {"ticket_id": "T9", "state": "closed"}),
    ("integration.merged", {"ticket_id": "T9", "release_id": "REL-9", "sha": "0" * 40}),
    ("threat_model.missing", {"subject_id": "SPEC-P9"}),
    ("project.stalled", {"project_id": "P9", "event_id": "E9"}),
    ("agent_error_unhandled", {"subject": "P9", "agent": "product", "topic": "research-requests", "event_id": "E9"}),
    ("integration.conflict", {"ticket_id": "T9", "release_id": "REL-9", "conflicts": []}),
    ("ticket.continued", {"ticket_id": "T9", "attempt": 1}),
    ("release.finding_waived", {"release_id": "REL-9", "source": "qa"}),
    ("debt.escalated", {"project_id": "P9", "debt_id": "D1"}),
    ("spec.runtime_missing", {"project_id": "P9", "event_id": "E9"}),
    ("plan.rework", {"project_id": "P9", "source_event": "E9", "attempt": 1}),
]


def _state(o: Orchestrator) -> dict:
    return {"processed": set(o.processed), "once": set(o.once), "plans": dict(o.plans), "delivered": dict(o.delivered),
            "lead.state": dict(o.lead.state), "missing_tm": set(o.missing_threat_model), "stalled": dict(o.stalled),
            "unhandled": dict(o.unhandled), "integrated": set(o.integrated), "conflicts": dict(o.conflict_retries),
            "continued": dict(o.turn_continuations),
            "waived": {k: set(v) for k, v in o.lead.release_waived.items() if v}, "debt": dict(o.debt_gate),
            "runtime": dict(o.spec_runtime_reworks), "plan_reworks": dict(o.plan_reworks)}


# (`plan.proposed`, product) KHÔNG nằm trong bảng: product là người ghi thật của nó (orchestrator ghi dưới tên
# product) — đường giả qua route product bị lớp 1 chặn (`test_route_change_request_ep_action_change_impact`).
_CASES = [(a, ev, actor) for a, ev in FORGED for actor in (ROLE.QA, ROLE.PRODUCT, ROLE.OPS)
          if (a, actor) not in {("plan.proposed", ROLE.PRODUCT), ("plan.rework", ROLE.PRODUCT)}]


@pytest.mark.parametrize(("action", "ev", "env_actor"), _CASES, ids=[f"{a}-{x}" for a, _, x in _CASES])
def test_rehydrate_khong_ap_action_do_sai_nguoi_ghi(tmp_path, action, ev, env_actor):
    db = tmp_path / "c.sqlite"
    SQLiteBus(db).close()
    sach = _state(Orchestrator(SQLiteBus(db), FakeClient(handler=handler)))
    bus = SQLiteBus(db); bus.publish(_forged(env_actor, action, ev)); bus.close()
    assert _state(Orchestrator(SQLiteBus(db), FakeClient(handler=handler))) == sach


def test_lead_van_duoc_tin_cho_action_cua_lead(tmp_path):
    """Chiều ngược: người ghi THẬT vẫn được áp — `ticket.blocked` do delivery-lead ghi."""
    db = tmp_path / "c.sqlite"
    bus = SQLiteBus(db); bus.publish(_forged(LEAD_ACTOR, "ticket.blocked", {"ticket_id": "T9"}, LEAD_ACTOR)); bus.close()
    assert Orchestrator(SQLiteBus(db), FakeClient(handler=handler)).lead.state.get("T9") == "blocked"


def test_route_change_request_ep_action_change_impact():
    from test_orchestrator import _pub

    def khai_gia(system, user):
        out = handler(system, user)
        if isinstance(out, dict) and out.get("action") == "change.impact":
            return {**out, "action": "plan.proposed", "actor": "orchestrator"}
        return out

    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=khai_gia))
    orch.blackboard.write("product", "architecture", "docs/c4.md", "L1-L2", project_id="P1")
    orch.blackboard.write("product", "api-contract", "openapi.yaml", "v1", project_id="P1")
    _pub(bus, "external-feedback", "P1", "human:customer", {"project_id": "P1", "from": "chị Lan", "text": "muốn xuất Excel"})
    orch.run()
    tu_product = [e for e in bus.replay(topic="audit-log") if e.actor == ROLE.PRODUCT
                  and e.payload["action"] in {"plan.proposed", "change.impact"}]
    assert tu_product and all(e.payload["action"] == "change.impact" and e.payload["actor"] == ROLE.PRODUCT
                              for e in tu_product), [(e.payload["action"], e.payload["actor"]) for e in tu_product]
    assert [e for e in bus.replay(topic="audit-log") if e.payload.get("action") == "output.action_overridden"]
