"""Orchestrator tự khởi động lại khi mã nguồn đổi — không còn taskkill + xoá lock bằng tay sau mỗi PR merge.

Đo được 2026-09-06: 4 lần restart tay trong một buổi; một lần quên xoá lock nên tiến trình mới thoát ngay mà tưởng đã
chạy. Vòng watch so `source_fingerprint()` mỗi nhịp; đổi và hàng đợi rỗng → `ReloadRequested` → `main` trả lease rồi
exec lại chính lệnh đó.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

import company.orchestrator as om
from company.bus import InMemoryBus
from company.events import Envelope
from company.llm import FakeClient
from company.orchestrator import Orchestrator, ReloadRequested, source_fingerprint
from company.orchestrator import main as orch_main
from test_orchestrator import handler


def _tree(tmp_path: Path) -> Path:
    (tmp_path / "src" / "company").mkdir(parents=True)
    (tmp_path / "src" / "company" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "agents").mkdir(); (tmp_path / "agents" / "b.md").write_text("# b\n", encoding="utf-8")
    return tmp_path


def _bump(path: Path) -> None:
    t = time.time() + 5
    os.utime(path, (t, t))


def test_fingerprint_doi_khi_file_nguon_doi(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    n, latest = source_fingerprint(root)
    assert n == 2 and "@" in latest
    _bump(root / "agents" / "b.md")
    n2, latest2 = source_fingerprint(root)
    assert n2 == 2 and latest2 != latest and latest2.startswith("agents/b.md@")
    (root / "src" / "company" / "c.py").write_text("y = 2\n", encoding="utf-8")
    assert source_fingerprint(root)[0] == 3
    assert source_fingerprint(tmp_path / "khong-co") == (0, "@0")


def test_fingerprint_bo_qua_file_khong_stat_duoc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """File vừa bị xoá giữa lúc quét (deploy đang ghi đè) không được làm hỏng cả vòng watch."""
    root = _tree(tmp_path); orig = Path.stat
    def flaky(self, *a, **k):
        if self.name == "a.py": raise OSError("biến mất")
        return orig(self, *a, **k)
    monkeypatch.setattr(Path, "stat", flaky)
    n, latest = source_fingerprint(root)
    assert n == 1 and latest.startswith("agents/b.md@")


def test_watch_xin_khoi_dong_lai_khi_ma_doi_va_hang_doi_rong(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _tree(tmp_path); monkeypatch.setattr(om, "COMPANY_ROOT", root)
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler))  # ghi dấu mã nguồn lúc khởi động
    orch.watch(interval=0, max_ticks=2, reload=True)  # không đổi → chạy hết 2 nhịp, không ném
    _bump(root / "src" / "company" / "a.py")
    with pytest.raises(ReloadRequested, match=r"a.py"):
        orch.watch(interval=0, max_ticks=3, reload=True)
    assert any(e.payload["action"] == "orchestrator.reload" for e in bus.replay(topic="audit-log"))
    # reload=False (--no-reload) thì mặc kệ mã đổi
    orch.watch(interval=0, max_ticks=1, reload=False)


def test_khong_khoi_dong_lai_khi_hang_doi_con_viec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Đang có lượt model dở (event trong hàng đợi) mà exec lại là mất công sức — chỉ reload lúc rảnh."""
    root = _tree(tmp_path); monkeypatch.setattr(om, "COMPANY_ROOT", root)
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler))
    fp0 = source_fingerprint(root); _bump(root / "src" / "company" / "a.py"); assert source_fingerprint(root) != fp0
    # giữ hàng đợi luôn có việc: tick() chạy run() cạn hàng đợi, nên chèn lại event ở mỗi nhịp qua monkeypatch tick
    orig = orch.tick
    def busy_tick(now=None):
        r = orig(now)
        orch.queue.append(Envelope(topic="research-requests", key="P9", actor="human:sales",
                                   payload={"project_id": "P9", "description": "còn việc"}))
        return r
    monkeypatch.setattr(orch, "tick", busy_tick)
    orch.watch(interval=0, max_ticks=2, reload=True)  # không ném dù mã đã đổi
    assert not any(e.payload["action"] == "orchestrator.reload" for e in bus.replay(topic="audit-log"))


def test_main_exec_lai_chinh_lenh_sau_khi_tra_lease(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "c.sqlite"
    monkeypatch.setenv("COMPANY_LLM_PROVIDER", "fake")
    called: dict = {}
    monkeypatch.setattr(om, "_reexec", lambda argv: called.setdefault("argv", argv))
    monkeypatch.setattr(om.Orchestrator, "watch", lambda self, interval, reload: (_ for _ in ()).throw(ReloadRequested("x")))
    monkeypatch.setattr(om.sys, "argv", ["orchestrator.py", "--db", str(db), "run", "--watch", "1"])
    assert orch_main(["--db", str(db), "run", "--watch", "1"]) == 0
    assert called["argv"] == [om.sys.executable, "-u", "-m", "company.orchestrator", "--db", str(db), "run", "--watch", "1"]
    assert not (tmp_path / "c.sqlite.lock").exists() or (tmp_path / "c.sqlite.lock").read_text() == "", "lease phải được trả trước khi exec"


def test_no_reload_tat_tu_khoi_dong_lai(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "c.sqlite"
    monkeypatch.setenv("COMPANY_LLM_PROVIDER", "fake")
    seen: list = []
    monkeypatch.setattr(om.Orchestrator, "watch", lambda self, interval, reload: seen.append(reload))
    assert orch_main(["--db", str(db), "run", "--watch", "1", "--no-reload"]) == 0
    assert orch_main(["--db", str(db), "run", "--watch", "1"]) == 0
    assert seen == [False, True], "mặc định tự khởi động lại; --no-reload tắt"


def test_reexec_goi_execv(monkeypatch: pytest.MonkeyPatch) -> None:
    got: dict = {}
    monkeypatch.setattr(om.os, "execv", lambda exe, argv: got.update(exe=exe, argv=argv))
    om._reexec(["py", "-m", "x"])
    assert got == {"exe": "py", "argv": ["py", "-m", "x"]}
