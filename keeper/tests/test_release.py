"""BT7 — `release.py`: dòng CHANGELOG + mục nhật ký phiên, và điền `(#n)` SAU khi có số PR.

Repo git thật được dựng trong `tmp_path` (đường ghi của `patcher` chỉ chạy trong worktree PHỤ), nên không ca
nào phụ thuộc trạng thái git của repo đang chạy.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from keeper.events import Ticket
from keeper.patcher import ForbiddenPath
from keeper.release import (
    PR_PLACEHOLDER,
    compose,
    fill_pr_number,
    record,
)

CHANGELOG = "# Nhật ký thay đổi\n\n- dòng cũ (#1)\n"


def _git(repo: Path, *args: str) -> None:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr


@pytest.fixture
def root(tmp_path: Path) -> Path:
    main = tmp_path / "chung"
    (main / "docs" / "sessions").mkdir(parents=True)
    (main / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    (main / "docs" / "sessions" / ".gitkeep").write_text("", encoding="utf-8")
    _git(main, "init", "-b", "main")
    _git(main, "add", "-A")
    _git(main, "-c", "user.name=t", "-c", "user.email=t@x", "commit", "-m", "khoi tao")
    wt = tmp_path / "wt-keeper-t"
    _git(main, "worktree", "add", "-b", "chore/keeper-t", str(wt), "HEAD")
    return wt


def _ticket(**kw) -> Ticket:
    base = {"ticket_id": "KEEP:0:dependency:requests", "subject": "requests", "risk_tier": "low"}
    base.update(kw)
    return Ticket.model_validate(base)


# ---------- soạn ----------

def test_compose_de_trong_so_pr_va_mang_ma_ticket():
    note = compose(_ticket())
    assert note.pr_number is None
    assert PR_PLACEHOLDER in note.changelog_line and "requests" in note.changelog_line
    assert note.ticket_id in note.session_line


def test_compose_giu_so_pr_neu_da_biet():
    note = compose(_ticket(), pr_number=42)
    assert note.pr_number == 42 and "(#42)" in note.changelog_line and PR_PLACEHOLDER not in note.changelog_line


# ---------- ghi ----------

def test_record_them_dong_dau_changelog_va_muc_nhat_ky(root: Path):
    note = compose(_ticket())
    proposal = record(root, note, session_date="2026-09-09")
    cl = (root / "CHANGELOG.md").read_text(encoding="utf-8").splitlines()
    assert cl[0] == "# Nhật ký thay đổi" and cl[2] == note.changelog_line and "- dòng cũ (#1)" in cl
    assert note.session_line in (root / "docs" / "sessions" / "2026-09-09.md").read_text(encoding="utf-8")
    assert proposal.operation == "fix_docs" and "CHANGELOG.md" in proposal.files


def test_record_di_qua_duong_ghi_cua_patcher_nen_duong_cam_van_bi_chan(root: Path):
    note = compose(_ticket())
    with pytest.raises(ForbiddenPath):
        record(root, note, session_date="2026-09-09", changelog=".github/workflows/ci.yml")


# ---------- điền số PR SAU, trong CHÍNH PR đó ----------

def test_fill_pr_number_thay_cho_trong_tai_cho_khong_them_dong_moi(root: Path):
    note = compose(_ticket())
    record(root, note, session_date="2026-09-09")
    filled = fill_pr_number(root, note, 218, session_date="2026-09-09")
    cl = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert filled.pr_number == 218 and "(#218)" in cl and PR_PLACEHOLDER not in cl
    assert cl.count("keeper") == 1, "điền số là SỬA dòng cũ, không phải thêm dòng thứ hai"
    assert "(#218)" in (root / "docs" / "sessions" / "2026-09-09.md").read_text(encoding="utf-8")


def test_fill_pr_number_khi_chua_ghi_dong_nao_thi_no(root: Path):
    """Không tìm thấy chỗ trống ⇒ hoặc chưa `record`, hoặc đã điền rồi. Im lặng bỏ qua ở đây là một dòng
    CHANGELOG vĩnh viễn thiếu số PR mà không ai thấy."""
    with pytest.raises(ValueError, match="không tìm thấy"):
        fill_pr_number(root, compose(_ticket()), 218, session_date="2026-09-09")


def test_fill_pr_number_tu_choi_note_da_co_so(root: Path):
    with pytest.raises(ValueError, match="đã có số PR"):
        fill_pr_number(root, compose(_ticket(), pr_number=7), 218, session_date="2026-09-09")


def test_fill_pr_number_chi_dien_changelog_khi_nhat_ky_chua_ghi(root: Path):
    note = compose(_ticket())
    record(root, note, session_date="2026-09-09")
    (root / "docs" / "sessions" / "2026-09-09.md").unlink()
    filled = fill_pr_number(root, note, 218, session_date="2026-09-09")
    assert filled.pr_number == 218
    assert not (root / "docs" / "sessions" / "2026-09-09.md").exists()
