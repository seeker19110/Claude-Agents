"""Clash detection hình học giữa các hệ MEPF trên bản vẽ DXF."""
import ezdxf
import pandas as pd
import pytest

from src.bim_tools import _segment_intersection, classify_layer_system, detect_clashes
from src.workspace import set_workspace_dir


@pytest.fixture
def workspace(tmp_path):
    set_workspace_dir(str(tmp_path))
    return tmp_path


def _make_dxf(path, lines):
    doc = ezdxf.new()
    msp = doc.modelspace()
    for layer, start, end in lines:
        doc.layers.add(layer) if layer not in doc.layers else None
        msp.add_line(start, end, dxfattribs={"layer": layer})
    doc.saveas(path)


def test_layer_classification_covers_the_four_systems():
    assert classify_layer_system("HVAC_DUCT_SUPPLY") == "HVAC"
    assert classify_layer_system("ELEC_CABLE_TRAY") == "Điện"
    assert classify_layer_system("PLUMB_WASTE") == "Cấp thoát nước"
    assert classify_layer_system("PCCC_SPRINKLER") == "PCCC"
    assert classify_layer_system("A_WALL") == ""


def test_crossing_segments_intersect():
    point = _segment_intersection((0, 0), (10, 0), (5, -5), (5, 5))
    assert point == (5.0, 0.0)


def test_non_touching_segments_do_not_intersect():
    assert _segment_intersection((0, 0), (10, 0), (0, 5), (10, 5)) is None


def test_parallel_segments_are_not_reported_as_clashes():
    """Hai tuyến chạy song song sát nhau là bố trí bình thường, không phải va chạm."""
    assert _segment_intersection((0, 0), (10, 0), (0, 0), (10, 0)) is None


def test_segments_that_would_cross_only_if_extended_are_ignored():
    assert _segment_intersection((0, 0), (1, 0), (5, -5), (5, 5)) is None


def test_detects_clash_between_two_different_systems(workspace):
    dxf = workspace / "ban_ve.dxf"
    _make_dxf(dxf, [
        ("HVAC_DUCT", (0, 0), (10, 0)),
        ("ELEC_TRAY", (5, -5), (5, 5)),
    ])
    result = detect_clashes.invoke({"file_path": "ban_ve.dxf"})
    assert "PHÁT HIỆN 1 ĐIỂM XUNG ĐỘT" in result

    report = pd.read_excel(workspace / "bao_cao_xung_dot.xlsx")
    assert len(report) == 1
    assert {report.iloc[0]["Hệ 1"], report.iloc[0]["Hệ 2"]} == {"HVAC", "Điện"}
    assert report.iloc[0]["Tọa độ X"] == 5.0


def test_crossings_within_the_same_system_are_not_clashes(workspace):
    """Hai nhánh cùng hệ cắt nhau là chuyện bình thường (rẽ nhánh), không báo động."""
    dxf = workspace / "cung_he.dxf"
    _make_dxf(dxf, [
        ("HVAC_DUCT_1", (0, 0), (10, 0)),
        ("HVAC_DUCT_2", (5, -5), (5, 5)),
    ])
    result = detect_clashes.invoke({"file_path": "cung_he.dxf"})
    assert "KHÔNG phát hiện xung đột" in result


def test_layers_outside_mepf_are_ignored(workspace):
    dxf = workspace / "kien_truc.dxf"
    _make_dxf(dxf, [
        ("A_WALL", (0, 0), (10, 0)),
        ("A_DOOR", (5, -5), (5, 5)),
    ])
    result = detect_clashes.invoke({"file_path": "kien_truc.dxf"})
    assert "Không tìm thấy tuyến nào thuộc các hệ MEPF" in result


def test_report_warns_that_2d_crossing_may_be_valid_at_different_elevation(workspace):
    dxf = workspace / "bv.dxf"
    _make_dxf(dxf, [("PCCC_PIPE", (0, 0), (10, 0)), ("PLUMB_WASTE", (5, -5), (5, 5))])
    result = detect_clashes.invoke({"file_path": "bv.dxf"})
    assert "cao độ" in result


def test_multiple_clashes_are_counted_and_grouped(workspace):
    dxf = workspace / "nhieu.dxf"
    _make_dxf(dxf, [
        ("HVAC_DUCT", (0, 0), (100, 0)),
        ("ELEC_TRAY", (10, -5), (10, 5)),
        ("ELEC_TRAY", (20, -5), (20, 5)),
        ("PCCC_PIPE", (30, -5), (30, 5)),
    ])
    result = detect_clashes.invoke({"file_path": "nhieu.dxf"})
    assert "PHÁT HIỆN 3 ĐIỂM XUNG ĐỘT" in result
    assert "HVAC x Điện: 2" in result


def test_output_path_cannot_escape_the_workspace(workspace):
    dxf = workspace / "bv.dxf"
    _make_dxf(dxf, [("HVAC_DUCT", (0, 0), (10, 0)), ("ELEC_TRAY", (5, -5), (5, 5))])
    result = detect_clashes.invoke({
        "file_path": "bv.dxf", "output_excel_path": "../../ra_ngoai.xlsx",
    })
    assert "ngoài phạm vi làm việc cho phép" in result


# --- Cao độ Z: loại trừ giao điểm mặt bằng nhưng thực ra cách xa nhau theo chiều đứng ---

def _make_dxf_3d(path, lines):
    """`lines`: (layer, (x,y,z), (x,y,z))."""
    doc = ezdxf.new()
    msp = doc.modelspace()
    for layer, start, end in lines:
        if layer not in doc.layers:
            doc.layers.add(layer)
        msp.add_line(start, end, dxfattribs={"layer": layer})
    doc.saveas(path)


def test_clash_is_skipped_when_z_declared_and_far_apart(workspace):
    """Hai tuyến cắt nhau trên mặt bằng nhưng cách nhau 2m theo cao độ không phải xung
    đột thật — trước đây tool luôn báo cần kiểm tra dù có đủ dữ liệu Z để loại trừ."""
    path = workspace / "bv.dxf"
    _make_dxf_3d(path, [
        ("HVAC_DUCT", (0, 0, 3000), (10, 0, 3000)),
        ("ELEC_TRAY", (5, -5, 1000), (5, 5, 1000)),
    ])
    result = detect_clashes.invoke({"file_path": "bv.dxf"})
    assert "KHÔNG phát hiện xung đột" in result
    assert "loại" in result.lower()


def test_clash_is_kept_when_z_declared_and_close(workspace):
    path = workspace / "bv.dxf"
    _make_dxf_3d(path, [
        ("HVAC_DUCT", (0, 0, 3000), (10, 0, 3000)),
        ("ELEC_TRAY", (5, -5, 3050), (5, 5, 3050)),  # chỉ lệch 50mm
    ])
    result = detect_clashes.invoke({"file_path": "bv.dxf"})
    assert "PHÁT HIỆN 1 ĐIỂM XUNG ĐỘT" in result
    assert "Cách nhau" in result


def test_clash_reports_unknown_elevation_honestly_when_no_z_declared(workspace):
    """Bản vẽ hoàn toàn 2D (không khai báo Z) phải nói rõ là chưa biết cao độ, không
    được ngầm coi là an toàn hay ngầm coi là xung đột chắc chắn."""
    path = workspace / "bv.dxf"
    _make_dxf(path, [
        ("HVAC_DUCT", (0, 0), (10, 0)),
        ("ELEC_TRAY", (5, -5), (5, 5)),
    ])
    result = detect_clashes.invoke({"file_path": "bv.dxf"})
    assert "KHÔNG khai báo cao độ" in result
    assert "Chưa rõ cao độ" in result


def test_vertical_clearance_threshold_is_configurable(workspace):
    path = workspace / "bv.dxf"
    _make_dxf_3d(path, [
        ("HVAC_DUCT", (0, 0, 0), (10, 0, 0)),
        ("ELEC_TRAY", (5, -5, 200), (5, 5, 200)),
    ])
    # Ngưỡng là khoảng cách đứng TỐI THIỂU để coi là an toàn: gap=200mm.
    # - Ngưỡng mặc định 150mm <= gap -> loại, không báo xung đột.
    default_result = detect_clashes.invoke({"file_path": "bv.dxf"})
    assert "KHÔNG phát hiện xung đột" in default_result

    # - Ngưỡng cao hơn gap (500mm > 200mm) -> gap chưa đủ an toàn -> vẫn phải báo xung đột.
    strict_result = detect_clashes.invoke({"file_path": "bv.dxf", "min_vertical_clearance": 500})
    assert "PHÁT HIỆN 1 ĐIỂM XUNG ĐỘT" in strict_result

    # - Ngưỡng thấp hơn gap (50mm < 200mm) -> gap đủ an toàn -> loại, không báo xung đột.
    lenient_result = detect_clashes.invoke({"file_path": "bv.dxf", "min_vertical_clearance": 50})
    assert "KHÔNG phát hiện xung đột" in lenient_result


# --- Cung cong (ARC) trong clash detection ---

def test_clash_detects_intersection_with_arc_entity(workspace):
    doc = ezdxf.new()
    msp = doc.modelspace()
    doc.layers.add("HVAC_DUCT")
    doc.layers.add("ELEC_TRAY")
    msp.add_arc(center=(0, 0), radius=10, start_angle=0, end_angle=180, dxfattribs={"layer": "HVAC_DUCT"})
    msp.add_line((0, -20), (0, 20), dxfattribs={"layer": "ELEC_TRAY"})
    doc.saveas(workspace / "bv.dxf")

    result = detect_clashes.invoke({"file_path": "bv.dxf"})
    assert "PHÁT HIỆN" in result
