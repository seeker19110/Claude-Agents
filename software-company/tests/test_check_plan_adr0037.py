"""ADR-0037 PR-1: `_check_plan` phải chặn mọi khoá "Code gửi kèm" của gate plan cũ (kích thước ticket, risk_tags,
threat model, architecture/api-contract trên blackboard) TRƯỚC khi plan tới người duyệt — vì PR-2 bỏ hẳn gate
plan và các khoá này sẽ không còn ai kiểm nếu không nằm trong `_check_plan`
(`docs/DAC-TA-TRIEN-KHAI-ADR-0037.md` §2)."""
from __future__ import annotations

import company.orch.ticket_fsm as ticket_fsm
from company.bus import InMemoryBus
from company.events import Envelope, ReviewResult, Task
from company.llm import FakeClient
from company.orchestrator import Orchestrator


def _orch() -> Orchestrator:
    return Orchestrator(InMemoryBus(), FakeClient())


def _task(**kw) -> Task:
    base = dict(ticket_id="T1", project_id="P1", requirement_id="REQ-1", assignee="backend", title="x",
                acceptance=["given/when/then"], estimate_tokens=4_000, budget_tokens=6_000)
    base.update(kw)
    return Task(**base)


def _satisfy_threat_and_blackboard(o: Orchestrator, project: str = "P1") -> None:
    o.bus.publish(Envelope(topic="review-results", key=f"SPEC-{project}", actor="security",
                            payload=ReviewResult(ticket_id=f"SPEC-{project}", source="security", verdict="pass").model_dump()))
    o.blackboard.write("delivery-lead", "architecture", "docs/c4.md", "L1-L2", project_id=project)
    o.blackboard.write("delivery-lead", "api-contract", "openapi.yaml", "v1", project_id=project)


def _baseline_ok(o: Orchestrator, project: str = "P1") -> list[Task]:
    _satisfy_threat_and_blackboard(o, project)
    return [_task()]


# ---------- ticket quá 1 ngày / 200k token ----------

def test_ticket_qua_lon_bi_tu_choi():
    o = _orch()
    tickets = _baseline_ok(o)
    tickets[0] = _task(estimate_tokens=250_000, budget_tokens=400_000)
    problems = o._check_plan(tickets, "P1")
    assert any("quá 1 ngày/200k token" in p for p in problems)

    tickets[0] = _task(estimate_tokens=100_000, budget_tokens=200_000)
    problems = o._check_plan(tickets, "P1")
    assert not any("quá 1 ngày/200k token" in p for p in problems)


def test_ticket_qua_1_ngay_bi_tu_choi():
    o = _orch()
    tickets = _baseline_ok(o)
    tickets[0] = _task(estimate_days=1.5)
    problems = o._check_plan(tickets, "P1")
    assert any("quá 1 ngày/200k token" in p for p in problems)

    tickets[0] = _task(estimate_days=1)
    problems = o._check_plan(tickets, "P1")
    assert not any("quá 1 ngày/200k token" in p for p in problems)


def test_tat_kiem_token_thi_khong_con_problem(monkeypatch):
    """Chiều ngược: tắt trần token thì ticket vượt token (nhưng estimate_days bình thường) không còn bị chặn."""
    o = _orch()
    tickets = _baseline_ok(o)
    tickets[0] = _task(estimate_tokens=250_000, budget_tokens=400_000)
    monkeypatch.setattr(ticket_fsm, "MAX_TICKET_TOKENS", 10**9)
    problems = o._check_plan(tickets, "P1")
    assert not any("quá 1 ngày/200k token" in p for p in problems)


# ---------- risk_tags ----------

def test_risk_hint_khong_tag():
    o = _orch()
    tickets = _baseline_ok(o)
    tickets[0] = _task(title="Đăng nhập OAuth")
    problems = o._check_plan(tickets, "P1")
    assert any("không có risk_tags" in p for p in problems)

    tickets[0] = _task(title="Đăng nhập OAuth", risk_tags=["auth"])
    problems = o._check_plan(tickets, "P1")
    assert not any("không có risk_tags" in p for p in problems)


def test_tat_risk_hints_thi_khong_con_problem(monkeypatch):
    o = _orch()
    tickets = _baseline_ok(o)
    tickets[0] = _task(title="Đăng nhập OAuth")
    monkeypatch.setattr(ticket_fsm, "RISK_HINTS", frozenset())
    problems = o._check_plan(tickets, "P1")
    assert not any("không có risk_tags" in p for p in problems)


# ---------- threat model ----------

def test_thieu_threat_model():
    o = _orch()
    o.blackboard.write("delivery-lead", "architecture", "docs/c4.md", "L1-L2", project_id="P1")
    o.blackboard.write("delivery-lead", "api-contract", "openapi.yaml", "v1", project_id="P1")
    problems = o._check_plan([_task()], "P1")
    assert any("thiếu threat model" in p for p in problems)

    o.bus.publish(Envelope(topic="review-results", key="SPEC-P1", actor="security",
                            payload=ReviewResult(ticket_id="SPEC-P1", source="security", verdict="pass").model_dump()))
    problems = o._check_plan([_task()], "P1")
    assert not any("thiếu threat model" in p for p in problems)


def test_missing_threat_model_set_cung_chan():
    o = _orch()
    _satisfy_threat_and_blackboard(o)
    o.missing_threat_model.add("SPEC-P1")
    problems = o._check_plan([_task()], "P1")
    assert any("thiếu threat model" in p for p in problems)


# ---------- blackboard architecture / api-contract ----------

def test_thieu_architecture_tren_blackboard():
    o = _orch()
    o.bus.publish(Envelope(topic="review-results", key="SPEC-P1", actor="security",
                            payload=ReviewResult(ticket_id="SPEC-P1", source="security", verdict="pass").model_dump()))
    problems = o._check_plan([_task()], "P1")
    assert any("blackboard thiếu architecture" in p for p in problems)
    assert any("blackboard thiếu api-contract" in p for p in problems)

    o.blackboard.write("delivery-lead", "architecture", "docs/c4.md", "L1-L2", project_id="P1")
    o.blackboard.write("delivery-lead", "api-contract", "openapi.yaml", "v1", project_id="P1")
    problems = o._check_plan([_task()], "P1")
    assert not any("blackboard thiếu" in p for p in problems)


def test_baseline_du_dieu_kien_khong_co_problem():
    o = _orch()
    tickets = _baseline_ok(o)
    assert o._check_plan(tickets, "P1") == []
