"""Kế hoạch bị `_check_plan` từ chối → orchestrator tự trả `product[plan]` sửa lại (kèm `hint`) TRƯỚC khi hỏi người.

Đo thật 2026-09-22/23 (CAMPUS-UNI): `PLAN-CAMPUS-UNI-20260922-1` bị từ chối hai lần liên tiếp, mỗi lần dự án
đứng im ở gate `escalation` chờ người gõ "retry" — mà "retry" chỉ là chạy lại đúng event nguồn, không cần phán
đoán gì. Anh em `_spec_runtime_missing` đã có lượt tự sửa (`SPEC_RUNTIME_REWORKS`); kế hoạch thì chưa.

Quy tắc: tối đa `PLAN_REWORKS` lượt tự sửa cho MỖI event nguồn (không phải mỗi dự án — một CR sau này của cùng
dự án có lượt riêng); quá thì `plan_rejected` + gate `escalation` như cũ; người duyệt retry ⇒ bộ đếm về 0 nên
lại có lượt tự sửa. Bộ đếm dựng lại từ audit `plan.rework` (khuôn 2 `TRAPS.md`: state không chỉ sống trong RAM).
"""

from __future__ import annotations

import json

from company.bus import InMemoryBus
from company.events import Envelope
from company.llm import FakeClient
from company.orch.routes import PLAN_REWORKS
from company.orchestrator import Orchestrator
from company.sqlite_bus import SQLiteBus
from test_orchestrator import _agent_of, _inp, _product_phase, handler


def _lead_rong_n_lan(fail_times: int):
    """`product[plan]` trả kế hoạch rỗng `fail_times` lần đầu, ghi lại đầu vào mỗi lượt."""
    seen: list[dict] = []

    def h(system, user):
        a, p = _agent_of(system), _inp(user)
        if a == "product" and _product_phase(system) == "plan" and p.get("decision") != "pending":
            seen.append(p)
            if len(seen) <= fail_times:
                return {"items": []}
        return handler(system, user)

    return h, seen


def _toi_plan(bus, orch):
    bus.publish(
        Envelope(
            topic="research-requests", key="P1", actor="human:sales", payload={"project_id": "P1", "description": "app"}
        )
    )
    orch.run()
    bus.publish(
        Envelope(
            topic="clarification-answers",
            key="P1",
            actor="human:po",
            payload={"project_id": "P1", "answers": [{"question_id": "Q1", "answer": "a"}]},
        )
    )
    orch.run()
    orch.gate.decide("SPEC-P1", "approve", by="human:po")
    orch.run()


def _audits(bus, action):
    return [json.loads(e.payload["evidence"]) for e in bus.replay(topic="audit-log") if e.payload["action"] == action]


def test_plan_bi_tu_choi_mot_lan_thi_tu_sua_khong_hoi_nguoi():
    h, seen = _lead_rong_n_lan(1)
    bus = InMemoryBus()
    orch = Orchestrator(bus, FakeClient(handler=h))
    _toi_plan(bus, orch)
    assert "P1" not in orch.gate.pending, "một lần từ chối thì chưa được hỏi người"
    assert "PLAN-P1-1" in orch.plans and orch.lead.tickets, "lượt sửa thành công → ticket được giao ngay"
    assert "P1" not in orch.unhandled
    assert not _audits(bus, "plan_rejected"), "lượt tự sửa không phải `plan_rejected` (chỉ ghi khi hỏi người)"
    rw = _audits(bus, "plan.rework")
    assert len(rw) == 1 and rw[0]["attempt"] == 1 and "kế hoạch rỗng" in rw[0]["problems"]
    assert len(seen) == 2
    assert "kế hoạch rỗng" in seen[1]["hint"], "lượt sửa phải mang lý do bị từ chối"
    assert "kế hoạch rỗng" in seen[1]["previous_plan"]["problems"]
    assert "hint" not in seen[0]


def test_qua_so_luot_tu_sua_thi_moi_hoi_nguoi():
    h, seen = _lead_rong_n_lan(99)
    bus = InMemoryBus()
    orch = Orchestrator(bus, FakeClient(handler=h))
    _toi_plan(bus, orch)
    assert orch.gate.pending["P1"].kind == "escalation" and "P1" in orch.unhandled and not orch.plans
    assert len(seen) == 1 + PLAN_REWORKS, "đúng số lượt tự sửa rồi mới hỏi, không thử vô hạn"
    assert len(_audits(bus, "plan.rework")) == PLAN_REWORKS
    assert len(_audits(bus, "plan_rejected")) == 1


def test_nguoi_duyet_retry_thi_lai_co_luot_tu_sua():
    h, seen = _lead_rong_n_lan(
        1 + PLAN_REWORKS + 1
    )  # hết lượt tự sửa → hỏi người; người retry → lại hỏng 1 lần → tự sửa → OK
    bus = InMemoryBus()
    orch = Orchestrator(bus, FakeClient(handler=h))
    _toi_plan(bus, orch)
    assert orch.gate.pending["P1"].kind == "escalation"
    orch.gate.decide("P1", "approve", by="human:lead", reason="lập lại")
    orch.run()
    assert "PLAN-P1-1" in orch.plans and "P1" not in orch.unhandled and "P1" not in orch.gate.pending
    assert len(seen) == 1 + PLAN_REWORKS + 1 + 1
    assert len(_audits(bus, "plan.rework")) == 2 * PLAN_REWORKS


def test_bo_dem_luot_tu_sua_song_qua_restart(tmp_path):
    h, _ = _lead_rong_n_lan(99)
    bus = SQLiteBus(tmp_path / "c.sqlite")
    orch = Orchestrator(bus, FakeClient(handler=h))
    _toi_plan(bus, orch)
    src = orch.unhandled["P1"]["event_id"]
    assert orch.plan_reworks[src] == 1 + PLAN_REWORKS
    bus.close()
    bus2 = SQLiteBus(tmp_path / "c.sqlite")
    orch2 = Orchestrator(bus2, FakeClient(handler=handler))
    assert orch2.plan_reworks[src] == 1 + PLAN_REWORKS, "bộ đếm không chỉ sống trong RAM"
    bus2.close()
