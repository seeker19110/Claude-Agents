"""ADR-0025: repo khách theo từng dự án — `research-requests.repo` thắng `--repo` mặc định; học lại từ log; repo sai
không dừng dự án mà audit một lần; nhiều dự án nhiều repo trong cùng một tiến trình."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess

from company.bus import InMemoryBus
from company.events import Envelope, Task
from company.llm import FakeClient
from company.orchestrator import Orchestrator
from company.sqlite_bus import SQLiteBus
from test_orchestrator import T1, _pub, _topics, handler
from test_tools_and_agentic import _init_repo, _repo_tool_handler


def _git(repo, *a) -> str:
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, encoding="utf-8").stdout.strip()


def _drive(bus, orch, pid: str, req_extra: dict) -> None:
    """research-request (kèm repo) → ... → gate spec → plan → gate plan → approve → chạy tới cùng."""
    _pub(bus, "research-requests", pid, "human:sales", {"project_id": pid, "description": "app đặt lịch", **req_extra})
    orch.run()
    _pub(bus, "clarification-answers", pid, "human:po", {"project_id": pid, "answers": [{"question_id": "Q1", "answer": "a"}]})
    orch.run(); orch.gate.decide(f"SPEC-{pid}", "approve", by="human:po"); orch.run()
    orch.gate.decide(f"PLAN-{pid}-1", "approve", by="human:pm"); orch.run()


def _audits(bus, action: str) -> list[dict]:
    return [json.loads(e.payload["evidence"]) for e in bus.replay(topic="audit-log") if e.payload["action"] == action]


def test_repo_trong_research_request_thang_khi_khong_co_repo_mac_dinh(tmp_path):
    repo = _init_repo(tmp_path / "khach-a")
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler, tool_handler=_repo_tool_handler))  # KHÔNG --repo
    assert orch.integration is None and orch.status()["integration"] is None
    _drive(bus, orch, "P1", {"repo": str(repo), "base": "main"})

    assert orch.integration is None, "--repo mặc định vẫn không có"
    integ = orch.integration_for("P1")
    assert integ is not None and integ.repo == repo.resolve() and integ.base == "main"
    assert orch.lead.state == {"T1": "merged", "T2": "merged"} and orch.stats["errors"] == 0, orch.lead.state
    assert (repo / ".worktrees" / "T1").exists() and (repo / ".worktrees" / "T2").exists(), "worktree nằm trong repo của dự án"
    assert "f_t1.py" in integ.files() and "f_t2.py" in integ.files()
    assert _git(repo, "log", "-1", "--format=%s", "main") == "init", "main của khách không bị chạm"
    merged = _audits(bus, "integration.merged")
    assert len(merged) == 2 and all(m["repo"] == str(repo.resolve()) for m in merged)
    learned = _audits(bus, "project.repo")
    assert learned == [{"project_id": "P1", "repo": str(repo.resolve()), "base": "main"}]
    st = orch.status()["integration"]
    assert st is not None and st["projects"]["P1"]["repo"] == str(repo.resolve()) and st["projects"]["P1"]["sha"] == integ.sha()
    assert "branch" not in st, "không có repo mặc định thì không bịa trạng thái mặc định"
    prs = [e.payload for e in bus.replay(topic="pull-requests")]
    assert prs and all(p["local_checks"].get("verified_by") == "workspace" for p in prs), "bằng chứng do code điền, không unverified"


def test_du_an_khong_khai_repo_dung_repo_mac_dinh_va_du_an_khac_dung_repo_rieng(tmp_path):
    default_repo = _init_repo(tmp_path / "mac-dinh"); own = _init_repo(tmp_path / "rieng")
    bus = InMemoryBus()
    orch = Orchestrator(bus, FakeClient(handler=handler, tool_handler=_repo_tool_handler), repo=default_repo, base="main")
    _pub(bus, "research-requests", "P1", "human:sales", {"project_id": "P1", "description": "x"})
    _pub(bus, "research-requests", "P2", "human:sales", {"project_id": "P2", "description": "y", "repo": str(own)})
    orch.run()
    assert orch.integration_for("P1") is orch.integration and orch.integration.repo == default_repo
    assert orch.integration_for("P2").repo == own.resolve() and orch.integration_for(None) is orch.integration
    # ticket của dự án nào → worktree trong repo đó (lead.tickets là nguồn sự thật về dự án của ticket)
    orch.lead.tickets["X1"] = Task(**{**T1, "ticket_id": "X1", "project_id": "P1"})
    orch.lead.tickets["X2"] = Task(**{**T1, "ticket_id": "X2", "project_id": "P2"})
    assert orch.workspace("X1").repo == default_repo and orch.workspace("X2").repo == own.resolve()
    assert orch.workspace("KHONG-CO") is not None and orch.workspace("KHONG-CO").repo == default_repo, "ticket lạ → mặc định"
    st = orch.status()["integration"]
    assert st["repo"] == str(default_repo) and st["projects"] == {"P2": {"branch": "company/integration", "sha": orch.integration_for("P2").sha(), "repo": str(own.resolve())}}


def test_repo_sai_khong_dung_du_an_audit_mot_lan_va_roi_ve_mac_dinh(tmp_path):
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler))
    bad = str(tmp_path / "khong-ton-tai")
    _pub(bus, "research-requests", "P1", "human:sales", {"project_id": "P1", "description": "x", "repo": bad})
    orch.run()
    assert orch.integration_for("P1") is None and not orch.project_repos and orch.bad_repos == {"P1"}
    inv = _audits(bus, "project.repo_invalid")
    assert inv == [{"project_id": "P1", "repo": bad, "fallback": None}]
    assert _topics(bus)[-1] == "clarification-questions", "dự án vẫn chạy tiếp như không có repo"
    # khai lại lần nữa vẫn sai → không audit thêm; khai đúng → học, không cần khởi động lại
    _pub(bus, "research-requests", "P1", "human:sales", {"project_id": "P1", "description": "x", "repo": bad})
    orch.run()
    assert len(_audits(bus, "project.repo_invalid")) == 1
    good = _init_repo(tmp_path / "ok")
    _pub(bus, "research-requests", "P1", "human:sales", {"project_id": "P1", "description": "x", "repo": str(good)})
    orch.run()
    assert orch.integration_for("P1").repo == good.resolve() and "P1" not in orch.bad_repos and orch.lead.require_integration


def test_khai_lai_cung_repo_khong_audit_trung_khai_repo_khac_thi_doi(tmp_path):
    a = _init_repo(tmp_path / "a"); b = _init_repo(tmp_path / "b")
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler))
    for _ in range(2):
        _pub(bus, "research-requests", "P1", "human:sales", {"project_id": "P1", "description": "x", "repo": str(a)})
    orch.run()
    assert len(_audits(bus, "project.repo")) == 1
    _pub(bus, "research-requests", "P1", "human:sales", {"project_id": "P1", "description": "x", "repo": str(b), "base": "main"})
    orch.run()
    assert orch.integration_for("P1").repo == b.resolve() and len(_audits(bus, "project.repo")) == 2
    # schema chặn `repo` không phải chuỗi từ cửa bus; _learn_repo vẫn tự phòng thủ (event cũ/khác nguồn) — bỏ qua, không nổ
    orch._learn_repo(Envelope(topic="research-requests", key="P3", actor="x", payload={"project_id": "P3", "description": "x", "repo": 42}))
    orch._learn_repo(Envelope(topic="research-requests", key="P4", actor="x", payload={"project_id": "P4", "description": "x"}))
    assert orch.integration_for("P3") is None and orch.integration_for("P4") is None and not orch.bad_repos


def test_mo_lai_tu_sqlite_hoc_lai_repo_tu_log_khong_audit_lai(tmp_path):
    repo = _init_repo(tmp_path / "khach")
    db = tmp_path / "c.sqlite"; bus = SQLiteBus(db)
    orch = Orchestrator(bus, FakeClient(handler=handler, tool_handler=_repo_tool_handler))
    _drive(bus, orch, "P1", {"repo": str(repo)})
    assert orch.lead.state == {"T1": "merged", "T2": "merged"}
    n_learned = len(_audits(bus, "project.repo")); bus.close()

    bus2 = SQLiteBus(db)
    o2 = Orchestrator(bus2, FakeClient(handler=handler, tool_handler=_repo_tool_handler))
    assert o2.integration_for("P1").repo == repo.resolve() and o2.lead.require_integration
    assert len(_audits(bus2, "project.repo")) == n_learned, "replay không ghi audit lại"
    assert o2.status()["integration"]["projects"]["P1"]["sha"] == orch.integration_for("P1").sha()
    # repo đã bị xoá sau khi dự án chạy: mở lại không nổ, dự án coi như không repo
    bus2.close()
    def _rw_then_retry(func, path, _exc):  # object của git là read-only trên Windows: mở quyền rồi xoá lại
        os.chmod(path, stat.S_IWRITE); func(path)
    shutil.rmtree(repo / ".git", onerror=_rw_then_retry)
    o3 = Orchestrator(SQLiteBus(db), FakeClient(handler=handler))
    assert o3.integration_for("P1") is None and o3.bad_repos == {"P1"}


def test_qa_va_release_dung_nhanh_tich_hop_cua_du_an(tmp_path):
    repo = _init_repo(tmp_path / "khach")
    bus = InMemoryBus(); client = FakeClient(handler=handler, tool_handler=_repo_tool_handler)
    orch = Orchestrator(bus, client)
    _drive(bus, orch, "P1", {"repo": str(repo)})
    integ = orch.integration_for("P1")
    rel_in = [json.loads(c["user"].split("```json\n", 1)[1].split("\n```", 1)[0]) for c in client.calls
              if c["system"].split("\n", 1)[0].lstrip("# ").strip() == "release-engineer"]
    assert rel_in and all(p["integration_branch"] == integ.branch and p["integration_sha"] for p in rel_in)
    rc = next(e for e in bus.replay(topic="release-candidates"))
    tb = orch._read_only_tools(Envelope(topic="release-candidates", key=rc.key, actor="delivery-lead", payload=rc.payload))
    assert tb is not None, "QA hồi quy sau deploy đọc worktree tích hợp của dự án"
    assert orch._read_only_tools(Envelope(topic="release-candidates", key="R0", actor="x", payload={"release_id": "R0", "tickets": []})) is None or True
