"""ADR-0028: vai viết test độc lập. Test ở đây kiểm bốn thứ mà thiết kế đứng hoặc đổ theo:
thứ tự (test trước code), ranh giới ghi (ai được chạm vùng nào), fail closed khi không phân vùng được,
và tính nhìn thấy được (`tests_authored_by`, `tests_red_as_expected` / `tests_green_before_code`)."""
from __future__ import annotations

from pathlib import Path

import pytest

from company.bus import InMemoryBus
from company.events import Envelope
from company.llm import FakeClient
from company.orchestrator import Orchestrator
from company.runner import AgentRunner, RunnerError
from company.workspace import TicketWorkspace
from test_orchestrator import T1, _agent_of, _drive_to_plan, _inp
from test_tools_and_agentic import _first_turn, _init_repo, _pr, _tc

TEST_FILE = "tests/test_feature.py"
TEST_BODY = "from feature import f\n\n\ndef test_f():\n    assert f() == 1\n"
SRC_BODY = "def f():\n    return 1\n"


def _ts(p: dict, **extra) -> dict:
    """Đầu ra tối thiểu hợp lệ của test-author; `files`/`branch`/`tests_status` sẽ bị CODE ghi đè."""
    return {"ticket_id": p["ticket_id"], "assignee": p.get("assignee", "backend"), "files": ["model khai bừa"],
            "acceptance_covered": [{"acceptance": a, "tests": ["test_f"]} for a in p.get("acceptance", ["x"])],
            "notes": "viết từ acceptance", **extra}


def _task(tid="T1", **extra) -> Envelope:
    return Envelope(topic="tasks", key=tid, actor="delivery-lead", payload={**T1, "ticket_id": tid, **extra})


# ---------- lượt của test-author ----------

def test_author_tests_dien_bang_chung_that_va_do_la_dung(tmp_path: Path) -> None:
    ws = TicketWorkspace(_init_repo(tmp_path / "repo"), "T1", base="main")
    th = lambda m, t: [_tc("write_file", path=TEST_FILE, content=TEST_BODY)] if _first_turn(m) else []  # noqa: E731
    bus = InMemoryBus()
    g, status = AgentRunner(bus, FakeClient(handler=lambda s, u: _ts(_inp(u)), tool_handler=th)).author_tests(
        "test-author", _task(), ws)
    p = g.payloads[0]
    assert status == "red", "test đỏ khi chưa có code là kết quả ĐÚNG"
    assert p["files"] == [TEST_FILE], "danh sách file do git nói, không phải model khai"
    assert p["branch"] == "ticket/T1" and len(p["commit"]) >= 7 and p["blind"] is True
    acts = [e.payload["action"] for e in bus.replay(topic="audit-log")]
    assert acts == ["tools_used", "tests_red_as_expected"]


def test_author_tests_khong_ghi_duoc_file_nguon(tmp_path: Path) -> None:
    """Ranh giới nằm ở runtime: test-author có thử ghi code cũng chỉ nhận lỗi, và worktree không có file đó."""
    repo = _init_repo(tmp_path / "repo"); ws = TicketWorkspace(repo, "T1", base="main")
    seen: list[str] = []
    def th(msgs, tools):
        if _first_turn(msgs):
            return [_tc("write_file", path="feature.py", content=SRC_BODY),
                    _tc("write_file", path=TEST_FILE, content=TEST_BODY)]
        seen.extend(m["content"] for m in msgs if m["role"] == "tool")
        return []
    g, _ = AgentRunner(InMemoryBus(), FakeClient(handler=lambda s, u: _ts(_inp(u)), tool_handler=th)).author_tests(
        "test-author", _task(), ws)
    assert seen[0].startswith("lỗi: chỉ được ghi file test")
    assert g.payloads[0]["files"] == [TEST_FILE] and not (ws.path / "feature.py").exists()


def test_author_tests_xanh_ngay_la_dang_ngo(tmp_path: Path) -> None:
    """Test xanh khi code chưa có = test rỗng/assert vô nghĩa. Không chặn, nhưng phải để lại vết."""
    ws = TicketWorkspace(_init_repo(tmp_path / "repo"), "T1", base="main")
    th = lambda m, t: [_tc("write_file", path=TEST_FILE, content="def test_luon_dung():\n    assert True\n")] if _first_turn(m) else []  # noqa: E731
    bus = InMemoryBus()
    _, status = AgentRunner(bus, FakeClient(handler=lambda s, u: _ts(_inp(u)), tool_handler=th)).author_tests(
        "test-author", _task(), ws)
    assert status == "green"
    assert [e.payload["action"] for e in bus.replay(topic="audit-log")][-1] == "tests_green_before_code"


def test_author_tests_khong_viet_gi_thi_khong_co_bo_test_rong(tmp_path: Path) -> None:
    ws = TicketWorkspace(_init_repo(tmp_path / "repo"), "T1", base="main")
    client = FakeClient(handler=lambda s, u: _ts(_inp(u)), tool_handler=lambda m, t: [_tc("read_file", path="mod.py")] if _first_turn(m) else [])
    with pytest.raises(RunnerError, match="không viết file test nào"):
        AgentRunner(InMemoryBus(), client).author_tests("test-author", _task(), ws)


# ---------- lượt của assignee sau khi có bộ test ----------

def test_assignee_khong_sua_duoc_test_cua_nguoi_khac(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo"); ws = TicketWorkspace(repo, "T1", base="main")
    ws.create()
    (ws.path / "tests").mkdir(exist_ok=True)
    (ws.path / TEST_FILE).write_text(TEST_BODY, encoding="utf-8")
    ws.commit_all("test(T1): bộ test của test-author")
    seen: list[str] = []
    def th(msgs, tools):
        if _first_turn(msgs):
            return [_tc("write_file", path=TEST_FILE, content="def test_f():\n    assert True\n"),  # nới cho dễ xanh
                    _tc("delete_file", path=TEST_FILE),                                            # hoặc xoá luôn
                    _tc("write_file", path="feature.py", content=SRC_BODY)]
        seen.extend(m["content"] for m in msgs if m["role"] == "tool")
        return []
    g = AgentRunner(InMemoryBus(), FakeClient(handler=lambda s, u: _pr(_inp(u)), tool_handler=th)).generate_in_workspace(
        "backend", _task(), ws, write_scope="src")
    assert all(x.startswith("lỗi: không được ghi file test") for x in seen[:2])
    assert (ws.path / TEST_FILE).read_text(encoding="utf-8") == TEST_BODY, "bộ test còn nguyên: nới lẫn xoá đều bị chặn"
    # PR vẫn mang cả file test (nó nằm trên nhánh ticket từ commit của test-author) — nhưng nội dung là của họ.
    assert g.payloads[0]["impact"]["files"] == ["feature.py", TEST_FILE]
    assert g.payloads[0]["local_checks"]["tests"] is True


# ---------- luồng qua orchestrator ----------

def _handler(system: str, user: str) -> dict:
    from test_orchestrator import handler as base
    a, p = _agent_of(system), _inp(user)
    if a == "test-author": return _ts(p)
    return base(system, user)


def _tool_handler(msgs, tools):
    if not _first_turn(msgs): return []
    names = {t.name for t in tools} if tools else set()
    if "delete_file" not in names and "write_file" not in names: return []
    # test-author chỉ ghi được test, assignee chỉ ghi được nguồn — cùng một tool_handler, ranh giới do runtime quyết
    return [_tc("write_file", path=TEST_FILE, content=TEST_BODY),
            _tc("write_file", path="feature.py", content=SRC_BODY)]


def _orch(tmp_path: Path, **kw) -> tuple[InMemoryBus, Orchestrator]:
    repo = _init_repo(tmp_path / "repo")
    bus = InMemoryBus()
    return bus, Orchestrator(bus, FakeClient(handler=_handler, tool_handler=_tool_handler), repo=repo, base="main", **kw)


def test_luong_ticket_di_qua_test_author_truoc_roi_moi_toi_code(tmp_path: Path) -> None:
    bus, orch = _orch(tmp_path, test_author=True)
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    ts = list(bus.replay(topic="test-suites"))
    prs = list(bus.replay(topic="pull-requests"))
    assert ts and prs, "phải có cả bộ test lẫn PR"
    assert ts[0].actor == "test-author" and ts[0].payload["files"] == [TEST_FILE]
    assert ts[0].ts <= prs[0].ts, "bộ test có TRƯỚC code"
    t1 = next(e for e in prs if e.key == "T1")
    assert t1.payload["tests_authored_by"] == "test-author"
    # File test có trên nhánh (do test-author commit), nhưng nội dung nguyên vẹn: assignee ghi vào đó thì bị chặn.
    ws = orch.workspace("T1")
    assert (ws.path / TEST_FILE).read_text(encoding="utf-8") == TEST_BODY


def test_test_author_tat_mac_dinh_thi_giu_nguyen_duong_cu(tmp_path: Path) -> None:
    bus, orch = _orch(tmp_path)
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    assert not list(bus.replay(topic="test-suites"))
    prs = list(bus.replay(topic="pull-requests"))
    assert prs and all(e.payload["tests_authored_by"] == "assignee" for e in prs)


def test_stack_khong_phan_vung_duoc_thi_di_duong_cu_va_noi_thang(tmp_path: Path) -> None:
    """Fail closed (ADR-0028 §3): không cưỡng chế được ranh giới thì đừng giả vờ có nó — nhưng phải nhìn thấy được."""
    repo = tmp_path / "repo"; _init_repo(repo)
    (repo / "pyproject.toml").unlink()  # còn lại là stack UNKNOWN: không có test_globs
    import subprocess
    subprocess.run(["git", "-C", str(repo), "commit", "-qam", "bỏ dấu hiệu stack"], check=True, capture_output=True)
    bus = InMemoryBus()
    orch = Orchestrator(bus, FakeClient(handler=_handler, tool_handler=_tool_handler), repo=repo, base="main", test_author=True)
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    assert not list(bus.replay(topic="test-suites")), "không phân vùng được thì KHÔNG chạy test-author"
    acts = {e.payload["action"] for e in bus.replay(topic="audit-log")}
    assert "tests_authored_by_assignee" in acts, "mất lớp bảo vệ thì phải ghi lại, không im lặng"


def test_tranh_chap_test_quay_ve_test_author_va_lan_nay_co_diff(tmp_path: Path) -> None:
    """Assignee không sửa được test; nó ghi `test_dispute` và route đưa việc về đúng người viết test."""
    repo = _init_repo(tmp_path / "repo")
    ws = TicketWorkspace(repo, "T1", base="main"); ws.create()
    (ws.path / "tests").mkdir(exist_ok=True)
    (ws.path / TEST_FILE).write_text(TEST_BODY, encoding="utf-8")
    ws.commit_all("test(T1): bộ test")
    seen: list[str] = []
    def th(msgs, tools):
        seen.extend(m["content"] for m in msgs if m["role"] == "user")
        return [_tc("write_file", path=TEST_FILE, content=TEST_BODY.replace("== 1", "== 1  # đã rà lại"))] if _first_turn(msgs) else []
    bus = InMemoryBus()
    orch = Orchestrator(bus, FakeClient(handler=lambda s, u: _ts({**_inp(u), "acceptance": ["x"]}), tool_handler=th),
                        repo=repo, base="main", test_author=True)
    pr = Envelope(topic="pull-requests", key="T1", actor="backend",
                  payload={"ticket_id": "T1", "project_id": "P1", "branch": "ticket/T1", "pr_ref": "abc1234",
                           "local_checks": {"lint": True, "tests": False},
                           "test_dispute": "test khẳng định f() == 1 nhưng acceptance nói 2"})
    from company.orchestrator import ROUTES, StepResult, _has_dispute
    assert _has_dispute(pr, orch) is True
    r = next(x for x in ROUTES if x.topic_in == "pull-requests" and x.agent == "test-author")
    orch._call("test-author", pr, r, StepResult("e", "pull-requests", "T1"))
    out = list(bus.replay(topic="test-suites"))
    assert out and out[0].payload["blind"] is False, "lượt tranh chấp KHÔNG mù"
    assert any("test_dispute" in s for s in seen), "test-author phải đọc được lý do tranh chấp"


def test_luot_mu_khong_thay_hint_cua_vong_review_truoc(tmp_path: Path) -> None:
    """`hint` là phản hồi review về CODE; đọc nó là hết mù, và bộ test lại bị uốn theo cách cài đặt."""
    repo = _init_repo(tmp_path / "repo")
    seen: list[str] = []
    def th(msgs, tools):
        seen.extend(m["content"] for m in msgs if m["role"] == "user")
        return [_tc("write_file", path=TEST_FILE, content=TEST_BODY)] if _first_turn(msgs) else []
    bus = InMemoryBus()
    orch = Orchestrator(bus, FakeClient(handler=lambda s, u: _ts(_inp(u)), tool_handler=th), repo=repo, base="main", test_author=True)
    from company.orchestrator import ROUTES, StepResult
    r = next(x for x in ROUTES if x.topic_in == "tasks" and x.agent == "test-author")
    orch._call("test-author", _task(hint="reviewer bảo dùng dict thay vì dataclass", retry=2), r, StepResult("e", "tasks", "T1"))
    joined = "\n".join(seen)
    assert "dataclass" not in joined and "given/when/then" in joined
