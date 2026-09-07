"""Khôi phục trạng thái phiên từ audit-log khi mở lại bus (tách khỏi orchestrator.py, ADR-0034).

`rehydrate(o)` chạy MỘT LẦN trong `Orchestrator.__init__`, cho MỌI tiến trình kể cả lệnh chỉ-đọc (`status`,
`report`, `show`) — không ghi audit ở đây. Thứ tự duyệt log là nguồn sự thật; mỗi nhánh dựng lại đúng một biến
RAM đã mất khi tiến trình trước dừng.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ..events import Envelope
from ..roles import ROLE
from ..runner import CONTEXT_ONLY
from .routes import ACTOR, ROUTES

if TYPE_CHECKING:
    from ..orchestrator import Orchestrator


def rehydrate(o: Orchestrator) -> None:
    from ..orchestrator import _evidence
    # Một lần duyệt log, không hai: `replay()` trên bus bền vững parse lại từng envelope, nên quét đôi là nhân đôi
    # thời gian mở lại một dự án đã chạy lâu.
    log = list(o.bus.replay())
    # Thứ tự trong log của lần `orchestrated` / `project.retried` gần nhất cho từng event: dùng ở cuối hàm
    # để nhận lại lệnh thử-lại chưa kịp chạy (xem chú thích ở đó).
    last_done: dict[str, int] = {}
    last_retry: dict[str, tuple[int, dict[str, Any]]] = {}   # event_id → (thứ tự trong log, bản ghi stalled)
    hen: dict[str, tuple[str, str]] = {}                     # event_id → (mốc hẹn ISO, lý do hoãn)
    for i, env in enumerate(log):
        if env.topic == "audit-log":
            a = env.payload; d = _evidence(a)
            if a["action"] == "project.retried" and d.get("event_id"): last_retry[str(d["event_id"])] = (i, d)
            if a["actor"] == ACTOR and a["action"] == "orchestrated":
                o.processed.add(d["event_id"]); last_done[str(d["event_id"])] = i
            elif a["actor"] == ACTOR and a["action"] == "once": o.once.add(d["key"])
            elif a["action"] == "plan.proposed":
                # ADR-0037: `plan.proposed` chỉ được ghi khi `_check_plan` không trả problem nào, và lúc đó ticket
                # đã được giao ngay — nên dựng lại trạng thái phải giao lại ở ĐÚNG chỗ này trong log, không chờ
                # một `gate.decide` không bao giờ tới nữa (khuôn 2 `TRAPS.md`: state chỉ sống trong RAM).
                # Giao ở đây cũng đúng thứ tự thời gian hơn nhánh cũ: mọi `tasks`/`ticket.blocked` của kế hoạch
                # này nằm SAU trong log nên vẫn ghi đè được trạng thái `dispatched`/`waiting` dựng ở đây.
                o.plans[d["plan_id"]] = d
                o.lead.plans_ok.add(str(d["plan_id"]))
                o._dispatch_plan(str(d["plan_id"]), replaying=True)
            elif a["action"] == "release.void": o._void(d["release_id"])
            elif a["action"] == "release.staged": o.release_sha[d["release_id"]] = d["sha"]
            elif a["action"] == "delivery.done": o.delivered[d["release_id"]] = d
            elif a["action"] == "delivery.rolled_back": o.delivered.pop(d["release_id"], None)
            elif a["action"] == "ticket.abandoned": o.lead.abandon(d["ticket_id"])
            elif a["action"] == "defer.until" and d.get("event_id"):
                hen[str(d["event_id"])] = (str(d.get("until") or ""), str(d.get("reason") or "transient:?"))
            elif a["action"] == "ticket.blocked":
                # xem chú thích ở `DeliveryLead._retry`: không dựng lại `blocked` thì ticket quay về
                # `dispatched` và người duyệt escalation bấm approve cũng không mở lại được nó.
                o.lead.state[str(d["ticket_id"])] = "blocked"
            elif a["action"] == "ticket.already_integrated" and d.get("state"):
                # Đối xứng với `ticket.blocked` ở trên: người đã quyết "việc này xong rồi" (code đã ở nhánh
                # tích hợp, xem `DeliveryLead.mark_done_already_integrated`). Không dựng lại thì mở lại bus là
                # `ticket.blocked` CŨ (nằm trước trong log) thắng, ticket quay về `blocked` và vòng lặp
                # escalation → duyệt → agent không có gì sửa → block mở lại từ đầu.
                o.lead.state[str(d["ticket_id"])] = str(d["state"])
            elif a["action"] == "integration.merged":
                o.integrated.add(d["ticket_id"])
                prev_r, o.lead.replaying = o.lead.replaying, True
                try: o.lead.mark_integrated(d["ticket_id"])
                finally: o.lead.replaying = prev_r
            elif a["action"] == "threat_model.missing": o.missing_threat_model.add(d["subject_id"])
            elif a["action"] == "project.stalled":
                o.stalled[d["project_id"]] = d; o.stall_count[d["event_id"]] += 1
            elif a["action"] in {"project.retried", "project.closed"}: o.stalled.pop(d["project_id"], None)
            elif a["action"] == "agent_error_unhandled" and d.get("subject"): o.unhandled[str(d["subject"])] = d
            elif a["action"] == "plan_rejected" and d.get("source_event"):
                o.unhandled[str(d["project_id"])] = {"agent": ROLE.LEAD, "topic": d.get("source_topic"),
                                                        "event_id": d["source_event"], "subject": str(d["project_id"])}
            elif a["action"] == "spec.runtime_missing": o.spec_runtime_reworks[str(d["project_id"])] += 1
            elif a["action"] == "spec.runtime_escalated" and d.get("source_event"):
                o.unhandled[str(d["project_id"])] = {"agent": ROLE.PRODUCT, "topic": d.get("source_topic"),
                                                        "event_id": d["source_event"], "subject": str(d["project_id"]),
                                                        "error": f"spec_runtime_missing: {str(d.get('reason', ''))[:200]}"}
            elif a["action"] in {"event.retried", "event.abandoned"}:
                o.unhandled.pop(str(d.get("subject")), None)
                o.spec_runtime_reworks.pop(str(d.get("subject")), None)
            elif a["action"] == "gate.decide":
                if d.get("subject_id"): o.escalation_decided[str(d["subject_id"])] += 1
            elif a["action"] == "integration.conflict":
                o.conflict_retries[str(d["ticket_id"])] += 1
            elif a["action"] == "release.finding_waived":
                o.lead.release_waived[str(d["release_id"])].add(str(d["source"]))
            elif a["action"] == "debt.escalated": o.debt_gate[str(d["project_id"])] = d
            elif a["action"] == "debt.decided": o.debt_gate.pop(str(d["project_id"]), None)
        elif env.topic == "supervisor-actions": o._track_pause(env)
        elif env.topic == "shared-context": o.blackboard._on(env)
        else:
            if env.topic == "research-requests": o._learn_repo(env, replaying=True)
            o.lead.replay(env)
        if env.actor in o.agents and env.causation_id:
            # Đầu ra agent đã publish cho event chưa được đánh dấu xong (crash giữa hai route): agent đó KHÔNG chạy
            # lại khi mở lại — tốn token và sinh PR/review trùng. `partial` được dựng lại từ causation_id.
            o.partial.setdefault(env.causation_id, set()).add(f"{env.actor}:{env.topic}")  # slot = "<agent>:<topic_out>" (PR-5b)
        o.supervisor.replay(env)
    # Lệnh thử-lại chỉ sống trong RAM: `_retry_stalled` bỏ dấu `processed` rồi đẩy event vào `o.queue`.
    # Restart giữa lúc đó là mất trắng — event vẫn mang dấu `orchestrated` của LẦN LỖI, nên hàng đợi dựng lại
    # loại nó ra và dự án nằm im vĩnh viễn dù người đã bấm duyệt. Đo được khi chạy thật (2026-09-04): duyệt
    # gate escalation lúc 06:51:31, restart lúc 06:51:45, sau đó không một dòng `orchestrated` nào nữa.
    # Ai đã bảo "chạy lại" mà event chưa được xử lý lại thì phải bỏ dấu để hàng đợi nhận lại — TRỪ khi việc
    # đó đã có người khác làm xong trong lúc chờ (xem `_retry_con_can`).
    reopened = {eid for eid, (idx, rec) in last_retry.items()
                if idx > last_done.get(eid, -1) and o._retry_con_can(log, idx, rec)}
    # KHÔNG audit ở đây: `_rehydrate` chạy trong MỌI tiến trình, kể cả lệnh chỉ-đọc (`status`, `report`,
    # `show`, console). Ghi bus từ đường đọc là mỗi lần xem trạng thái lại thêm một dòng rác — chính tôi
    # đã mắc và thấy nó trong log. Việc mở lại sẽ tự hiện ra ở dòng `orchestrated` khi event thật sự chạy.
    o.processed -= reopened
    o.partial = {k: v for k, v in o.partial.items() if k not in o.processed}
    o.queue = [e for e in log if o._actionable(e) and e.event_id not in o.processed]
    o._nap_lai_hen(hen)



def _nap_lai_hen(o: Orchestrator, hen: dict[str, tuple[str, str]]) -> None:
    """Event còn hẹn chờ thì vào `deferred`, KHÔNG vào hàng đợi chạy ngay.

    Không có bước này thì bản ghi `defer.until` chỉ là một dòng log đẹp: `_rehydrate` vẫn đẩy event vào
    `o.queue` và nhịp chạy đầu tiên gọi thẳng backend đang cạn quota.

    Mốc hẹn lưu theo GIỜ TƯỜNG nên quy được về `monotonic` của tiến trình này; hẹn đã qua thì bỏ, để event
    chạy bình thường. Event đã xong không nằm trong hàng đợi nên hẹn cũ của nó vô hại."""
    if not hen: return
    gio, mono = datetime.now(UTC), time.monotonic()
    giu: list[Envelope] = []
    for e in o.queue:
        moc, ly_do = hen.get(e.event_id, ("", ""))
        con = 0.0
        if moc:
            try: con = (datetime.fromisoformat(moc) - gio).total_seconds()
            except ValueError: con = 0.0          # mốc hỏng: thà chạy còn hơn kẹt vĩnh viễn
        if con > 0:
            o.deferred[e.event_id] = (e, ly_do or "transient:?")
            o.defer_until[e.event_id] = mono + con
        else:
            giu.append(e)
    o.queue = giu



def _retry_con_can(o: Orchestrator, log: list[Envelope], idx: int, rec: dict[str, Any]) -> bool:
    """Lệnh chạy lại còn ý nghĩa không, hay việc đã có người khác làm xong trong lúc chờ?

    Lệnh chạy lại chỉ sống trong RAM nên có thể nằm chờ rất lâu (người duyệt gate xong, tiến trình chết,
    hết hạn mức model...). Trong lúc đó dự án vẫn có thể đi tiếp bằng đường khác. Chạy lại một việc đã xong
    là đốt một lượt model đắt tiền để sinh ra bản trùng. Đo được khi chạy thật (2026-09-04): lệnh chạy lại
    ghi lúc 07:00:48, `spec-writer` sau đó thành công ba lần (08:15, 08:22, 08:28), nhưng lệnh cũ vẫn nổ
    lúc 09:54:42 và tiêu 317 giây `claude-opus-5` chỉ để hệ thống báo `plan.duplicate_spec` ở bước sau.

    Cách nhận biết: tra ROUTES xem event đó lẽ ra sinh ra topic nào; nếu topic đó đã có event mới cho cùng
    khoá SAU thời điểm ra lệnh, thì việc đã xong."""
    outs = {r.topic_out for r in ROUTES
            if r.topic_in == rec.get("topic") and r.agent == rec.get("agent")}
    outs.discard(CONTEXT_ONLY)
    if not outs: return True          # không suy ra được route → giữ nguyên hành vi cũ, thà chạy lại còn hơn kẹt
    key = str(rec.get("project_id") or "")
    return not any(e.topic in outs and e.key == key for e in log[idx + 1:])
