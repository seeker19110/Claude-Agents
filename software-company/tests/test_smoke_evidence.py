"""ADR-0029: `status=deployed` ở staging phải kèm bằng chứng máy chạy (`smoke`, `verified_by=orchestrator`).

Đo được 2026-09-06 (QLKH): 4 gate xanh, 389 test pass, 25 release — 0 điểm vào chạy được. `deployed` là lời khai
của release-engineer, `regression-staging` là verdict đọc diff. Test ở đây đo cả hai chiều: sản phẩm chạy → `ok`;
sản phẩm chết / không trả lời → status bị ghi đè thành `failed`; spec không khai `runtime` → `unverified` nói thẳng."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from company.events import Envelope, Task
from company.llm import FakeClient
from company.orchestrator import Orchestrator
from company.smoke import Runtime, parse_runtime, run_smoke, unverified
from company.sqlite_bus import SQLiteBus
from test_orchestrator import handler

SERVER_OK = "import http.server,sys;http.server.test(http.server.SimpleHTTPRequestHandler,port=int(sys.argv[1]),bind='127.0.0.1')"
SERVER_DIE = "import sys;sys.stderr.write('config thiếu DATABASE_URL\\n');sys.exit(3)"


# ---------- run_smoke: đơn vị ----------

def test_run_smoke_ok_khi_san_pham_tra_loi(tmp_path):
    rt = Runtime((sys.executable, "-c", SERVER_OK, "{port}"), path="/", timeout_s=20)
    r = run_smoke(tmp_path, rt)
    assert r["ok"] is True and r["http_status"] == 200 and r["verified_by"] == "orchestrator"
    assert str(r["port"]) in r["command"][-1], "cổng trống được thế vào `{port}`"
    assert r["exit_code"] is None, "tiến trình bị orchestrator giết sau khi có bằng chứng, không phải tự chết"


def test_run_smoke_ghi_ma_thoat_va_stderr_khi_chet_som(tmp_path):
    rt = Runtime((sys.executable, "-c", SERVER_DIE), timeout_s=10)
    r = run_smoke(tmp_path, rt)
    assert r["ok"] is False and r["exit_code"] == 3 and r["http_status"] is None
    assert "DATABASE_URL" in r.get("stderr_tail", ""), "đuôi stderr là thứ người đọc cần để hiểu vì sao"


def test_run_smoke_het_gio_khi_khong_tra_loi(tmp_path):
    rt = Runtime((sys.executable, "-c", "import time;time.sleep(30)"), timeout_s=2)
    r = run_smoke(tmp_path, rt)
    assert r["ok"] is False and "không trả lời" in r["error"] and r["elapsed_s"] < 10


def test_run_smoke_lenh_khong_ton_tai(tmp_path):
    r = run_smoke(tmp_path, Runtime(("lenh-khong-co-that-xyz",), timeout_s=2))
    assert r["ok"] is False and "error" in r


def test_run_smoke_ma_http_khac_ky_vong_khong_phai_ok(tmp_path):
    rt = Runtime((sys.executable, "-c", SERVER_OK, "{port}"), path="/khong-co-file-nay", timeout_s=20)
    r = run_smoke(tmp_path, rt)
    assert r["http_status"] == 404 and r["ok"] is False


# ---------- parse_runtime ----------

def test_parse_runtime_chuoi_hay_danh_sach_deu_duoc():
    a = parse_runtime({"runtime": {"command": "python -m app --port {port}", "health": "health", "port": 0}})
    assert a is not None and a.command == ("python", "-m", "app", "--port", "{port}") and a.path == "/health"
    assert a.argv(8123)[0] == sys.executable and "8123" in a.argv(8123)
    b = parse_runtime({"runtime": {"command": ["npm", "start"], "port": 3000}})
    assert b is not None and b.port == 3000 and b.path == "/"


def test_parse_runtime_thieu_hoac_hong_thi_none():
    assert parse_runtime(None) is None
    assert parse_runtime({}) is None
    assert parse_runtime({"runtime": "python -m app"}) is None
    assert parse_runtime({"runtime": {"command": ""}}) is None
    assert parse_runtime({"runtime": {"command": ["x"], "port": "abc"}}) is None


def test_unverified_noi_ly_do():
    u = unverified("vì sao")
    assert u["unverified"] is True and u["reason"] == "vì sao" and u["verified_by"] == "orchestrator"


# ---------- orchestrator: lời khai `deployed` đi qua smoke ----------

def _git(repo: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True).stdout.strip()


def _repo(tmp_path: Path, server_src: str) -> Path:
    repo = tmp_path / "khach"; repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t"); _git(repo, "config", "user.name", "t")
    (repo / "pyproject.toml").write_text("[project]\nname='app'\nversion='0'\n", encoding="utf-8")
    (repo / "serve.py").write_text(server_src, encoding="utf-8")
    _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "init")
    return repo


def _orch(tmp_path: Path, repo: Path | None, runtime: dict | None):
    bus = SQLiteBus(tmp_path / "c.sqlite")
    orch = Orchestrator(bus, FakeClient(handler=handler), repo=repo)
    orch.lead.tickets["T1"] = Task(ticket_id="T1", project_id="P", requirement_id="R1", assignee="backend",
                                   title="T1", acceptance=["a"])
    orch.lead.state["T1"] = "approved"
    spec = {"project_id": "P", "status": "approved", "artifacts": {"prd": "prd", "requirements": "req"}}
    if runtime is not None: spec["runtime"] = runtime
    bus.publish(Envelope(topic="approved-specs", key="P", actor="spec-writer", payload=spec))
    bus.publish(Envelope(topic="release-candidates", key="REL-001", actor="delivery-lead",
                         payload={"release_id": "REL-001", "project_id": "P", "tickets": ["T1"], "version": "0.1.0",
                                  "notes": "rc"}))
    return bus, orch


def _staging(bus):
    return [e.payload for e in bus.replay(topic="release-events") if e.payload.get("env") == "staging"]


def test_deployed_kem_smoke_ok_khi_san_pham_chay(tmp_path):
    repo = _repo(tmp_path, f"import sys\n{SERVER_OK}\n")
    bus, orch = _orch(tmp_path, repo, {"command": "python serve.py {port}", "health": "/", "timeout_s": 20})
    orch.run()
    st = _staging(bus)
    assert st and st[-1]["status"] == "deployed"
    sm = st[-1]["smoke"]
    assert sm["ok"] is True and sm["http_status"] == 200 and sm["verified_by"] == "orchestrator"
    assert sm["cwd"].endswith("_integration"), "chạy trong worktree tích hợp, không phải repo gốc của khách"
    acts = [e.payload["action"] for e in bus.replay(topic="audit-log")]
    assert "release.smoke" in acts and "release.smoke_failed" not in acts
    # lượt production phải THẤY bằng chứng smoke trong evidence (agent không có tool đọc bus)
    assert orch._release_evidence("REL-001")["staging"]["smoke"]["ok"] is True


def test_deployed_bi_ghi_de_failed_khi_san_pham_khong_chay(tmp_path):
    """Chiều đo quan trọng nhất: release-engineer khai `deployed` nhưng máy khởi động không được → `failed`."""
    repo = _repo(tmp_path, SERVER_DIE)
    bus, orch = _orch(tmp_path, repo, {"command": "python serve.py", "port": 0, "timeout_s": 10})
    orch.run()
    st = _staging(bus)
    assert st and st[-1]["status"] == "failed", "bốn gate xanh không được che một sản phẩm không chạy"
    assert st[-1]["smoke"]["exit_code"] == 3
    fails = [e.payload for e in bus.replay(topic="audit-log") if e.payload["action"] == "release.smoke_failed"]
    assert fails and fails[0]["ticket_id"] is None and "REL-001" in fails[0]["evidence"]
    g = orch.gate.pending.get("REL-001")
    assert g is not None and g.kind == "escalation", "RC failed không được nằm im: mở escalation cho người quyết"
    assert g.kind != "release", "không có deployed thật thì QA hồi quy không chạy, Gate 3 không mở"


def test_khong_khai_runtime_thi_unverified_khong_chan(tmp_path):
    repo = _repo(tmp_path, SERVER_DIE)
    bus, orch = _orch(tmp_path, repo, None)
    orch.run()
    st = _staging(bus)
    assert st[-1]["status"] == "deployed" and st[-1]["smoke"]["unverified"] is True
    assert "runtime" in st[-1]["smoke"]["reason"]
    acts = [e.payload["action"] for e in bus.replay(topic="audit-log")]
    assert acts.count("release.smoke_unverified") == 1


def test_khong_co_repo_thi_unverified_noi_ro_ly_do(tmp_path):
    bus, orch = _orch(tmp_path, None, {"command": "python serve.py"})
    orch.run()
    st = _staging(bus)
    assert st[-1]["status"] == "deployed" and st[-1]["smoke"]["unverified"] is True
    assert "worktree" in st[-1]["smoke"]["reason"]
