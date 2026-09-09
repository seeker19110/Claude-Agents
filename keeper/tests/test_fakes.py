"""`FakeGitHub` — cùng giao diện với `GitHubReader`, dùng cho mọi test không đọc mạng của các khối sau BT2."""
from __future__ import annotations

from keeper.fakes import FakeGitHub


def test_fake_github_cung_giao_dien() -> None:
    fake = FakeGitHub()
    assert fake.open_prs()[0].number == 101
    assert fake.checks(101)[0].name == "keeper-static"
    assert fake.dependabot_alerts()[0].severity == "medium"
    assert fake.code_scanning_alerts()[0].severity == "low"
    assert fake.workflow_runs()[0].databaseId == 1
    assert fake.merged_prs("2026-09-01")[0].number == 99
    age = fake.pr_age_days(101)
    assert age == 8.0
    assert fake.calls == {
        "open_prs": 1, "checks": 1, "dependabot_alerts": 1, "code_scanning_alerts": 1,
        "workflow_runs": 1, "merged_prs": 1, "pr_age_days": 1,
    }
