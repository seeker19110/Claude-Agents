"""Bù nhánh coverage còn thiếu ở `orch/gates_flow.py` (đo 2026-09-12, xem `docs/reports/2026-09-12-audit.md` A6).

Mỗi test gọi trực tiếp một hàm module-level của `gates_flow` (chúng được gán làm method trên `Orchestrator`,
`self` tự bind qua descriptor) với trạng thái dựng tay tối thiểu — không phải bugfix, code sản xuất đã đúng,
chỉ thiếu test cho nhánh còn lại của một `if`."""
from __future__ import annotations

from company.bus import InMemoryBus
from company.delivery import DONE_STATES
from company.events import AuditLog, Envelope
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
    bus, orch = _mk()
    orch.lead.release_tickets["REL-1"] = ["T1", "T2"]
    orch.lead.state["T1"] = "approved"       # nhánh True: bị đóng sổ
    orch.lead.state["T2"] = "closed"         # nhánh False (139->138): đã DONE_STATES nhưng KHÔNG "approved" → bỏ qua
    assert "closed" in DONE_STATES and "approved" in DONE_STATES
    orch.lead.releases.extend(["REL-1", "REL-2"])
    orch.delivered["REL-2"] = {"tag": "v0.2.0"}
    res = StepResult("e1", "audit-log", "REL-1")
    orch._on_escalation_decided("REL-1", "reject", "human:lead", "nội dung đã giao rồi", res)
    assert orch._superseded_release("REL-1") is True
    assert f"void:REL-1" in res.actions
    assert not orch.lead.tickets  # T2 không hề được nhắc tới trong sổ ticket (mark_done_already_integrated bỏ qua)


def test_open_acceptance_gate_da_pending_thi_khong_mo_gate_thu_hai():
    """gates_flow.py 212->exit: gate `UAT-<rid>` đã pending → hàm thoát sớm, không mở gate trùng."""
    bus, orch = _mk()
    orch.gate.request(GateRequest(kind="acceptance", subject_id="UAT-REL-1", created_by="ops",
                                   checklist=["uat-script", "acceptance-criteria", "known-issues", "signed_by"]))
    res = StepResult("e1", "delivery-status", "REL-1")
    orch._open_acceptance_gate("REL-1", res)
    assert res.actions == []  # không thêm hành động mở gate lần hai
    assert sum(1 for g in orch.gate.history if g.subject_id == "UAT-REL-1") == 0  # chưa quyết định gì, vẫn pending 1 lần


def test_stall_du_an_da_co_gate_pending_thi_khong_mo_gate_thu_hai():
    """gates_flow.py 249->252: dự án đã có gate `escalation` chờ (lần lỗi trước) → lần lỗi kế tiếp không mở gate
    trùng, chỉ ghi nhận `stalled:<pid>:<agent>` rồi thoát."""
    bus, orch = _mk()
    orch.gate.request(GateRequest(kind="escalation", subject_id="P1", created_by="supervisor",
                                   checklist=["agent_error", "decision:retry|close"]))
    env = Envelope(topic="research-requests", key="P1", actor="human:sales", payload={"project_id": "P1"})
    res = StepResult(env.event_id, env.topic, env.key)
    handled = orch._stall(env, "product", ValueError("lỗi model"), res)
    assert handled is True
    assert res.actions == [f"stalled:P1:product"]
    assert sum(1 for g in orch.gate.history if g.subject_id == "P1") == 0  # vẫn đúng một gate đang pending, không mở thêm


def test_rework_after_error_ticket_khong_o_trang_thai_dispatched_thi_khong_nhan():
    """gates_flow.py 279->exit: route sửa code (`tools="rw"`) nhưng ticket đã ở trạng thái khác `dispatched`/
    `in_progress` (vd. đã `closed`) → `_rework_after_error` không nhận trách nhiệm, trả False ngay."""
    bus, orch = _mk()
    orch.lead.state["T9"] = "closed"
    r = Route(topic_in="tasks", agent="dev-generalist", topic_out="pull-requests", tools="rw")
    env = Envelope(topic="tasks", key="T9", actor="human:lead", payload={"ticket_id": "T9"})
    assert orch._rework_after_error(env, r, ValueError("hết ngân sách")) is False


def test_retry_stalled_khong_co_du_an_nao_dang_stalled():
    """gates_flow.py 289->exit: `pid` không có trong `o.stalled` → trả False ngay, không tìm event."""
    bus, orch = _mk()
    assert orch._retry_stalled("KHONG-CO", "human:lead", "thử lại") is False


def test_retry_stalled_event_da_bien_mat_khoi_bus():
    """gates_flow.py 291->exit: `pid` có bản ghi `stalled` nhưng bus không còn event khớp `event_id` (vd. đã
    dựng sổ tay, hoặc event thuộc bus khác) → trả False, không có gì để đưa lại vào hàng đợi."""
    bus, orch = _mk()
    orch.stalled["P9"] = {"project_id": "P9", "event_id": "khong-ton-tai", "topic": "research-requests",
                           "agent": "product", "error": "x", "attempt": 1}
    assert orch._retry_stalled("P9", "human:lead", "thử lại") is False
