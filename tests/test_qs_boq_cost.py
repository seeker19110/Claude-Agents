"""Lập dự toán có giá trị tiền từ bảng khối lượng đã bóc tách."""
import pandas as pd
import pytest

from src import qs_tools
from src.qs_tools import calc_boq_cost, load_unit_prices, lookup_unit_price, match_unit_price
from src.workspace import set_workspace_dir


@pytest.fixture
def workspace(tmp_path):
    set_workspace_dir(str(tmp_path))
    return tmp_path


@pytest.fixture
def prices():
    return load_unit_prices()


def _write_takeoff(path, rows):
    pd.DataFrame(rows).to_excel(path, index=False)


def test_unit_price_csv_loads_with_numeric_columns(prices):
    assert not prices.empty
    for col in ("don_gia_vat_tu", "don_gia_nhan_cong", "don_gia_may"):
        assert pd.api.types.is_numeric_dtype(prices[col])


def test_match_is_accent_and_case_insensitive(prices):
    assert match_unit_price("Đầu phun Sprinkler", prices) is not None
    assert match_unit_price("SPRINKLER", prices)["ma_hieu"] == "MEP.FF.01"


def test_longer_keyword_wins_over_shorter_one(prices):
    """'bơm chữa cháy' phải ra bơm PCCC chứ không phải bơm cấp nước sinh hoạt."""
    assert match_unit_price("Bơm chữa cháy trục ngang", prices)["ma_hieu"] == "MEP.FF.05"
    assert match_unit_price("Bơm cấp nước sinh hoạt", prices)["ma_hieu"] == "MEP.PL.03"


def test_unknown_item_returns_none_instead_of_guessing(prices):
    assert match_unit_price("Thiết bị không tồn tại XYZ", prices) is None


def test_boq_computes_line_totals_and_grand_total(workspace):
    takeoff = workspace / "khoi_luong.xlsx"
    _write_takeoff(takeoff, [
        {"STT": 1, "Hạng mục": "SPRINKLER", "Đơn vị": "Bộ", "Khối lượng": 10},
        {"STT": 2, "Hạng mục": "Ống uPVC D110", "Đơn vị": "m", "Khối lượng": 100},
    ])

    result = calc_boq_cost.invoke({"takeoff_excel_path": "khoi_luong.xlsx"})
    assert "LẬP DỰ TOÁN CHI PHÍ THÀNH CÔNG" in result

    detail = pd.read_excel(workspace / "du_toan_chi_phi.xlsx", sheet_name="Chi tiết dự toán")
    sprinkler = detail[detail["Mã hiệu"] == "MEP.FF.01"].iloc[0]
    # 10 bộ x (185.000 VT + 75.000 NC + 0 M) = 2.600.000
    assert sprinkler["Thành tiền"] == 2_600_000


def test_boq_summary_follows_vietnamese_cost_structure(workspace):
    takeoff = workspace / "kl.xlsx"
    _write_takeoff(takeoff, [{"STT": 1, "Hạng mục": "SPRINKLER", "Đơn vị": "Bộ", "Khối lượng": 100}])
    calc_boq_cost.invoke({"takeoff_excel_path": "kl.xlsx", "output_excel_path": "dt.xlsx"})

    summary = pd.read_excel(workspace / "dt.xlsx", sheet_name="Tổng hợp")
    values = dict(zip(summary["Khoản mục"], summary["Giá trị (VNĐ)"]))
    direct = values["I"]
    assert direct == 26_000_000
    assert values["II"] == pytest.approx(direct * 0.065, rel=1e-6)                 # chi phí chung
    assert values["III"] == pytest.approx((direct + values["II"]) * 0.055, rel=1e-6)  # TNCTTT
    assert values["IV"] == pytest.approx(direct + values["II"] + values["III"], rel=1e-6)
    assert values["V"] == pytest.approx(values["IV"] * 0.10, rel=1e-6)             # VAT
    assert values["VI"] == pytest.approx(values["IV"] + values["V"], rel=1e-6)


def test_custom_percentages_are_respected(workspace):
    _write_takeoff(workspace / "kl.xlsx", [{"STT": 1, "Hạng mục": "SPRINKLER", "Đơn vị": "Bộ", "Khối lượng": 10}])
    calc_boq_cost.invoke({
        "takeoff_excel_path": "kl.xlsx", "output_excel_path": "dt.xlsx",
        "overhead_percent": 0, "profit_percent": 0, "vat_percent": 8,
    })
    summary = pd.read_excel(workspace / "dt.xlsx", sheet_name="Tổng hợp")
    values = dict(zip(summary["Khoản mục"], summary["Giá trị (VNĐ)"]))
    assert values["II"] == 0 and values["III"] == 0
    assert values["V"] == pytest.approx(values["I"] * 0.08, rel=1e-6)


def test_items_without_a_price_are_flagged_not_silently_dropped(workspace):
    """Hạng mục thiếu đơn giá phải được nêu rõ, vì nếu bỏ qua âm thầm thì tổng dự
    toán sẽ THIẾU tiền mà không ai biết."""
    _write_takeoff(workspace / "kl.xlsx", [
        {"STT": 1, "Hạng mục": "SPRINKLER", "Đơn vị": "Bộ", "Khối lượng": 5},
        {"STT": 2, "Hạng mục": "Thiết bị lạ chưa có giá", "Đơn vị": "Bộ", "Khối lượng": 3},
    ])
    result = calc_boq_cost.invoke({"takeoff_excel_path": "kl.xlsx"})
    assert "CHƯA CÓ ĐƠN GIÁ" in result
    detail = pd.read_excel(workspace / "du_toan_chi_phi.xlsx", sheet_name="Chi tiết dự toán")
    assert len(detail) == 2  # vẫn liệt kê đủ, không bị bỏ dòng


def test_missing_takeoff_file_gives_actionable_message(workspace):
    result = calc_boq_cost.invoke({"takeoff_excel_path": "khong_ton_tai.xlsx"})
    assert "auto_quantity_takeoff" in result


def test_wrong_columns_are_reported(workspace):
    pd.DataFrame([{"Cột lạ": 1}]).to_excel(workspace / "sai.xlsx", index=False)
    result = calc_boq_cost.invoke({"takeoff_excel_path": "sai.xlsx"})
    assert "không có cột" in result


def test_boq_output_stays_inside_the_session_workspace(workspace):
    _write_takeoff(workspace / "kl.xlsx", [{"STT": 1, "Hạng mục": "SPRINKLER", "Đơn vị": "Bộ", "Khối lượng": 1}])
    result = calc_boq_cost.invoke({
        "takeoff_excel_path": "kl.xlsx", "output_excel_path": "../../thoat_ra_ngoai.xlsx",
    })
    assert "ngoài phạm vi làm việc cho phép" in result


def test_lookup_unit_price_finds_and_reports_missing(workspace):
    assert "MEP.FF.01" in lookup_unit_price.invoke({"keyword": "sprinkler"})
    assert "Không tìm thấy đơn giá" in lookup_unit_price.invoke({"keyword": "vật tư không có thật"})
