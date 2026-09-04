"""ADR-0026: giao hàng thật — tag `v<version>` + fast-forward `company/release` trong repo khách khi production được duyệt;
rollback lùi con trỏ (tag giữ nguyên); push tuỳ chọn, lỗi push không chặn; `main` của khách không bị chạm."""
from __future__ import annotations

import json
import subprocess

import pytest

from company.bus import InMemoryBus
from company.events import Envelope
from company.llm import FakeClient
from company.orchestrator import Orchestrator
from company.orchestrator import main as orch_main
from company.sqlite_bus import SQLiteBus
from company.workspace import Integration, TicketWorkspace, WorkspaceError
from test_orchestrator import _drive_to_plan, handler
from test_tools_and_agentic import _init_repo, _repo_tool_handler


def _git(repo, *a) -> str:
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, encoding="utf-8").stdout.strip()


def _rev(repo, ref) -> str:
    return _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")


def _merge_ticket(repo, it: Integration, tid: str, fname: str) -> str:
    ws = TicketWorkspace(repo, tid, base=it.branch); ws.create()
    (ws.path / fname).write_text(f"X = '{tid}'\n", encoding="utf-8"); ws.commit_all(f"feat({tid}): {fname}")
    m = it.merge(ws.branch, f"merge({tid})"); assert m.ok
    return _rev(repo, it.branch)


def _audits(bus, prefix):
    return [(e.payload["action"], json.loads(e.payload["evidence"] or "{}")) for e in bus.replay(topic="audit-log")
            if e.payload["action"].startswith(prefix)]


# ---------- Integration.deliver / rollback_delivery / push ----------

def test_deliver_tag_va_fast_forward_nhanh_release(tmp_path):
    repo = _init_repo(tmp_path / "repo"); it = Integration(repo, base="main"); it.ensure()
    sha_a = _merge_ticket(repo, it, "A", "a.py")
    r = it.deliver("0.1.1", "release REL-001 v0.1.1\n\ntickets: A")
    assert r.ok and r.tag == "v0.1.1" and r.tag_created and r.branch_moved and r.previous is None and r.pushed is None
    assert r.sha == sha_a == _rev(repo, "v0.1.1") == _rev(repo, "company/release") and r.short == sha_a[:7]
    assert _git(repo, "cat-file", "-t", "v0.1.1") == "tag", "tag chú thích, có thông điệp release"
    assert "tickets: A" in _git(repo, "tag", "-l", "-n3", "v0.1.1")
    assert _git(repo, "log", "-1", "--format=%s", "main") == "init", "main của khách không bị chạm"
    # idempotent: giao lại cùng phiên bản → không tạo gì, không lỗi
    r2 = it.deliver("0.1.1", "lại")
    assert r2.ok and not r2.tag_created and not r2.branch_moved and r2.previous == sha_a
    # lần giao sau: fast-forward, nhớ sha trước để rollback
    sha_b = _merge_ticket(repo, it, "B", "b.py")
    r3 = it.deliver("0.1.2", "release REL-002")
    assert r3.ok and r3.tag_created and r3.branch_moved and r3.previous == sha_a and r3.sha == sha_b
    assert _rev(repo, "company/release") == sha_b and _git(repo, "tag", "-l").split() == ["v0.1.1", "v0.1.2"]
    # giao một sha cụ thể (sha đã kiểm trên staging), không phải đầu nhánh tích hợp
    sha_c = _merge_ticket(repo, it, "C", "c.py")
    r4 = it.deliver("0.1.3", "x", sha=sha_b)
    assert r4.ok and r4.sha == sha_b and not r4.branch_moved and _rev(repo, "v0.1.3") == sha_b != sha_c
    assert _rev(repo, "company/release") == sha_b, "sha đã giao nằm sau con trỏ → không lùi, không lỗi"


def test_deliver_khong_ghi_de_tag_khong_ep_nhanh_lech(tmp_path):
    repo = _init_repo(tmp_path / "repo"); it = Integration(repo, base="main"); it.ensure()
    _merge_ticket(repo, it, "A", "a.py")
    subprocess.run(["git", "-C", str(repo), "tag", "v9.9.9", "main"], check=True)
    r = it.deliver("9.9.9", "x")
    assert not r.ok and r.problems == [f"tag_conflict:v9.9.9@{_rev(repo, 'main')[:7]}"] and not r.tag_created
    assert _rev(repo, "v9.9.9") == _rev(repo, "main"), "tag đã có ở sha khác thì giữ nguyên"
    assert r.branch_moved and _rev(repo, "company/release") == r.sha, "nhánh release vẫn được tạo"
    # ai đó commit thẳng lên company/release → lần giao sau không fast-forward được → nhánh giữ nguyên, tag vẫn tạo
    tay = TicketWorkspace(repo, "tay", base="main"); tay.create()
    (tay.path / "tay.py").write_text("x = 1\n", encoding="utf-8"); tay.commit_all("sửa tay")
    subprocess.run(["git", "-C", str(repo), "branch", "-f", "company/release", tay.branch], check=True)
    sha_b = _merge_ticket(repo, it, "B", "b.py")
    r2 = it.deliver("0.2.0", "y")
    assert not r2.ok and r2.problems == [f"diverged:{_rev(repo, tay.branch)[:7]}"] and r2.tag_created and not r2.branch_moved
    assert _rev(repo, "company/release") == _rev(repo, tay.branch) and _rev(repo, "v0.2.0") == sha_b
    with pytest.raises(WorkspaceError, match="chưa có gì để giao"):
        Integration(_init_repo(tmp_path / "trong"), base="main").deliver("0.1.0", "z")
    with pytest.raises(WorkspaceError, match="chưa có gì để giao"):
        it.deliver("0.3.0", "z", sha="0000000000000000000000000000000000000000")


def test_rollback_lui_con_tro_giu_tag_va_khong_de_len_release_sau(tmp_path):
    repo = _init_repo(tmp_path / "repo"); it = Integration(repo, base="main"); it.ensure()
    _merge_ticket(repo, it, "A", "a.py"); r1 = it.deliver("0.1.1", "1")
    _merge_ticket(repo, it, "B", "b.py"); r2 = it.deliver("0.1.2", "2")
    rb = it.rollback_delivery(r2.previous, expected=r2.sha)
    assert rb.ok and rb.branch_moved and _rev(repo, "company/release") == r1.sha and _rev(repo, "v0.1.2") == r2.sha
    # release sau đã lên: rollback của bản trước không được lùi đè lên nó
    r3 = it.deliver("0.1.3", "3", sha=r2.sha)
    assert r3.ok and _rev(repo, "company/release") == r2.sha
    sup = it.rollback_delivery(r1.previous, expected=r1.sha)
    assert not sup.ok and sup.problems == [f"superseded:{r2.sha[:7]}"] and _rev(repo, "company/release") == r2.sha
    # lần giao đầu: rollback xoá nhánh; rollback lần nữa → nhánh không còn
    rb3 = it.rollback_delivery(None, expected=r2.sha)
    assert rb3.ok and rb3.branch_moved and not _git(repo, "branch", "--list", "company/release")
    rb4 = it.rollback_delivery(None, expected=r2.sha)
    assert not rb4.ok and rb4.problems == ["missing:nhánh release không còn"]
    assert _git(repo, "tag", "-l").split() == ["v0.1.1", "v0.1.2", "v0.1.3"], "tag là lịch sử bất biến"


def test_push_len_remote_cua_khach_va_loi_push_khong_chan(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    bare = tmp_path / "remote.git"; subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(bare)], check=True)
    it = Integration(repo, base="main"); it.ensure(); _merge_ticket(repo, it, "A", "a.py")
    r = it.deliver("0.1.1", "1", push_remote="origin")
    assert r.ok and r.pushed is True and r.push_error == ""
    assert _rev(bare, "company/release") == r.sha and _rev(bare, "v0.1.1") == r.sha
    _merge_ticket(repo, it, "B", "b.py"); r2 = it.deliver("0.1.2", "2", push_remote="origin")
    assert r2.pushed is True and _rev(bare, "company/release") == r2.sha
    rb = it.rollback_delivery(r2.previous, expected=r2.sha, push_remote="origin")
    assert rb.ok and rb.pushed is True and _rev(bare, "company/release") == r.sha, "force-with-lease lùi remote về bản trước"
    # remote không tồn tại: bản giao cục bộ vẫn xong, lỗi push chỉ được ghi lại
    _merge_ticket(repo, it, "C", "c.py"); r3 = it.deliver("0.1.3", "3", push_remote="khong-co")
    assert r3.ok and r3.tag_created and r3.pushed is False and r3.push_error
    # remote đã bị người khác đẩy đi (lease sai) → push bị từ chối, nhánh cục bộ vẫn lùi, không đè lên remote
    subprocess.run(["git", "-C", str(repo), "push", "-q", "origin", f"{r3.sha}:refs/heads/company/release"], check=True)
    rb2 = it.rollback_delivery(r2.sha, expected=r3.sha, push_remote="origin")
    assert rb2.ok and rb2.branch_moved and rb2.pushed is True and _rev(bare, "company/release") == r2.sha
    subprocess.run(["git", "-C", str(repo), "push", "-q", "origin", f"{r3.sha}:refs/heads/company/release"], check=True)
    it2 = Integration(repo, base="main"); subprocess.run(["git", "-C", str(repo), "branch", "-f", "company/release", r3.sha], check=True)
    rb3 = it2.rollback_delivery(r.sha, expected=r3.sha, push_remote="origin")  # lease đúng cục bộ, remote đã khác? không — remote = r3
    assert rb3.ok and rb3.pushed is True
    subprocess.run(["git", "-C", str(repo), "branch", "-f", "company/release", r3.sha], check=True)
    rb4 = it2.rollback_delivery(r2.sha, expected=r3.sha, push_remote="origin")  # remote đang ở r.sha, lease đòi r3 → từ chối
    assert rb4.ok and rb4.branch_moved and rb4.pushed is False and rb4.push_error and _rev(bare, "company/release") == r.sha
    # giao lại cùng phiên bản lên remote hợp lệ: push lại tag/nhánh là idempotent
    r5 = it.deliver("0.1.3", "3", push_remote="origin")
    assert r5.ok and r5.pushed is True and r5.push_error == "" and _rev(bare, "company/release") == r3.sha
    # không có ref nào để push (tag trùng ở sha khác, nhánh đã đúng chỗ) → không gọi push, không báo lỗi push
    subprocess.run(["git", "-C", str(repo), "tag", "v7.7.7", "main"], check=True)
    r6 = it.deliver("7.7.7", "x", sha=r3.sha, push_remote="khong-co")
    assert not r6.ok and r6.problems[0].startswith("tag_conflict") and not r6.branch_moved
    assert r6.pushed is True and r6.push_error == ""


# ---------- orchestrator: production duyệt → giao; rolled_back → lùi; bền qua restart ----------

def test_orchestrator_giao_hang_khi_production_va_lui_khi_rollback(tmp_path):
    repo = _init_repo(tmp_path / "repo"); db = tmp_path / "c.sqlite"
    bus = SQLiteBus(db); client = FakeClient(handler=handler, tool_handler=_repo_tool_handler)
    orch = Orchestrator(bus, client, repo=repo, base="main", deliver=True)
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    assert orch.lead.state == {"T1": "merged", "T2": "merged"} and orch.stats["errors"] == 0
    assert not orch.delivered and not _git(repo, "tag", "-l"), "chưa qua gate 3 thì chưa giao"
    staged = orch.release_sha
    assert set(staged) == {"REL-001", "REL-002"} and staged["REL-001"] != staged["REL-002"]
    assert _git(repo, "ls-tree", "-r", "--name-only", staged["REL-001"]).split().count("f_t2.py") == 0, "sha staging của REL-001 chưa có T2"

    orch.gate.decide("REL-001", "approve", by="human:release-manager"); orch.run()
    d = orch.delivered["REL-001"]
    assert d["version"] == "0.1.1" and d["tag"] == "v0.1.1" and d["tag_created"] and d["branch_moved"]
    assert d["problems"] == [] and d["pushed"] is None and d["previous"] is None and d["sha"] == staged["REL-001"]
    assert _rev(repo, "v0.1.1") == d["sha"] == _rev(repo, "company/release"), "tag ở đúng sha QA đã hồi quy, không phải đầu nhánh tích hợp"
    assert _rev(repo, "company/integration") == staged["REL-002"] != d["sha"]
    assert "f_t2.py" not in _git(repo, "ls-tree", "-r", "--name-only", "v0.1.1")
    assert _git(repo, "log", "-1", "--format=%s", "main") == "init", "main của khách không bị chạm"
    done = _audits(bus, "delivery.")
    assert [a for a, _ in done] == ["delivery.done"] and done[0][1]["release_id"] == "REL-001"
    st = orch.status()["delivery"]
    assert st == {"REL-001": {"version": "0.1.1", "tag": "v0.1.1", "short": d["short"], "branch": "company/release",
                              "problems": [], "pushed": None}}
    assert any(a.startswith("delivered:REL-001@v0.1.1") for r in orch.run() for a in r.actions) is False, "không giao lại"

    # mở lại bus: bản đã giao và sha staging dựng lại từ audit-log
    o2 = Orchestrator(SQLiteBus(db), FakeClient(handler=handler, tool_handler=_repo_tool_handler), repo=repo, base="main", deliver=True)
    assert o2.delivered == orch.delivered and o2.release_sha == orch.release_sha
    assert not _git(repo, "tag", "-l").split() != ["v0.1.1"] and o2.run() == [], "mở lại không tag lại, không giao lại"

    # REL-002 lên production: fast-forward tiếp
    orch.gate.decide("REL-002", "approve", by="human:release-manager"); orch.run()
    d2 = orch.delivered["REL-002"]
    assert d2["tag"] == "v0.2.0" and d2["previous"] == d["sha"] and _rev(repo, "company/release") == d2["sha"] == staged["REL-002"]

    # production của REL-002 rolled_back → con trỏ lùi về REL-001, tag v0.2.0 giữ nguyên
    bus.publish(Envelope(topic="release-events", key="REL-002", actor="release-engineer",
                         payload={"release_id": "REL-002", "version": "0.2.0", "env": "production", "status": "rolled_back"}))
    orch.run()
    assert "REL-002" not in orch.delivered and "REL-001" in orch.delivered
    assert _rev(repo, "company/release") == d["sha"] and _rev(repo, "v0.2.0") == d2["sha"]
    rb = [ev for a, ev in _audits(bus, "delivery.rolled_back")]
    assert rb and rb[0]["from"] == d2["sha"] and rb[0]["to"] == d["sha"] and rb[0]["problems"] == []
    o3 = Orchestrator(SQLiteBus(db), FakeClient(handler=handler), repo=repo, base="main", deliver=True)
    assert set(o3.delivered) == {"REL-001"}


def test_khong_bat_deliver_thi_nhu_cu(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler, tool_handler=_repo_tool_handler), repo=repo, base="main")
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    orch.gate.decide("REL-001", "approve", by="human:release-manager"); orch.run()
    assert orch.lead.state["T1"] == "released" and not orch.delivered and orch.status()["delivery"] == {}
    assert not _git(repo, "tag", "-l") and not _git(repo, "branch", "--list", "company/release")
    assert not _audits(bus, "delivery.") and orch.release_sha, "sha staging vẫn được ghi để bật giao hàng về sau"


def test_deliver_khong_repo_thi_bo_qua_co_audit(tmp_path):
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler), deliver=True)
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    orch.gate.decide("REL-001", "approve", by="human:release-manager"); orch.run()
    assert orch.lead.state["T1"] == "released" and not orch.delivered
    skipped = _audits(bus, "delivery.skipped")
    assert len(skipped) == 1 and "không có nhánh tích hợp" in skipped[0][1]["reason"]


def test_deliver_ghi_van_de_va_loi_push_vao_audit(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    subprocess.run(["git", "-C", str(repo), "tag", "v0.1.1", "main"], check=True)  # tag trùng phiên bản sẽ giao
    bus = InMemoryBus()
    orch = Orchestrator(bus, FakeClient(handler=handler, tool_handler=_repo_tool_handler), repo=repo, base="main",
                        deliver=True, push_remote="khong-co", release_branch="rel/prod")
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    res = []
    orch.gate.decide("REL-001", "approve", by="human:release-manager"); res = orch.run()
    d = orch.delivered["REL-001"]
    assert d["problems"] == [f"tag_conflict:v0.1.1@{_rev(repo, 'main')[:7]}"] and d["pushed"] is False and d["push_error"]
    assert d["branch"] == "rel/prod" and _rev(repo, "rel/prod") == d["sha"]
    acts = [a for a, _ in _audits(bus, "delivery.")]
    assert acts == ["delivery.done", "delivery.tag_conflict", "delivery.push_failed"]
    assert any(a.startswith("delivered:REL-001@v0.1.1(tag_conflict") for r in res for a in r.actions)


def test_cli_co_co_deliver(tmp_path, capsys):
    repo = _init_repo(tmp_path / "repo"); db = str(tmp_path / "c.sqlite")
    assert orch_main(["--db", db, "--repo", str(repo), "--deliver", "--push-remote", "origin", "--release-branch", "rel", "status"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["delivery"] == {}
