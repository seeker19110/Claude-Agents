"""C7 — "commit vượt integration" đo bằng `git rev-list --count`, trên một repo git THẬT dựng trong tmp_path.

Test hai chiều của mục này nằm ở đúng chỗ đau: `git branch --contains` (cách làm bị loại) trả cùng một câu trả lời
cho một nhánh rỗng và một nhánh có commit chưa gộp; `rev-list --count` trả 0 và 2. Nếu ai đó đổi implementation
sang `--contains`, `test_nhanh_rong_va_nhanh_co_commit_khong_duoc_giong_nhau` đỏ.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from console.git_truth import INTEGRATION_BRANCH, ahead_count


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", check=True)
    return r.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    d = tmp_path / "khach-hang"
    d.mkdir()
    git(d, "init", "-q", "-b", "main")
    git(d, "config", "user.email", "t@t.local")
    git(d, "config", "user.name", "t")
    (d / "a.txt").write_text("1", encoding="utf-8")
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "nen")
    git(d, "branch", INTEGRATION_BRANCH)
    return d


def _commit(repo: Path, branch: str, n: int) -> None:
    git(repo, "checkout", "-q", "-B", branch, INTEGRATION_BRANCH)
    for i in range(n):
        (repo / f"{branch.replace('/', '_')}-{i}.txt").write_text(str(i), encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", f"{branch} {i}")


def test_nhanh_rong_va_nhanh_co_commit_khong_duoc_giong_nhau(repo: Path) -> None:
    """Cả hai nhánh đều "chứa" đầu nhánh tích hợp — `--contains` không phân biệt được. Con số thì phân biệt."""
    _commit(repo, "ticket/T-rong", 0)
    _commit(repo, "ticket/T-hai", 2)
    assert ahead_count(repo, "T-rong") == 0
    assert ahead_count(repo, "T-hai") == 2
    contains = git(repo, "branch", "--contains", INTEGRATION_BRANCH)
    assert "ticket/T-rong" in contains and "ticket/T-hai" in contains, "đây chính là lý do không dùng --contains"


def test_gop_xong_thi_ve_0(repo: Path) -> None:
    _commit(repo, "ticket/T-1", 1)
    assert ahead_count(repo, "T-1") == 1
    git(repo, "checkout", "-q", INTEGRATION_BRANCH)
    git(repo, "merge", "-q", "--no-ff", "-m", "gop", "ticket/T-1")
    assert ahead_count(repo, "T-1") == 0, "0 = đã gộp hết; phải khác None (không đo được)"


def test_khong_do_duoc_tra_none_chu_khong_phai_0(tmp_path: Path, repo: Path) -> None:
    """None và 0 là hai câu trả lời khác nhau: "chưa biết" không được hiện như "đã gộp hết"."""
    assert ahead_count(tmp_path / "khong-co-thu-muc", "T-1") is None
    assert ahead_count(tmp_path, "T-1") is None, "thư mục không phải repo git"
    assert ahead_count(repo, "T-khong-ton-tai") is None, "nhánh ticket chưa tồn tại"
    assert ahead_count(repo, "T-1", "khong-co-nhanh-nay") is None


def test_git_hong_khong_lam_do_trang(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Máy không có git, hoặc git treo: console vẫn phải trả trang, chỉ là cột đó thành "—"."""
    def boom(*a: object, **k: object) -> None:
        raise OSError("không có git")

    monkeypatch.setattr(subprocess, "run", boom)
    assert ahead_count(repo, "T-1") is None
