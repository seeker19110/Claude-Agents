"""__main__.py: CLI entrypoint. server/collect/decide thật do agent khác viết; ở đây monkeypatch
make_server để không mở socket thật (trừ các test đã có sẵn ở test_server.py dùng server thật)."""
from __future__ import annotations

import runpy
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from console import __main__ as cli
from console import server as srv


class _FakeServer:
    """Server giả: không mở socket, chỉ ghi lại lời gọi để test kiểm tra."""

    def __init__(self, *, port: int = 12345, raise_on_serve: Exception | None = None) -> None:
        self.port = port
        self._raise_on_serve = raise_on_serve
        self.serve_forever_called = False
        self.server_close_called = False

    def serve_forever(self) -> None:
        self.serve_forever_called = True
        if self._raise_on_serve is not None:
            raise self._raise_on_serve

    def server_close(self) -> None:
        self.server_close_called = True


def test_argv_none_lay_tu_sys_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    """argv=None -> lấy sys.argv[1:]. Dùng --host bậy để thoát sớm bằng mã 2, không đụng make_server."""
    monkeypatch.setattr(sys, "argv", ["console", "--host", "8.8.8.8"])
    assert cli.main() == 2


def test_models_subcommand_dispatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from console import settings

    llm = tmp_path / "llm.yaml"
    llm.write_text("backends: []\n", encoding="utf-8")
    monkeypatch.setattr(settings, "DEFAULT_LLM_YAML", {"software-company": llm})
    monkeypatch.setattr(settings, "gateway_catalog", lambda *a, **k: [])
    assert cli.main(["models"]) == 0
    assert "CẤU HÌNH MODEL" in capsys.readouterr().out


def test_host_khong_loopback_khong_co_i_know_tra_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--host", "8.8.8.8"]) == 2
    out = capsys.readouterr().out
    assert "Từ chối khởi động" in out


def test_host_khong_loopback_voi_i_know_canh_bao_va_tiep_tuc(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--i-know: in cảnh báo rồi vẫn đi tới make_server (mock để không mở socket ra ngoài)."""
    fake = _FakeServer()
    monkeypatch.setattr(cli, "make_server", lambda *a, **k: fake)
    token_path = tmp_path / "tok"
    token_path.write_text("t", encoding="utf-8")
    monkeypatch.setattr(cli, "write_token_file", lambda token: token_path)
    monkeypatch.setattr(cli, "generate_token", lambda: "tok")

    code = cli.main(["--host", "8.8.8.8", "--i-know"])

    out = capsys.readouterr().out
    assert "CẢNH BÁO" in out
    assert code == 0
    assert fake.serve_forever_called
    assert fake.server_close_called
    assert not token_path.exists()  # unlink(missing_ok=True) đã dọn file token


def test_make_server_oserror_tra_1(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def _raise(*a: Any, **k: Any) -> Any:
        raise OSError("port đã dùng")

    monkeypatch.setattr(cli, "make_server", _raise)
    assert cli.main([]) == 1
    assert "Không mở được" in capsys.readouterr().out


def test_khoi_dong_thanh_cong_in_banner_va_dung_ctrl_c(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _FakeServer(raise_on_serve=KeyboardInterrupt())
    monkeypatch.setattr(cli, "make_server", lambda *a, **k: fake)
    token_path = tmp_path / "tok2"
    token_path.write_text("t", encoding="utf-8")
    monkeypatch.setattr(cli, "write_token_file", lambda token: token_path)

    code = cli.main([])

    out = capsys.readouterr().out
    assert "CONSOLE" in out
    assert "Đã dừng console" in out
    assert code == 0
    assert fake.server_close_called
    assert not token_path.exists()


def test_open_browser_thanh_cong(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = _FakeServer()
    monkeypatch.setattr(cli, "make_server", lambda *a, **k: fake)
    token_path = tmp_path / "tok3"
    token_path.write_text("t", encoding="utf-8")
    monkeypatch.setattr(cli, "write_token_file", lambda token: token_path)
    opened: list[str] = []
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: opened.append(url))

    assert cli.main(["--open"]) == 0
    assert opened


def test_open_browser_that_bai_khong_lam_hong_khoi_dong(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _FakeServer()
    monkeypatch.setattr(cli, "make_server", lambda *a, **k: fake)
    token_path = tmp_path / "tok4"
    token_path.write_text("t", encoding="utf-8")
    monkeypatch.setattr(cli, "write_token_file", lambda token: token_path)

    def _raise(url: str) -> None:
        raise RuntimeError("không có trình duyệt")

    monkeypatch.setattr(cli.webbrowser, "open", _raise)

    assert cli.main(["--open"]) == 0
    assert "Không mở được trình duyệt" in capsys.readouterr().out


def test_dung_bang_thanh_cong_khong_ctrl_c(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """serve_forever() trả về bình thường (không KeyboardInterrupt) — nhánh finally vẫn chạy."""
    fake = _FakeServer()
    monkeypatch.setattr(cli, "make_server", lambda *a, **k: fake)
    token_path = tmp_path / "tok5"
    token_path.write_text("t", encoding="utf-8")
    monkeypatch.setattr(cli, "write_token_file", lambda token: token_path)

    assert cli.main([]) == 0
    assert fake.serve_forever_called and fake.server_close_called
    assert not token_path.exists()


def test_dunder_main_goi_main_va_sys_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """`python -m console --help`: argparse tự thoát bằng SystemExit(0), không chạm make_server."""
    monkeypatch.setattr(sys, "argv", ["console", "--help"])
    with pytest.raises(SystemExit) as e:
        runpy.run_module("console.__main__", run_name="__main__")
    assert e.value.code == 0
