"""BT5 — `keeper run --dry-run`: in kế hoạch mà KHÔNG chạm file nào.

Chiều thuận: hash cả cây thư mục trước/sau `--dry-run` phải BẰNG nhau.
Chiều ngược: bỏ `--dry-run` (chạy thật) → hash ĐỔI. Nếu hash không đổi ở chiều ngược thì phép đo vô nghĩa,
nên ca chiều ngược assert cả nội dung file đã đổi, không chỉ assert hash khác.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from keeper.cli import Plan, main, plan_for
from keeper.events import Ticket


def cay_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if ".git" in p.parts or not p.is_file():
            continue
        h.update(str(p.relative_to(root)).replace("\\", "/").encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def _git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.fixture
def main_repo(tmp_path: Path) -> Path:
    r = tmp_path / "chung"
    (r / "docs" / "sessions").mkdir(parents=True)
    (r / "docs" / "sessions" / ".gitkeep").write_text("", encoding="utf-8")
    (r / "CHANGELOG.md").write_text("# Nhật ký thay đổi\n\n- dòng cũ\n", encoding="utf-8")
    (r / "pyproject.toml").write_text('dependencies = ["pydantic>=2.6"]\n', encoding="utf-8")
    _git(r, "init", "-b", "main")
    _git(r, "add", "-A")
    _git(r, "-c", "user.name=t", "-c", "user.email=t@x", "commit", "-m", "khoi tao")
    return r


@pytest.fixture
def root(main_repo: Path) -> Path:
    """CLI chỉ ghi được trong worktree phụ (CHẶN-1)."""
    wt = main_repo.parent / "wt"
    _git(main_repo, "worktree", "add", "-b", "chore/keeper-t", str(wt), "HEAD")
    return wt


def _ticket(ticket_id: str, subject: str, tier: str = "low") -> dict:
    return Ticket(ticket_id=ticket_id, subject=subject, risk_tier=tier).model_dump()  # type: ignore[arg-type]


@pytest.fixture
def tickets(tmp_path: Path) -> Path:
    """File ticket nằm NGOÀI `root` để nó không lọt vào hash cây thư mục."""
    f = tmp_path / "tickets.json"
    f.write_text(json.dumps([
        _ticket("T-doc", "CHANGELOG.md"),
        _ticket("T-dep", "pydantic"),
        _ticket("T-golden", "tests/golden/x.json"),
        _ticket("T-prompt", "software-company/agents/builder.md", tier="high"),
    ]), encoding="utf-8")
    return f


def test_plan_for_xep_dung_thao_tac():
    assert plan_for(Ticket(ticket_id="a", subject="CHANGELOG.md", risk_tier="low")).operation == "fix_docs"
    assert plan_for(Ticket(ticket_id="a", subject="pydantic", risk_tier="medium")).operation == "bump_dependency"
    assert plan_for(Ticket(ticket_id="a", subject="tests/golden/x.json", risk_tier="low")).operation == "regen_derived"
    p = plan_for(Ticket(ticket_id="a", subject="keeper/skills/x.md", risk_tier="low"))
    assert p.operation == "needs_human"
    assert plan_for(Ticket(ticket_id="a", subject="pydantic", risk_tier="high")).operation == "needs_human"


def test_dry_run_in_ke_hoach_va_khong_cham_file_nao(root: Path, tickets: Path, capsys):
    truoc = cay_hash(root)
    assert main(["run", "--dry-run", "--tickets", str(tickets), "--root", str(root)]) == 0
    sau = cay_hash(root)
    assert sau == truoc
    out = capsys.readouterr().out
    for phan in ("T-doc", "fix_docs", "CHANGELOG.md", "T-dep", "bump_dependency", "T-golden", "regen_derived",
                 "T-prompt", "needs_human"):
        assert phan in out
    assert "CHẠY KHÔ" in out


def test_chieu_nguoc_chay_that_thi_hash_DOI(root: Path, tmp_path: Path, capsys):
    f = tmp_path / "mot.json"
    f.write_text(json.dumps([_ticket("T-doc", "CHANGELOG.md")]), encoding="utf-8")
    truoc = cay_hash(root)
    assert main(["run", "--tickets", str(f), "--root", str(root)]) == 0
    assert cay_hash(root) != truoc
    assert "T-doc" in (root / "CHANGELOG.md").read_text(encoding="utf-8")


def test_chay_that_bo_qua_thao_tac_chua_noi_vao_cli(root: Path, tickets: Path, capsys):
    truoc = cay_hash(root)
    assert main(["run", "--tickets", str(tickets), "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "bỏ qua" in out
    assert (root / "CHANGELOG.md").read_text(encoding="utf-8") != ""
    assert cay_hash(root) != truoc  # chỉ T-doc được thi hành


def test_ticket_hong_thi_bao_loi_khong_no(root: Path, tmp_path: Path, capsys):
    f = tmp_path / "hong.json"
    f.write_text(json.dumps([{"ticket_id": "x"}]), encoding="utf-8")
    assert main(["run", "--dry-run", "--tickets", str(f), "--root", str(root)]) == 2
    assert "không đọc được" in capsys.readouterr().err


def test_khong_co_lenh_thi_tra_ma_khac_0(capsys):
    with pytest.raises(SystemExit):
        main([])


def test_plan_la_dataclass_doc_duoc():
    p = Plan(ticket_id="a", operation="fix_docs", files=["CHANGELOG.md"], reason="")
    assert "fix_docs" in str(p)


def test_root_la_bat_buoc_khong_con_mac_dinh_cham(tmp_path: Path, capsys):
    """CHẶN-1: `--root` không còn mặc định `"."` — gõ thiếu là lỗi tham số, không phải ghi vào thư mục hiện tại."""
    f = tmp_path / "t.json"
    f.write_text(json.dumps([_ticket("T-doc", "CHANGELOG.md")]), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        main(["run", "--tickets", str(f)])
    assert e.value.code != 0
    assert "--root" in capsys.readouterr().err


def test_cli_tu_choi_ghi_vao_checkout_chung(main_repo: Path, tmp_path: Path, capsys):
    f = tmp_path / "t.json"
    f.write_text(json.dumps([_ticket("T-doc", "CHANGELOG.md")]), encoding="utf-8")
    truoc = cay_hash(main_repo)
    assert main(["run", "--tickets", str(f), "--root", str(main_repo)]) == 3
    assert cay_hash(main_repo) == truoc
    assert "worktree" in capsys.readouterr().err


def test_chieu_nguoc_cung_lenh_do_tren_worktree_phu_thi_GHI_THAT(root: Path, tmp_path: Path):
    """Chiều ngược của ca trên: đổi đúng một biến (checkout chung → worktree phụ) thì lệnh chạy và ghi thật."""
    f = tmp_path / "t2.json"
    f.write_text(json.dumps([_ticket("T-doc", "CHANGELOG.md")]), encoding="utf-8")
    assert main(["run", "--tickets", str(f), "--root", str(root)]) == 0
    assert "T-doc" in (root / "CHANGELOG.md").read_text(encoding="utf-8")
