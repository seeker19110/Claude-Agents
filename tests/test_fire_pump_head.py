"""Bơm chữa cháy phải cho ra CẢ Q và H — chỉ có Q thì không chọn được bơm thật."""
import pytest

from src.ff_tools import HYDRANT_MIN_PRESSURE_BAR, SPRINKLER_MIN_PRESSURE_BAR, calc_fire_pump


def _head(text):
    for line in text.splitlines():
        if "CỘT ÁP BƠM YÊU CẦU" in line:
            return float(line.split(":")[1].replace("m", "").strip())
    raise AssertionError(f"Không tìm thấy cột áp trong:\n{text}")


def test_missing_inputs_warns_instead_of_silently_returning_flow_only():
    result = calc_fire_pump.invoke({"hazard_class": "ordinary"})
    assert "CẢNH BÁO" in result
    assert "CHƯA tính được cột áp" in result


def test_reports_both_flow_and_head_when_inputs_present():
    result = calc_fire_pump.invoke({
        "hazard_class": "ordinary", "static_head_m": 30, "pipe_length_m": 150,
    })
    assert "Lưu lượng Q" in result
    assert "CỘT ÁP BƠM YÊU CẦU" in result
    assert "m3/h" in result


def test_head_increases_with_building_height():
    low = _head(calc_fire_pump.invoke({"static_head_m": 10, "pipe_length_m": 100}))
    high = _head(calc_fire_pump.invoke({"static_head_m": 60, "pipe_length_m": 100}))
    assert high - low == pytest.approx(50.0)


def test_head_increases_with_pipe_length():
    short = _head(calc_fire_pump.invoke({"static_head_m": 20, "pipe_length_m": 50}))
    long = _head(calc_fire_pump.invoke({"static_head_m": 20, "pipe_length_m": 400}))
    assert long > short


def test_hydrant_requires_more_pressure_than_sprinkler():
    assert HYDRANT_MIN_PRESSURE_BAR > SPRINKLER_MIN_PRESSURE_BAR
    sprinkler = _head(calc_fire_pump.invoke({"static_head_m": 20, "pipe_length_m": 100, "has_hydrant": False}))
    hydrant = _head(calc_fire_pump.invoke({"static_head_m": 20, "pipe_length_m": 100, "has_hydrant": True}))
    assert hydrant > sprinkler


def test_flow_scales_with_hazard_class():
    light = calc_fire_pump.invoke({"hazard_class": "light", "static_head_m": 20, "pipe_length_m": 50})
    extra = calc_fire_pump.invoke({"hazard_class": "extra", "static_head_m": 20, "pipe_length_m": 50})
    assert "500 GPM" in light
    assert "1500 GPM" in extra
