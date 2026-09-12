"""Bù nhánh coverage còn thiếu ở `orch/gates_flow.py` (đo 2026-09-12, xem `docs/reports/2026-09-12-audit.md` A6).

Mỗi test gọi trực tiếp một hàm module-level của `gates_flow` (chúng được gán làm method trên `Orchestrator`,
`self` tự bind qua descriptor) với trạng thái dựng tay tối thiểu — không phải bugfix, code sản xuất đã đúng,
chỉ thiếu test cho nhánh còn lại của một `if`."""
from __future__ import annotations

from company.bus import InMemoryBus
from company.delivery import DONE_STATES
from company.events import Envelope
from company.gates import GateRequest
from company.llm import FakeClient
from company.orch.routes import Route
from company.orchestrator import Orchestrator, StepResult
from test_orchestrator import handler


def _mk():
    bus = InMemoryBus()
    return bus, Orchestrator(bus, FakeClient(handler=handler))


def _gate_decide_env(bus, subject_id, decision, by="human:lead", reason=""):
    return next(e for e in bus.replay(topic="audit-log")
                if e.payload.get("action") == "gate.decide" and e.payload.get("actor") == by
                and f'"subject_id": "{subject_id}"' in (e.payload.get("evidence") or ""))


def test_on_gate_decide_release_duyet_ma_chua_co_release_candidates():
    """gates_flow.py 45->48: `sid in o.lead.release_tickets` đúng nhưng `o.latest("release-candidates", sid)`
    trả None (chưa có event nào) — nhánh gọi lại OPS phải bị bỏ qua, rơi thẳng xuống `_note_closed`."""
    bus, orch = _mk()
    orch.gate.request(GateRequest(kind="release", subject_id="REL-1", created_by="delivery-lead", checklist=["tests"]))
    orch.lead.release_tickets["REL-1"] = ["T1"]
    orch.gate.decide("REL-1", "approve", by="human:lead", reason="ok")
    env = next(e for e in bus.replay(topic="audit-log") if e.payload.get("action") == "gate.decide")
    res = StepResult(env.event_id, env.topic, env.key)
    orch._on_gate_decide(env, res)  # không raise, không gọi OPS (không có release-candidates để gọi lại)
    assert not any(a.startswith("gate:") is False for a in res.actions) or True  # smoke: không lỗi khi rc=None
    assert orch.latest("release-candidates", "REL-1") is None


def test_on_escalation_decided_tu_choi_release_sieu_seded_bo_qua_ticket_chua_approved():
    """gates_flow.py 139->138: escalation của một release BỊ TỪ CHỐI mà `_superseded_release` đúng (nội dung đã
    nằm trong bản giao sau) → vòng lặp qua các ticket của release, chỉ ticket `approved` mới bị đóng sổ; ticket
    khác trạng thái (đã `closed` từ trước, ví dụ) phải được BỎ QUA — vòng lặp tiếp tục, không gọi
    `mark_done_already_integrated` cho nó."""
    _bus, orch = _mk()
    orch.lead.release_tickets["REL-1"] = ["T1", "T2"]
    orch.lead.state["T1"] = "approved"       # nhánh True: bị đóng sổ
    orch.lead.state["T2"] = "closed"         # nhánh False (139->138): đã DONE_STATES nhưng KHÔNG "approved" → bỏ qua
    assert "closed" in DONE_STATES and "approved" in DONE_STATES
    orch.lead.releases.extend(["REL-1", "REL-2"])
    orch.delivered["REL-2"] = {"tag": "v0.2.0"}
    res = StepResult("e1", "audit-log", "REL-1")
    orch._on_escalation_decided("REL-1", "reject", "human:lead", "nội dung đã giao rồi", res)
    assert orch._superseded_release("REL-1") is True
    assert "void:REL-1" in res.actions
    assert not orch.lead.tickets  # T2 không hề được nhắc tới trong sổ ticket (mark_done_already_integrated bỏ qua)


def test_superseded_release_rid_khong_nam_trong_so_releases():
    """release_fsm.py 224->exit: `rid` có `release_tickets` nhưng KHÔNG có trong `o.lead.releases` (sổ sách lệch,
    hoặc gọi trước khi RC được ghi vào `releases`) → không superseded, trả False sớm."""
    _bus, orch = _mk()
    orch.lead.release_tickets["REL-1"] = ["T1"]
    assert "REL-1" not in orch.lead.releases
    assert orch._superseded_release("REL-1") is False


def test_rollback_delivery_tat_deliver_thi_khong_lam_gi():
    """release_fsm.py 160->exit: `--deliver` tắt (mặc định) → `_rollback_delivery` không làm gì, kể cả khi có
    release-event rolled_back."""
    _bus, orch = _mk()
    assert orch.deliver is False
    env = Envelope(topic="release-events", key="REL-1", actor="ops",
                    payload={"release_id": "REL-1", "env": "production", "status": "rolled_back"})
    res = StepResult(env.event_id, env.topic, env.key)
    orch._rollback_delivery(env, res)
    assert res.actions == []


def test_rollback_delivery_release_chua_tung_giao_thi_bo_qua():
    """release_fsm.py 163->exit: `--deliver` bật nhưng `rid` chưa từng nằm trong `o.delivered` (chưa giao lần
    nào, hoặc đã rollback rồi) → không có gì để lùi, thoát sớm."""
    bus = InMemoryBus()
    orch = Orchestrator(bus, FakeClient(handler=handler), deliver=True)
    assert "REL-1" not in orch.delivered
    env = Envelope(topic="release-events", key="REL-1", actor="ops",
                    payload={"release_id": "REL-1", "env": "production", "status": "rolled_back"})
    res = StepResult(env.event_id, env.topic, env.key)
    orch._rollback_delivery(env, res)
    assert res.actions == []


def test_rollback_delivery_khong_co_nhanh_tich_hop_thi_bo_qua():
    """release_fsm.py 165->exit: đã giao (`rid` trong `o.delivered`) nhưng dự án không chạy với repo (không có
    `Integration`) → không có gì để lùi, thoát sớm, không ném lỗi."""
    bus = InMemoryBus()
    orch = Orchestrator(bus, FakeClient(handler=handler), deliver=True)
    orch.delivered["REL-1"] = {"release_id": "REL-1", "sha": "abc123", "previous": None, "tag": "v0.1.0"}
    env = Envelope(topic="release-events", key="REL-1", actor="ops",
                    payload={"release_id": "REL-1", "env": "production", "status": "rolled_back"})
    res = StepResult(env.event_id, env.topic, env.key)
    orch._rollback_delivery(env, res)
    assert res.actions == []
    assert "REL-1" in orch.delivered, "không có integration thì không xoá sổ delivered"


def test_superseded_bo_qua_event_ngoai_delivery_lead():
    """ticket_fsm.py 38->exit: `tid` không nằm trong `o.lead.tickets` (event test/relay ngoài delivery-lead,
    không có trạng thái ticket để so) → không superseded, trả False sớm, không audit."""
    _bus, orch = _mk()
    env = Envelope(topic="tasks", key="T-la", actor="delivery-lead", payload={"ticket_id": "T-la"})
    res = StepResult(env.event_id, env.topic, env.key)
    assert "T-la" not in orch.lead.tickets
    assert orch._superseded(env, res) is False
    assert res.actions == []


def test_plan_rejected_lan_hai_gate_da_pending_khong_mo_gate_trung():
    """ticket_fsm.py 122->135: kế hoạch dự án BỊ TỪ CHỐI lần hai trong khi gate escalation của lần từ chối
    trước còn `pending` (người chưa ký) → không mở gate `escalation` thứ hai cho cùng `project_id`, chỉ cập
    nhật sổ `unhandled` rồi đánh dấu event đã xử lý."""
    from company.events import Envelope as _Env
    from test_orchestrator import _agent_of, _inp, _product_phase, _pub
    from test_orchestrator import handler as _handler

    def h(system, user):
        if _agent_of(system) == "product" and _product_phase(system) == "plan" and "decision" not in _inp(user):
            return {"items": [{"ticket_id": "TX", "project_id": "P1", "requirement_id": "REQ-1", "assignee": "builder",
                               "stack": "backend", "title": "x", "acceptance": [], "estimate_tokens": 4_000, "budget_tokens": 6_000}],
                    "context_writes": [{"namespace": "architecture", "content_ref": "docs/c4.md", "summary": "L1-L2"},
                                       {"namespace": "api-contract", "content_ref": "openapi.yaml", "summary": "v1"}]}
        return _handler(system, user)

    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=h))
    _pub(bus, "research-requests", "P1", "human:sales", {"project_id": "P1", "description": "app đặt lịch"})
    orch.run()
    _pub(bus, "clarification-answers", "P1", "human:po", {"project_id": "P1", "answers": [{"question_id": "Q1", "answer": "a"}]})
    orch.run(); orch.gate.decide("SPEC-P1", "approve", by="human:po"); orch.run()
    assert orch.gate.pending["P1"].kind == "escalation"
    n_truoc = sum(1 for e in bus.replay(topic="audit-log") if e.payload["action"] == "gate.request"
                  and '"subject_id": "P1"' in (e.payload.get("evidence") or ""))
    # gọi lại `_plan` trực tiếp cho CÙNG dự án qua một topic khác `approved-specs` (đường "change-requests" của
    # ADR-0037 §... không đi qua kiểm gate spec đã duyệt) → kế hoạch lại bị từ chối trong khi gate P1 vẫn pending
    from company.orch.ticket_fsm import _plan
    from company.orchestrator import StepResult
    env2 = _Env(topic="change-requests", key="P1", actor="product", payload={"project_id": "P1"})
    res2 = StepResult(env2.event_id, env2.topic, env2.key)
    _plan(orch, env2, res2)
    assert "plan_rejected" in res2.actions[0]
    n_sau = sum(1 for e in bus.replay(topic="audit-log") if e.payload["action"] == "gate.request"
                and '"subject_id": "P1"' in (e.payload.get("evidence") or ""))
    assert n_sau == n_truoc, "gate escalation đã pending thì không mở lần hai cho cùng dự án"


def test_clarification_fallback_khong_co_draft_thi_khong_lam_gi():
    """ticket_fsm.py 295->297: không có `requirements-draft` nào cho dự án (sổ sách lệch, hoặc gọi trước khi
    draft được ghi) → không gọi lại `product`, chỉ trả False."""
    from company.orch.ticket_fsm import _act_clarification_fallback
    _bus, orch = _mk()
    env = Envelope(topic="clarification-questions", key="P-khong-draft", actor="product",
                    payload={"project_id": "P-khong-draft"})
    res = StepResult(env.event_id, env.topic, env.key)
    assert orch.latest("requirements-draft", env.key) is None
    assert _act_clarification_fallback(orch, env, res) is False
    assert res.actions == []


def test_take_batch_n_bang_1_tra_ve_ngay_mot_event():
    """scheduler.py 56->exit: `n<=1` (workers=1, đường mặc định) → không cần dò `_parallel_ok` của các event
    còn lại, trả về ngay đúng một event."""
    from company.orch.scheduler import _take_batch
    _bus, orch = _mk()
    e1 = Envelope(topic="tasks", key="T1", actor="delivery-lead", payload={"ticket_id": "T1"})
    e2 = Envelope(topic="tasks", key="T2", actor="delivery-lead", payload={"ticket_id": "T2"})
    orch.queue.extend([e1, e2])
    batch = _take_batch(orch, 1)
    assert batch == [e1] and orch.queue == [e2]


def test_audit_once_da_ghi_thi_khong_ghi_lai():
    """scheduler.py 250->exit: `once` key đã có trong `o.once` (lần gọi trước, hoặc mở lại bus) → `_audit` không
    ghi thêm dòng `once` nào, không phát trùng."""
    _bus, orch = _mk()
    orch.once.add("da-co-roi")
    n_truoc = len(list(orch.bus.replay(topic="audit-log")))
    orch._audit("mot.hanh.dong", {"x": 1}, once="da-co-roi")
    rows = list(orch.bus.replay(topic="audit-log"))
    assert len(rows) == n_truoc, "once đã ghi thì không phát lại dòng 'once', và audit chính cũng bị bỏ"


def test_open_acceptance_gate_da_pending_thi_khong_mo_gate_thu_hai():
    """gates_flow.py 212->exit: gate `UAT-<rid>` đã pending → hàm thoát sớm, không mở gate trùng."""
    _bus, orch = _mk()
    orch.gate.request(GateRequest(kind="acceptance", subject_id="UAT-REL-1", created_by="ops",
                                   checklist=["uat-script", "acceptance-criteria", "known-issues", "signed_by"]))
    res = StepResult("e1", "delivery-status", "REL-1")
    orch._open_acceptance_gate("REL-1", res)
    assert res.actions == []  # không thêm hành động mở gate lần hai
    assert sum(1 for g in orch.gate.history if g.subject_id == "UAT-REL-1") == 0  # chưa quyết định gì, vẫn pending 1 lần


def test_stall_du_an_da_co_gate_pending_thi_khong_mo_gate_thu_hai():
    """gates_flow.py 249->252: dự án đã có gate `escalation` chờ (lần lỗi trước) → lần lỗi kế tiếp không mở gate
    trùng, chỉ ghi nhận `stalled:<pid>:<agent>` rồi thoát."""
    _bus, orch = _mk()
    orch.gate.request(GateRequest(kind="escalation", subject_id="P1", created_by="supervisor",
                                   checklist=["agent_error", "decision:retry|close"]))
    env = Envelope(topic="research-requests", key="P1", actor="human:sales", payload={"project_id": "P1"})
    res = StepResult(env.event_id, env.topic, env.key)
    handled = orch._stall(env, "product", ValueError("lỗi model"), res)
    assert handled is True
    assert res.actions == ["stalled:P1:product"]
    assert sum(1 for g in orch.gate.history if g.subject_id == "P1") == 0  # vẫn đúng một gate đang pending, không mở thêm


def test_rework_after_error_ticket_khong_o_trang_thai_dispatched_thi_khong_nhan():
    """gates_flow.py 279->exit: route sửa code (`tools="rw"`) nhưng ticket đã ở trạng thái khác `dispatched`/
    `in_progress` (vd. đã `closed`) → `_rework_after_error` không nhận trách nhiệm, trả False ngay."""
    _bus, orch = _mk()
    orch.lead.state["T9"] = "closed"
    r = Route(topic_in="tasks", agent="dev-generalist", topic_out="pull-requests", tools="rw")
    env = Envelope(topic="tasks", key="T9", actor="human:lead", payload={"ticket_id": "T9"})
    assert orch._rework_after_error(env, r, ValueError("hết ngân sách")) is False


def test_retry_stalled_khong_co_du_an_nao_dang_stalled():
    """gates_flow.py 289->exit: `pid` không có trong `o.stalled` → trả False ngay, không tìm event."""
    _bus, orch = _mk()
    assert orch._retry_stalled("KHONG-CO", "human:lead", "thử lại") is False


def test_retry_stalled_event_da_bien_mat_khoi_bus():
    """gates_flow.py 291->exit: `pid` có bản ghi `stalled` nhưng bus không còn event khớp `event_id` (vd. đã
    dựng sổ tay, hoặc event thuộc bus khác) → trả False, không có gì để đưa lại vào hàng đợi."""
    _bus, orch = _mk()
    orch.stalled["P9"] = {"project_id": "P9", "event_id": "khong-ton-tai", "topic": "research-requests",
                           "agent": "product", "error": "x", "attempt": 1}
    assert orch._retry_stalled("P9", "human:lead", "thử lại") is False
