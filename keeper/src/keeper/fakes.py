"""`FakeGitHub` — cùng giao diện với `GitHubReader` (`github.py`), trả bản ghi JSON CỐ ĐỊNH. Mọi test của
`keeper` dùng cái này; không test nào được chạm mạng hay gọi `gh` thật (`DAC-TA-KEEPER.md` §4, cạm bẫy)."""
from __future__ import annotations

from datetime import UTC, datetime

from .github import CheckRun, CodeScanningAlert, DependabotAlert, PullRequest, WorkflowRun


class FakeGitHub:
    """Dữ liệu cố định, không đọc đĩa hay mạng. `calls` đếm số lần mỗi method được gọi — dùng để test bộ đệm
    của `GitHubReader` mà không cần lặp lại logic bộ đệm ở đây (fake này KHÔNG có TTL, nó không giả lập
    `gh`, nó thay hẳn `GitHubReader` ở lớp cao hơn — scout/health/triage gọi `FakeGitHub` thẳng)."""

    def __init__(self) -> None:
        self.calls: dict[str, int] = {}

    def _count(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def open_prs(self) -> list[PullRequest]:
        self._count("open_prs")
        return [
            PullRequest(number=101, title="fix(keeper): vá mẫu", url="https://github.com/o/r/pull/101",
                        headRefName="fix/keeper-mau", createdAt="2026-09-01T00:00:00Z"),
        ]

    def checks(self, pr: int) -> list[CheckRun]:
        self._count("checks")
        return [
            CheckRun(name="keeper-static", state="SUCCESS", link=f"https://github.com/o/r/pull/{pr}/checks"),
            CheckRun(name="keeper-unit", state="SUCCESS", link=f"https://github.com/o/r/pull/{pr}/checks"),
        ]

    def dependabot_alerts(self) -> list[DependabotAlert]:
        self._count("dependabot_alerts")
        return [DependabotAlert(number=1, state="open", severity="medium", summary="bump gói mẫu")]

    def code_scanning_alerts(self) -> list[CodeScanningAlert]:
        self._count("code_scanning_alerts")
        return [CodeScanningAlert(number=1, state="open", severity="low", rule_description="mẫu")]

    def pr_age_days(self, pr: int, *, now: datetime | None = None) -> float | None:
        self._count("pr_age_days")
        reference = now or datetime(2026, 9, 9, tzinfo=UTC)
        created = datetime(2026, 9, 1, tzinfo=UTC)
        return (reference - created).total_seconds() / 86400.0

    def workflow_runs(self) -> list[WorkflowRun]:
        self._count("workflow_runs")
        return [
            WorkflowRun(databaseId=1, name="ci", status="completed", conclusion="success", headSha="abc123",
                        createdAt="2026-09-08T00:00:00Z", startedAt="2026-09-08T00:00:00Z",
                        updatedAt="2026-09-08T00:00:12Z"),
        ]

    def merged_prs(self, since: str) -> list[PullRequest]:
        self._count("merged_prs")
        return [
            PullRequest(number=99, title="chore(keeper): đã gộp", url="https://github.com/o/r/pull/99",
                        headRefName="chore/keeper-cu", mergedAt="2026-09-05T00:00:00Z"),
        ]
