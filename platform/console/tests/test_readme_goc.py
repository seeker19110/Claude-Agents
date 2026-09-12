"""README gốc (`/README.md`) không được lệch số ADR/agent thật của software-company trên đĩa.

Không trùng với `test_readme_khop_so_lieu_that` (canh README package) — test này chỉ canh README gốc.
"""

from __future__ import annotations

import re
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
