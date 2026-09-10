"""`python -m company.demo`: chạy guard `if __name__ == "__main__"` để phủ dòng cuối demo.py (run() không gọi sys.exit)."""
from __future__ import annotations

import runpy


def test_dunder_main_goi_run(capsys) -> None:
    runpy.run_module("company.demo", run_name="__main__")
    out = capsys.readouterr().out
    assert "sau dispatch" in out
