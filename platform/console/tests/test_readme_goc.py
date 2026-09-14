"""README gốc (`/README.md`) không được lệch số ADR/agent thật của software-company trên đĩa.

Không trùng với `test_readme_khop_so_lieu_that` (canh README package) — test này chỉ canh README gốc.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
ROOT_README = ROOT / "README.md"
COMPANY_ROW_RE = re.compile(
    r"\[`companies/software-company/`\].*?7 khối, (\d+) agent.*?ADR (\d{4})–(\d{4})",
)


def _company_row() -> re.Match[str]:
    text = ROOT_README.read_text(encoding="utf-8")
    match = COMPANY_ROW_RE.search(text)
    assert match, "README gốc: không tìm thấy dòng software-company đúng khuôn 7 khối/agent/ADR"
    return match


def test_so_agent_khop_dia() -> None:
    agent_files = list((ROOT / "companies" / "software-company" / "agents").glob("*/*.md"))
    match = _company_row()
    assert int(match.group(1)) == len(agent_files), (
        f"README gốc ghi {match.group(1)} agent nhưng companies/software-company/agents/*/*.md có {len(agent_files)} file"
    )


def test_so_adr_khop_dia() -> None:
    adr_files = list((ROOT / "companies" / "software-company" / "docs" / "adr").glob("*.md"))
    match = _company_row()
    adr_dau, adr_cuoi = int(match.group(2)), int(match.group(3))
    assert adr_cuoi - adr_dau + 1 == len(adr_files), (
        f"README gốc ghi ADR {match.group(2)}–{match.group(3)} "
        f"({adr_cuoi - adr_dau + 1} bản) nhưng companies/software-company/docs/adr/*.md có {len(adr_files)} file"
    )


# Dòng treo từ 2026-09-07 trong `docs/TASK-PACK.md`: cổng cũ chỉ canh software-company, nên dãy ADR của
# console lệch (README ghi 0001–0003 khi đĩa có 4) sống được 5 ngày mà không gì đỏ. Repo có BỐN dãy ADR cùng
# đánh số từ 0001, canh một dãy là bỏ ba.
DAY_ADR = {
    "platform/console": r"\[`platform/console/`\].*?ADR (\d{4})–(\d{4})",
    "platform/gateway": r"\[`platform/gateway/`\].*?ADR (\d{4})–(\d{4})",
}


@pytest.mark.parametrize("pkg", sorted(DAY_ADR))
def test_so_adr_cac_day_khac_khop_dia(pkg: str) -> None:
    thu_muc = ROOT / pkg / "docs" / "adr"
    tren_dia = len([f for f in thu_muc.glob("*.md") if f.name != "README.md"])
    m = re.search(DAY_ADR[pkg], ROOT_README.read_text(encoding="utf-8"), re.S)
    assert m is not None, f"README gốc chưa khai dãy ADR cho {pkg} — thêm dòng ADR NNNN–NNNN vào bảng"
    khai = int(m.group(2)) - int(m.group(1)) + 1
    assert khai == tren_dia, f"README gốc ghi {khai} ADR cho {pkg} nhưng {thu_muc} có {tren_dia} file"


# `| [`companies/keeper/`](…) | … | … 553 test |` — một dòng bảng "Quy mô" của README gốc.
_DONG_GOI = re.compile(r"^\|\s*\[`([^`]+?)/?`\]\([^)]*\).*?\b(\d+) test\b", re.MULTILINE)


def _dem_that(goi: str) -> int:
    """Số ca `pytest` THẬT của một package — hỏi chính pytest, không đếm `def test_` bằng tay.

    Đếm bằng grep thì sai ở mọi chỗ có `parametrize`, mà repo này dùng `parametrize` khắp nơi (`test_cong_repo`
    chạy một ca cho mỗi package). Sai theo hướng nói ÍT hơn thật — đúng hướng lệch mà phép này sinh ra để bắt.
    """
    # `uv run --directory` chứ không `sys.executable -m pytest`: mỗi package có nhóm dev riêng — chạy pytest của
    # console trong thư mục gateway thì 10 file lỗi thu thập vì thiếu `pytest-asyncio`, và một cổng "đếm được 0"
    # là cổng nói dối chứ không phải cổng đỏ. `uv` luôn có: CI chạy test bằng chính nó.
    kq = subprocess.run(["uv", "run", "--directory", str(ROOT / goi), "pytest", "--collect-only", "-q"],
                        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"(\d+) tests? collected", kq.stdout)
    assert m, f"không đọc được số ca của {goi}: {kq.stdout[-500:]}\n{kq.stderr[-500:]}"
    return int(m.group(1))


def test_so_test_trong_readme_khop_dia() -> None:
    """Số test README khai phải bằng số pytest thu được — **không có cổng nào canh dòng này trước 2026-09-15**.

    Vì sao đáng một phép riêng: bản tự kiểm 2026-09-07 đã bắt 5/10 dòng số liệu README lệch với đĩa, **tất cả
    đều lệch một chiều "nói ít hơn thật"** và đúng những dòng KHÔNG có test CI canh. Sửa số một lần thì ba tháng
    sau lệch lại — thứ duy nhất giữ được là một cổng. Đo lại 2026-09-15 trước khi viết phép này: company
    1249→1256, gateway 251→256, core 479→488, cùng một chiều lệch, y hệt lần trước.

    Con số nói ít hơn thật không vô hại: nó là lời khai về quy mô kiểm thử, và người đọc README (kể cả agent
    phiên sau) dùng nó để quyết định có tin bộ test hay không.
    """
    doc = (ROOT / "README.md").read_text(encoding="utf-8")
    khai = {goi: int(so) for goi, so in _DONG_GOI.findall(doc)}
    assert khai, "không dòng nào của bảng README khai số test — regex hỏng chứ không phải README sạch"

    lech = {goi: (so, that) for goi, so in khai.items() if (that := _dem_that(goi)) != so}
    assert not lech, ("README khai số test không khớp đĩa (khai, thật): " + repr(lech) +
                      " — sửa README trong CÙNG PR làm số đổi, đừng để lại cho phiên audit.")
