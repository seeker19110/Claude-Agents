"""`python -m company.mcp_bridge --help`: argparse tự thoát SystemExit(0), không chạm ProxyServer.run() thật."""
from __future__ import annotations

import runpy
import sys

import pytest


def test_dunder_main_goi_main_va_sys_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["mcp_bridge", "--help"])
    with pytest.raises(SystemExit) as e:
        runpy.run_module("company.mcp_bridge", run_name="__main__")
    assert e.value.code == 0
