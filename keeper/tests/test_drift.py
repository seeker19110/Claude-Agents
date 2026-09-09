import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from keeper import drift


def _write_source_agent(company_root: Path, rel: str, *, version: int | None) -> None:
    p = company_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    front = "---\nid: foo\nblock: engineering\n" + (f"version: {version}\n" if version is not None else "") + "---\n"
    p.write_text(front + "\n## Vai trò\nlàm việc\n", encoding="utf-8")


def _write_sc_agent(claude_dir: Path, name: str, *, src: str, recorded_version: int) -> None:
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / f"{name}.md").write_text(
        f"---\nname: {name}\n---\n\n<!-- SINH TỰ ĐỘNG từ {src} version={recorded_version} — sửa nguồn rồi "
        "chạy make subagents -->\n\nnội dung\n",
        encoding="utf-8",
    )


def test_sc_agent_drift_phat_khi_lech(tmp_path: Path) -> None:
    company_root = tmp_path / "software-company"
    claude_dir = tmp_path / ".claude" / "agents"
    _write_source_agent(company_root, "agents/engineering/foo.md", version=2)
    _write_sc_agent(claude_dir, "sc-foo", src="agents/engineering/foo.md", recorded_version=1)

    out = drift.sc_agent_drift(claude_dir, company_root)

    assert len(out) == 1
    assert out[0].kind == "drift"
    assert "sc-foo.md" in out[0].subject


def test_sc_agent_drift_im_khi_khop(tmp_path: Path) -> None:
    """Chiều ngược của ca trên: hoàn nguyên version cho khớp lại → im lặng, không phát signal."""
    company_root = tmp_path / "software-company"
    claude_dir = tmp_path / ".claude" / "agents"
    _write_source_agent(company_root, "agents/engineering/foo.md", version=1)
    _write_sc_agent(claude_dir, "sc-foo", src="agents/engineering/foo.md", recorded_version=1)

    assert drift.sc_agent_drift(claude_dir, company_root) == []


def test_sc_agent_drift_mac_dinh_version_1(tmp_path: Path) -> None:
    company_root = tmp_path / "software-company"
    claude_dir = tmp_path / ".claude" / "agents"
    _write_source_agent(company_root, "agents/engineering/foo.md", version=None)  # không khai version → default 1
    _write_sc_agent(claude_dir, "sc-foo", src="agents/engineering/foo.md", recorded_version=1)

    assert drift.sc_agent_drift(claude_dir, company_root) == []


def test_sc_agent_drift_nguon_khong_ton_tai(tmp_path: Path) -> None:
    """File nguồn KHÔNG tồn tại → báo sai đường dẫn, không im lặng.

    Bản cũ trả mặc định `version=1` cho file thiếu, nên một bản dẫn xuất ghi `version=1` trỏ vào đường dẫn
    trống lọt lưới hoàn toàn — đúng ca đã xảy ra thật với `sc-supervisor.md` (trỏ `agents/supervision/`, thư
    mục thật là `agents/supervisor/`). Ghi `recorded_version=1` ở đây để khoá đúng ca lọt lưới ấy."""
    company_root = tmp_path / "software-company"
    claude_dir = tmp_path / ".claude" / "agents"
    _write_sc_agent(claude_dir, "sc-foo", src="agents/engineering/khong-ton-tai.md", recorded_version=1)

    out = drift.sc_agent_drift(claude_dir, company_root)
    assert len(out) == 1
    assert "KHÔNG có file đó" in out[0].detail


def test_sc_agent_drift_bo_qua_file_khong_co_comment_nguon(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude" / "agents"
    claude_dir.mkdir(parents=True)
    (claude_dir / "sc-khac.md").write_text("---\nname: sc-khac\n---\n\nkhông có comment dẫn xuất\n",
                                            encoding="utf-8")
    assert drift.sc_agent_drift(claude_dir, tmp_path / "software-company") == []


def test_golden_drift_bo_qua_file_khong_co_comment(tmp_path: Path) -> None:
    golden_dir = tmp_path / "tests" / "golden" / "agents"
    golden_dir.mkdir(parents=True)
    (golden_dir / "khac.md").write_text("không có comment golden\n", encoding="utf-8")
    assert drift.golden_drift(golden_dir, tmp_path / "software-company") == []


def test_sc_agent_drift_bo_qua_sc_gate(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude" / "agents"
    claude_dir.mkdir(parents=True)
    (claude_dir / "sc-gate-spec.md").write_text(
        "---\nname: sc-gate-spec\n---\n\n<!-- SINH TỰ ĐỘNG từ gates/checklists.md (spec) — sửa nguồn -->\n",
        encoding="utf-8",
    )
    assert drift.sc_agent_drift(claude_dir, tmp_path / "software-company") == []


def test_golden_drift_phat_khi_lech(tmp_path: Path) -> None:
    company_root = tmp_path / "software-company"
    golden_dir = tmp_path / "tests" / "golden" / "agents"
    golden_dir.mkdir(parents=True)
    _write_source_agent(company_root, "agents/engineering/foo.md", version=3)
    (golden_dir / "foo.md").write_text("<!-- golden agent=foo version=1 -->\n# foo\n", encoding="utf-8")

    out = drift.golden_drift(golden_dir, company_root)
    assert len(out) == 1
    assert out[0].kind == "drift"


def test_golden_drift_im_khi_khop(tmp_path: Path) -> None:
    company_root = tmp_path / "software-company"
    golden_dir = tmp_path / "tests" / "golden" / "agents"
    golden_dir.mkdir(parents=True)
    _write_source_agent(company_root, "agents/engineering/foo.md", version=1)
    (golden_dir / "foo.md").write_text("<!-- golden agent=foo version=1 -->\n# foo\n", encoding="utf-8")

    assert drift.golden_drift(golden_dir, company_root) == []


def test_golden_drift_nguon_khong_ton_tai(tmp_path: Path) -> None:
    company_root = tmp_path / "software-company"
    golden_dir = tmp_path / "tests" / "golden" / "agents"
    golden_dir.mkdir(parents=True)
    (company_root / "agents").mkdir(parents=True)
    (golden_dir / "ghost.md").write_text("<!-- golden agent=ghost version=2 -->\n", encoding="utf-8")

    out = drift.golden_drift(golden_dir, company_root)
    assert len(out) == 1
    assert "không có file nguồn" in out[0].detail  # không còn giả vờ "version=1"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)


def _commit(repo: Path, message: str, when: datetime) -> None:
    (repo / "f.txt").write_text(message, encoding="utf-8")
    iso = when.isoformat()
    env_args = [f"GIT_AUTHOR_DATE={iso}", f"GIT_COMMITTER_DATE={iso}"]
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", message, "--date", iso],
        cwd=str(repo), check=True, capture_output=True,
        env={**_base_env(), **dict(a.split("=", 1) for a in env_args)},
    )


def _base_env() -> dict[str, str]:
    import os
    return dict(os.environ)


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")


def test_changelog_drift_phat_sau_moc(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    after_cutoff = drift.CHANGELOG_RULE_CUTOFF + timedelta(days=1)
    _commit(repo, "feat(keeper): thứ gì đó (#123)", after_cutoff)
    changelog = repo / "CHANGELOG.md"
    changelog.write_text("# Changelog\n", encoding="utf-8")  # không có (#123)

    out = drift.changelog_drift(repo, changelog)

    assert len(out) == 1
    assert out[0].subject == "pr-123"


def test_changelog_drift_im_khi_co_dong(tmp_path: Path) -> None:
    """Chiều ngược: thêm đúng dòng CHANGELOG cho PR đó → im lặng."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    after_cutoff = drift.CHANGELOG_RULE_CUTOFF + timedelta(days=1)
    _commit(repo, "feat(keeper): thứ gì đó (#123)", after_cutoff)
    changelog = repo / "CHANGELOG.md"
    changelog.write_text("# Changelog\n- feat(keeper): thứ gì đó (#123)\n", encoding="utf-8")

    assert drift.changelog_drift(repo, changelog) == []


def test_changelog_drift_truoc_moc_khong_bi_soi(tmp_path: Path) -> None:
    """Ca chứng minh chặn dưới: PR merge TRƯỚC mốc luật §10 mà thiếu dòng CHANGELOG vẫn im — luật đó chưa có
    hiệu lực khi PR merge."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    before_cutoff = drift.CHANGELOG_RULE_CUTOFF - timedelta(days=30)
    _commit(repo, "feat(keeper): PR cũ (#1)", before_cutoff)
    changelog = repo / "CHANGELOG.md"
    changelog.write_text("# Changelog\n", encoding="utf-8")  # không có (#1) — vẫn phải im vì trước mốc

    assert drift.changelog_drift(repo, changelog) == []


def test_changelog_drift_khong_co_changelog_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    after_cutoff = drift.CHANGELOG_RULE_CUTOFF + timedelta(days=1)
    _commit(repo, "feat(keeper): x (#9)", after_cutoff)
    out = drift.changelog_drift(repo, repo / "khong-ton-tai.md")
    assert len(out) == 1


def test_changelog_drift_commit_khong_co_so_pr_bi_bo_qua(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    after_cutoff = drift.CHANGELOG_RULE_CUTOFF + timedelta(days=1)
    _commit(repo, "chore: dọn dẹp không liên quan PR nào", after_cutoff)
    assert drift.changelog_drift(repo, repo / "CHANGELOG.md") == []


def test_git_log_that_bai_tra_rong(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`git log` thất bại (returncode != 0, ví dụ thư mục không phải repo) → rỗng, không ném."""
    class _Bad:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Bad())
    assert drift._git_log_pr_commits(tmp_path) == []


def test_git_log_dong_hong_va_ngay_hong_bi_bo_qua(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Dòng không có ký tự phân cách `\\x1f` (không đúng khuôn `--format`) và dòng có ngày không parse được
    đều bị bỏ qua, không ném lỗi — chỉ dòng hợp lệ mới vào kết quả."""
    class _Ok:
        returncode = 0
        stdout = (
            "dong khong co dau phan cach khong (#1)\n"
            "feat: hong ngay (#2)\x1fkhong-phai-ngay\n"
            "feat: hop le (#3)\x1f2026-09-08T00:00:00+07:00\n"
        )

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Ok())
    out = drift._git_log_pr_commits(tmp_path)
    assert out == [(3, datetime.fromisoformat("2026-09-08T00:00:00+07:00"))]


def test_scan_tong_hop(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit(repo, "chore: khoi tao", datetime.now(tz=UTC))
    claude_dir = tmp_path / ".claude" / "agents"
    claude_dir.mkdir(parents=True)
    golden_dir = tmp_path / "tests" / "golden" / "agents"
    golden_dir.mkdir(parents=True)
    company_root = tmp_path / "software-company"
    (company_root / "agents").mkdir(parents=True)

    out = drift.scan(
        claude_agents_dir=claude_dir, golden_agents_dir=golden_dir, company_root=company_root,
        repo=repo, changelog=repo / "CHANGELOG.md",
    )
    assert isinstance(out, list)
