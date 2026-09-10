"""BT5 — `worktree.py`: worktree riêng cho ticket, và LỜI TỪ CHỐI chạy trên checkout chung.

Mọi ca dựng repo git THẬT trong `tmp_path`; không ca nào chạm repo X-Agents, không ca nào chạm mạng,
không ca nào bỏ qua theo `os.name` hay biến môi trường.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from keeper.worktree import (
    BRANCH_PREFIX,
    WORKTREE_PREFIX,
    KeeperWorktree,
    SharedCheckoutRefused,
    WorktreeError,
    _discard,
    is_linked_worktree,
    open_worktree,
    refuse_shared_checkout,
    slug,
)


def _run(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Checkout CHUNG giả: một repo git có đúng một commit, nằm trong `tmp_path/nha/repo`."""
    root = tmp_path / "nha" / "repo"
    root.mkdir(parents=True)
    _run(root, "init", "-b", "main")
    (root / "README.md").write_text("xin chao\n", encoding="utf-8")
    _run(root, "add", "-A")
    _run(root, "-c", "user.name=t", "-c", "user.email=t@x", "commit", "-m", "khoi tao")
    return root


def test_slug_bo_ky_tu_khong_hop_le_cho_duong_dan_va_nhanh():
    assert slug("KEEP:0:dependency:pydantic") == "KEEP-0-dependency-pydantic"
    assert slug("bt5") == "bt5"


def test_slug_rong_thi_no():
    with pytest.raises(WorktreeError):
        slug(":::")


def test_ten_worktree_va_nhanh_dung_khuon(repo: Path):
    wt = KeeperWorktree(repo=repo, ticket_id="KEEP:1")
    assert wt.path.name == f"{WORKTREE_PREFIX}KEEP-1"
    assert wt.path.parent == repo.parent  # `../Claude-Agents-wt-keeper-<id>`
    assert wt.branch == f"{BRANCH_PREFIX}KEEP-1"


def test_open_worktree_idempotent_goi_hai_lan_khong_hong(repo: Path):
    a = open_worktree("bt5", repo=repo)
    (a.path / "moi.txt").write_text("noi dung\n", encoding="utf-8")
    b = open_worktree("bt5", repo=repo)
    assert a.path == b.path
    assert b.path.is_dir()
    assert (b.path / "moi.txt").read_text(encoding="utf-8") == "noi dung\n"  # lần hai không xoá việc dở
    assert b.branch in _run(repo, "branch", "--list", b.branch)
    a.close()


def test_close_don_sach_worktree_va_nhanh(repo: Path):
    wt = open_worktree("bt5", repo=repo)
    path = wt.path
    assert path.is_dir()
    wt.close()
    assert not path.exists()
    assert _run(repo, "branch", "--list", wt.branch) == ""
    assert str(path) not in _run(repo, "worktree", "list")
    wt.close()  # gọi lại trên cái đã dọn: không nổ


def test_close_giu_nhanh_khi_duoc_yeu_cau(repo: Path):
    wt = open_worktree("bt5", repo=repo)
    wt.close(delete_branch=False)
    assert wt.branch in _run(repo, "branch", "--list", wt.branch)


def test_open_worktree_dung_lai_nhanh_da_co(repo: Path):
    wt = open_worktree("bt5", repo=repo)
    wt.close(delete_branch=False)  # nhánh còn, thư mục mất
    lai = open_worktree("bt5", repo=repo)
    assert lai.path.is_dir()
    lai.close()


def test_repo_khong_phai_git_thi_no(tmp_path: Path):
    with pytest.raises(WorktreeError):
        open_worktree("bt5", repo=tmp_path)


# --- Cơ chế TỪ CHỐI checkout chung, đo hai chiều ---------------------------------------------------------


def test_is_linked_worktree_phan_biet_dung(repo: Path):
    wt = open_worktree("bt5", repo=repo)
    assert is_linked_worktree(wt.path) is True
    assert is_linked_worktree(repo) is False
    wt.close()


def test_refuse_shared_checkout_nem_tren_checkout_chung(repo: Path):
    with pytest.raises(SharedCheckoutRefused):
        refuse_shared_checkout(repo)


def test_refuse_shared_checkout_im_lang_trong_worktree_rieng(repo: Path):
    wt = open_worktree("bt5", repo=repo)
    refuse_shared_checkout(wt.path)  # không ném
    wt.close()


def test_discard_local_changes_tu_choi_tren_checkout_chung_va_khong_dong_vao_file(repo: Path):
    """CHIỀU THUẬN: chốt bật → ném và file dở của phiên khác CÒN NGUYÊN."""
    do_dang = repo / "phien-khac.txt"
    do_dang.write_text("viec dang lam\n", encoding="utf-8")
    wt = KeeperWorktree(repo=repo, ticket_id="bt5")
    with pytest.raises(SharedCheckoutRefused):
        wt.discard_local_changes(target=repo)
    assert do_dang.read_text(encoding="utf-8") == "viec dang lam\n"


def test_chieu_nguoc_tat_chot_thi_file_cua_phien_khac_BIEN_MAT(repo: Path):
    """CHIỀU NGƯỢC: gọi thẳng `_discard` (đúng thao tác, không qua chốt) → file untracked bị xoá thật.
    Đây là bằng chứng chốt không phải trang trí: tắt nó đi thì thiệt hại xảy ra ngay trên checkout chung."""
    do_dang = repo / "phien-khac.txt"
    do_dang.write_text("viec dang lam\n", encoding="utf-8")
    _discard(repo)
    assert not do_dang.exists()


def test_discard_local_changes_lam_viec_trong_worktree_rieng(repo: Path):
    wt = open_worktree("bt5", repo=repo)
    rac = wt.path / "rac.txt"
    rac.write_text("rac\n", encoding="utf-8")
    (wt.path / "README.md").write_text("bi sua\n", encoding="utf-8")
    assert wt.discard_local_changes() is True
    assert not rac.exists()
    assert (wt.path / "README.md").read_text(encoding="utf-8") == "xin chao\n"
    assert wt.discard_local_changes() is False  # đã sạch
    wt.close()


class _WorktreeTroSaiChoNguyHiem(KeeperWorktree):
    """Một `KeeperWorktree` bị cấu hình sai để `path` trỏ vào checkout CHUNG — đúng tình huống mà chốt phải bắt."""

    @property
    def path(self) -> Path:
        return self.repo


def test_close_tu_choi_khi_path_tro_vao_checkout_chung(repo: Path):
    wt = _WorktreeTroSaiChoNguyHiem(repo=repo, ticket_id="bt5")
    with pytest.raises(SharedCheckoutRefused):
        wt.close()
    assert (repo / "README.md").exists()


def test_is_linked_worktree_voi_thu_muc_khong_phai_git(tmp_path: Path):
    (tmp_path / "trong").mkdir()
    assert is_linked_worktree(tmp_path / "trong") is False
