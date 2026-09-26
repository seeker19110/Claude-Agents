"""Hai chỗ làm công ty dừng chờ người dù máy tự xử lý được, đo từ lần chạy thật CAMPUS-UNI 2026-09-24:

1. Builder hết lượt tool (`claude -p` `error_max_turns`) trong khi worktree CÓ tiến độ → trước đây tính một retry
   như một lần làm sai: TCK-011/015 cháy 2/3 retry vì hết lượt, lần thứ ba test đỏ → blocked, kéo 32 ticket chờ.
   Nay: làm tiếp từ WIP, không tính retry, trần riêng `MAX_TURN_CONTINUATIONS` (khuôn `conflict_retries`).
2. CLI không ép được đầu ra đúng schema (`error_max_structured_output_retries`, ops trên REL-003) → trước đây mở
   gate escalation ngay. Nay: máy thử lại đúng một lần (khoá `once`, bền qua restart) rồi mới hỏi người.
"""

from __future__ import annotations

import json

from company.bus import InMemoryBus
from company.llm import FakeClient, LLMError
from company.orch.routes import MAX_TURN_CONTINUATIONS
from company.orchestrator import Orchestrator
from company.runner import RunnerError
from company.sqlite_bus import SQLiteBus
from test_orchestrator import _agent_of, _drive_to_plan, _inp, _pub, handler
from test_tools_and_agentic import _init_repo

HET_LUOT = "claude -p thoát mã 1 (subtype=error_max_turns, api_error_status=None): "
SCHEMA = "claude -p thoát mã 1 (subtype=error_max_structured_output_retries, api_error_status=None): "


def _audits(bus, action):
    return [e.payload for e in bus.replay(topic="audit-log") if e.payload["action"] == action]


def _retries(bus, tid="T1"):
    return [e.payload["retry"] for e in bus.replay(topic="tasks") if e.key == tid]


def _builder_het_luot(orch, monkeypatch, *, sua_file: bool, err: Exception | None = None):
    n = {"i": 0}

    def fake(agent, inp, ws, **_k):
        n["i"] += 1
        if not ws.path.exists(): ws.create()  # `generate_in_workspace` thật dựng worktree trước vòng tool
        if sua_file:  # lượt bị cắt vẫn để lại việc dở chưa commit trong worktree
            (ws.path / f"buoc_{n['i']}.py").write_text(f"x = {n['i']}\n", encoding="utf-8")
        raise err or LLMError(HET_LUOT, model_text="(không có thông điệp)")

    monkeypatch.setattr(orch.runner, "generate_in_workspace", fake)


# ---------- 1. hết lượt tool mà có tiến độ: làm tiếp, không đốt retry ----------


def test_het_luot_tool_ma_worktree_co_tien_do_thi_lam_tiep_khong_dot_retry(tmp_path, monkeypatch):
    bus = InMemoryBus()
    orch = Orchestrator(bus, FakeClient(handler=handler), repo=_init_repo(tmp_path / "repo"), base="main")
    _builder_het_luot(orch, monkeypatch, sua_file=True)
    _drive_to_plan(bus, orch)
    orch.run()
    tasks = [e.payload for e in bus.replay(topic="tasks") if e.key == "T1"]
    assert [t["retry"] for t in tasks] == [0] + [0] * MAX_TURN_CONTINUATIONS + [1, 2], (
        "hết lượt có tiến độ không tính retry cho tới trần riêng; quá trần thì về đường retry cũ"
    )
    assert all("error_max_turns" in t["hint"] and "WIP" in t["hint"] for t in tasks[1 : 1 + MAX_TURN_CONTINUATIONS])
    assert len({t["hint"] for t in tasks[1 : 1 + MAX_TURN_CONTINUATIONS]}) == MAX_TURN_CONTINUATIONS, (
        "hint mỗi lần phải khác nhau, không thì delivery-lead coi task là bản cũ và bỏ qua"
    )
    assert len(_audits(bus, "ticket.continued")) == MAX_TURN_CONTINUATIONS
    assert orch.lead.state["T1"] == "blocked" and orch.gate.pending["T1"].kind == "escalation"


def test_het_luot_tool_ma_worktree_sach_van_tinh_retry(tmp_path, monkeypatch):
    """Hết lượt mà không sửa gì: đang đi vòng tròn, không phải thiếu lượt — giữ nguyên hành vi cũ."""
    bus = InMemoryBus()
    orch = Orchestrator(bus, FakeClient(handler=handler), repo=_init_repo(tmp_path / "repo"), base="main")
    _builder_het_luot(orch, monkeypatch, sua_file=False)
    _drive_to_plan(bus, orch)
    orch.run()
    assert _retries(bus) == [0, 1, 2] and not _audits(bus, "ticket.continued")
    assert orch.lead.state["T1"] == "blocked"


def test_loi_khac_het_luot_ma_worktree_co_tien_do_van_tinh_retry(tmp_path, monkeypatch):
    """Chỉ `error_max_turns` được làm tiếp: đầu ra hỏng (RunnerError) dù có sửa file vẫn là một lần làm sai."""
    bus = InMemoryBus()
    orch = Orchestrator(bus, FakeClient(handler=handler), repo=_init_repo(tmp_path / "repo"), base="main")
    _builder_het_luot(orch, monkeypatch, sua_file=True, err=RunnerError("đầu ra hỏng"))
    _drive_to_plan(bus, orch)
    orch.run()
    assert _retries(bus) == [0, 1, 2] and not _audits(bus, "ticket.continued")


def test_so_lan_lam_tiep_ben_qua_restart(tmp_path, monkeypatch):
    """Bộ đếm sống trong RAM thì restart là được thêm ba lần làm tiếp nữa — trần thành vô hạn."""
    db = tmp_path / "c.sqlite"
    bus = SQLiteBus(db)
    orch = Orchestrator(bus, FakeClient(handler=handler), repo=_init_repo(tmp_path / "repo"), base="main")
    _builder_het_luot(orch, monkeypatch, sua_file=True)
    _drive_to_plan(bus, orch)
    orch.run()
    bus.close()
    lai = Orchestrator(SQLiteBus(db), FakeClient(handler=handler), repo=tmp_path / "repo", base="main")
    assert lai.turn_continuations["T1"] == MAX_TURN_CONTINUATIONS


# ---------- 2. CLI không ép được schema: máy thử lại đúng một lần ----------


def _reviewer_loi(so_lan_loi: int, msg: str = SCHEMA):
    n = {"i": 0}

    def h(system, user):
        # không đụng lượt threat-model của security (payload có `artifacts`), như test gốc ở test_orchestrator.py
        if _agent_of(system) in {"qa", "security"} and "artifacts" not in _inp(user) and n["i"] < so_lan_loi:
            n["i"] += 1
            raise LLMError(msg, model_text="(không có thông điệp)")
        return handler(system, user)

    return h


def _pr_t1(bus):
    _pub(
        bus,
        "pull-requests",
        "T1",
        "builder",
        {
            "ticket_id": "T1",
            "project_id": "P1",
            "branch": "ticket/T1",
            "pr_ref": "#1",
            "summary": "s",
            "impact": {"files": ["a.py"]},
            "local_checks": {"lint": True, "tests": True, "verified_by": "workspace"},
        },
    )


def test_loi_schema_lan_dau_thi_may_tu_thu_lai_khong_hoi_nguoi():
    bus = InMemoryBus()
    orch = Orchestrator(bus, FakeClient(handler=_reviewer_loi(1)))
    _drive_to_plan(bus, orch)
    orch.run()
    _pr_t1(bus)
    orch.run()
    orch.tick()
    assert len(_audits(bus, "llm.autoretry")) == 1
    assert not _audits(bus, "agent_error_unhandled") and "T1" not in orch.gate.pending
    assert any(e.payload.get("ticket_id") == "T1" for e in bus.replay(topic="review-results")), "lần thử lại chạy thật"


def test_loi_schema_lan_hai_thi_moi_mo_gate():
    bus = InMemoryBus()
    orch = Orchestrator(bus, FakeClient(handler=_reviewer_loi(99)))
    _drive_to_plan(bus, orch)
    orch.run()
    _pr_t1(bus)
    orch.run()
    orch.tick()
    orch.tick()
    orch.tick()
    # hai event PR (builder tự nộp + PR phát thêm ở trên) → mỗi event đúng MỘT lần thử lại, dù chạy bao nhiêu nhịp
    ids = [json.loads(a["evidence"])["event_id"] for a in _audits(bus, "llm.autoretry")]
    assert ids and len(ids) == len(set(ids)), "đúng một lần mỗi event, không lặp mãi"
    assert _audits(bus, "agent_error_unhandled") and orch.gate.pending["T1"].kind == "escalation"


def test_loi_khac_schema_khong_tu_thu_lai():
    bus = InMemoryBus()
    orch = Orchestrator(bus, FakeClient(handler=_reviewer_loi(99, "model không trả về nội dung nào")))
    _drive_to_plan(bus, orch)
    orch.run()
    _pr_t1(bus)
    orch.run()
    assert not _audits(bus, "llm.autoretry") and orch.gate.pending.get("T1")
