"""ADR-0037 PR-2: bỏ hẳn human gate `plan` (`docs/DAC-TA-TRIEN-KHAI-ADR-0037.md` §3).

Kế hoạch không còn chờ ai ký: `_check_plan` (PR-1) đã mang mọi khoá "Code gửi kèm" của gate cũ thành `problems`,
nên plan sạch được `_dispatch_plan` giao NGAY trong cùng lượt, plan có `problems` thì `plan_rejected` + gate
`escalation` như cũ. Guard không biến mất mà đổi nguồn sự thật: `DeliveryLead.dispatch` hỏi `lead.plans_ok`
(orchestrator ghi vào ngay sau `_check_plan`) thay vì hỏi `gate.is_approved`.

Ba điều file này canh, mỗi điều là một chiều đo được:
1. plan sạch → `dispatch:` ngay, và KHÔNG có `PLAN-*` nào trong `gate.pending`;
2. plan bẩn → không ticket nào tồn tại, có gate `escalation` cấp dự án;
3. mở lại bus dựng trạng thái từ `plan.proposed`, không cần một `gate.decide` nào.
"""
from __future__ import annotations

import json
from typing import get_args

import pytest

from company import gate_checklists as GC
from company.bus import InMemoryBus
from company.delivery import DeliveryLead
from company.events import Envelope, Task
from company.gates import GateKind, HumanGate
from company.llm import FakeClient
from company.orchestrator import Orchestrator
from company.registry import ROOT
from company.sqlite_bus import SQLiteBus
from test_orchestrator import _agent_of, _drive_to_plan, _inp, _pub, handler


def _acts(bus) -> list[str]:
    return [e.payload["action"] for e in bus.replay(topic="audit-log")]


def _ev(env: Envelope) -> dict:
    return json.loads(env.payload["evidence"])


# ---------- 1. plan sạch: giao ngay, không gate ----------

def test_plan_sach_thi_dispatch_ngay_khong_mo_gate_plan():
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler))
    _drive_to_plan(bus, orch)
    assert "PLAN-P1-1" in orch.plans and not orch.plans["PLAN-P1-1"]["problems"]
    assert not [sid for sid in orch.gate.pending if sid.startswith("PLAN-")], "ADR-0037: không mở gate plan nữa"
    assert not [g for g in orch.gate.history if g.subject_id.startswith("PLAN-")], \
        "kể cả trong lịch sử cũng không có gate plan nào"
    assert "PLAN-P1-1" in orch.lead.plans_ok, "`_check_plan` sạch = nguồn sự thật cho phép giao"
    assert set(orch.lead.tickets) == {"T1", "T2"} and orch.lead.state["T1"] != "waiting"
    assert bus.latest("tasks", "T1") is not None, "ticket đã lên bus trong chính lượt lập kế hoạch"


def test_action_dispatch_nam_ngay_sau_plan_trong_cung_mot_step():
    """`res.actions` là thứ người trực đọc trong `orchestrator run`: `plan:` và `dispatch:` phải cùng một dòng
    kết quả, không phải hai lượt cách nhau bởi một chữ ký."""
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler))
    _pub(bus, "research-requests", "P1", "human:sales", {"project_id": "P1", "description": "app đặt lịch"})
    orch.run()
    _pub(bus, "clarification-answers", "P1", "human:po", {"project_id": "P1", "answers": [{"question_id": "Q1", "answer": "a"}]})
    orch.run()
    orch.gate.decide("SPEC-P1", "approve", by="human:po")
    steps = orch.run()
    acts = [a for s in steps for a in s.actions]
    i = next(i for i, a in enumerate(acts) if a.startswith("plan:PLAN-P1-1:"))
    assert acts[i + 1].startswith("dispatch:") and "T1" in acts[i + 1], acts


# ---------- 2. plan bẩn: không giao gì, escalation như cũ ----------

def _lead_thieu_acceptance(system, user):
    """delivery-lead trả ticket thiếu `acceptance` → `_check_plan` ra `problems`."""
    if _agent_of(system) == "delivery-lead" and "decision" not in _inp(user):
        return {"items": [{"ticket_id": "TX", "project_id": "P1", "requirement_id": "REQ-1", "assignee": "builder",
                           "title": "x", "acceptance": [], "estimate_tokens": 4_000, "budget_tokens": 6_000}],
                "context_writes": [{"namespace": "architecture", "content_ref": "docs/c4.md", "summary": "L1-L2"},
                                   {"namespace": "api-contract", "content_ref": "openapi.yaml", "summary": "v1"}]}
    return handler(system, user)


def test_plan_khong_qua_check_thi_khong_dispatch():
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=_lead_thieu_acceptance))
    _pub(bus, "research-requests", "P1", "human:sales", {"project_id": "P1", "description": "app đặt lịch"})
    orch.run()
    _pub(bus, "clarification-answers", "P1", "human:po", {"project_id": "P1", "answers": [{"question_id": "Q1", "answer": "a"}]})
    orch.run(); orch.gate.decide("SPEC-P1", "approve", by="human:po"); orch.run()
    assert "plan_rejected" in _acts(bus) and not orch.plans, "có problem thì không có plan.proposed"
    assert not orch.lead.tickets and not list(bus.replay(topic="tasks")), "không ticket nào được giao"
    assert not orch.lead.plans_ok, "không plan nào được phép giao"
    assert orch.gate.pending["P1"].kind == "escalation", "hành vi cũ giữ nguyên: người được hỏi"


# ---------- 3. guard bằng code, chỉ đổi nguồn sự thật ----------

def test_dispatch_tu_choi_plan_chua_qua_check_plan():
    """Đo hai chiều ngay trong một ca: `plans_ok` rỗng → `PermissionError`; ghi plan_id vào → giao được.
    Gate `plan` đã duyệt (thứ trước đây mở khoá) KHÔNG còn tác dụng gì ở đây."""
    bus = InMemoryBus(); gate = HumanGate(); lead = DeliveryLead(bus, gate)
    task = Task(ticket_id="T1", project_id="P", requirement_id="R1", assignee="builder", title="x",
                acceptance=["a"], estimate_tokens=4_000, budget_tokens=6_000)
    with pytest.raises(PermissionError, match="plan chưa qua _check_plan"):
        lead.dispatch(task, "PLAN-X")
    assert not list(bus.replay(topic="tasks"))
    lead.plans_ok.add("PLAN-X")
    assert lead.dispatch(task, "PLAN-X").ticket_id == "T1"
    assert lead.state["T1"] == "dispatched"


# ---------- 4. mở lại bus: dựng lại từ `plan.proposed`, không cần `gate.decide` ----------

def test_mo_lai_bus_dung_lai_plan_va_dispatch_khong_can_gate_decide(tmp_path):
    db = tmp_path / "c.sqlite"
    bus = SQLiteBus(db); orch = Orchestrator(bus, FakeClient(handler=handler))
    _drive_to_plan(bus, orch)
    trang_thai, ve = dict(orch.lead.state), dict(orch.lead.tickets)
    quyet = [e for e in bus.replay(topic="audit-log") if e.payload["action"] == "gate.decide"]
    assert [_ev(e)["subject_id"] for e in quyet] == ["SPEC-P1"], "chỉ gate spec được ký trên đường này"
    bus.close()

    bus2 = SQLiteBus(db); o2 = Orchestrator(bus2, FakeClient(handler=handler))
    assert "PLAN-P1-1" in o2.plans and "PLAN-P1-1" in o2.lead.plans_ok
    assert o2.lead.state == trang_thai and o2.lead.tickets.keys() == ve.keys()
    bus2.close()



# ---------- 5. `plan` biến mất khỏi mọi bản dẫn xuất ----------

def test_gatekind_va_ban_dan_xuat_khong_con_plan():
    assert set(get_args(GateKind)) == {"spec", "release", "escalation", "acceptance"}
    assert set(GC.parse()) == set(get_args(GateKind))
    assert "plan" not in GC.SELF_CHECK_SOURCES and "plan" not in GC.EXPERTS
    assert not (ROOT.parent / ".claude" / "agents" / "sc-gate-plan.md").exists()
    # hai mục người-tự-kiểm của gate plan cũ không mất: chúng nằm ở gate release, giữ nguyên `id`
    ids = {it.id for it in GC.parse()["release"].self_checks}
    assert {"plan.uoc-luong-co-so", "plan.ngan-sach-token"} <= ids
    assert {"threat-model", "architecture"} <= {c.key for c in GC.parse()["release"].code}
