"""Bảng chuyển giao `orch/fsm.py` (K1.7, ADR-0034): cơ chế `step()` + tính toàn vẹn của
`TICKET_TRANSITIONS`/`RELEASE_TRANSITIONS`, và ba cặp "event cũ/trùng lặp" phải bị bỏ qua có audit,
không exception (khuôn TRAPS.md §1 khuôn 4: event cũ không được phát lại như mới).

`Transition` không có trường `dst` tường minh (khác đề xuất gốc trong đặc tả) vì bảng ở đây định tuyến
theo TOPIC của event (như `process()` cũ làm), không theo trạng thái ticket — nguồn sự thật trạng thái
vẫn là `lead.state` (delivery.py, ADR-0034). "đúng dst" ở đây nghĩa là: đúng HÀNH ĐỘNG được gọi cho đúng
topic, và với ba cặp cấm — không hành động nào chạy (audit + không lỗi), thay vì gọi nhầm agent."""
from __future__ import annotations

import json

from company.bus import InMemoryBus
from company.events import Envelope
from company.llm import FakeClient
from company.orch import fsm
from company.orch.release_fsm import RELEASE_TRANSITIONS
from company.orch.ticket_fsm import TICKET_TRANSITIONS
from company.orchestrator import Orchestrator, StepResult
from test_orchestrator import _drive_to_plan, _pub, handler
from test_tools_and_agentic import _init_repo


def _orch(bus=None):
    if bus is None: bus = InMemoryBus()  # InMemoryBus có __len__: bus rỗng bị coi là falsy, `bus or ...` sẽ tráo nhầm
    return Orchestrator(bus, FakeClient(handler=handler))


# ---------- tính toàn vẹn của bảng ----------

def test_moi_dong_bang_co_ten_duy_nhat_va_topic_khong_rong():
    all_rows = [*TICKET_TRANSITIONS, *RELEASE_TRANSITIONS]
    names = [t.name for t in all_rows]
    assert len(names) == len(set(names)), f"tên trùng: {names}"
    for t in all_rows:
        assert t.topics, f"{t.name}: topics rỗng"
        assert t.phase in {"pre", "post"}, f"{t.name}: phase lạ {t.phase!r}"


def test_bang_release_co_ca_hai_phase_theo_dung_vi_tri_quanh_routes():
    """`integrate_rc`/`integrate_approved` phải chạy TRƯỚC vòng ROUTES (`_integrate_approved` cần chạy trước khi
    ROUTES giao việc cho ticket phụ thuộc); ba nhánh sau (deploy/rollback/pending_human/acceptance) chạy SAU."""
    by_name = {t.name: t.phase for t in RELEASE_TRANSITIONS}
    assert by_name["integrate_rc"] == "pre" and by_name["integrate_approved"] == "pre"
    assert by_name["production_deploy_or_rollback"] == "post"
    assert by_name["release_pending_human"] == "post"
    assert by_name["acceptance_close"] == "post"


# ---------- cơ chế step(): guard, terminal/non-terminal, lọc theo phase ----------

def test_step_bo_qua_hang_khac_topic():
    calls = []
    table = [fsm.Transition("x", frozenset({"tasks"}), lambda o, e, r: (calls.append(1), False)[1])]
    env = Envelope(topic="pull-requests", key="T1", actor="a", payload={})
    assert fsm.step(table, object(), env, StepResult("e1", env.topic, env.key)) is False
    assert not calls


def test_step_chay_hang_khop_topic_va_guard():
    calls = []
    table = [fsm.Transition("x", frozenset({"tasks"}), lambda o, e, r: (calls.append(1), False)[1],
                            guard=lambda e, o: e.payload.get("ok"))]
    env_no = Envelope(topic="tasks", key="T1", actor="a", payload={})
    env_yes = Envelope(topic="tasks", key="T1", actor="a", payload={"ok": True})
    fsm.step(table, object(), env_no, StepResult("e1", "tasks", "T1"))
    assert not calls, "guard sai không được chạy action"
    fsm.step(table, object(), env_yes, StepResult("e2", "tasks", "T1"))
    assert calls == [1]


def test_step_dung_ngay_khi_action_tra_true_khong_chay_hang_sau():
    calls = []
    table = [
        fsm.Transition("a", frozenset({"tasks"}), lambda o, e, r: (calls.append("a"), True)[1]),
        fsm.Transition("b", frozenset({"tasks"}), lambda o, e, r: (calls.append("b"), False)[1]),
    ]
    env = Envelope(topic="tasks", key="T1", actor="a", payload={})
    stopped = fsm.step(table, object(), env, StepResult("e1", "tasks", "T1"))
    assert stopped is True and calls == ["a"], "hàng b không được chạy sau khi hàng a báo dừng"


def test_step_loc_dung_phase_khong_lan_sang_phase_khac():
    calls = []
    table = [
        fsm.Transition("pre_row", frozenset({"tasks"}), lambda o, e, r: (calls.append("pre"), False)[1], phase="pre"),
        fsm.Transition("post_row", frozenset({"tasks"}), lambda o, e, r: (calls.append("post"), False)[1], phase="post"),
    ]
    env = Envelope(topic="tasks", key="T1", actor="a", payload={})
    fsm.step(table, object(), env, StepResult("e1", "tasks", "T1"), phase="pre")
    assert calls == ["pre"]
    fsm.step(table, object(), env, StepResult("e2", "tasks", "T1"), phase="post")
    assert calls == ["pre", "post"]


# ---------- ba cặp cấm: event cũ/trùng lặp phải bị bỏ qua có audit, không exception (TRAPS.md khuôn 4) ----------

def test_cap_cam_task_cu_cho_ticket_da_vuot_qua_dispatched():
    """`tasks` (dòng `superseded` của TICKET_TRANSITIONS) cho ticket đã đi QUA khỏi `dispatched` không được giao
    lại cho backend — event cũ, không phải trạng thái hiện tại. `handler` giả lập chạy hết review/PR trong một
    `run()` (không dừng ở `in_review`), nên ticket đã tới `merged` khi ta phát lại `tasks` gốc."""
    bus = InMemoryBus(); orch = _orch(bus)
    _drive_to_plan(bus, orch)
    orch.run()
    assert orch.lead.state["T1"] == "merged"
    old = bus.latest("tasks", "T1")
    orch.processed.discard(old.event_id)  # mô phỏng event cũ được phát lại (mở lại bus / xử lý lại)
    res = orch.process(old)
    assert res is not None and any(a.startswith("superseded:") for a in res.actions)
    assert orch.lead.state["T1"] == "merged", "không bị đá lại về dispatched"


def test_cap_cam_release_candidate_cho_rc_da_bi_huy(tmp_path):
    """`release-candidates` (dòng `integrate_rc`) cho một RC đã `void` phải dừng êm — không lỗi, không deploy lại.
    `_integrate` chỉ kiểm `void_releases` khi CÓ nhánh tích hợp (`_has_integration()`), nên cần `repo=`."""
    repo = _init_repo(tmp_path / "repo")
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler), repo=repo, base="main")
    rc = _pub(bus, "release-candidates", "R1", "delivery-lead",
             {"release_id": "R1", "project_id": "P1", "tickets": ["T1"], "version": "1.0.0"})
    orch.void_releases.add("R1")
    res = orch.process(rc)
    assert res is not None and res.actions == [], "RC đã void: không hành động nào chạy, không lỗi"
    audits = [e.payload["action"] for e in bus.replay(topic="audit-log") if e.payload["action"] == "orchestrated"]
    assert audits, "event vẫn được _mark, không treo lại hàng đợi"


def test_cap_cam_plan_input_trung_khi_da_co_plan_dang_cho_gate():
    """`approved-specs` publish lặp trong lúc `PLAN-P1-1` còn chờ gate → `plan.duplicate_spec`, không sinh plan thứ hai
    (dòng `plan` của TICKET_TRANSITIONS gọi `_plan`, và `_plan` tự chặn trùng — bảng chỉ định tuyến, không nhân đôi)."""
    bus = InMemoryBus(); orch = _orch(bus)
    _drive_to_plan(bus, orch)
    spec = bus.latest("approved-specs", "P1")
    _pub(bus, "approved-specs", "P1", "spec-writer", spec.payload); orch.run()
    assert list(orch.plans) == ["PLAN-P1-1"]
    dup = [json.loads(e.payload["evidence"]) for e in bus.replay(topic="audit-log")
           if e.payload["action"] == "plan.duplicate_spec"]
    assert dup and dup[0]["existing"] == ["PLAN-P1-1"]
