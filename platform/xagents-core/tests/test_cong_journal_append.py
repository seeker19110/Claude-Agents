"""Cổng: một đường ghi duy nhất vào ExecutionJournal — chỉ qua `transition` (ADR-0019, gói P1).

`ExecutionJournal.append` là alias legacy phát `DeprecationWarning`; mã sản xuất (`src/`) không được gọi nó,
vì nó bỏ qua kiểm compare-and-swap của `transition`. Cổng này quét mã nguồn thật (không phải test) tìm lời gọi
`.append(` trên một biến rõ ràng là journal — sót một chỗ là một đường ghi không qua CAS, và không ai nhận ra
cho tới khi hai quyết định cùng ghi chồng lên nhau.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

_JOURNAL_APPEND = re.compile(r"\b_?journal\w*\.append\(")


def _quet(thu_muc: Path) -> list[str]:
    vi_pham: list[str] = []
    for tep in sorted(thu_muc.rglob("*.py")):
        noi_dung = tep.read_text(encoding="utf-8")
        for so_dong, dong in enumerate(noi_dung.splitlines(), start=1):
            if _JOURNAL_APPEND.search(dong):
                vi_pham.append(f"{tep}:{so_dong}: {dong.strip()}")
    return vi_pham


def test_khong_co_loi_goi_journal_append_truc_tiep_trong_src() -> None:
    thu_muc_can_quet = [
        *(ROOT / "companies").glob("*/src"),
        *(ROOT / "platform").glob("*/src"),
    ]
    vi_pham: list[str] = []
    for thu_muc in thu_muc_can_quet:
        if thu_muc.is_dir():
            vi_pham.extend(_quet(thu_muc))
    assert vi_pham == [], "src/ chỉ được ghi qua transition(), không qua journal.append():\n" + "\n".join(vi_pham)


def test_ham_quet_bat_duoc_loi_goi_journal_append(tmp_path) -> None:
    """Chiều ngược của test trên: hàm quét phải thật sự bắt được vi phạm, không phải luôn trả rỗng."""
    tep = tmp_path / "vi_du.py"
    tep.write_text("def f(self):\n    self._journal.append(event)\n    journal2.append(event)\n", encoding="utf-8")
    vi_pham = _quet(tmp_path)
    assert len(vi_pham) == 2
    assert all("append(" in dong for dong in vi_pham)


def test_ham_quet_bo_qua_bien_khong_ten_journal(tmp_path) -> None:
    tep = tmp_path / "vi_du.py"
    tep.write_text("def f():\n    findings.append('x')\n    blockers.append('y')\n", encoding="utf-8")
    assert _quet(tmp_path) == []
