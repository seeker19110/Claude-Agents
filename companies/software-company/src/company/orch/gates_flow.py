"""Quyết định gate: release → production; escalation → mở lại/đóng dự án hoặc ticket;
đường xử lý lỗi agent không nhánh nào nhận (ADR-0034, tách khỏi orchestrator.py).

Mỗi hàm nhận `o: Orchestrator` làm tham số đầu và được gán làm method trên `Orchestrator`
(`_on_gate_decide = gates_flow._on_gate_decide`, …) — `self` tự bind qua descriptor của Python nên lời gọi
cũ (`o._check_escalations()`, `o._after_error(...)`) không đổi.

Cạm bẫy ghi trong đặc tả K1.6: `escalation_decided` tăng ở `_on_gate_decide` và đọc ở `_check_escalations`
— cả hai cùng module, giữ nguyên thứ tự. `unhandled` được ghi từ ba nơi (hai ở `ticket_fsm`/`_plan` khi K1.7
chạy, một ở đây `_after_error`) — cả ba đi qua `mark_unhandled` khi K1.7 dựng hàm đó, ở đây tạm ghi trực tiếp
để không phá vỡ hành vi trước khi `ticket_fsm.py` tồn tại.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ..delivery import DONE_STATES
from ..events import Envelope
from ..gate_risk import request_gate
from ..gates import Decision, GateRequest
from ..roles import LEAD_ACTOR, ROLE
from .routes import ACTOR, PROD_ROUTE, RESEARCH_TOPICS, REVIEW_AGENT, Route, review_route

if TYPE_CHECKING:
    from ..orchestrator import Orchestrator, StepResult


def _on_gate_decide(o: Orchestrator, env: Envelope, res: StepResult) -> StepResult:
    from ..orchestrator import _evidence  # nhập lười: orchestrator.py nhập module này trước khi định nghĩa _evidence
    d = _evidence(env.payload); sid, decision, by = d["subject_id"], d["decision"], d.get("by", "human")
    kind = next((g.kind for g in reversed(o.gate.history) if g.subject_id == sid), None)
    res.actions.append(f"gate:{kind}:{sid}:{decision}")
    # Đếm ở ĐÂY chứ không ở `_on_escalation_decided`: `_rehydrate` đếm mọi `gate.decide` theo subject, nên đếm
    # sống hẹp hơn (chỉ gate escalation) là hai đường lệch nhau và test bất biến restart đỏ — nó đã bắt đúng
    # lỗi này trong chính bản sửa mở gate cho lần chặn thứ hai.
    o.escalation_decided[sid] += 1
    if kind == "escalation":
        o._on_escalation_decided(sid, decision, by, d.get("reason", ""), res)
    elif decision == "approve":
        # ADR-0037: không còn nhánh `sid in o.plans` — kế hoạch được `_check_plan` cho đi thẳng lúc lập, không
        # chờ ai ký. Duyệt gate release vẫn là bước cho phép deploy production.
        if sid in o.lead.release_tickets:
            rc = o.latest("release-candidates", sid)
            if rc is not None:
                o._recall(ROLE.OPS, rc)  # ký lại gate release phải chạy lại được lượt production
                o._call(ROLE.OPS, rc, PROD_ROUTE, res)
    o._note_closed()
    o._mark(env, res)
    o._retry_deferred()
    return res

def _check_escalations(o: Orchestrator) -> None:
    """Ticket blocked (retry hết) hoặc bị supervisor escalate → gate `escalation` cho người quyết (checklist gate 'bất thường')."""
    # `o.paused` chứa cả ID DỰ ÁN (supervisor pause khi dự án chạm trần ngân sách), không chỉ ticket. Lọc
    # `t in o.lead.tickets` bỏ sót đúng nhóm đó: dự án bị pause thì mọi event của nó bị hoãn, không cổng
    # nào mở, không ai được hỏi — đo được: `paused=['P1']` mà `gates_pending={}`.
    # Người ĐÃ quyết nhưng `gate.decide` còn nằm trong hàng đợi (mở lại bus: `_rehydrate` đã đếm nó vào
    # `escalation_decided` nhưng `resume` chỉ được phát khi event đó được xử lý) → subject vẫn `paused`, khoá mang số
    # quyết định mới → gate TRÙNG cho một việc người vừa duyệt. Đo được (2026-09-05): REL-004 duyệt 21:19, orchestrator
    # mở lại 21:30, gate thứ hai mở ngay sau event đầu tiên trong hàng đợi, trước khi decide được áp dụng.
    from ..orchestrator import _evidence  # nhập lười, lý do như trong _on_gate_decide
    o._check_paused_releases()
    with o._qlock:
        decided_pending = {str(_evidence(e.payload).get("subject_id")) for e in o.queue
                           if e.topic == "audit-log" and e.payload.get("action") == "gate.decide"}
    for tid in {*o.lead.blocked(), *o.paused}:
        if o.lead.state.get(tid) in DONE_STATES: continue  # đã đóng/đã xong: không mở gate nữa
        if tid in decided_pending: continue  # đã có quyết định chờ áp dụng: không hỏi người lần nữa
        # budget_cut cũng là "dừng chờ người" (approve = cấp thêm ngân sách): không có gate thì ticket treo im lặng.
        # `pause` cũng vậy và còn nặng hơn — dự án chạm trần ngân sách bị pause thì MỌI event của nó bị hoãn.
        # Thiếu `pause` ở đây thì `n = 0` cho một dự án bị pause, điều kiện bên dưới sai, và không gate nào mở.
        n = sum(1 for a in o.supervisor.actions
                if a.target == tid and a.action in {"escalate", "budget_cut", "pause"})
        # Mỗi lần escalate/cắt mới, mỗi lần blocked mới → một gate mới. `escalation_decided` là thành phần bắt
        # buộc: sau khi người duyệt mở lại ticket, ticket có thể bị chặn LẠI mà supervisor không hành động gì
        # thêm (n không đổi, state vẫn `blocked`) — thiếu nó thì khoá trùng lần trước, `once` nuốt, và ticket
        # nằm im mãi không ai được hỏi. Đo được khi chạy thật (2026-09-04): QLKH-001 blocked lúc 13:25 với
        # key `escalation:QLKH-001:5:blocked` đã có trong `once` từ lần chặn trước → `gates_pending` rỗng,
        # `status` không báo gì bất thường, 13 ticket phụ thuộc đứng chờ vô hạn.
        key = f"escalation:{tid}:{n}:{o.lead.state.get(tid)}:{o.escalation_decided[tid]}"
        if tid in o.gate.pending or key in o.once: continue
        if o.lead.state.get(tid) == "blocked" or n:
            o._remember(key)
            request_gate(o.gate, GateRequest(kind="escalation", subject_id=tid, created_by=ROLE.SUPERVISOR,
                                          checklist=["root_cause", "decision:reopen|close", "hint"]))
    o._check_debt()

def _check_debt(o: Orchestrator) -> None:
    """ADR-0032: mã nợ kiến trúc chạm ngưỡng (supervisor đếm từ bus, xác định) → gate `escalation` cấp DỰ ÁN với
    danh sách nợ, số lần, ticket nào nhắc, và hint "cần ticket ADR + người ký". Không pause dự án: nợ treo là
    quyết định bị né, không phải sự cố — việc khác vẫn chạy trong lúc người quyết.

    Khoá once mang (dự án, mã nợ, lần thứ mấy): restart không mở trùng (`once` dựng lại từ audit), nhưng nợ tăng
    tiếp tới bội số kế của ngưỡng là lần thứ n+1 → gate mới (khuôn 3, TRAPS.md). Gate của dự án đang bận (stall
    hoặc nợ khác) thì đợi — không `remember`, nhịp sau mở."""
    for due in o.supervisor.debt_due:
        pid = due["project_id"]; key = f"debt:{pid}:{due['debt_id']}:{due['times']}"
        if key in o.once: continue
        if pid in o.gate.pending or pid in o.debt_gate: continue
        o._remember(key)
        rec = {**due, "table": o.supervisor.debt_table(pid)}
        o.debt_gate[pid] = rec
        o._audit("debt.escalated", rec, project_id=pid)
        checklist = [f"debt:{due['debt_id']}×{due['consecutive']} liên tiếp ({due['source']}; {','.join(due['tickets'])})",
                     *[f"debt:{r['debt_id']}×{r['mentions']} ({','.join(r['tickets'])})" for r in rec["table"]
                       if r["debt_id"] != due["debt_id"]],
                     "decision:adr|waive", f"hint:{due['hint']}"]
        request_gate(o.gate, GateRequest(kind="escalation", subject_id=pid, created_by=ROLE.SUPERVISOR, checklist=checklist))

def _on_escalation_decided(o: Orchestrator, tid: str, decision: str, by: str, reason: str, res: StepResult) -> None:
    if tid in o.debt_gate:  # ADR-0032: nợ kiến trúc cấp dự án — người ghi nhận (ADR + người ký) hay chấp nhận treo
        rec = o.debt_gate.pop(tid)
        o._audit("debt.decided", {"project_id": tid, "debt_id": rec.get("debt_id"), "times": rec.get("times"),
                                     "decision": decision, "by": by, "reason": reason[:300]}, project_id=tid)
        res.actions.append(f"debt:{tid}:{rec.get('debt_id')}:{decision}")
        return
    if tid in o.lead.release_tickets:  # escalation của một RELEASE (không phải ticket): xem docstring
        # `Delivery.waive_release_findings`/`rework_release_tickets` — người quyết định chấp nhận rủi ro (finding
        # không có code để sửa: DPIA, license...) hay đúng là lỗi code thật cần các ticket merged làm lại.
        if decision == "approve":
            sources = o.lead.waive_release_findings(tid)
            o.bus.publish(Envelope(topic="supervisor-actions", key=tid, actor=by,
                                      payload={"target": tid, "action": "resume", "reason": f"escalation approve: {reason}"[:300]}))
            res.actions.append(f"release_waived:{tid}:{','.join(sources)}")
            if o._rerun_release(tid, by, reason, res): res.actions.append(f"release_rerun:{tid}")
        elif o._superseded_release(tid):
            # RC cũ mà nội dung đã nằm trong một bản GIAO sau nó (nhánh tích hợp cộng dồn): "đóng" là huỷ RC,
            # KHÔNG trả ticket đã giao về làm lại. Đo được 2026-09-06: sau bản giao v0.15.1, 10 RC cũ
            # pending_human sẽ mở gate; từ chối theo hành vi cũ đá 14 ticket đã giao về changes_requested.
            o._audit("release.void", {"release_id": tid, "reason": f"nội dung đã nằm trong bản giao; {reason}"[:300]})
            o._void(tid); res.actions.append(f"void:{tid}")
            # `void_release` (DeliveryLead) đưa ticket về `unreleased()` — đúng cho ca xung đột tích hợp (ticket
            # thật sự cần một RC kế tiếp), nhưng SAI ở đây: ticket đã giao rồi, không cần RC nào nữa. Không đóng
            # sổ ở đây thì `scheduler.tick()` (flush_releases mỗi nhịp, #251) thấy ticket "approved, không RC" và
            # tạo ngay một RC trùng — nếu vòng đó đụng lỗi thật, ticket ĐÃ GIAO bị đá về rework rồi hết retry →
            # blocked. Đo được 2026-09-10 (QLKH): QLKH-002/005 và cả nhóm TCK-CR-RUNTIME-03..06 dính đúng vòng này.
            for rtid in o.lead.release_tickets.get(tid, []):
                if o.lead.state.get(rtid) == "approved":
                    o.lead.mark_done_already_integrated(rtid)
        else:
            o.lead.rework_release_tickets(tid, reason or "người từ chối escalation release: cần sửa nội dung thật")
            res.actions.append(f"release_reworked:{tid}")
        return
    if tid in o.stalled:  # escalation cấp dự án (chuỗi nghiên cứu lỗi): retry event hoặc đóng dự án
        if decision == "approve":
            o.bus.publish(Envelope(topic="supervisor-actions", key=tid, actor=by,
                                      payload={"target": tid, "action": "resume", "reason": f"escalation approve: {reason}"[:300]}))
            res.actions.append(f"retry:{tid}" if o._retry_stalled(tid, by, reason) else f"retry_failed:{tid}")
        else:
            st = o.stalled.pop(tid, {})
            o._audit("project.closed", {**st, "project_id": tid, "by": by, "reason": reason}, project_id=tid)
            res.actions.append(f"closed:{tid}")
        return
    if tid not in o.lead.tickets and tid in o.unhandled:
        # Event KHÔNG phải ticket (change-request, acceptance...) mà agent lỗi không nhánh nào nhận: trước đây rơi
        # xuống nhánh ticket bên dưới → "reopen" một ticket không tồn tại, event không bao giờ chạy lại. Đo được
        # 2026-09-06: CR-DEV-001, delivery-lead lỗi error_max_structured_output_retries, duyệt escalation xong
        # hàng đợi rỗng, phải phát lại CR bằng tay.
        # `resume` trước: supervisor đã `pause` subject khi escalate — không gỡ thì event chạy lại bị hoãn
        # "paused:<subject>" và `_check_escalations` mở gate mới cho cùng việc.
        o.bus.publish(Envelope(topic="supervisor-actions", key=tid, actor=by,
                                  payload={"target": tid, "action": "resume", "reason": f"escalation {decision}: {reason}"[:300]}))
        if decision == "approve":
            ok = o._retry_unhandled(tid, by, reason)
            res.actions.append(f"retry:{tid}" if ok else f"retry_failed:{tid}")
        else:
            rec = o.unhandled.pop(tid, {})
            o._audit("event.abandoned", {**rec, "subject": tid, "by": by, "reason": reason})
            res.actions.append(f"closed:{tid}")
        return
    if decision == "approve":  # mở lại với hint = lý do người duyệt, cấp thêm một ngân sách ticket
        b = o.supervisor.budgets.get(tid); t = o.lead.tickets.get(tid)
        if b and t:
            b.limit = max(b.limit, b.used) + t.budget_tokens
            o._audit("budget.extended", {"ticket_id": tid, "limit": b.limit, "by": by}, ticket_id=tid)
        if tid in o.integrated and o.lead.state.get(tid) in {"blocked", "escalated", "changes_requested"}:
            # Code của ticket ĐÃ ở trong nhánh tích hợp: giao lại chỉ tổ bắt agent làm lại việc đã merge, nó
            # không sửa gì (đúng) rồi bị tính `invalid_output` → block → escalation → lặp. Xem
            # `DeliveryLead.mark_done_already_integrated`.
            o._audit("ticket.already_integrated", {"ticket_id": tid, "by": by}, ticket_id=tid,
                        project_id=o.lead.tickets[tid].project_id if tid in o.lead.tickets else None)
            o.lead.mark_done_already_integrated(tid)
            res.actions.append(f"already_integrated:{tid}")
        elif o.lead.state.get(tid) in {"blocked", "escalated"}:
            o.lead.reopen(tid, hint=reason or "người duyệt mở lại sau escalation")
        o.bus.publish(Envelope(topic="supervisor-actions", key=tid, actor=by,
                                  payload={"target": tid, "action": "resume", "reason": f"escalation approve: {reason}"[:300]}))
        res.actions.append(f"reopen:{tid}")
        # Escalation vì một REVIEW AGENT lỗi (không phải assignee): ticket vẫn `in_review`, event PR đã bị đánh dấu
        # xử lý, nên duyệt gate xong không có gì chạy lại review còn thiếu — ticket nằm im tới `review_timeout`
        # (2 giờ) mới được `tick` giao lại. Đo được (2026-09-05): QLKH-005/QLKH-013 duyệt xong đứng im, người
        # phải `takeover` nộp lại PR nguyên trạng để vòng review chạy. Ở đây gọi lại đúng nguồn còn thiếu trên PR
        # mới nhất; `partial` giữ cho reviewer/qa đã chấm không chạy lại.
        if o.lead.state.get(tid) == "in_review" and (pr := o.latest("pull-requests", tid)) is not None:
            for src in sorted(o.lead.required_reviews(tid) - set(o.lead.reviews.get(tid, {}))):
                o._audit("review.rerun", {"ticket_id": tid, "source": src, "by": by}, ticket_id=tid,
                            project_id=o.project_for(pr))
                o._call(REVIEW_AGENT[src], pr, review_route(REVIEW_AGENT[src]), res)
    elif decision in {"reject", "rollback"} and tid in o.lead.tickets:
        blocked = o.lead.close_escalated(tid); res.actions.append(f"closed:{tid}")
        o._audit("ticket.abandoned", {"ticket_id": tid, "by": by, "dependents_blocked": blocked}, ticket_id=tid,
                    project_id=o.lead.tickets[tid].project_id)
        if blocked: res.actions.append("blocked:" + ",".join(blocked))
        if o.lead.batch_releases:  # ticket đóng không còn giữ release của các ticket đã approved
            o.lead.flush_releases(o.lead.tickets[tid].project_id)

def _open_acceptance_gate(o: Orchestrator, rid: str, res: StepResult) -> None:
    """Sau production: mở gate `acceptance` cho khách ký (ADR-0017). Là gate thật nên có hạn 24h, có nhắc ở 12h
    và được escalate khi quá hạn — trước đây chỉ là một dòng audit `uat.pending` không ai theo dõi."""
    sid = f"UAT-{rid}"
    if sid in o.gate.pending or o.gate.is_approved(sid) or f"uat:{rid}" in o.once: return
    o._remember(f"uat:{rid}")
    request_gate(o.gate, GateRequest(kind="acceptance", subject_id=sid, created_by=ROLE.OPS,
                                  checklist=["uat-script", "acceptance-criteria", "known-issues", "signed_by"]))
    res.actions.append(f"gate:acceptance:{sid}")

def _close_acceptance_gate(o: Orchestrator, env: Envelope, res: StepResult) -> None:
    """Khách ký `acceptance-results` → đóng gate nghiệm thu bằng chính chữ ký đó. Four-eyes bảo đảm người ký của
    khách khác account-manager. Conditional đóng ở dạng request_changes; phần còn lại đi qua change request."""
    rid = env.payload.get("release_id"); sid = f"UAT-{rid}"
    if sid not in o.gate.pending: return
    verdict = env.payload.get("verdict")
    decision: Decision = {"accepted": "approve", "rejected": "reject"}.get(str(verdict), "request_changes")  # type: ignore[assignment]
    by = str(env.payload.get("signed_by") or env.actor)
    try:
        # `enforce=False`: `by` là chữ ký khách (chuỗi tự do trong acceptance-results), không phải id một
        # người duyệt nội bộ — allowlist `COMPANY_GATE_APPROVERS` (K3.7) nói về ai được duyệt spec/release/
        # escalation, không nói về khách hàng. Four-eyes (`created_by=ROLE.OPS` ở `_open_acceptance_gate`) vẫn
        # áp bình thường qua `super().decide` bất kể `enforce`.
        o.gate.decide(sid, decision, by=by, reason=f"acceptance-results: {verdict}", actor=ACTOR, enforce=False)
        res.actions.append(f"gate:acceptance:{sid}:{decision}")
    except (KeyError, PermissionError) as e:
        o._audit("handler_error", {"agent": ROLE.OPS, "error": str(e)[:300]})

def _stall(o: Orchestrator, env: Envelope, agent: str, error: Exception, res: StepResult) -> bool:
    """Agent của chuỗi nghiên cứu lỗi → dự án không có bước kế tiếp. Ghi `project.stalled`, supervisor escalate
    (dự án bị hoãn mọi event), mở gate `escalation` subject=project_id. Ticket có cơ chế retry/blocked riêng.
    Trả True nếu nhánh này đã nhận trách nhiệm xử lý lỗi."""
    if env.topic not in RESEARCH_TOPICS: return False
    pid = str(env.payload.get("project_id") or env.key)
    with o._lock:
        o.stall_count[env.event_id] += 1; n = o.stall_count[env.event_id]
        o.stalled[pid] = {"project_id": pid, "event_id": env.event_id, "topic": env.topic, "agent": agent,
                             "error": str(error)[:300], "attempt": n}
    o._audit("project.stalled", o.stalled[pid], project_id=pid)
    o.supervisor.escalate_gate(pid, f"{agent} lỗi trên {env.topic} (lần {n}): {str(error)[:200]}",
                                  once_key=f"stall:{env.event_id}:{n}")
    if pid not in o.gate.pending:
        request_gate(o.gate, GateRequest(kind="escalation", subject_id=pid, created_by=ROLE.SUPERVISOR,
                                      checklist=["agent_error", "decision:retry|close"]))
    res.actions.append(f"stalled:{pid}:{agent}")
    return True

def _after_error(o: Orchestrator, env: Envelope, agent: str, error: Exception, r: Route, res: StepResult) -> None:
    """Mọi lỗi agent phải có người nhận: `_stall` lo chuỗi nghiên cứu, `_rework_after_error` lo agent sửa code.
    KHÔNG đường nào nhận thì đây là đường cuối — trước đây lỗi rơi vào im lặng: event vẫn bị `_mark` là đã xử
    lý, ticket treo nguyên trạng thái cũ, không gate nào mở, và `status` báo mọi chỉ số XANH trong khi dự án
    đã chết. Đo được khi chạy thật (2026-09-04): ba reviewer của `pull-requests:QLKH-001` cùng lỗi
    (`env.topic` không thuộc RESEARCH_TOPICS nên `_stall` bỏ qua, `r.tools != "rw"` nên `_rework_after_error`
    cũng bỏ qua) → 13 ticket phụ thuộc chờ vĩnh viễn mà không có một tín hiệu nào."""
    handled = o._stall(env, agent, error, res)
    handled = o._rework_after_error(env, r, error) or handled
    if handled: return
    subject = str(env.payload.get("ticket_id") or env.key)
    rec = {"agent": agent, "topic": env.topic, "event_id": env.event_id, "subject": subject, "error": str(error)[:300]}
    with o._lock: o.unhandled[subject] = rec
    o._audit("agent_error_unhandled", rec, ticket_id=env.payload.get("ticket_id"), project_id=o.project_for(env))
    o.supervisor.escalate_gate(subject, f"{agent} lỗi trên {env.topic}, không nhánh nào xử lý: {str(error)[:200]}",
                                  once_key=f"unhandled:{env.event_id}:{agent}")
    res.actions.append(f"unhandled:{subject}:{agent}")

def _rework_after_error(o: Orchestrator, env: Envelope, r: Route, error: Exception) -> bool:
    """Agent kỹ thuật lỗi (không sửa file, JSON hỏng, hết ngân sách lượt...) → ticket không được treo `dispatched`
    mãi: delivery-lead phát lại task retry+1 với hint là lỗi, hết retry → blocked → gate escalation.
    Trả True nếu nhánh này đã nhận trách nhiệm xử lý lỗi."""
    if r.tools != "rw": return False
    tid = str(env.payload.get("ticket_id") or env.key)
    if o.lead.state.get(tid) not in {"dispatched", "in_progress"}: return False
    try:
        o.lead.rework(tid, f"lần trước lỗi: {str(error)[:500]}")
    except ValueError as ex:
        o._audit("handler_error", {"agent": LEAD_ACTOR, "error": str(ex)[:300]}, ticket_id=tid)
    return True

def _retry_stalled(o: Orchestrator, pid: str, by: str, reason: str) -> bool:
    """Người duyệt gate escalation của dự án: chạy lại event đã lỗi (bỏ dấu đã xử lý, đưa về đầu hàng đợi)."""
    st = o.stalled.get(pid)
    if st is None: return False
    env = next((e for e in o.bus.replay(topic=st["topic"], key=pid) if e.event_id == st["event_id"]), None)
    if env is None: return False
    with o._lock:
        o.processed.discard(env.event_id); o.partial.pop(env.event_id, None); o.stalled.pop(pid, None)
    o._audit("project.retried", {**st, "by": by, "reason": reason}, project_id=pid)
    with o._qlock: o.queue.insert(0, env)
    return True

def _retry_unhandled(o: Orchestrator, subject: str, by: str, reason: str) -> bool:
    """Như `_retry_stalled` nhưng cho event bất kỳ mà agent lỗi không nhánh nào nhận (`unhandled`)."""
    rec = o.unhandled.get(subject)
    if rec is None: return False
    env = next((e for e in o.bus.replay(topic=str(rec["topic"])) if e.event_id == rec["event_id"]), None)
    if env is None: return False
    with o._lock:
        o.processed.discard(env.event_id); o.partial.pop(env.event_id, None); o.unhandled.pop(subject, None)
        o.spec_runtime_reworks.pop(subject, None)  # người cho chạy lại → spec-writer được thêm một lượt sửa tự động
    o._audit("event.retried", {**rec, "subject": subject, "by": by, "reason": reason[:300]}, project_id=o.project_for(env))
    with o._qlock: o.queue.insert(0, env)
    return True

def _record_lessons(o: Orchestrator, rid: str) -> None:
    """Sau nghiệm thu: estimate vs actual mỗi ticket đã closed → supervisor.knowledge + blackboard `knowledge`."""
    for tid in o.lead.release_tickets.get(rid, []):
        if o.lead.state.get(tid) != "closed" or f"lesson:{tid}" in o.once: continue
        o._remember(f"lesson:{tid}")
        t = o.lead.tickets[tid]; b = o.supervisor.budgets.get(tid)
        actual = b.used if b else 0; est = t.estimate_tokens or 0
        lesson = {"ticket_id": tid, "assignee": t.assignee, "estimate_tokens": est, "actual_tokens": actual,
                  "review_tokens": b.review_used if b else 0,
                  "ratio": round(actual / est, 2) if est else None, "retry": t.retry, "risk_tags": t.risk_tags}
        o.supervisor.record_lesson(context=f"{t.project_id}/{tid} {t.title}", problem=f"retry={t.retry}",
                                      solution=t.hint or "", evidence=json.dumps(lesson, ensure_ascii=False))
        o.blackboard.write(ROLE.SUPERVISOR, "knowledge", f"audit-log:lesson:{tid}", json.dumps(lesson, ensure_ascii=False))
