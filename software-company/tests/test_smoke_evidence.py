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
    # ADR-0031: spec ứng dụng chưa khai `runtime` không được mở gate spec — các ca dưới đây đo giai đoạn RELEASE
    # (smoke, QA hồi quy) nên spec nền khai `kind: library` để dừng đúng ở gate spec như trước; ca nào khảo sát
    # `kind` thì tự publish lại spec với kind của nó.
    spec = {"project_id": "P", "status": "approved", "kind": "library",
            "artifacts": {"prd": "prd", "requirements": "req"}}
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


def test_run_smoke_communicate_qua_gio_khong_lam_hong_bang_chung(tmp_path, monkeypatch):
    """Tiến trình bị kill mà `communicate` vẫn treo (pipe stderr bị con giữ) → bỏ qua stderr, bằng chứng còn lại giữ nguyên."""
    import subprocess as sp

    from company import smoke as sm

    class Proc:
        returncode = 7
        def poll(self): return 7
        def kill(self): raise AssertionError("đã chết thì không kill")
        def communicate(self, timeout=None): raise sp.TimeoutExpired(cmd="x", timeout=timeout)

    monkeypatch.setattr(sm.subprocess, "Popen", lambda *a, **k: Proc())
    r = run_smoke(tmp_path, Runtime(("x",), timeout_s=2))
    assert r["ok"] is False and r["exit_code"] == 7 and "stderr_tail" not in r


# ---------- ADR-0029 mở rộng (B3): `regression-staging` mang `evidence.run` do orchestrator tự chạy ----------

def _qa_reviews(bus):
    return [e.payload for e in bus.replay(topic="review-results") if e.payload.get("source") == "qa"]


def _acts(bus):
    return [e.payload["action"] for e in bus.replay(topic="audit-log")]


def _fake_smoke(monkeypatch, results):
    """Runtime giả: `run_smoke` của `company.orch.verify` (K1: tách khỏi orchestrator.py, ADR-0034) trả lần lượt
    từng kết quả (lượt deployed rồi lượt QA hồi quy)."""
    from company.orch import verify as ov
    calls: list[Path] = []
    def fake(root, rt):
        calls.append(root)
        return dict(results[min(len(calls), len(results)) - 1])
    monkeypatch.setattr(ov, "run_smoke", fake)
    return calls


OK = {"verified_by": "orchestrator", "command": ["python", "serve.py", "8123"], "port": 8123, "url": "http://127.0.0.1:8123/",
      "ok": True, "http_status": 200, "exit_code": None, "elapsed_s": 0.5}
BAD = {**OK, "ok": False, "http_status": 500, "elapsed_s": 0.7}


def test_regression_staging_giu_pass_va_mang_evidence_run_khi_smoke_200(tmp_path, monkeypatch):
    repo = _repo(tmp_path, SERVER_DIE)
    calls = _fake_smoke(monkeypatch, [OK, OK])
    bus, orch = _orch(tmp_path, repo, {"command": "python serve.py {port}", "timeout_s": 5})
    orch.run()
    qa = _qa_reviews(bus)
    assert qa and qa[-1]["verdict"] == "pass"
    run = qa[-1]["evidence"]["run"]
    assert run["ok"] is True and run["http_status"] == 200 and run["verified_by"] == "orchestrator"
    assert run["command"] == OK["command"] and run["sha"], "lệnh thật và sha RC: người ký Gate 3 biết CÁI GÌ đã chạy"
    assert len(calls) == 2 and all(str(c).endswith("_integration") for c in calls), "một lần cho deployed, một lần cho QA — cùng worktree tích hợp"
    acts = _acts(bus)
    assert "regression.run" in acts and "regression.run_failed" not in acts and "regression.verdict_overridden" not in acts
    g = orch.gate.pending.get("REL-001")
    assert g is not None and g.kind == "release", "smoke ok + QA pass → Gate 3 mở như thường"


def test_regression_staging_pass_ma_smoke_fail_thi_ha_fail_rc_khong_di_tiep(tmp_path, monkeypatch):
    """Chiều đo quan trọng nhất: deployed qua smoke, nhưng ở lượt QA sản phẩm không trả lời đúng → verdict pass của
    model bị hạ `fail`, escalation mở cho RC, Gate 3 KHÔNG mở."""
    repo = _repo(tmp_path, SERVER_DIE)
    _fake_smoke(monkeypatch, [OK, BAD])
    bus, orch = _orch(tmp_path, repo, {"command": "python serve.py {port}", "timeout_s": 5})
    orch.run()
    qa = _qa_reviews(bus)
    assert qa and qa[-1]["verdict"] == "fail", "verdict không có bằng chứng chạy đạt thì không được là pass"
    assert qa[-1]["evidence"]["run"]["http_status"] == 500
    assert any(f["level"] == "block" and "http_status=500" in f["text"] for f in qa[-1]["findings"])
    assert "http_status=500" in qa[-1]["root_cause"]
    acts = _acts(bus)
    assert "regression.run_failed" in acts and "regression.verdict_overridden" in acts
    g = orch.gate.pending.get("REL-001")
    assert g is not None and g.kind == "escalation", "RC fail không nằm im: escalation cho người quyết"


def test_khong_runtime_kind_application_thi_unverified_va_rc_khong_di_tiep(tmp_path, monkeypatch):
    repo = _repo(tmp_path, SERVER_DIE)
    calls = _fake_smoke(monkeypatch, [OK])
    bus, orch = _orch(tmp_path, repo, None)
    spec = bus.latest("approved-specs", "P").payload
    bus.publish(Envelope(topic="approved-specs", key="P", actor="spec-writer", payload={**spec, "kind": "application"}))
    orch.run()
    assert calls == [], "không có runtime thì không có gì để chạy — không đoán lệnh"
    st = _staging(bus)
    assert st[-1]["status"] == "deployed" and st[-1]["smoke"]["unverified"] is True, "deployed giữ nguyên như ADR-0029 mục 3"
    qa = _qa_reviews(bus)
    run = qa[-1]["evidence"]["run"]
    assert run["unverified"] is True and "runtime" in run["reason"] and run["spec_kind"] == "application"
    assert qa[-1]["verdict"] == "fail" and "kind=application" in qa[-1]["root_cause"]
    acts = _acts(bus)
    assert "regression.run_unverified" in acts and "regression.verdict_overridden" in acts
    g = orch.gate.pending.get("REL-001")
    assert g is not None and g.kind == "escalation" and g.kind != "release"


def test_khong_runtime_kind_library_hay_docs_thi_unverified_khong_chan(tmp_path, monkeypatch):
    """`library`/`docs` không có server: smoke `unverified` nhưng KHÔNG chặn RC.

    Trước ADR-0031 ca này còn nhánh "spec chưa khai kind" — nay thiếu `kind` = `application` (im lặng không phải
    miễn trừ) nên spec đó bị chặn ngay ở Gate 1, không bao giờ tới được RC; nhánh ấy đo ở
    `tests/test_gate_spec_runtime.py`."""
    for kind in ("library", "docs"):
        d = tmp_path / kind; d.mkdir()
        repo = _repo(d, SERVER_DIE)
        _fake_smoke(monkeypatch, [OK])
        bus, orch = _orch(d, repo, None)
        spec = bus.latest("approved-specs", "P").payload
        bus.publish(Envelope(topic="approved-specs", key="P", actor="spec-writer", payload={**spec, "kind": kind}))
        orch.run()
        qa = _qa_reviews(bus)
        assert qa[-1]["verdict"] == "pass" and qa[-1]["evidence"]["run"]["unverified"] is True
        assert qa[-1]["evidence"]["run"]["spec_kind"] == kind
        assert "regression.run_unverified" in _acts(bus) and "regression.verdict_overridden" not in _acts(bus)
        g = orch.gate.pending.get("REL-001")
        assert g is not None and g.kind == "release", f"kind={kind}: không chặn cứng, nhưng bằng chứng nói 'chưa kiểm'"


def test_qa_thay_evidence_run_trong_input_va_loi_khai_cua_no_bi_bo(tmp_path, monkeypatch):
    """Prompt qa-debugger v13 nói 'kết quả ở payload.evidence.run' — input phải THẬT SỰ mang nó; và mọi
    `evidence.run` model tự khai bị thay bằng bản của orchestrator (một nguồn bằng chứng duy nhất)."""
    from test_orchestrator import _agent_of, _inp
    seen: list[dict] = []
    def h(system, user):
        out = handler(system, user)
        if _agent_of(system) == "qa-debugger":
            seen.append(_inp(user))
            out = {**out, "evidence": {"run": {"ok": True, "http_status": 200, "verified_by": "qa-debugger"}, "note": "giữ"}}
        return out
    repo = _repo(tmp_path, SERVER_DIE)
    _fake_smoke(monkeypatch, [OK, BAD])
    bus, orch = _orch(tmp_path, repo, {"command": "python serve.py {port}"})
    orch.runner.client = FakeClient(handler=h)
    orch.run()
    assert seen and seen[-1]["evidence"]["run"]["http_status"] == 500, "QA nhìn thấy đúng kết quả máy vừa chạy"
    qa = _qa_reviews(bus)
    assert qa[-1]["evidence"]["run"]["verified_by"] == "orchestrator" and qa[-1]["evidence"]["note"] == "giữ"
    assert qa[-1]["verdict"] == "fail" and "regression.run_claimed_ignored" in _acts(bus)


def test_evidence_run_song_qua_restart_va_redeploy_khong_bi_once_nuot(tmp_path, monkeypatch):
    """TRAPS §1 khuôn 2/3: bằng chứng ở trên bus (không RAM) — mở lại bus vẫn đọc được; RC redeploy là lượt deployed
    THỨ HAI hợp lệ → `regression.run_unverified` phải ghi lần nữa (khoá once mang event_id)."""
    repo = _repo(tmp_path, SERVER_DIE)
    _fake_smoke(monkeypatch, [OK])
    bus, orch = _orch(tmp_path, repo, None)
    orch.run()
    assert _acts(bus).count("regression.run_unverified") == 1
    bus2 = SQLiteBus(tmp_path / "c.sqlite")
    orch2 = Orchestrator(bus2, FakeClient(handler=handler), repo=repo)
    qa = [e.payload for e in bus2.replay(topic="review-results") if e.payload.get("source") == "qa"]
    assert qa[-1]["evidence"]["run"]["unverified"] is True
    assert orch2.lead.release_qa["REL-001"].verdict == "pass"
    assert "regression.unverified:REL-001:" in " ".join(orch2.once), "khoá once dựng lại từ audit-log"
    bus2.publish(Envelope(topic="release-events", key="REL-001", actor="release-engineer",
                          payload={"release_id": "REL-001", "env": "staging", "status": "deployed", "version": "0.1.0"}))
    orch2.run()
    assert _acts(bus2).count("regression.run_unverified") == 2, "lượt deployed thứ hai không bị khoá của lượt một nuốt"


def test_verdict_with_run_giu_fail_cua_model_va_khong_nhan_doi_finding(tmp_path):
    """Model đã fail (tự thấy lỗi) và smoke cũng fail → giữ fail, không ghi `verdict_overridden`."""
    bus, orch = _orch(tmp_path, None, None)
    env = Envelope(topic="release-events", key="REL-001", actor="release-engineer",
                   payload={"release_id": "REL-001", "env": "staging", "status": "deployed"})
    p = orch._verdict_with_run("qa-debugger", env, {"ticket_id": "REL-001", "source": "qa", "verdict": "fail",
                                                    "root_cause": "của model", "findings": []}, BAD)
    assert p["verdict"] == "fail" and p["root_cause"] == "của model" and p["findings"] == []
    assert p["evidence"]["run"] == BAD
    assert "regression.verdict_overridden" not in _acts(bus) and "regression.run_failed" in _acts(bus)


def test_khong_co_worktree_thi_regression_run_unverified_noi_ro(tmp_path):
    bus, orch = _orch(tmp_path, None, {"command": "python serve.py"})
    orch.run()
    qa = _qa_reviews(bus)
    assert qa[-1]["evidence"]["run"]["unverified"] is True and "worktree" in qa[-1]["evidence"]["run"]["reason"]


def test_gate_brief_release_hien_evidence_run(tmp_path, monkeypatch):
    from company.gate_brief import _run_summary, build, render_md
    assert _run_summary({"evidence": {"run": {"unverified": True, "reason": "x"}}}) == "unverified — x"
    assert _run_summary({"evidence": {"run": OK}}) == "ok=True http=200 exit=None (orchestrator)"
    assert _run_summary({"evidence": {"run": "lạ"}}) is None and _run_summary({}) is None
    repo = _repo(tmp_path, SERVER_DIE)
    _fake_smoke(monkeypatch, [OK, OK])
    _, orch = _orch(tmp_path, repo, {"command": "python serve.py {port}"})
    orch.run()
    b = build(orch, "REL-001")
    assert b["extra"]["staging_reviews"][0]["run"].startswith("ok=True http=200")
    assert "chạy: ok=True http=200" in render_md(b)
