"""C8 — hồ sơ `gate_brief` dựng được từ console, và là ĐÚNG văn bản mà CLI của công ty sinh ra.

Test hai chiều: nếu `brief.gate_brief` tự chế lại nội dung thay vì gọi `company.gate_brief.render_md`, phép so
"cùng một văn bản" đỏ; nếu nó nuốt lỗi thành hồ sơ rỗng, phép so thông điệp đỏ.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from company import gate_brief as gb

from console.brief import BriefUnavailable, gate_brief


def test_ho_so_tren_trang_va_ho_so_cua_cli_la_mot(company_db: Path) -> None:
    got = gate_brief(company_db, "PLAN-1")
    assert got["kind"] == "plan" and got["subject_id"] == "PLAN-1"
    orch = gb.load_state(company_db)
    assert got["md"] == gb.render_md(gb.build(orch, "PLAN-1")), "trang và CLI phải đọc cùng một văn bản"
    assert "Nửa của người" in got["md"]


def test_gate_da_dong_chi_dung_duoc_khi_xin_closed(company_db: Path) -> None:
    with pytest.raises(BriefUnavailable, match="không có trong hàng đợi gate"):
        gate_brief(company_db, "SPEC-1")
    assert gate_brief(company_db, "SPEC-1", closed=True)["kind"] == "spec"


def test_moi_ly_do_khong_dung_duoc_deu_noi_thanh_loi(company_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(BriefUnavailable, match="Studio-creators"):
        gate_brief(company_db, "PUB-vid-042", xuong="Studio-creators")
    with pytest.raises(BriefUnavailable, match="thiếu subject_id"):
        gate_brief(company_db, "   ")
    with pytest.raises(BriefUnavailable, match="chưa có file DB"):
        gate_brief(None, "PLAN-1")
    with pytest.raises(BriefUnavailable, match="chưa có file DB"):
        gate_brief(tmp_path / "khong-co.sqlite", "PLAN-1")

    def hong(*a: object, **k: object) -> None:
        raise gb.BriefError("log hỏng")

    monkeypatch.setattr(gb, "load_state", hong)
    with pytest.raises(BriefUnavailable, match="không dựng được hồ sơ: log hỏng"):
        gate_brief(company_db, "PLAN-1")

    def no(*a: object, **k: object) -> None:
        raise RuntimeError("checklist đổi hình dạng")

    monkeypatch.setattr(gb, "load_state", no)
    with pytest.raises(BriefUnavailable, match="RuntimeError: checklist đổi hình dạng"):
        gate_brief(company_db, "PLAN-1")


def test_dung_ho_so_khong_ghi_gi_vao_db(company_db: Path) -> None:
    """Chỉ đọc là điều kiện để nút này nằm cạnh nút Duyệt mà không cần `--allow-decide`."""
    before = company_db.stat().st_size, company_db.read_bytes()
    gate_brief(company_db, "PLAN-1")
    assert (company_db.stat().st_size, company_db.read_bytes()) == before
