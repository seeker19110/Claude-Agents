"""4L-5: `metrics.collect()["loops"]` — đo vòng tool tới hội tụ + tỉ lệ chạm trần (đặc tả L3 "cách đo").

Bẫy đã biết ("số xanh vì rỗng", console/TRAPS.md #2): `capped_ratio = 0` khi `n = 0` nhìn giống "tốt" nhưng thực ra
là KHÔNG CÓ DỮ LIỆU — `empty=True` phải tách hai trạng thái đó ra, không để trang suy từ giá trị số.
"""
from __future__ import annotations

import json

from company import metrics as M
from company.bus import InMemoryBus
from company.events import Envelope


def _audit(bus: InMemoryBus, actor: str, action: str, evidence: dict, **kw: object) -> None:
    bus.publish(Envelope(topic="audit-log", key=actor, actor=actor,
                         payload={"actor": actor, "action": action, "evidence": json.dumps(evidence), **kw}))


def _tools_used(turns: int, capped: bool, max_turns: int = 25, calls: dict | None = None) -> dict:
    return {"turns": turns, "mode": "loop", "calls": {"read_file": 1} if calls is None else calls,
            "capped": capped, "max_turns": max_turns}


def test_loops_bon_ban_ghi_ca_bat_buoc():
    bus = InMemoryBus()
    for turns, capped in ((3, False), (5, False), (25, True), (25, True)):
        _audit(bus, "builder", "tools_used", _tools_used(turns, capped))
    m = M.collect(bus)
    loops = m["loops"]
    assert loops["empty"] is False
    assert loops["n"] == 4
    assert loops["turns_p50"] == 15, loops
    assert loops["capped_ratio"] == 0.5
    assert loops["turns_max"] == 25


def test_loops_bus_rong_la_empty_khong_phai_xanh_gia():
    bus = InMemoryBus()
    m = M.collect(bus)
    loops = m["loops"]
    assert loops["empty"] is True
    assert loops["n"] == 0
    # bẫy "xanh vì rỗng": capped_ratio=0 nhìn như "tốt" — mọi field số phải là 0/None, KHÔNG NaN, KHÔNG exception
    assert loops["capped_ratio"] in (0, None)
    assert loops["turns_p50"] is None and loops["turns_p90"] is None and loops["turns_max"] is None
    assert loops["no_progress_ratio"] in (0, None)
    assert loops["retry_max_ratio"] in (0, None)
    json.dumps(loops)  # không NaN — NaN không tự dump được ở strict mode nhưng ta kiểm rõ ràng
    for k, v in loops.items():
        if isinstance(v, float):
            assert v == v, f"{k} là NaN"  # NaN != NaN


def test_loops_capped_khong_progress():
    bus = InMemoryBus()
    # chạm trần mà KHÔNG gọi tool nào ở lượt cuối (calls rỗng) → không tiến triển
    _audit(bus, "builder", "tools_used", _tools_used(25, True, calls={}))
    _audit(bus, "builder", "tools_used", _tools_used(25, True, calls={"read_file": 2}))
    m = M.collect(bus)
    loops = m["loops"]
    assert loops["n"] == 2 and loops["capped_ratio"] == 1.0
    assert loops["no_progress_ratio"] == 0.5, loops


_TASK = {"project_id": "P1", "requirement_id": "REQ-1", "assignee": "builder", "stack": "backend", "title": "x",
         "acceptance": ["given/when/then"], "estimate_tokens": 1_000, "budget_tokens": 2_000, "retry": 0}


def _task_env(tid: str) -> Envelope:
    return Envelope(topic="tasks", key=tid, actor="delivery-lead", payload={**_TASK, "ticket_id": tid})


def test_loops_retry_max_ratio_chi_tinh_ticket_co_task():
    bus = InMemoryBus()
    bus.publish(_task_env("T1")); bus.publish(_task_env("T2"))
    _audit(bus, "orchestrator", "ticket.blocked", {"ticket_id": "T1"})
    _audit(bus, "builder", "tools_used", _tools_used(3, False))
    m = M.collect(bus)
    # 2 ticket có task, 1 bị blocked -> 0.5 (ticket không có task nào không được tính vào mẫu số)
    assert m["loops"]["retry_max_ratio"] == 0.5


def test_prometheus_co_sau_gauge_company_loop():
    bus = InMemoryBus()
    bus.publish(_task_env("T1"))
    _audit(bus, "orchestrator", "ticket.blocked", {"ticket_id": "T1"})
    for turns, capped in ((3, False), (25, True)):
        _audit(bus, "builder", "tools_used", _tools_used(turns, capped))
    text = M.prometheus(M.collect(bus))
    for name in ("company_loop_turns_p50", "company_loop_turns_p90", "company_loop_turns_max",
                 "company_loop_capped_ratio", "company_loop_no_progress_ratio", "company_loop_retry_max_ratio"):
        assert f"{name} " in text or f"{name}{{" in text, f"thiếu gauge {name}\n{text}"


def test_prometheus_khong_ghi_gauge_khi_empty():
    text = M.prometheus(M.collect(InMemoryBus()))
    assert "company_loop_turns_p50 " not in text, "empty=True: không bịa số 0/None ra Prometheus, bỏ qua các gauge"
