"""Các tool MEPF bổ sung ở đợt hoàn tất backlog: NC, phụ tải, ngắn mạch, máng cáp,
chống sét, bảng tủ điện, thủy lực sprinkler, standpipe, kiểm soát khói, đầu báo cháy."""
import json

import pandas as pd
import pytest

from src.elec_tools import (
    DIVERSITY_FACTORS, calc_cable_tray_size, calc_lightning_protection,
    calc_short_circuit, calc_total_load,
)
from src.ff_tools import (
    calc_fire_detector_qty, calc_smoke_control, calc_sprinkler_hydraulics, calc_standpipe,
)
from src.hvac_tools import NC_RECOMMENDED, calc_nc_level
from src.panel_schedule import build_panel_rows, generate_panel_schedule
from src.workspace import set_workspace_dir


# --- HVAC: NC level ---

def test_nc_fails_for_quiet_room_and_passes_for_workshop():
    args = {"sound_power_lw": 60, "room_volume_m3": 120}
    assert "KHÔNG ĐẠT" in calc_nc_level.invoke({**args, "space_type": "studio"})
    assert "ĐẠT yêu cầu" in calc_nc_level.invoke({**args, "space_type": "xuong"})


def test_nc_rises_with_more_identical_sources():
    def nc(n):
        text = calc_nc_level.invoke({"sound_power_lw": 60, "room_volume_m3": 100, "num_sources": n})
        line = next(l for l in text.splitlines() if "NC ước tính" in l)
        return float(line.split("NC-")[1])

    assert nc(4) > nc(1)


def test_attenuation_reduces_nc():
    base = calc_nc_level.invoke({"sound_power_lw": 70, "room_volume_m3": 100})
    damped = calc_nc_level.invoke({"sound_power_lw": 70, "room_volume_m3": 100, "duct_attenuation_db": 15})
    assert "KHÔNG ĐẠT" in base and "ĐẠT" in damped


def test_unknown_space_type_says_so_instead_of_silently_defaulting():
    result = calc_nc_level.invoke({"sound_power_lw": 50, "room_volume_m3": 100, "space_type": "phong_la"})
    assert "không nhận diện được" in result


def test_quiet_rooms_have_stricter_limits_than_public_areas():
    assert NC_RECOMMENDED["studio"][1] < NC_RECOMMENDED["phong_ngu"][1] < NC_RECOMMENDED["xuong"][1]


def test_invalid_volume_is_rejected():
    assert "Lỗi" in calc_nc_level.invoke({"sound_power_lw": 60, "room_volume_m3": 0})


# --- Điện: tổng hợp phụ tải ---

def _loads(*pairs):
    return json.dumps([{"ten": n, "loai": k, "cong_suat_kw": p} for n, k, p in pairs], ensure_ascii=False)


def test_diversity_factor_reduces_calculated_load_below_installed():
    result = calc_total_load.invoke({"loads_json": _loads(("Ổ cắm", "o_cam", 100))})
    assert "50.0 kW" in result       # 100 kW x Kđt 0.5
    assert DIVERSITY_FACTORS["o_cam"] == 0.5


def test_transformer_choice_comes_from_the_standard_range():
    result = calc_total_load.invoke({"loads_json": _loads(("Điều hòa", "dieu_hoa", 300))})
    line = next(l for l in result.splitlines() if "CHỌN MÁY BIẾN ÁP" in l)
    assert int(line.split(":")[1].replace("kVA", "").strip()) in [100, 160, 250, 400, 560, 630, 750, 800, 1000, 1250, 1600, 2000, 2500]


def test_unknown_load_type_falls_back_to_generic_factor():
    result = calc_total_load.invoke({"loads_json": _loads(("Lạ", "khong_biet", 100))})
    assert f"Kđt {DIVERSITY_FACTORS['khac']}" in result


def test_malformed_load_json_gives_a_usable_error():
    assert "Lỗi đọc JSON" in calc_total_load.invoke({"loads_json": "{khong phai json}"})


def test_empty_load_list_is_rejected():
    assert "không được rỗng" in calc_total_load.invoke({"loads_json": "[]"})


# --- Điện: ngắn mạch ---

def test_short_circuit_scales_with_transformer_size():
    def isc(kva):
        text = calc_short_circuit.invoke({"transformer_kva": kva})
        return float(next(l for l in text.splitlines() if "thanh cái tổng" in l).split(":")[1].replace("kA", ""))

    assert isc(2000) > isc(400)


def test_fault_current_decays_along_the_cable():
    result = calc_short_circuit.invoke({
        "transformer_kva": 1000, "cable_length_m": 100, "cable_section_mm2": 50,
    })
    main = float(next(l for l in result.splitlines() if "thanh cái tổng" in l).split(":")[1].replace("kA", ""))
    end = float(next(l for l in result.splitlines() if "cuối tuyến:" in l).split(":")[1].replace("kA", ""))
    assert end < main
    assert "PHỐI HỢP BẢO VỆ" in result


def test_short_circuit_without_cable_data_asks_for_it():
    result = calc_short_circuit.invoke({"transformer_kva": 1000})
    assert "cable_length_m" in result


def test_invalid_transformer_input_rejected():
    assert "Lỗi" in calc_short_circuit.invoke({"transformer_kva": 0})


# --- Điện: máng cáp ---

def test_tray_grows_with_more_cables():
    def area(qty):
        text = calc_cable_tray_size.invoke({
            "cables_json": json.dumps([{"ten": "Cáp", "duong_kinh_mm": 20, "so_luong": qty}]),
        })
        line = next(l for l in text.splitlines() if "CHỌN MÁNG CÁP" in l)
        w, h = line.split(":")[1].split("(")[0].strip().replace(" mm", "").split(" x ")
        return int(w) * int(h)

    assert area(30) > area(4)


def test_tray_report_includes_conduit_alternative_and_separation_note():
    result = calc_cable_tray_size.invoke({
        "cables_json": json.dumps([{"ten": "Cáp", "duong_kinh_mm": 18, "so_luong": 6}]),
    })
    assert "ỐNG LUỒN DÂY" in result
    assert "tín hiệu" in result


def test_tray_rejects_bad_json():
    assert "Lỗi đọc JSON" in calc_cable_tray_size.invoke({"cables_json": "khong-phai-json"})


# --- Điện: chống sét & tiếp địa ---

def test_protection_radius_grows_with_rod_height():
    def radius(h):
        text = calc_lightning_protection.invoke({"length_m": 40, "width_m": 20, "height_m": h})
        return float(next(l for l in text.splitlines() if "Bán kính bảo vệ" in l).split(":")[1].replace("m", ""))

    assert radius(20) > radius(5)


def test_poor_soil_requires_more_grounding_rods():
    def rods(rho):
        text = calc_lightning_protection.invoke({
            "length_m": 40, "width_m": 20, "height_m": 15, "soil_resistivity": rho,
        })
        return int(next(l for l in text.splitlines() if "Số cọc tiếp địa" in l).split(":")[1].split("cọc")[0])

    assert rods(1000) > rods(50)


def test_stricter_protection_level_needs_more_air_terminals():
    def count(level):
        text = calc_lightning_protection.invoke({
            "length_m": 80, "width_m": 60, "height_m": 30, "protection_level": level,
        })
        return int(next(l for l in text.splitlines() if "Số kim thu sét" in l).split(":")[1].split("kim")[0])

    assert count("I") >= count("IV")


def test_lightning_report_insists_on_field_measurement():
    result = calc_lightning_protection.invoke({"length_m": 30, "width_m": 20, "height_m": 12})
    assert "ĐO điện trở nối đất thực tế" in result


def test_unknown_protection_level_is_flagged():
    result = calc_lightning_protection.invoke({
        "length_m": 30, "width_m": 20, "height_m": 12, "protection_level": "Z",
    })
    assert "không nhận diện được" in result


# --- Điện: bảng tủ điện ---

@pytest.fixture
def workspace(tmp_path):
    set_workspace_dir(str(tmp_path))
    return tmp_path


CIRCUITS = [
    {"ten": "Chiếu sáng T1", "cong_suat_kw": 8, "so_pha": 3, "chieu_dai_m": 45, "loai": "lighting"},
    {"ten": "Ổ cắm T1", "cong_suat_kw": 15, "so_pha": 3, "chieu_dai_m": 30},
    {"ten": "Điều hòa", "cong_suat_kw": 60, "so_pha": 3, "chieu_dai_m": 80},
]


def test_panel_rows_size_breaker_above_working_current():
    for row in build_panel_rows(CIRCUITS):
        assert row["Aptomat (A)"] >= row["Dòng tính toán (A)"]


def test_panel_rows_respect_voltage_drop_limits():
    for row in build_panel_rows(CIRCUITS):
        assert row["Sụt áp (%)"] <= 5.0


def test_circuit_without_length_is_flagged_not_silently_passed():
    rows = build_panel_rows([{"ten": "Chưa rõ", "cong_suat_kw": 10, "so_pha": 3}])
    assert rows[0]["Sụt áp (%)"] is None
    assert "chưa kiểm tra sụt áp" in rows[0]["Ghi chú"]


def test_panel_schedule_writes_excel_and_dxf(workspace):
    result = generate_panel_schedule.invoke({"circuits_json": json.dumps(CIRCUITS, ensure_ascii=False)})
    assert "LẬP BẢNG TỦ ĐIỆN THÀNH CÔNG" in result
    assert (workspace / "bang_tu_dien.xlsx").exists()
    assert (workspace / "so_do_nguyen_ly.dxf").exists()

    detail = pd.read_excel(workspace / "bang_tu_dien.xlsx", sheet_name="Bảng tủ điện")
    assert len(detail) == len(CIRCUITS)


def test_main_breaker_reflects_diversity_factor(workspace):
    full = generate_panel_schedule.invoke({
        "circuits_json": json.dumps(CIRCUITS, ensure_ascii=False), "diversity_factor": 1.0,
    })
    diversified = generate_panel_schedule.invoke({
        "circuits_json": json.dumps(CIRCUITS, ensure_ascii=False), "diversity_factor": 0.5,
    })

    def main(text):
        return int(next(l for l in text.splitlines() if "APTOMAT TỔNG" in l).split("APTOMAT TỔNG")[1].split("A,")[0])

    assert main(diversified) < main(full)


def test_panel_schedule_rejects_empty_circuit_list(workspace):
    assert "không được rỗng" in generate_panel_schedule.invoke({"circuits_json": "[]"})


def test_panel_output_cannot_escape_workspace(workspace):
    result = generate_panel_schedule.invoke({
        "circuits_json": json.dumps(CIRCUITS, ensure_ascii=False),
        "output_excel_path": "../../ra_ngoai.xlsx",
    })
    assert "ngoài phạm vi làm việc cho phép" in result


# --- PCCC: thủy lực sprinkler ---

def test_hydraulic_total_exceeds_naive_multiplication():
    """Đầu gần nguồn chịu áp cao hơn nên phun nhiều nước hơn — tổng lưu lượng thật lớn
    hơn phép nhân (số đầu x lưu lượng một đầu)."""
    result = calc_sprinkler_hydraulics.invoke({
        "hazard_class": "ordinary", "num_sprinklers": 10, "pipe_diameter_mm": 32,
    })
    total = float(next(l for l in result.splitlines() if "TỔNG LƯU LƯỢNG" in l).split("=")[1].replace("l/s", ""))
    naive = 10 * 80 * (0.5 ** 0.5) / 60
    assert total > naive


def test_pressure_increases_toward_the_source():
    result = calc_sprinkler_hydraulics.invoke({"hazard_class": "ordinary", "num_sprinklers": 5})
    pressures = [float(l.split("áp ")[1].split(" bar")[0]) for l in result.splitlines() if l.strip().startswith("Đầu ")]
    assert pressures == sorted(pressures)


def test_sprinkler_count_defaults_to_standard_when_not_given():
    result = calc_sprinkler_hydraulics.invoke({"hazard_class": "ordinary"})
    assert "Số đầu phun trong diện tích tính toán: 27 đầu" in result  # ceil(240 / 9)


def test_hydraulics_reports_pump_inputs():
    result = calc_sprinkler_hydraulics.invoke({"hazard_class": "light", "num_sprinklers": 6})
    assert "calc_fire_pump" in result


def test_zero_pipe_diameter_rejected():
    assert "Lỗi" in calc_sprinkler_hydraulics.invoke({"num_sprinklers": 4, "pipe_diameter_mm": 0})


# --- PCCC: họng nước vách tường ---

def test_standpipe_head_grows_with_building_height():
    def head(floors):
        text = calc_standpipe.invoke({"num_floors": floors})
        line = next(l for l in text.splitlines() if l.startswith("=> CỘT ÁP YÊU CẦU"))
        return float(line.split(":")[1].strip().rstrip("m").strip())

    assert head(25) > head(5)


def test_standpipe_flow_uses_simultaneous_hydrants_not_total():
    result = calc_standpipe.invoke({"num_floors": 10, "num_hydrants_per_floor": 4, "simultaneous_hydrants": 2})
    assert "Tổng số họng: 40" in result
    assert "Lưu lượng tính toán: 5.0 l/s" in result


def test_standpipe_warns_about_pressure_zoning_for_tall_buildings():
    assert "van giảm áp" in calc_standpipe.invoke({"num_floors": 20})


def test_standpipe_rejects_zero_floors():
    assert "Lỗi" in calc_standpipe.invoke({"num_floors": 0})


# --- PCCC: kiểm soát khói ---

def test_pressurization_flow_grows_with_open_doors():
    def flow(doors):
        text = calc_smoke_control.invoke({
            "area_m2": 200, "height_m": 3, "system_type": "tang_ap", "num_doors": doors,
        })
        line = next(l for l in text.splitlines() if "LƯU LƯỢNG QUẠT TĂNG ÁP" in l)
        return float(line.split(":")[1].split("m3/s")[0].strip())

    assert flow(4) > flow(1)


def test_pressurization_warns_about_door_opening_force():
    result = calc_smoke_control.invoke({"area_m2": 200, "height_m": 3, "system_type": "tang_ap"})
    assert "van xả áp" in result
    assert "50 Pa" in result


def test_smoke_extraction_scales_with_volume_and_needs_make_up_air():
    result = calc_smoke_control.invoke({"area_m2": 300, "height_m": 3})
    assert "9000 m3/h" in result       # 300 x 3 x 10 ACH
    assert "GIÓ BÙ" in result


def test_smoke_fan_temperature_rating_is_stated():
    assert "400°C" in calc_smoke_control.invoke({"area_m2": 100, "height_m": 3})


# --- PCCC: đầu báo cháy ---

def test_heat_detectors_are_denser_than_smoke_detectors():
    args = {"area_m2": 500, "height_m": 3}

    def qty(kind):
        text = calc_fire_detector_qty.invoke({**args, "detector_type": kind})
        return int(next(l for l in text.splitlines() if "SỐ LƯỢNG" in l).split(":")[1].split("đầu")[0])

    assert qty("nhiet") > qty("khoi")


def test_higher_ceiling_needs_more_detectors():
    def qty(h):
        text = calc_fire_detector_qty.invoke({"area_m2": 600, "height_m": h})
        return int(next(l for l in text.splitlines() if "SỐ LƯỢNG" in l).split(":")[1].split("đầu")[0])

    assert qty(11) > qty(3)


def test_very_high_ceiling_warns_point_detectors_are_ineffective():
    result = calc_fire_detector_qty.invoke({"area_m2": 800, "height_m": 15})
    assert "CẢNH BÁO" in result
    assert "aspirating" in result


def test_detector_report_mentions_diffuser_clearance():
    assert "miệng gió" in calc_fire_detector_qty.invoke({"area_m2": 100})


def test_tiny_room_still_gets_one_detector():
    result = calc_fire_detector_qty.invoke({"area_m2": 4})
    assert "SỐ LƯỢNG CẦN THIẾT: 1 đầu" in result
