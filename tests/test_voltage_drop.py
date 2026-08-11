"""Chọn cáp phải kiểm tra sụt áp theo chiều dài tuyến (TCVN 9206 / IEC 60364-5-52)."""
from src.elec_tools import (
    STANDARD_CABLE_SIZES, VOLTAGE_DROP_LIMIT_LIGHTING, VOLTAGE_DROP_LIMIT_POWER,
    _voltage_drop_percent, calc_cable_size, calc_voltage_drop,
)


def _num(text, prefix):
    """Lấy số ngay sau một nhãn trong báo cáo văn bản."""
    for line in text.splitlines():
        if prefix in line:
            return line
    raise AssertionError(f"Không thấy dòng chứa {prefix!r} trong:\n{text}")


def test_voltage_drop_grows_with_length_and_shrinks_with_section():
    base = _voltage_drop_percent(50, 100, 25, 380, 3, 0.85)
    assert _voltage_drop_percent(50, 200, 25, 380, 3, 0.85) > base
    assert _voltage_drop_percent(50, 100, 50, 380, 3, 0.85) < base


def test_zero_length_has_no_drop():
    assert _voltage_drop_percent(50, 0, 25, 380, 3, 0.85) == 0.0


def test_single_phase_drop_is_larger_than_three_phase():
    """1 pha có dòng đi và về (hệ số 2) nên sụt áp lớn hơn 3 pha (hệ số sqrt(3))."""
    three = _voltage_drop_percent(30, 80, 10, 380, 3, 0.85)
    single = _voltage_drop_percent(30, 80, 10, 380, 1, 0.85)
    assert single > three


def test_calc_voltage_drop_flags_failure_on_long_run():
    result = calc_voltage_drop.invoke({
        "current_a": 100, "length_m": 250, "section_mm2": 25, "voltage": 380, "phase": 3,
    })
    assert "KHÔNG ĐẠT" in result


def test_calc_voltage_drop_passes_on_short_run():
    result = calc_voltage_drop.invoke({
        "current_a": 20, "length_m": 15, "section_mm2": 10, "voltage": 380, "phase": 3,
    })
    assert "Kết luận: ĐẠT" in result


def test_lighting_limit_is_stricter_than_power():
    assert VOLTAGE_DROP_LIMIT_LIGHTING < VOLTAGE_DROP_LIMIT_POWER
    args = {"current_a": 25, "length_m": 120, "section_mm2": 10, "voltage": 380, "phase": 3}
    power = calc_voltage_drop.invoke({**args, "circuit_type": "power"})
    lighting = calc_voltage_drop.invoke({**args, "circuit_type": "lighting"})
    # Cùng một tuyến có thể đạt cho động lực nhưng trượt cho chiếu sáng.
    assert "5.0 %" in power and "3.0 %" in lighting


def test_cable_size_warns_when_length_missing():
    """Không có chiều dài thì phải NÓI RÕ là chưa kiểm tra sụt áp, không im lặng."""
    result = calc_cable_size.invoke({"power_kw": 50})
    assert "CẢNH BÁO" in result
    assert "sụt áp" in result


def test_long_run_forces_larger_cable_than_current_alone():
    """Regression cho lỗi kỹ thuật gốc: chọn cáp chỉ theo dòng điện sẽ ra tiết diện
    thiếu với tuyến dài, vì ràng buộc quyết định lúc đó là sụt áp chứ không phải phát nóng."""
    short = calc_cable_size.invoke({"power_kw": 50, "length_m": 10})
    long = calc_cable_size.invoke({"power_kw": 50, "length_m": 300})

    def selected(text):
        line = _num(text, "Đề xuất cáp")
        return float(line.split(":")[1].split("mm2")[0].strip())

    assert selected(long) > selected(short)
    assert "PHẢI TĂNG TIẾT DIỆN" in long


def test_selected_cable_always_within_standard_sizes():
    result = calc_cable_size.invoke({"power_kw": 30, "length_m": 120})
    line = _num(result, "Đề xuất cáp")
    value = float(line.split(":")[1].split("mm2")[0].strip())
    assert value in STANDARD_CABLE_SIZES


def test_final_cable_actually_satisfies_the_limit():
    result = calc_cable_size.invoke({"power_kw": 20, "length_m": 150})
    assert "ĐẠT" in _num(result, "Đề xuất cáp")
