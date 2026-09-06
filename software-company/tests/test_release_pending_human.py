"""release-engineer tự dừng (`status=pending_human`) thì phải có người được hỏi, và duyệt là chạy lại được ngay.

Trước đây không có gì xử lý trạng thái này: không gate nào mở, `status` xanh, RC nằm im vô hạn; muốn chạy lại phải
DỪNG orchestrator để gọi `redeploy` (lease). Đo được 2026-09-06 (QLKH): 10 RC kẹt đúng kiểu này (7 staging, 3
production), `gates_pending={}`.
"""
from __future__ import annotations

from company.bus import InMemoryBus
from company.llm import FakeClient
from company.orchestrator import Orchestrator
from test_orchestrator import _agent_of, _drive_to_plan, _inp, handler


def _pausing_release_engineer(pause_envs: dict[str, int]):
    """release-engineer trả `pending_human` `n` lần đầu cho mỗi (env, release) rồi mới `deployed`."""
    seen: dict[str, int] = {}
    def h(system, user):
        a, p = _agent_of(system), _inp(user)
        if a == "release-engineer":
            env = p["target_env"]; k = f"{env}:{p['release_id']}"; seen[k] = seen.get(k, 0) + 1
            if seen[k] <= pause_envs.get(env, 0):
                return {"release_id": p["release_id"], "version": "1.0.0", "env": env, "status": "pending_human",
                        "summary": f"dừng {env}: chờ người ({p.get('human_hint') or 'không hint'})"}
        return handler(system, user)
    h.seen = seen  # type: ignore[attr-defined]
    return h


def _events(bus, rid, env):
    return [e.payload["status"] for e in bus.replay(topic="release-events") if e.key == rid and e.payload["env"] == env]


def test_staging_pending_human_mo_gate_va_duyet_thi_chay_lai():
    h = _pausing_release_engineer({"staging": 1})
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=h))
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    assert _events(bus, "REL-001", "staging") == ["pending_human"]
    g = orch.gate.pending.get("REL-001")
    assert g is not None and g.kind == "escalation" and g.created_by == "release-engineer", \
        "agent tự dừng mà không ai được hỏi = bế tắc im lặng; phải mở gate escalation cho chính release"
    assert "decision:redeploy|close" in g.checklist
    assert any(e.payload["action"] == "release.pending_human" for e in bus.replay(topic="audit-log"))

    orch.gate.decide("REL-001", "approve", by="human:lead", reason="nợ đã đóng, chạy lại staging"); orch.run()
    assert _events(bus, "REL-001", "staging") == ["pending_human", "deployed"], "duyệt = chạy lại lượt staging, không cần dừng orchestrator"
    assert any(e.payload["action"] == "release.rerun" for e in bus.replay(topic="audit-log"))
    # lý do người duyệt tới tay agent làm hint (lượt thứ hai mới deployed nên summary của lượt đó không còn; kiểm qua lượt pending)
    assert orch.lead.state["T1"] == "merged", "staging deployed → ticket merged → QA hồi quy chạy → Gate 3"
    assert "REL-001" in orch.gate.pending and orch.gate.pending["REL-001"].kind == "release"


def test_production_pending_human_mo_gate_va_duyet_thi_chay_lai_production():
    h = _pausing_release_engineer({"production": 1})
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=h))
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    orch.gate.decide("REL-001", "approve", by="human:release-manager"); orch.run()  # Gate 3
    assert _events(bus, "REL-001", "production") == ["pending_human"]
    assert orch.gate.pending["REL-001"].kind == "escalation"
    orch.gate.decide("REL-001", "approve", by="human:lead", reason="runbook đã có, deploy"); orch.run()
    assert _events(bus, "REL-001", "production") == ["pending_human", "deployed"]
    assert orch.lead.state["T1"] == "released"


def test_tu_choi_escalation_cua_release_dang_pending_thi_tra_ticket_ve_lam_lai():
    h = _pausing_release_engineer({"staging": 5})
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=h))
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    assert orch.gate.pending["REL-001"].kind == "escalation"
    # T1 chưa merged (staging chưa deployed) nên rework không đổi được state — nhưng không được chạy lại
    orch.gate.decide("REL-001", "reject", by="human:lead", reason="nội dung sai thật"); orch.run()
    assert _events(bus, "REL-001", "staging") == ["pending_human"], "từ chối thì KHÔNG chạy lại"
    assert "REL-001" not in orch.gate.pending


def test_khong_mo_gate_trung_khi_da_co_gate_cho_release():
    h = _pausing_release_engineer({"staging": 1})
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=h))
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    n = sum(1 for e in bus.replay(topic="audit-log") if e.payload["action"] == "gate.request"
            and '"subject_id": "REL-001"' in (e.payload.get("evidence") or ""))
    assert n == 1
    # Cùng event pending_human xử lý lại (replay) → `once` chặn, không mở gate thứ hai
    ev = next(e for e in bus.replay(topic="release-events") if e.key == "REL-001")
    orch.gate.decide("REL-001", "approve", by="human:lead", reason="ok chạy lại"); orch.run()
    orch.processed.discard(ev.event_id); orch.queue.append(ev); orch.run()
    n2 = sum(1 for e in bus.replay(topic="audit-log") if e.payload["action"] == "gate.request"
             and '"subject_id": "REL-001"' in (e.payload.get("evidence") or "") and '"escalation"' in (e.payload.get("evidence") or ""))
    assert n2 == 1, "event cũ phát lại không được mở gate escalation lần hai"


def test_rerun_khong_lam_gi_khi_khong_pending_human():
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler))
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    from company.orchestrator import StepResult
    res = StepResult("x", "audit-log", "REL-001")
    assert orch._rerun_release("REL-001", "human:lead", "", res) is False  # staging deployed rồi
    assert orch._rerun_release("REL-999", "human:lead", "", res) is False  # không có RC


def test_ky_lai_gate_3_chay_lai_duoc_luot_production_khong_can_restart():
    """`partial[rc.event_id]` ghi release-engineer sau lượt production đầu; ký lại Gate 3 (như lead làm 03:06
    2026-09-06 cho REL-019) trước đây chỉ chạy được vì orchestrator vừa restart."""
    h = _pausing_release_engineer({"production": 1})
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=h))
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    orch.gate.decide("REL-001", "approve", by="human:release-manager"); orch.run()
    assert _events(bus, "REL-001", "production") == ["pending_human"]
    # đóng escalation bằng cách ký LẠI Gate 3 (request + approve kind=release) thay vì duyệt escalation
    orch.gate.decide("REL-001", "reject", by="human:lead", reason="đóng escalation, sẽ ký lại gate release"); orch.run()
    from company.gates import GateRequest
    orch.gate.request(GateRequest(kind="release", subject_id="REL-001", created_by="delivery-lead", checklist=["tests"]))
    orch.gate.decide("REL-001", "approve", by="human:lead", reason="ký lại"); orch.run()
    assert _events(bus, "REL-001", "production") == ["pending_human", "deployed"]


def test_mo_lai_bus_thi_rc_dang_pending_human_tu_truoc_van_duoc_mo_gate(tmp_path):
    """RC kẹt `pending_human` từ TRƯỚC bản vá (event đã processed, không gate): mở lại orchestrator phải thấy gate,
    không cần chờ event mới. Và gate đã quyết rồi mà lượt chạy lại vẫn dừng → gate mới (khoá theo event_id)."""
    from company.sqlite_bus import SQLiteBus
    h = _pausing_release_engineer({"staging": 2})
    bus = SQLiteBus(tmp_path / "c.sqlite"); orch = Orchestrator(bus, FakeClient(handler=h))
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    assert orch.gate.pending["REL-001"].kind == "escalation"
    # giả lập "trước bản vá": xoá gate khỏi RAM và khoá once, rồi mở lại bus bằng orchestrator mới
    bus.close()
    bus2 = SQLiteBus(tmp_path / "c.sqlite"); orch2 = Orchestrator(bus2, FakeClient(handler=h))
    assert "REL-001" in orch2.gate.pending, "gate bền qua restart (replay audit)"
    orch2.gate.decide("REL-001", "approve", by="human:lead", reason="chạy lại"); orch2.run()
    # lượt chạy lại (lần 2) vẫn pending_human → gate MỚI cho event mới, không bị `once` của event cũ nuốt
    assert _events(bus2, "REL-001", "staging") == ["pending_human", "pending_human"]
    assert orch2.gate.pending["REL-001"].kind == "escalation"
    orch2.gate.decide("REL-001", "approve", by="human:lead", reason="chạy lại lần nữa"); orch2.run()
    assert _events(bus2, "REL-001", "staging") == ["pending_human", "pending_human", "deployed"]


def test_sweep_mo_gate_cho_rc_pending_khong_co_gate(tmp_path):
    """Đường thẳng vào sweep: RC có event pending_human đã processed, không gate, once trống → tick mở gate."""
    from company.events import Envelope
    from company.sqlite_bus import SQLiteBus
    bus = SQLiteBus(tmp_path / "c.sqlite")
    bus.publish(Envelope(topic="release-candidates", key="REL-001", actor="delivery-lead",
                         payload={"release_id": "REL-001", "project_id": "P1", "tickets": ["T1"], "version": "1.0.0"}))
    bus.publish(Envelope(topic="release-events", key="REL-001", actor="release-engineer",
                         payload={"release_id": "REL-001", "version": "1.0.0", "env": "staging", "status": "pending_human"}))
    orch = Orchestrator(bus, FakeClient(handler=handler))
    for e in list(bus.replay()): orch.processed.add(e.event_id)  # coi như đã xử lý hết từ trước bản vá
    orch.queue.clear()
    orch.tick()
    assert orch.gate.pending["REL-001"].kind == "escalation"
    assert sum(1 for e in bus.replay(topic="audit-log") if e.payload["action"] == "release.pending_human") == 1
    orch.tick()
    assert sum(1 for e in bus.replay(topic="audit-log") if e.payload["action"] == "gate.request") == 1, "không mở trùng"
