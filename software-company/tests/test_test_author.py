"""ADR-0028: vai viết test độc lập. Test ở đây kiểm bốn thứ mà thiết kế đứng hoặc đổ theo:
thứ tự (test trước code), ranh giới ghi (ai được chạm vùng nào), fail closed khi không phân vùng được,
và tính nhìn thấy được (`tests_authored_by`, `tests_red_as_expected` / `tests_green_before_code`)."""
from __future__ import annotations

import json
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

# `token_estimate` (p3.2a) là số đo CHẨN ĐOÁN, phát ở mọi bước agent: sai số giữa ước lượng của `fit` và
# token thật trong `usage`. Các khẳng định dưới đây đo TRÌNH TỰ SỰ VIỆC của luồng, nên lọc nó ra —
# chính nó được đo riêng ở `test_adr0012.py::test_runner_audits_token_estimate_sau_moi_buoc`.
DIAG = {"token_estimate"}

TEST_FILE = "tests/test_feature.py"
TEST_BODY = "from feature import f\n\n\ndef test_f():\n    assert f() == 1\n"
SRC_BODY = "def f():\n    return 1\n"


def _ts(p: dict, **extra) -> dict:
    """Đầu ra tối thiểu hợp lệ của test-author; `files`/`branch`/`tests_status` sẽ bị CODE ghi đè."""
    return {"ticket_id": p["ticket_id"], "assignee": p.get("assignee", "builder"), "files": ["model khai bừa"],
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
        "qa", _task(), ws)
    p = g.payloads[0]
    assert status == "red", "test đỏ khi chưa có code là kết quả ĐÚNG"
    assert p["files"] == [TEST_FILE], "danh sách file do git nói, không phải model khai"
    assert p["branch"] == "ticket/T1" and len(p["commit"]) >= 7 and p["blind"] is True
    acts = [e.payload["action"] for e in bus.replay(topic="audit-log") if e.payload["action"] not in DIAG]
    assert acts == ["tools_used", "tools_trace", "tests_red_as_expected"]


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
        "qa", _task(), ws)
    assert seen[0].startswith("lỗi: chỉ được ghi file test")
    assert g.payloads[0]["files"] == [TEST_FILE] and not (ws.path / "feature.py").exists()


def test_author_tests_xanh_ngay_la_dang_ngo(tmp_path: Path) -> None:
    """Test xanh khi code chưa có = test rỗng/assert vô nghĩa. Không chặn, nhưng phải để lại vết."""
    ws = TicketWorkspace(_init_repo(tmp_path / "repo"), "T1", base="main")
    th = lambda m, t: [_tc("write_file", path=TEST_FILE, content="def test_luon_dung():\n    assert True\n")] if _first_turn(m) else []  # noqa: E731
    bus = InMemoryBus()
    _, status = AgentRunner(bus, FakeClient(handler=lambda s, u: _ts(_inp(u)), tool_handler=th)).author_tests(
        "qa", _task(), ws)
    assert status == "green"
    assert [e.payload["action"] for e in bus.replay(topic="audit-log") if e.payload["action"] not in DIAG][-1] == "tests_green_before_code"


def test_author_tests_khong_viet_gi_thi_khong_co_bo_test_rong(tmp_path: Path) -> None:
    ws = TicketWorkspace(_init_repo(tmp_path / "repo"), "T1", base="main")
    client = FakeClient(handler=lambda s, u: _ts(_inp(u)), tool_handler=lambda m, t: [_tc("read_file", path="mod.py")] if _first_turn(m) else [])
    with pytest.raises(RunnerError, match="không viết file test nào"):
        AgentRunner(InMemoryBus(), client).author_tests("qa", _task(), ws)


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
        "builder", _task(), ws, write_scope="src")
    assert all(x.startswith("lỗi: không được ghi file test") for x in seen[:2])
    assert (ws.path / TEST_FILE).read_text(encoding="utf-8") == TEST_BODY, "bộ test còn nguyên: nới lẫn xoá đều bị chặn"
    # PR vẫn mang cả file test (nó nằm trên nhánh ticket từ commit của test-author) — nhưng nội dung là của họ.
    assert g.payloads[0]["impact"]["files"] == ["feature.py", TEST_FILE]
    assert g.payloads[0]["local_checks"]["tests"] is True


# ---------- luồng qua orchestrator ----------

def _handler(system: str, user: str) -> dict:
    from test_orchestrator import _qa_phase
    from test_orchestrator import handler as base
    a, p = _agent_of(system), _inp(user)
    # ADR-0037: `qa` gộp cả vai viết test lẫn vai chấm — chỉ lượt pha `author` trả `test-suites`.
    if a == "qa" and _qa_phase(system) == "author": return _ts(p)
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
    _drive_to_plan(bus, orch); orch.run()
    ts = list(bus.replay(topic="test-suites"))
    prs = list(bus.replay(topic="pull-requests"))
    assert ts and prs, "phải có cả bộ test lẫn PR"
    assert ts[0].actor == "qa" and ts[0].payload["files"] == [TEST_FILE]
    assert ts[0].ts <= prs[0].ts, "bộ test có TRƯỚC code"
    t1 = next(e for e in prs if e.key == "T1")
    assert t1.payload["tests_authored_by"] == "qa"
    # File test có trên nhánh (do test-author commit), nhưng nội dung nguyên vẹn: assignee ghi vào đó thì bị chặn.
    ws = orch.workspace("T1")
    assert (ws.path / TEST_FILE).read_text(encoding="utf-8") == TEST_BODY


def test_test_author_tat_mac_dinh_thi_giu_nguyen_duong_cu(tmp_path: Path) -> None:
    bus, orch = _orch(tmp_path)
    _drive_to_plan(bus, orch); orch.run()
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
    _drive_to_plan(bus, orch); orch.run()
    assert not list(bus.replay(topic="test-suites")), "không phân vùng được thì KHÔNG chạy test-author"
    acts = {e.payload["action"] for e in bus.replay(topic="audit-log")} - DIAG
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
    pr = Envelope(topic="pull-requests", key="T1", actor="builder",
                  payload={"ticket_id": "T1", "project_id": "P1", "branch": "ticket/T1", "pr_ref": "abc1234",
                           "local_checks": {"lint": True, "tests": False},
                           "test_dispute": "test khẳng định f() == 1 nhưng acceptance nói 2"})
    from company.orchestrator import ROUTES, StepResult, _has_dispute
    assert _has_dispute(pr, orch) is True
    r = next(x for x in ROUTES if x.topic_in == "pull-requests" and x.agent == "qa")
    orch._call("qa", pr, r, StepResult("e", "pull-requests", "T1"))
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
    r = next(x for x in ROUTES if x.topic_in == "tasks" and x.agent == "qa")
    orch._call("qa", _task(hint="reviewer bảo dùng dict thay vì dataclass", retry=2), r, StepResult("e", "tasks", "T1"))
    joined = "\n".join(seen)
    assert "dataclass" not in joined and "given/when/then" in joined


# ---------- các nhánh lỗi ----------

def test_khong_dung_duoc_worktree_thi_di_duong_cu(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Worktree hỏng (git lỗi, đĩa đầy) không được làm ticket đứng im: rơi về đường cũ, `_engineer` báo lỗi thật."""
    from company import orchestrator as orch_mod
    _bus, orch = _orch(tmp_path, test_author=True)
    monkeypatch.setattr(TicketWorkspace, "create", lambda self: (_ for _ in ()).throw(OSError("đĩa đầy")))
    assert orch_mod._test_scope_ok(orch, "T1") is False
    assert orch_mod._can_author_tests(_task(), orch) is False


def test_orchestrator_ghi_audit_khi_test_xanh_ngay(tmp_path: Path) -> None:
    """Cùng tín hiệu như ở runner, nhưng đi qua orchestrator: cờ phải tới được audit-log của dự án."""
    repo = _init_repo(tmp_path / "repo")
    def th(msgs, tools):
        return [_tc("write_file", path=TEST_FILE, content="def test_luon_dung():\n    assert True\n")] if _first_turn(msgs) else []
    bus = InMemoryBus()
    orch = Orchestrator(bus, FakeClient(handler=lambda s, u: _ts(_inp(u)), tool_handler=th), repo=repo, base="main", test_author=True)
    from company.orchestrator import ROUTES, StepResult
    r = next(x for x in ROUTES if x.topic_in == "tasks" and x.agent == "qa")
    orch._call("qa", _task(), r, StepResult("e", "tasks", "T1"))
    ev = [e.payload for e in bus.replay(topic="audit-log") if e.payload["action"] == "tests_green_before_code"]
    assert ev and ev[-1]["ticket_id"] == "T1"
    assert json.loads(ev[-1]["evidence"])["files"] == [TEST_FILE]


def test_giu_file_do_dang_cua_lan_truoc_thanh_wip_truoc_khi_viet_tiep(tmp_path: Path) -> None:
    """Lần chạy trước bị giết giữa chừng để lại test dở: giữ thành WIP rồi viết tiếp, bộ test mang cả hai — không vứt
    công sức lượt trước (cùng chính sách với `generate_in_workspace`)."""
    repo = _init_repo(tmp_path / "repo"); ws = TicketWorkspace(repo, "T1", base="main")
    ws.create()
    (ws.path / "tests" / "test_do_dang.py").parent.mkdir(parents=True, exist_ok=True)
    (ws.path / "tests" / "test_do_dang.py").write_text("def test_half():\n    assert True\n", encoding="utf-8")
    th = lambda m, t: [_tc("write_file", path=TEST_FILE, content=TEST_BODY)] if _first_turn(m) else []  # noqa: E731
    bus = InMemoryBus()
    g, _ = AgentRunner(bus, FakeClient(handler=lambda s, u: _ts(_inp(u)), tool_handler=th)).author_tests(
        "qa", _task(), ws)
    assert (ws.path / "tests" / "test_do_dang.py").exists()
    assert sorted(g.payloads[0]["files"]) == sorted([TEST_FILE, "tests/test_do_dang.py"])
    acts = [e.payload["action"] for e in bus.replay(topic="audit-log") if e.payload["action"] not in DIAG]
    assert "workspace_kept" in acts and "workspace_reset" not in acts


def test_commit_bo_test_that_bai_thi_noi_thang(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from company.workspace import WorkspaceError
    ws = TicketWorkspace(_init_repo(tmp_path / "repo"), "T1", base="main")
    th = lambda m, t: [_tc("write_file", path=TEST_FILE, content=TEST_BODY)] if _first_turn(m) else []  # noqa: E731
    monkeypatch.setattr(TicketWorkspace, "commit_all",
                        lambda self, msg: (_ for _ in ()).throw(WorkspaceError("index đang khoá")))
    with pytest.raises(RunnerError, match="commit bộ test thất bại"):
        AgentRunner(InMemoryBus(), FakeClient(handler=lambda s, u: _ts(_inp(u)), tool_handler=th)).author_tests(
            "qa", _task(), ws)


# ---------- ADR-0037 PR-5c: một agent `qa`, hai pha, hai bộ quyền ----------

def test_qa_hai_route_khac_tool(tmp_path: Path) -> None:
    """Gộp `test-author` + `reviewer` + `qa-debugger` thành một agent chỉ an toàn nếu HAI LƯỢT VẪN KHÁC NHAU.

    Đo đúng ba khác biệt mà ADR-0037 hứa, trên cùng một `Orchestrator`:
    1. đầu vào — lượt `author` đi từ `tasks` bị `BLIND_STRIP` gỡ `hint`/`diff`/`chan_doan`; lượt `review` được
       `enrich` bơm đúng những thứ đó vào;
    2. quyền — lượt `author` có tool GHI với `write_scope="tests"` (ghi file nguồn bị runtime từ chối), lượt
       `review` chỉ-đọc (không có `write_file`/`delete_file` trong toolbox);
    3. prompt — `cache_key` mang tên pha, nên hai lượt nạp hai bộ skill khác nhau.

    Chiều tắt bản sửa: bỏ `phase=` khỏi hai route trong `orch/routes.py` → cả hai lượt dùng chung prompt
    (`cache_key == "qa"`) và test đỏ ngay ở khẳng định (3).
    """
    from company.orchestrator import ROUTES, StepResult

    repo = _init_repo(tmp_path / "repo")
    ket_qua_tool: list[str] = []

    def th(msgs, tools):
        names = {t.name for t in tools} if tools else set()
        ket_qua_tool.extend(m["content"] for m in msgs if m["role"] == "tool")
        if not _first_turn(msgs) or "write_file" not in names: return []
        # thử ghi CẢ file nguồn: `write_scope="tests"` phải chặn, không phải "được ghi rồi mới hối"
        return [_tc("write_file", path="feature.py", content=SRC_BODY),
                _tc("write_file", path=TEST_FILE, content=TEST_BODY)]

    def handler(system: str, user: str) -> dict:
        from test_orchestrator import _qa_phase
        p = _inp(user)
        if _qa_phase(system) == "author": return _ts(p)
        return {"ticket_id": p["ticket_id"], "source": "reviewer", "verdict": "pass"}

    client = FakeClient(handler=handler, tool_handler=th)
    bus = InMemoryBus()
    orch = Orchestrator(bus, client, repo=repo, base="main", test_author=True)
    r_author = next(x for x in ROUTES if x.topic_in == "tasks" and x.agent == "qa")
    r_review = next(x for x in ROUTES if x.topic_in == "pull-requests" and x.topic_out == "review-results" and x.agent == "qa")
    assert (r_author.phase, r_review.phase) == ("author", "review")

    orch._call("qa", _task(hint="reviewer bảo dùng dict", retry=2), r_author, StepResult("e1", "tasks", "T1"))
    pr = Envelope(topic="pull-requests", key="T1", actor="builder",
                  payload=_pr({"ticket_id": "T1"}, branch="ticket/T1"))
    orch._call("qa", pr, r_review, StepResult("e2", "pull-requests", "T1"))

    author_call, review_call = client.calls[0], client.calls[-1]

    # (1) đầu vào
    vao_author = _inp(author_call["user"])
    assert not ({"hint", "diff", "chan_doan", "test_suite", "retry"} & set(vao_author)), \
        "lượt author phải MÙ: BLIND_STRIP gỡ hết thứ nói về code (ADR-0028)"
    assert "acceptance" in vao_author, "nhưng vẫn phải còn đặc tả để mà viết test"

    # (2) quyền
    assert {"write_file", "delete_file"} <= set(author_call["tools"]), "lượt author phải ghi được vùng test"
    assert not ({"write_file", "delete_file"} & set(review_call["tools"])), "lượt review chỉ-đọc"
    assert "read_file" in review_call["tools"], "chỉ-đọc không có nghĩa là mù: vẫn đọc được diff bị cắt"
    assert any("chỉ được ghi file test" in x for x in ket_qua_tool), \
        f"write_scope=tests phải từ chối `feature.py`; tool trả về: {ket_qua_tool}"
    assert not (orch.workspace("T1").path / "feature.py").exists()

    # (3) prompt theo pha — đây là dòng đỏ khi tắt `phase=` trong bảng route
    assert (author_call["cache_key"], review_call["cache_key"]) == ("qa[author]", "qa[review]")
    assert "# Skills của pha review" in review_call["system"] and "# Skills của pha" not in author_call["system"], \
        "pha `author` khai skills rỗng (lượt MÙ), pha `review` nạp thêm code-review/debugging"


def test_review_route_khong_co_thi_gay_to() -> None:
    """`review_route` là chỗ hai đường giao-lại-review lấy route THẬT. Agent không chấm PR mà lọt vào đây nghĩa là
    `REVIEW_AGENT` và `ROUTES` đã lệch nhau — phải gãy to ngay, chứ không trả một Route dựng tay để lượt giao lại
    chạy sai pha (đúng cái bug ADR-0037 PR-5c vừa vá)."""
    from company.orch.routes import review_route

    assert review_route("qa").phase == "review"
    with pytest.raises(KeyError, match="không có route chấm pull-requests"):
        review_route("builder")
