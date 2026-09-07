"""Máy trạng thái TICKET: gate spec → threat model → delivery-lead sinh ticket → gate plan → dispatch; event
cũ bị vượt (superseded); ticket vào trạng thái cuối (ADR-0034, tách khỏi orchestrator.py).

Mỗi hàm nhận `o: Orchestrator` làm tham số đầu, gán làm method trên `Orchestrator`
(`_plan = ticket_fsm._plan`, …) — bề mặt gọi cũ không đổi. Nguồn sự thật trạng thái ticket vẫn là
`lead.state` (delivery.py); các hàm ở đây chỉ ĐỌC/ĐỔI trạng thái đó qua `DeliveryLead`, không nhân đôi.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..events import BUDGET_FACTOR, Envelope, Task
from ..gates import GateRequest
from ..llm import LLMError, TransientError
from ..runner import RunnerError
from .fsm import Transition
from .routes import PLAN_INPUTS, SPEC_RUNTIME_REWORKS, Route, _with_draft, spec_runtime_gap

if TYPE_CHECKING:
    from ..orchestrator import Orchestrator, StepResult


def _superseded(o, env: Envelope, res: StepResult) -> bool:
    """Event `tasks`/`pull-requests` còn trong hàng đợi (hoãn vì paused/transient, hoặc mở lại bus) mà ticket đã
    đi tiếp thì là hàng cũ: bỏ, audit `<topic>.superseded`, không giao agent.

    - `tasks` chỉ còn giá trị khi ticket vẫn `dispatched` — trạng thái mà chính event đó đặt. Người tiếp quản
      publish PR (ADR-0012 → `in_review`) hay ticket đã approved/blocked thì task này đã bị vượt. Giao nó cho
      backend là backend chạy trên worktree đã commit → "không sửa file nào" ×3 → `blocked` → review PR của
      người bị bỏ vì ticket không còn `in_review`.
    - `pull-requests` chỉ còn giá trị khi là PR MỚI NHẤT của ticket: `_on_pr` đã đặt lại vòng review theo PR
      sau, review PR trước là chấm commit cũ rồi ghi verdict vào vòng của PR mới.
    Đo được (2026-09-04/05): QLKH-004 mở lại 7 lần, 13 lần review block, 10.7M token; sau khi mở lại bus,
    PR tiếp quản 04:10 (đã có 2/3 verdict, hoãn vì qa transient) vẫn nằm hàng đợi cạnh PR tiếp quản mới."""
    tid = str(env.payload.get("ticket_id") or env.key)
    if tid not in o.lead.tickets: return False  # event ngoài delivery-lead (test/relay): không có trạng thái để so
    st = o.lead.state.get(tid)
    if env.topic == "tasks":
        if st == "dispatched": return False
        why = {"state": st, "retry": env.payload.get("retry", 0)}
    else:
        newest = o.latest("pull-requests", tid)
        if newest is None or newest.event_id == env.event_id: return False
        why = {"state": st, "pr_ref": env.payload.get("pr_ref"), "newest_pr_ref": newest.payload.get("pr_ref")}
    o._audit(f"{env.topic}.superseded", {"ticket_id": tid, "event_id": env.event_id, **why},
                ticket_id=tid, project_id=o.project_for(env))
    res.actions.append(f"superseded:{tid}:{env.topic}")
    o._mark(env, res)
    return True

def _note_closed(o) -> None:
    """Ghi `ticket.closed` cho ticket vừa vào trạng thái cuối. `metrics.collect` tính lead time (tasks đầu → closed)
    từ chính action này; không ai phát thì `ticket_lead_seconds` luôn rỗng và gauge Prometheus không bao giờ hiện."""
    for tid, st in list(o.lead.state.items()):
        if st != "closed": continue
        t = o.lead.tickets.get(tid)
        o._audit("ticket.closed", {"ticket_id": tid, "retry": t.retry if t else 0}, once=f"closed:{tid}",
                    ticket_id=tid, project_id=t.project_id if t else None)

def _plan(o, env: Envelope, res: StepResult) -> StepResult:
    project = env.payload.get("project_id") or env.key
    if env.topic == "approved-specs":
        sid = f"SPEC-{project}"
        if not o.gate.is_approved(sid):
            decided = [g for g in o.gate.history if g.subject_id == sid]
            if sid not in o.gate.pending and not decided:
                if (gap := spec_runtime_gap(env.payload)) is not None:
                    return o._spec_runtime_missing(env, project, gap, res)
                o.gate.request(GateRequest(kind="spec", subject_id=sid, created_by=env.actor,
                                              checklist=["prd", "acceptance-criteria", "ux-flow", "risks"]))
            if decided and sid not in o.gate.pending:
                res.actions.append(f"gate:{sid}:{decided[-1].decision}"); o._mark(env, res); return res
            return o._defer(env, res, f"gate:{sid}")
        if not o._threat_model(env, sid, res):
            o._mark(env, res); return res
        live = [pid for pid, p in o.plans.items() if p["project_id"] == project and p["source_topic"] == "approved-specs"
                and (pid in o.gate.pending or o.gate.is_approved(pid))]
        if live:
            # Spec publish lặp (spec-writer chạy lại, người publish hai lần) không được sinh plan thứ hai cho cùng
            # dự án: ticket trùng, hai gate plan cho một việc. Muốn lập lại thì reject plan cũ trước.
            o._audit("plan.duplicate_spec", {"project_id": project, "event_id": env.event_id, "existing": live}, project_id=project)
            res.actions.append(f"plan_skipped:{','.join(live)}"); o._mark(env, res); return res
    cal = o.supervisor.calibration()  # vòng học: bài học estimate-vs-actual quay lại người ước lượng
    inp = env.model_copy(update={"payload": {**env.payload, "estimate_calibration": cal}}) if cal else env
    try:
        g = o.runner.generate("delivery-lead", inp, "tasks", many=True)
    except TransientError as e:
        res.actions.append(f"transient:delivery-lead:{str(e)[:120]}")
        with o._lock: o.stats["transient"] += 1
        return o._defer(env, res, "transient:delivery-lead")
    except (RunnerError, LLMError) as e:
        res.actions.append(f"error:delivery-lead:{str(e)[:120]}")
        with o._lock: o.stats["errors"] += 1
        o._mark(env, res); return res
    if g.context_writes:  # C4, API contract lên blackboard TRƯỚC khi xin gate plan để người duyệt đọc được
        o.runner.write_context("delivery-lead", env, g.context_writes)
    tickets = [Task.model_validate(p) for p in g.payloads]
    problems = o._check_plan(tickets)
    n = 1 + sum(1 for p in o.plans.values() if p["project_id"] == project)
    plan_id = f"PLAN-{project}-{n}"
    plan = {"plan_id": plan_id, "project_id": project, "source_event": env.event_id, "source_topic": env.topic,
            "tickets": [t.model_dump() for t in tickets], "problems": problems,
            "threat_model": "missing" if f"SPEC-{project}" in o.missing_threat_model else "ok"}
    if problems:
        o._audit("plan_rejected", plan, actor="delivery-lead", tokens=g.tokens, cost=g.cost_usd, project_id=project)
        res.actions.append(f"plan_rejected:{'; '.join(problems)[:120]}")
        with o._lock: o.stats["errors"] += 1
        # Kế hoạch bị từ chối là ngõ cụt: không ticket nào được tạo, không gate nào mở, và không có cơ chế
        # tự lập lại. Trước đây dự án đứng im ở đây mà `status` vẫn báo mọi chỉ số xanh (đo được với dự án
        # DHCB: `tickets: []` → "kế hoạch rỗng" → im lặng vĩnh viễn). Phải hiện ra cho người quyết.
        o.supervisor.escalate_gate(project, f"kế hoạch {plan_id} bị từ chối: {'; '.join(problems)[:200]}",
                                      once_key=f"plan_rejected:{env.event_id}")
        # Duyệt escalation này = lập lại kế hoạch: ghi vào `unhandled` để `_retry_unhandled` chạy lại đúng event
        # nguồn (change-request / approved-specs). Trước đây duyệt rơi xuống nhánh ticket → "reopen" một ticket
        # không tồn tại, không gì xảy ra. Đo được 2026-09-06 (CR-STAGE-001, PLAN-QLKH-5 rỗng): duyệt xong hàng
        # đợi rỗng, phải phát lại decide-change bằng tay.
        with o._lock:
            o.unhandled[project] = {"agent": "delivery-lead", "topic": env.topic, "event_id": env.event_id,
                                       "subject": project, "error": f"plan_rejected: {'; '.join(problems)[:200]}"}
        if project not in o.gate.pending:
            o.gate.request(GateRequest(kind="escalation", subject_id=project, created_by="delivery-lead",
                                          checklist=["plan_problems", "decision:retry|close"]))
    else:
        o.plans[plan_id] = plan
        o._audit("plan.proposed", plan, actor="delivery-lead", tokens=g.tokens, cost=g.cost_usd, project_id=project)
        o.gate.request(GateRequest(kind="plan", subject_id=plan_id, created_by="delivery-lead",
                                      checklist=["tickets", "estimate_tokens", "risk_tags", "depends_on", "threat-model",
                                                 "architecture", "api-contract"]))
        res.actions.append(f"plan:{plan_id}:{len(tickets)} ticket")
        with o._lock: o.stats["plans"] += 1
    o._mark(env, res)
    return res

def _spec_runtime_missing(o, env: Envelope, project: str, gap: str, res: StepResult) -> StepResult:
    """ADR-0031: spec ứng dụng không có `runtime` hợp lệ thì KHÔNG mở gate spec — người ký Gate 1 không được đặt
    trước một PRD mà câu "chạy cho tôi xem" chưa có câu trả lời. Thay vào đó trả về spec-writer với lý do (`hint`)
    đúng như `request_changes` của người; quá `SPEC_RUNTIME_REWORKS` lần vẫn thiếu → escalation cấp dự án, cùng
    khuôn với kế hoạch bị `_check_plan` từ chối (approve = chạy lại event nguồn, reject = bỏ).
    Khoá theo `event_id` của spec (mỗi lần spec-writer publish là một event mới, không nuốt lần hai — khuôn 3
    `TRAPS.md`); bộ đếm theo dự án dựng lại từ audit (khuôn 2)."""
    with o._lock:
        o.spec_runtime_reworks[project] += 1; n = o.spec_runtime_reworks[project]
    cause = next((e for t in ("clarification-answers", "requirements-draft", "clarification-questions")
                  for e in o.bus.replay(topic=t) if e.event_id == env.causation_id), None) if env.causation_id else None
    if cause is None:
        cause = o.latest("requirements-draft", project)
    o._audit("spec.runtime_missing", {"project_id": project, "event_id": env.event_id, "kind": env.payload.get("kind"),
                                         "runtime": env.payload.get("runtime"), "reason": gap, "attempt": n,
                                         "source_event": cause.event_id if cause else None}, project_id=project)
    if cause is not None and n <= SPEC_RUNTIME_REWORKS:
        hint = f"orchestrator từ chối mở gate spec (lần {n}): {gap}"
        prev = {k: env.payload.get(k) for k in ("kind", "runtime", "artifacts")}
        inp = cause.model_copy(update={"payload": {**cause.payload, "hint": hint, "previous_spec": prev}})
        o._recall("spec-writer", cause)  # `partial` đã ghi spec-writer cho event nguồn: gọi lại là CHỦ Ý
        route = Route(cause.topic, "spec-writer", "approved-specs",
                      enrich=None if cause.topic == "requirements-draft" else _with_draft)
        o._call("spec-writer", inp, route, res)
        res.actions.append(f"spec_runtime_missing:{project}:rework:{n}")
        o._mark(env, res); return res
    why = gap if cause is not None else f"{gap}; không có requirements-draft để spec-writer làm lại"
    o._audit("spec.runtime_escalated", {"project_id": project, "event_id": env.event_id, "attempts": n, "reason": why,
                                           "source_event": cause.event_id if cause else None,
                                           "source_topic": cause.topic if cause else None}, project_id=project)
    res.actions.append(f"spec_runtime_missing:{project}:escalated")
    with o._lock: o.stats["errors"] += 1
    o.supervisor.escalate_gate(project, f"spec thiếu runtime sau {n} lần: {gap[:200]}", once_key=f"spec_runtime:{env.event_id}")
    if cause is not None:
        with o._lock:
            o.unhandled[project] = {"agent": "spec-writer", "topic": cause.topic, "event_id": cause.event_id,
                                       "subject": project, "error": f"spec_runtime_missing: {gap[:200]}"}
    if project not in o.gate.pending:
        o.gate.request(GateRequest(kind="escalation", subject_id=project, created_by="spec-writer",
                                      checklist=["spec_runtime", "decision:retry|close"]))
    o._mark(env, res); return res

def _threat_model(o, env: Envelope, sid: str, res: StepResult) -> bool:
    """Security-engineer đọc spec đã duyệt: threat model v1 lên blackboard + review-results key=SPEC-*.
    Verdict block → không lập kế hoạch (người sửa spec rồi publish lại). Trả về True nếu được đi tiếp."""
    prior = o.latest("review-results", sid)
    if prior is not None and prior.payload.get("verdict") != "block":
        return True
    try:
        g = o.runner.generate("security-engineer", env, "review-results")
        p = {**g.payloads[0], "ticket_id": sid, "source": "security"}
        o.runner.publish("security-engineer", env, "review-results", p, key=sid, tokens=g.tokens, model=g.model,
                            context_writes=g.context_writes, generated=g)
        with o._lock: o.stats["runs"] += 1
    except TransientError as e:
        res.actions.append(f"transient:security-engineer:{str(e)[:120]}")
        with o._lock: o.stats["transient"] += 1
        return True  # threat model không chặn plan; lần lập kế hoạch sau (nếu có) sẽ thử lại
    except (RunnerError, LLMError) as e:
        # Không chặn kế hoạch (người duyệt gate plan vẫn quyết được), nhưng phải hiện ra: audit riêng + đánh dấu
        # vào plan để mục `threat-model` trong checklist gate không bị tick nhầm là đã có.
        o._audit("threat_model.missing", {"subject_id": sid, "error": str(e)[:300]},
                    project_id=env.payload.get("project_id"))
        with o._lock: o.missing_threat_model.add(sid)
        res.actions.append(f"error:security-engineer:{str(e)[:120]}")
        with o._lock: o.stats["errors"] += 1
        return True
    if p["verdict"] == "block":
        o._audit("spec_blocked_by_security", {"subject_id": sid, "findings": p.get("findings", [])}, project_id=env.payload.get("project_id"))
        res.actions.append(f"spec_blocked:{sid}"); return False
    res.actions.append(f"threat-model:{sid}:{p['verdict']}"); return True

def _check_plan(o, tickets: list[Task]) -> list[str]:
    ids = {t.ticket_id for t in tickets}; known = ids | set(o.lead.tickets)
    problems = ["kế hoạch rỗng"] if not tickets else []
    if len(ids) != len(tickets): problems.append("ticket_id trùng")
    for t in tickets:
        if t.ticket_id in o.lead.tickets: problems.append(f"{t.ticket_id} đã tồn tại")
        if t.estimate_tokens is None: problems.append(f"{t.ticket_id} thiếu estimate_tokens")
        elif t.budget_tokens < t.estimate_tokens * BUDGET_FACTOR: problems.append(f"{t.ticket_id} budget < estimate×{BUDGET_FACTOR}")
        if not t.acceptance: problems.append(f"{t.ticket_id} thiếu acceptance")
        unknown = [d for d in t.depends_on if d not in known]
        if unknown or t.ticket_id in t.depends_on: problems.append(f"{t.ticket_id} depends_on sai {unknown or 'chính nó'}")
    cyc = _cycle({t.ticket_id: [d for d in t.depends_on if d in ids] for t in tickets})
    if cyc: problems.append("depends_on vòng: " + " → ".join(cyc))
    return problems

def _dispatch_plan(o, plan_id: str, replaying: bool = False) -> list[str]:
    plan = o.plans[plan_id]
    pending = [Task.model_validate(t) for t in plan["tickets"] if t["ticket_id"] not in o.lead.tickets]
    done: list[str] = []
    prev, o.lead.replaying = o.lead.replaying, replaying
    try:
        while pending:
            ready = [t for t in pending if all(d in o.lead.tickets for d in t.depends_on)]
            if not ready: raise ValueError(f"{plan_id}: depends_on vòng hoặc chưa biết: {[t.ticket_id for t in pending]}")
            for t in sorted(ready, key=lambda x: x.priority):
                o.lead.dispatch(t, plan_id); pending.remove(t); done.append(t.ticket_id)
    finally:
        o.lead.replaying = prev
    return done


def _cycle(graph: dict[str, list[str]]) -> list[str]:
    """Một chu trình trong đồ thị phụ thuộc (rỗng nếu không có) — bắt ở bước lập kế hoạch, trước gate, không để tới dispatch."""
    state: dict[str, int] = {}; stack: list[str] = []
    def visit(n: str) -> list[str]:
        state[n] = 1; stack.append(n)
        for m in graph.get(n, []):
            if state.get(m) == 1: return [*stack[stack.index(m):], m]
            if m not in state and (c := visit(m)): return c
        stack.pop(); state[n] = 2; return []
    for n in graph:
        if n not in state and (c := visit(n)): return c
    return []


# ---------- bảng chuyển giao (K1.7, orch/fsm.py) — dùng bởi Orchestrator.process() ----------

def _act_superseded(o: Orchestrator, env: Envelope, res: StepResult) -> bool:
    return o._superseded(env, res)  # True: event cũ đã bị vượt, _superseded tự _mark — process() dừng ngay


def _act_learn_repo(o: Orchestrator, env: Envelope, res: StepResult) -> bool:
    o._learn_repo(env)  # repo riêng của dự án (ADR-0025), trước khi intake chạy — không dừng process()
    return False


def _act_plan(o: Orchestrator, env: Envelope, res: StepResult) -> bool:
    o._plan(env, res)  # _plan tự _mark và trả res; process() luôn dừng ở đây khi PLAN_INPUTS khớp
    return True


def _act_clarification_fallback(o: Orchestrator, env: Envelope, res: StepResult) -> bool:
    """Clarifier không còn câu hỏi (hoặc quá round 2 → assumption): spec-writer đi thẳng từ draft sau risk."""
    draft = o.latest("requirements-draft", env.key)
    if draft is not None:
        o._call("spec-writer", draft, Route("requirements-draft", "spec-writer", "approved-specs"), res)
    return False


TICKET_TRANSITIONS: list[Transition] = [
    Transition("superseded", frozenset({"tasks", "pull-requests"}), _act_superseded),
    Transition("learn_repo", frozenset({"research-requests"}), _act_learn_repo),
    Transition("plan", frozenset(PLAN_INPUTS), _act_plan,
               guard=lambda env, o: PLAN_INPUTS[env.topic](env, o)),
    Transition("clarification_fallback", frozenset({"clarification-questions"}), _act_clarification_fallback,
               guard=lambda env, o: not env.payload.get("questions")),
]
