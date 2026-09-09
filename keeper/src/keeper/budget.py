"""Ngân sách thay đổi + hàng đợi việc (BT4, `DAC-TA-KEEPER.md` §6, bất biến I3).

**`can_open_pr()` HỎI GitHub mỗi lần được gọi** — không có biến đếm nào sống trong instance ở đây. Đó là chủ
đích, không phải quên tối ưu: "state chỉ sống trong RAM" là một trong bốn khuôn lỗi lặp lại của X-Agents
(`TRAPS.md`). Một con số PR-đang-mở nhớ trong tiến trình sẽ sai ngay khi một người merge tay, khi tiến trình
khởi động lại, hay khi có phiên thứ hai — và cái sai đó mở PR thứ hai, phá đúng bất biến I3. Lớp đệm duy nhất
là TTL theo argv trong `GitHubReader` (BT2, `github.py`): nó vẫn là câu trả lời của `gh`, có hạn dùng, và
không phải một biến đếm do `keeper` tự cộng.

Bảng kiểm cũng tra cứu được theo tên (`BUDGET_CHECKS` + `checks_without`), cùng lý do như `risk.RISK_RULES`:
ca chiều ngược phải bỏ được ĐÚNG một hàng kiểm rồi đo lại.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from pydantic import BaseModel

from .core import CORE
from .events import RiskTier, Signal
from .github import PullRequest
from .risk import risk_tier

MAX_PR_ENV = CORE.env_name("MAX_PR_PER_WEEK")  # "KEEPER_MAX_PR_PER_WEEK" — ghép tiền tố ở MỘT chỗ (config.py:90)
DEFAULT_MAX_PR_PER_WEEK = 5
WINDOW_DAYS = 7

# Ưu tiên hàng đợi: rủi ro cao đi trước. Bảng chứ không `if`, cùng lý do với `risk.py`.
_TIER_RANK: dict[RiskTier, int] = {"high": 0, "medium": 1, "low": 2}


class GitHubLike(Protocol):
    def open_prs(self) -> list[PullRequest]: ...
    def merged_prs(self, since: str) -> list[PullRequest]: ...


@dataclass(frozen=True)
class BudgetContext:
    """Ảnh chụp NGAY LÚC HỎI. Không được giữ lại giữa hai lần `can_open_pr()` — xem docstring module."""
    open_pr_count: int
    merged_last_week: int
    max_per_week: int


@dataclass(frozen=True)
class BudgetCheck:
    name: str
    ok: Callable[[BudgetContext], bool]


BUDGET_CHECKS: tuple[BudgetCheck, ...] = (
    BudgetCheck("no-open-pr", lambda c: c.open_pr_count == 0),              # bất biến I3
    BudgetCheck("weekly-quota", lambda c: c.merged_last_week < c.max_per_week),
)


def checks_without(*names: str) -> tuple[BudgetCheck, ...]:
    """Bảng kiểm thiếu đúng những hàng được nêu. Tên lạ thì NỔ (xem `risk.rules_without`)."""
    known = {c.name for c in BUDGET_CHECKS}
    missing = sorted(set(names) - known)
    if missing:
        raise KeyError(f"không có hàng kiểm {missing} trong BUDGET_CHECKS")
    return tuple(c for c in BUDGET_CHECKS if c.name not in names)


def max_pr_per_week(env: Mapping[str, str] | None = None) -> int:
    """Đọc `KEEPER_MAX_PR_PER_WEEK` MỖI LẦN gọi (người vận hành hạ hạn mức giữa đêm phải có hiệu lực ngay).
    Giá trị không phải số nguyên → mặc định, không nổ: một biến gõ sai không được biến thành "không giới hạn"
    cũng không được làm chết vòng watch."""
    raw = (env if env is not None else os.environ).get(MAX_PR_ENV)
    if raw is None:
        return DEFAULT_MAX_PR_PER_WEEK
    try:
        return int(raw.strip())
    except ValueError:
        return DEFAULT_MAX_PR_PER_WEEK


def since_iso(now: datetime) -> str:
    """Mốc `merged:>=` cho `gh pr list --search`: `gh` nhận NGÀY (`YYYY-MM-DD`), không nhận timestamp đầy đủ."""
    return (_as_aware(now) - timedelta(days=WINDOW_DAYS)).date().isoformat()


def _as_aware(now: datetime) -> datetime:
    return now.replace(tzinfo=UTC) if now.tzinfo is None else now


def budget_context(
    gh: GitHubLike, *, now: datetime | None = None, env: Mapping[str, str] | None = None,
) -> BudgetContext:
    """Hai câu hỏi tới `gh` + một lần đọc biến môi trường, mỗi lần gọi."""
    reference = now or datetime.now(UTC)
    return BudgetContext(
        open_pr_count=len(gh.open_prs()),
        merged_last_week=len(gh.merged_prs(since_iso(reference))),
        max_per_week=max_pr_per_week(env),
    )


def can_open_pr(
    gh: GitHubLike, *, now: datetime | None = None, env: Mapping[str, str] | None = None,
    checks: tuple[BudgetCheck, ...] = BUDGET_CHECKS,
) -> bool:
    ctx = budget_context(gh, now=now, env=env)
    return all(c.ok(ctx) for c in checks)


class QueueItem(BaseModel):
    """Một signal đang chờ tới lượt. `age_days` đi KÈM signal chứ không nằm trong `Signal`: payload trên bus
    không mang mốc thời gian riêng (`signals.py` docstring — `ts` ở `Envelope`), nên tuổi là thứ người gọi đo
    từ envelope rồi đưa vào, không phải thứ suy ra từ nội dung."""
    signal: Signal
    age_days: float


def order_queue(items: Sequence[QueueItem]) -> list[QueueItem]:
    """FIFO theo `risk_tier` rồi tuổi: tier cao trước, trong cùng tier thì signal GIÀ nhất trước (FIFO thật —
    việc chờ lâu không được để một việc mới cùng tier chen lên)."""
    return sorted(items, key=lambda q: (_TIER_RANK[risk_tier(q.signal)], -q.age_days))
