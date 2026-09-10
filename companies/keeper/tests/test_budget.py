"""BT4 — `budget.py`: ngân sách thay đổi + hàng đợi.

Ca quan trọng nhất là `test_hoi_github_moi_lan_khong_tin_ram`: đổi câu trả lời của `FakeGitHub` GIỮA hai lần
gọi `can_open_pr()` → kết quả phải đổi theo. Nếu cài đặt đếm trong RAM thì ca đó đỏ.
"""
from datetime import UTC, datetime

import pytest

from keeper.budget import (
    BUDGET_CHECKS,
    DEFAULT_MAX_PR_PER_WEEK,
    MAX_PR_ENV,
    QueueItem,
    budget_context,
    can_open_pr,
    checks_without,
    order_queue,
    since_iso,
)
from keeper.events import Signal
from keeper.fakes import FakeGitHub
from keeper.github import PullRequest

NOW = datetime(2026, 9, 9, 12, tzinfo=UTC)


class _GH(FakeGitHub):
    """`FakeGitHub` với hai danh sách GHI ĐƯỢC — đổi giữa chừng để chứng minh `can_open_pr` hỏi lại thật."""

    def __init__(self, open_list: list[PullRequest], merged_list: list[PullRequest]) -> None:
        super().__init__()
        self.open_list = open_list
        self.merged_list = merged_list

    def open_prs(self) -> list[PullRequest]:
        self._count("open_prs")
        return list(self.open_list)

    def merged_prs(self, since: str) -> list[PullRequest]:
        self._count("merged_prs")
        self.last_since = since
        return list(self.merged_list)


def _pr(n: int) -> PullRequest:
    return PullRequest(number=n, title=f"pr {n}")


def test_ten_bien_moi_truong_qua_env_name():
    assert MAX_PR_ENV == "KEEPER_MAX_PR_PER_WEEK"
    assert DEFAULT_MAX_PR_PER_WEEK == 5


def test_khong_pr_mo_va_duoi_han_muc_thi_mo_duoc(monkeypatch):
    monkeypatch.delenv(MAX_PR_ENV, raising=False)
    gh = _GH([], [_pr(1), _pr(2)])
    assert can_open_pr(gh, now=NOW) is True


def test_co_mot_pr_mo_thi_chan(monkeypatch):
    monkeypatch.delenv(MAX_PR_ENV, raising=False)
    gh = _GH([_pr(9)], [])
    assert can_open_pr(gh, now=NOW) is False


def test_max_bang_0_thi_chan_va_bo_kiem_thi_mo(monkeypatch):
    """Chiều ngược THẬT: cùng một `gh`, chỉ khác việc có giữ hàng kiểm `weekly-quota` hay không."""
    monkeypatch.setenv(MAX_PR_ENV, "0")
    gh = _GH([], [])
    assert can_open_pr(gh, now=NOW) is False
    assert can_open_pr(gh, now=NOW, checks=checks_without("weekly-quota")) is True


def test_bo_kiem_pr_mo_thi_mot_pr_mo_khong_con_chan(monkeypatch):
    monkeypatch.delenv(MAX_PR_ENV, raising=False)
    gh = _GH([_pr(9)], [])
    assert can_open_pr(gh, now=NOW) is False
    assert can_open_pr(gh, now=NOW, checks=checks_without("no-open-pr")) is True


def test_dat_han_muc_thi_chan(monkeypatch):
    monkeypatch.setenv(MAX_PR_ENV, "2")
    gh = _GH([], [_pr(1), _pr(2)])
    assert can_open_pr(gh, now=NOW) is False


def test_bien_moi_truong_hong_thi_dung_mac_dinh(monkeypatch):
    monkeypatch.setenv(MAX_PR_ENV, "nhiều lắm")
    gh = _GH([], [_pr(i) for i in range(4)])
    assert budget_context(gh, now=NOW).max_per_week == DEFAULT_MAX_PR_PER_WEEK
    assert can_open_pr(gh, now=NOW) is True


def test_hoi_github_moi_lan_khong_tin_ram(monkeypatch):
    """Gọi hai lần, đổi câu trả lời giữa chừng → kết quả đổi theo (state trong RAM thì không đổi)."""
    monkeypatch.delenv(MAX_PR_ENV, raising=False)
    gh = _GH([], [])
    assert can_open_pr(gh, now=NOW) is True
    gh.open_list.append(_pr(42))
    assert can_open_pr(gh, now=NOW) is False
    assert gh.calls["open_prs"] == 2


def test_cua_so_7_ngay(monkeypatch):
    monkeypatch.delenv(MAX_PR_ENV, raising=False)
    gh = _GH([], [])
    can_open_pr(gh, now=NOW)
    assert since_iso(NOW) == "2026-09-02"
    assert gh.last_since == "2026-09-02"


def test_now_mac_dinh_la_gio_that(monkeypatch):
    monkeypatch.delenv(MAX_PR_ENV, raising=False)
    gh = _GH([], [])
    assert can_open_pr(gh) is True
    assert gh.last_since <= datetime.now(UTC).date().isoformat()


def test_checks_without_ten_khong_co_thi_no():
    with pytest.raises(KeyError):
        checks_without("khong-ton-tai")


def test_bang_kiem_du_hai_hang():
    assert [c.name for c in BUDGET_CHECKS] == ["no-open-pr", "weekly-quota"]


def test_hang_doi_fifo_theo_tier_roi_tuoi():
    items = [
        QueueItem(signal=Signal(subject="a", kind="drift", detail="x"), age_days=1.0),
        QueueItem(signal=Signal(subject="b", kind="dependency", detail="x", semver_jump="major"), age_days=0.5),
        QueueItem(signal=Signal(subject="c", kind="dependency", detail="x", semver_jump="major"), age_days=9.0),
        QueueItem(signal=Signal(subject="d", kind="dependency", detail="x", semver_jump="patch", is_dev=True),
                  age_days=30.0),
    ]
    assert [q.signal.subject for q in order_queue(items)] == ["c", "b", "a", "d"]
