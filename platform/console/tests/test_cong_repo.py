"""Cổng cứng cho các file cấu hình CẤP GỐC trỏ vào cây thư mục.

Vì sao cần: cải tổ thư mục #262 (`software-company/` → `companies/software-company/`, `console|gateway|
xagents-core` → `platform/`) làm mọi đường dẫn trong `.pre-commit-config.yaml` và `.github/CODEOWNERS` trỏ vào
hư không. Không có gì gãy, không có gì đỏ — hook `subagents-check` chỉ đơn giản **không bao giờ chạy nữa**, và
CODEOWNERS rút về còn mỗi dòng `*`. Một cổng chết im lặng nguy hiểm hơn không có cổng: người ta vẫn tin nó canh.

Test này ở `platform/console/tests/` theo đúng lối `test_readme_goc.py` — package console là nơi repo đặt các
phép canh cấp gốc (chạy trong job `console-unit` trên cả ba nền).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
PRE_COMMIT = ROOT / ".pre-commit-config.yaml"
CODEOWNERS = ROOT / ".github" / "CODEOWNERS"

# Tiền tố đường dẫn nghĩa đen trong một regex `files:` — cắt ở ký tự metachar đầu tiên.
_LITERAL = re.compile(r"[\w./-]+")


def _duong_dan_trong_regex(pattern: str) -> list[str]:
    """Các tiền tố đường dẫn nghĩa đen của một regex `files:` của pre-commit.

    `^(a/b/|c/d\\.md|\\.claude/x-)` → ['a/b/', 'c/d.md', '.claude/x-']. Chỉ lấy nhánh nào trông như đường dẫn
    (có dấu `/`); nhánh không có `/` là tiền tố tên file, không kiểm được bằng `exists()`.
    """
    than = pattern.lstrip("^").strip("()")
    ra = []
    for nhanh in than.split("|"):
        m = _LITERAL.match(nhanh.replace("\\", ""))
        if m and "/" in m.group(0):
            ra.append(m.group(0))
    return ra


def _hooks_local() -> list[dict]:
    cfg = yaml.safe_load(PRE_COMMIT.read_text(encoding="utf-8"))
    return [h for r in cfg["repos"] if r.get("repo") == "local" for h in r["hooks"]]


def test_moi_tien_to_duong_dan_trong_pre_commit_ton_tai() -> None:
    """`files:` trỏ vào thư mục không tồn tại = hook không bao giờ khớp file nào = cổng chết im lặng."""
    hong: list[str] = []
    for hook in _hooks_local():
        for dd in _duong_dan_trong_regex(hook.get("files", "")):
            goc = dd.rstrip("/")
            # tiền tố kiểu `.claude/agents/sc-` khớp nhiều file: đủ khi THƯ MỤC CHA có thật
            if not (ROOT / goc).exists() and not (ROOT / goc).parent.is_dir():
                hong.append(f"{hook['id']}: {dd}")
    assert not hong, f".pre-commit-config.yaml trỏ vào đường dẫn không tồn tại: {hong}"


def test_project_trong_entry_pre_commit_la_package_that() -> None:
    """`uv run --project <path>` với path sai thì hook lỗi ngay khi chạy, không phải khi review."""
    hong: list[str] = []
    for hook in _hooks_local():
        m = re.search(r"--project\s+(\S+)", hook.get("entry", ""))
        if m and not (ROOT / m.group(1) / "pyproject.toml").is_file():
            hong.append(f"{hook['id']}: --project {m.group(1)}")
    assert not hong, f"--project không trỏ tới package có pyproject.toml: {hong}"


def test_moi_duong_dan_trong_codeowners_ton_tai() -> None:
    """CODEOWNERS trỏ đường dẫn cũ thì luật sở hữu rút về còn dòng `*` — mất hẳn lớp bảo vệ theo vùng."""
    if not CODEOWNERS.is_file():
        pytest.skip("repo không dùng CODEOWNERS")
    hong: list[str] = []
    for dong in CODEOWNERS.read_text(encoding="utf-8").splitlines():
        dong = dong.split("#", 1)[0].strip()
        if not dong:
            continue
        mau = dong.split()[0]
        if mau == "*" or "*" in mau:
            continue
        if not (ROOT / mau.strip("/")).exists():
            hong.append(mau)
    assert not hong, f".github/CODEOWNERS trỏ vào đường dẫn không tồn tại: {hong}"
