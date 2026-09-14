"""Cổng cho lớp hàng rào lấy từ `seeker19110/project-template`: `scripts/dev-task.sh` + `.claude/hooks/`.

Vì sao cần: `AGENTS.md` có 8 luật cấm rất chặt (không push `main`, không commit `llm.yaml`/`*.sqlite`, không hạ
`fail_under`) nhưng trước bộ này **không một cơ chế nào thi hành** chúng — tất cả dựa vào agent tự nhớ, CI bắt
sau khi đã push. Hook chặn tại chỗ gõ lệnh; test này canh chính hook, vì một hook trỏ sai đường dẫn là cổng
chết im lặng — nguy hiểm hơn không có cổng (cùng lý do `test_cong_repo.py`).

Đặt ở `platform/console/tests/` theo đúng lối `test_cong_repo.py`/`test_readme_goc.py`: console là nơi repo đặt
các phép canh cấp gốc.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DEV_TASK = ROOT / "scripts" / "dev-task.sh"
HOOKS = ROOT / ".claude" / "hooks"
SETTINGS = ROOT / ".claude" / "settings.json"

BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="cần bash (Git Bash trên Windows) để chạy hook")

# Năm package của workspace và module mypy tương ứng — nguồn đối chiếu cho dev-task.sh.
GOI = {
    "company": ("companies/software-company", "company"),
    "gateway": ("platform/gateway", "gateway"),
    "console": ("platform/console", "console"),
    "core": ("platform/xagents-core", "xagents_core"),
    "keeper": ("companies/keeper", "keeper"),
}


def _chay(script: Path, *args: str, stdin: str = "", **moi_truong: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT), **moi_truong}
    assert BASH is not None
    return subprocess.run(
        [BASH, str(script), *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',   # hook in tiếng Việt ra stderr; mặc định Windows là cp1252 → vỡ, stderr thành None
        env=env,
        cwd=ROOT,
    )


def _payload(cmd: str) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})


def _git(kho: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(kho), *args], check=True, capture_output=True)


@pytest.fixture
def kho_main(tmp_path: Path) -> Path:
    """Một repo git rỗng đang đứng trên nhánh `main` — để thử luật cấm 1 mà không đụng repo thật."""
    kho = tmp_path / "kho"
    kho.mkdir()
    _git(kho, "init", "-q", "-b", "main")
    _git(kho, "config", "user.email", "t@t")
    _git(kho, "config", "user.name", "t")
    return kho


# --- scripts/dev-task.sh ----------------------------------------------------


def test_dev_task_ton_tai_va_chay_duoc() -> None:
    assert DEV_TASK.is_file(), "AGENTS.md §3 bắt nhớ ba lệnh CI khác nhau cho năm package — cần một điểm vào"


def test_dev_task_task_la_bao_loi() -> None:
    kq = _chay(DEV_TASK, "khong-co-task-nay")
    assert kq.returncode == 2, f"task lạ phải exit 2, nhận {kq.returncode}: {kq.stderr}"


def test_dev_task_thieu_task_bao_loi() -> None:
    assert _chay(DEV_TASK).returncode == 2


@pytest.mark.parametrize("goi", sorted(GOI))
def test_dev_task_lint_dung_lenh_ci_cua_tung_goi(goi: str) -> None:
    """Lệnh in ra phải khớp AGENTS.md §3 — sai một chữ là cổng cục bộ khác cổng CI."""
    thu_muc, _ = GOI[goi]
    kq = _chay(DEV_TASK, "lint", goi, DEV_TASK_DRY_RUN="1")
    assert kq.returncode == 0, kq.stderr
    assert "uv run ruff check src tests" in kq.stdout
    assert thu_muc in kq.stdout


@pytest.mark.parametrize("goi", sorted(GOI))
def test_dev_task_typecheck_dung_module(goi: str) -> None:
    _, module = GOI[goi]
    kq = _chay(DEV_TASK, "typecheck", goi, DEV_TASK_DRY_RUN="1")
    assert kq.returncode == 0, kq.stderr
    assert f"uv run mypy src/{module} --ignore-missing-imports" in kq.stdout


@pytest.mark.parametrize("goi", sorted(GOI))
def test_dev_task_test_luon_do_coverage(goi: str) -> None:
    """CI chạy `--cov` cho CẢ NĂM package (ci.yml) — cổng cục bộ thiếu `--cov` là cổng khác cổng CI.

    `fail_under = 100` chỉ có hiệu lực khi có `--cov`; bỏ nó đi thì cổng cục bộ xanh trong khi CI đỏ.
    """
    assert "--cov" in _chay(DEV_TASK, "test", goi, DEV_TASK_DRY_RUN="1").stdout


def test_dev_task_chi_software_company_chay_xdist() -> None:
    """`-n auto` chỉ software-company (ci.yml): bộ test của nó nặng I/O, các gói khác chạy tuần tự."""
    assert "-n auto" in _chay(DEV_TASK, "test", "company", DEV_TASK_DRY_RUN="1").stdout
    assert "-n auto" not in _chay(DEV_TASK, "test", "gateway", DEV_TASK_DRY_RUN="1").stdout


def test_dev_task_gate_chay_du_ba_cong_dung_thu_tu() -> None:
    kq = _chay(DEV_TASK, "gate", "console", DEV_TASK_DRY_RUN="1")
    assert kq.returncode == 0, kq.stderr
    vi_tri = [kq.stdout.find(x) for x in ("ruff check", "mypy", "pytest")]
    assert all(v >= 0 for v in vi_tri), f"gate thiếu bước: {kq.stdout}"
    assert vi_tri == sorted(vi_tri), f"gate sai thứ tự lint→typecheck→test: {kq.stdout}"


def test_dev_task_gate_khong_goi_chay_ca_nam_package() -> None:
    ra = _chay(DEV_TASK, "gate", DEV_TASK_DRY_RUN="1").stdout
    for thu_muc, _ in GOI.values():
        assert thu_muc in ra, f"gate toàn workspace bỏ sót {thu_muc}"


def test_moi_thu_muc_goi_trong_dev_task_ton_tai_that() -> None:
    """Cải tổ thư mục #262 từng làm mọi đường dẫn trỏ vào hư không — không để lặp lại ở đây."""
    than = DEV_TASK.read_text(encoding="utf-8")
    for thu_muc, module in GOI.values():
        assert (ROOT / thu_muc).is_dir()
        assert (ROOT / thu_muc / "src" / module).is_dir()
        assert thu_muc in than, f"dev-task.sh không biết tới {thu_muc}"


def test_dev_task_format_file_chi_dong_vao_file_python() -> None:
    assert "ruff format" in _chay(DEV_TASK, "format-file", "a/b.py", DEV_TASK_DRY_RUN="1").stdout
    assert "ruff format" not in _chay(DEV_TASK, "format-file", "a/b.md", DEV_TASK_DRY_RUN="1").stdout


# --- .claude/hooks/block-dangerous-git.sh -----------------------------------

CHAN_GIT = HOOKS / "block-dangerous-git.sh"


@pytest.mark.parametrize(
    "cmd",
    [
        "git push --force origin main",
        "git push -f origin main",
        "git push --force-with-lease origin main",
        "git push origin main",
        "git push origin HEAD:main",
        "git reset --hard origin/main",
        "git merge --abort",
        "git rebase --abort",
        "git cherry-pick --abort",
    ],
)
def test_chan_git_chan_dung_khuon_cam(cmd: str) -> None:
    """Luật cấm 1 (`main`) và `CLAUDE.md` §8 (`reset --hard`, `--abort`) — exit 2 = chặn."""
    kq = _chay(CHAN_GIT, stdin=_payload(cmd))
    assert kq.returncode == 2, f"đáng lẽ chặn: {cmd} (exit {kq.returncode})"


@pytest.mark.parametrize(
    "cmd",
    [
        "git status --short",
        "git log --oneline -5",
        "git push origin worktree-abc",
        "git push --force-with-lease origin worktree-abc",
        "git commit -m 'nói về git reset --hard trong message'",
        "echo 'git push origin main'",
        "git diff main...HEAD",
    ],
)
def test_chan_git_khong_chan_oan(cmd: str) -> None:
    """Chặn oan làm agent tưởng repo hỏng rồi đi đường vòng — tệ hơn không chặn."""
    kq = _chay(CHAN_GIT, stdin=_payload(cmd))
    assert kq.returncode == 0, f"chặn oan: {cmd}\n{kq.stderr}"


def test_chan_git_co_duong_thoat_tuong_minh() -> None:
    kq = _chay(CHAN_GIT, stdin=_payload("git reset --hard"), ALLOW_DANGEROUS_GIT="1")
    assert kq.returncode == 0


def test_chan_git_thieu_jq_thi_noi_ra() -> None:
    """Fail-open IM LẶNG là cái bẫy: người tưởng hàng rào đang canh suốt phiên (template F-007)."""
    kq = _chay(CHAN_GIT, stdin=_payload("git reset --hard"), PATH="/nonexistent")
    assert kq.returncode == 0
    assert "jq" in kq.stderr


# --- .claude/hooks/pre-commit-gate.sh ---------------------------------------

CONG_COMMIT = HOOKS / "pre-commit-gate.sh"


def _cong(cmd: str, kho: Path, **env: str) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    return subprocess.run(
        [BASH, str(CONG_COMMIT)],
        input=_payload(cmd),
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(kho), "DEV_TASK_DRY_RUN": "1", **env},
        cwd=kho,
    )


def test_cong_commit_chan_khi_dang_dung_tren_main(kho_main: Path) -> None:
    """Luật cấm 1: commit thẳng `main` — bắt TRƯỚC khi commit, không đợi ruleset từ chối lúc push."""
    kq = _cong("git commit -m 'x'", kho_main)
    assert kq.returncode == 2, kq.stderr + kq.stdout
    assert "main" in kq.stderr


def test_cong_commit_cho_qua_tren_nhanh_rieng(kho_main: Path) -> None:
    _git(kho_main, "checkout", "-q", "-b", "worktree-thu")
    assert _cong("git commit -m 'x'", kho_main).returncode == 0


@pytest.mark.parametrize("ten", ["llm.yaml", "media.yaml", "company.sqlite", "a/b/llm.yaml"])
def test_cong_commit_chan_file_cam_trong_staged(kho_main: Path, ten: str) -> None:
    """Luật cấm 3: gitleaks quét cả lịch sử — lỡ commit rồi xoá vẫn đỏ, nên phải chặn trước khi vào lịch sử."""
    _git(kho_main, "checkout", "-q", "-b", "worktree-thu")
    f = kho_main / ten
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("x", encoding="utf-8")
    _git(kho_main, "add", "-f", ten)
    kq = _cong("git commit -m 'x'", kho_main)
    assert kq.returncode == 2, f"đáng lẽ chặn {ten}"
    assert ten.split("/")[-1] in kq.stderr


def test_cong_commit_chan_ha_nguong_coverage(kho_main: Path) -> None:
    """Luật cấm 6: `fail_under = 100`, mất một dòng phủ thì thêm test — không hạ số."""
    _git(kho_main, "checkout", "-q", "-b", "worktree-thu")
    (kho_main / "pyproject.toml").write_text("fail_under = 100\n", encoding="utf-8")
    _git(kho_main, "add", "pyproject.toml")
    _git(kho_main, "commit", "-qm", "nen")
    (kho_main / "pyproject.toml").write_text("fail_under = 95\n", encoding="utf-8")
    _git(kho_main, "add", "pyproject.toml")
    kq = _cong("git commit -m 'x'", kho_main)
    assert kq.returncode == 2, "hạ fail_under phải bị chặn"
    assert "fail_under" in kq.stderr


def test_cong_commit_bo_qua_khi_co_no_verify(kho_main: Path) -> None:
    assert _cong("git commit --no-verify -m 'x'", kho_main).returncode == 0


def test_cong_commit_khong_dong_vao_lenh_khac(kho_main: Path) -> None:
    assert _cong("git status", kho_main).returncode == 0


def test_cong_commit_chi_chay_cong_cua_goi_bi_dung(kho_main: Path) -> None:
    """Chạy cổng cả năm package trước MỖI commit mất nhiều phút — agent sẽ tìm cách né, hàng rào thành vô dụng.

    Cổng chỉ chạy cho package có file trong diff staged.
    """
    _git(kho_main, "checkout", "-q", "-b", "worktree-thu")
    f = kho_main / "platform" / "console" / "src" / "console" / "x.py"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("x = 1\n", encoding="utf-8")
    _git(kho_main, "add", "-A")
    kq = _cong("git commit -m 'x'", kho_main)
    assert kq.returncode == 0, kq.stderr
    assert "console" in kq.stderr, f"không nói nó chạy cổng cho gói nào: {kq.stderr}"
    assert "gateway" not in kq.stderr, f"chạy cổng cho gói không đụng tới: {kq.stderr}"


def test_cong_commit_doi_file_goc_thi_chay_ca_workspace(kho_main: Path) -> None:
    """Đổi `pyproject.toml`/`Makefile` ở gốc ảnh hưởng mọi gói → không được chạy cổng hẹp rồi báo xanh."""
    _git(kho_main, "checkout", "-q", "-b", "worktree-thu")
    (kho_main / "Makefile").write_text("x:\n", encoding="utf-8")
    _git(kho_main, "add", "-A")
    assert "all" in _cong("git commit -m 'x'", kho_main).stderr


# --- .claude/hooks/auto-format.sh -------------------------------------------

DINH_DANG = HOOKS / "auto-format.sh"


def test_auto_format_khong_bao_gio_can_luong() -> None:
    """Hook format mà chặn được luồng là hook sai: nó chạy sau MỌI lần sửa file."""
    for payload in ('{"tool_input":{"file_path":"a.py"}}', "{}", "khong-phai-json"):
        kq = subprocess.run(
            [str(BASH), str(DINH_DANG)],
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT), "DEV_TASK_DRY_RUN": "1"},
            cwd=ROOT,
        )
        assert kq.returncode == 0, f"auto-format trả {kq.returncode} với payload {payload!r}"


# --- .claude/settings.json --------------------------------------------------


def test_moi_hook_khai_trong_settings_ton_tai_that() -> None:
    """Hook trỏ sai đường dẫn = cổng chết im lặng, đúng khuôn lỗi `test_cong_repo.py` canh."""
    cfg = json.loads(SETTINGS.read_text(encoding="utf-8"))
    lenh = [
        h["command"]
        for nhom in cfg.get("hooks", {}).values()
        for muc in nhom
        for h in muc["hooks"]
    ]
    assert lenh, "settings.json chưa nối hook nào — hàng rào không được bật"
    for mot_lenh in lenh:
        duong_dan = mot_lenh.replace("${CLAUDE_PROJECT_DIR}/", "").split()[0]
        assert (ROOT / duong_dan).is_file(), f"settings.json trỏ vào hook không tồn tại: {duong_dan}"


def test_moi_hook_deu_co_test_trong_file_nay() -> None:
    """Thêm hook mà quên test = thêm một cổng không ai biết nó còn sống không."""
    than = Path(__file__).read_text(encoding="utf-8")
    for hook in sorted(HOOKS.glob("*.sh")):
        assert hook.name in than, f"hook {hook.name} chưa có test nào trong test_cong_khung.py"


def test_moi_script_sh_duoc_chot_eol_lf() -> None:
    """Máy phát triển là Windows: `.sh` lọt vào repo với CRLF thì bash trên CI Linux báo `\\r: command not found`.

    Hook vỡ theo kiểu này KHÔNG đỏ ở đâu cả — nó chỉ lặng lẽ không canh gì nữa.
    """
    scripts = [
        str(p.relative_to(ROOT)).replace("\\", "/")
        for p in [*(ROOT / "scripts").glob("*.sh"), *HOOKS.glob("*.sh"), *(ROOT / "docker").glob("*.sh")]
    ]
    assert scripts
    kq = subprocess.run(
        ["git", "-C", str(ROOT), "check-attr", "eol", "--", *scripts],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    hong = [d for d in kq.stdout.splitlines() if not d.endswith(": eol: lf")]
    assert not hong, f".gitattributes chưa chốt eol=lf cho: {hong}"


# --- luật phát cho mọi harness ----------------------------------------------


@pytest.mark.parametrize("ten", [".cursorrules", "GEMINI.md", ".windsurfrules", ".clinerules"])
def test_file_luat_cho_harness_khac_tro_ve_agents_md(ten: str) -> None:
    """Agent không phải Claude Code cũng phải đọc đúng một nguồn luật, không tự suy diễn."""
    f = ROOT / ten
    assert f.is_file(), f"thiếu {ten}: agent khác Claude Code vào repo không biết luật ở đâu"
    assert "AGENTS.md" in f.read_text(encoding="utf-8")
