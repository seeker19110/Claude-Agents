"""Kiểm tra xung đột (Clash Detection) giữa các hệ MEPF trên bản vẽ DXF/DWG.

Prompt của `bim_agent_node` từ trước tới nay vẫn tuyên bố BIM Agent "kiểm tra xung đột",
nhưng KHÔNG hề có tool nào làm việc đó — nghĩa là agent chỉ có thể nói suông. Module này
bù đúng khoảng trống ấy bằng thuật toán hình học thuần (giao điểm đoạn thẳng, cung được
rời rạc hóa), không cần LLM suy luận, nên chạy tốt cả với model yếu/offline.

Phạm vi: chồng nhiều bản vẽ MEPF mặt bằng vốn KHÔNG có cao độ Z thật (bản vẽ 2D thuần)
là trường hợp phổ biến nhất — tool vẫn đọc cao độ Z nếu entity có khai báo (LINE 3D,
polyline có `elevation`) và dùng để LOẠI những giao điểm rõ ràng cách nhau đủ xa theo
chiều đứng (không phải xung đột thật). Khi cả hai tuyến đều không khai báo Z (Z=0 mặc
định), tool trung thực báo "chưa rõ cao độ, cần kiểm tra thủ công" thay vì kết luận thay
kỹ sư — đây là giới hạn thật của dữ liệu 2D, không phải lỗi của tool.
"""
import logging
import math
import os

import pandas as pd
from langchain_core.tools import tool

from src import cad_geometry
from src import cad_loader
from src.workspace import resolve_safe_path

logger = logging.getLogger(__name__)

# Nhận diện hệ kỹ thuật từ tên Layer. Khớp theo thứ tự, từ khóa đặc thù đứng trước.
SYSTEM_KEYWORDS = [
    ("PCCC", ("pccc", "fire", "sprinkler", "ff_", "-ff", "chua chay", "hydrant")),
    ("HVAC", ("hvac", "duct", "gio", "air", "me_", "-me", "chiller", "fcu", "refrigerant")),
    ("Điện", ("elec", "dien", "power", "cable", "tray", "el_", "-el", "light", "lighting")),
    ("Cấp thoát nước", ("plumb", "nuoc", "water", "drain", "waste", "pl_", "-pl", "upvc", "ppr")),
]

# Khoảng cách đứng tối thiểu (đơn vị bản vẽ, thường mm) để coi hai tuyến CÁCH XA nhau
# theo cao độ là không xung đột thật, dù cắt nhau trên mặt bằng. Mặc định 150mm — nhỏ
# hơn khe hở lắp đặt tối thiểu giữa hai tuyến MEPF trong thực tế.
DEFAULT_MIN_VERTICAL_CLEARANCE = 150.0


def classify_layer_system(layer_name: str) -> str:
    """Suy ra hệ kỹ thuật ('HVAC', 'Điện', ...) từ tên layer; '' nếu không nhận ra."""
    name = (layer_name or "").lower()
    for system, keywords in SYSTEM_KEYWORDS:
        if any(kw in name for kw in keywords):
            return system
    return ""


def _segment_intersection(a1, a2, b1, b2):
    """Giao điểm của hai đoạn thẳng 2D, hoặc None nếu không cắt nhau.

    Dùng tham số hóa chuẩn: p + t*r và q + u*s, xung đột thật sự khi 0<=t<=1 và 0<=u<=1.
    Hai đoạn song song/trùng nhau được coi là KHÔNG xung đột (chúng chạy dọc nhau, không
    cắt qua nhau) để tránh báo động giả tràn lan trên các tuyến đi song song.
    """
    (x1, y1), (x2, y2) = a1, a2
    (x3, y3), (x4, y4) = b1, b2
    rx, ry = x2 - x1, y2 - y1
    sx, sy = x4 - x3, y4 - y3
    denom = rx * sy - ry * sx
    if abs(denom) < 1e-12:
        return None
    qpx, qpy = x3 - x1, y3 - y1
    t = (qpx * sy - qpy * sx) / denom
    u = (qpx * ry - qpy * rx) / denom
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return (x1 + t * rx, y1 + t * ry)
    return None


def _z_at(z1, z2, t):
    return z1 + (z2 - z1) * t


def _segment_z_range(a1, a2, t):
    """Xấp xỉ cao độ tại điểm giao (nội suy tuyến tính theo tham số t dọc đoạn thẳng)."""
    return _z_at(a1[2], a2[2], t)


def _extract_segments(msp):
    """Mọi đoạn (kể cả cung đã rời rạc hóa) của bản vẽ kèm layer, hệ kỹ thuật và Z."""
    segments = []
    for entity in msp:
        layer = entity.dxf.layer
        system = classify_layer_system(layer)
        if not system:
            continue
        points = cad_geometry.entity_points_3d(entity)
        for i in range(1, len(points)):
            segments.append((system, layer, points[i - 1], points[i]))
    return segments


def _has_declared_elevation(points_3d) -> bool:
    """Bản vẽ có thật sự khai báo cao độ Z hay không (không chỉ toàn số 0 mặc định)."""
    return any(abs(p[2]) > 1e-9 for p in points_3d)


@tool
def detect_clashes(file_path: str, output_excel_path: str = "bao_cao_xung_dot.xlsx",
                   min_vertical_clearance: float = DEFAULT_MIN_VERTICAL_CLEARANCE) -> str:
    """Kiểm tra XUNG ĐỘT (clash detection) giữa các hệ MEPF trên bản vẽ CAD (.dxf/.dwg).

    Quét toàn bộ tuyến ống/gió/cáp (kể cả đoạn cong ARC/bulge), phân loại theo hệ dựa
    trên tên Layer (HVAC, Điện, Cấp thoát nước, PCCC) và tìm mọi điểm hai hệ KHÁC NHAU
    cắt nhau trên mặt bằng, rồi xuất danh sách tọa độ xung đột ra file Excel. Nếu bản vẽ
    có khai báo cao độ Z thật (LINE 3D, polyline có `elevation`), tool dùng Z để LOẠI các
    giao điểm mà hai tuyến thực ra cách nhau đủ xa theo chiều đứng — không phải xung đột
    thật. Thuần hình học, không cần LLM suy luận. Dùng khi khách hàng yêu cầu "kiểm tra
    xung đột", "clash", "va chạm giữa các hệ".
    """
    logger.info("Detecting clashes: %s", file_path)
    try:
        doc, load_notes = cad_loader.load_drawing(file_path)
        segments = _extract_segments(doc.modelspace())

        base_dir = os.path.dirname(resolve_safe_path(file_path))
        xref_segs_raw, xref_notes = cad_loader.resolve_xref_segments(
            doc, base_dir,
            lambda space: [
                {"layer": layer, "start": s, "end": e, "length": 0, "is_arc": False}
                for entity in list(space)
                for (layer, s, e) in (
                    (entity.dxf.layer, points[i - 1], points[i])
                    for points in [cad_geometry.entity_points_3d(entity)]
                    for i in range(1, len(points))
                ) if classify_layer_system(layer)
            ],
        )
        for seg in xref_segs_raw:
            system = classify_layer_system(seg["layer"])
            if system:
                segments.append((system, seg["layer"], seg["start"], seg["end"]))
        load_notes.extend(xref_notes)

        if not segments:
            return ("Không tìm thấy tuyến nào thuộc các hệ MEPF trong bản vẽ (dựa trên tên Layer). "
                    "Hãy đặt tên Layer theo quy ước có chứa từ khóa hệ (VD: 'HVAC_DUCT', 'ELEC_TRAY', "
                    "'PCCC_SPRINKLER', 'PLUMB_WASTE') rồi kiểm tra lại.")

        has_any_elevation = any(_has_declared_elevation([a, b]) for _, _, a, b in segments)

        clashes = []
        seen = set()
        skipped_by_elevation = 0
        for i in range(len(segments)):
            sys_a, layer_a, a1, a2 = segments[i]
            for j in range(i + 1, len(segments)):
                sys_b, layer_b, b1, b2 = segments[j]
                if sys_a == sys_b:
                    continue  # xung đột trong cùng một hệ là chuyện bình thường (nhánh rẽ)
                point = _segment_intersection((a1[0], a1[1]), (a2[0], a2[1]), (b1[0], b1[1]), (b2[0], b2[1]))
                if point is None:
                    continue

                # Có khai báo Z thật thì dùng để loại giao điểm cách xa nhau theo chiều đứng.
                z_gap = None
                if has_any_elevation:
                    l2a = (a2[0] - a1[0]) ** 2 + (a2[1] - a1[1]) ** 2
                    l2b = (b2[0] - b1[0]) ** 2 + (b2[1] - b1[1]) ** 2
                    ta = (((point[0] - a1[0]) * (a2[0] - a1[0]) + (point[1] - a1[1]) * (a2[1] - a1[1])) / l2a
                         if l2a > 0 else 0.0)
                    tb = (((point[0] - b1[0]) * (b2[0] - b1[0]) + (point[1] - b1[1]) * (b2[1] - b1[1])) / l2b
                         if l2b > 0 else 0.0)
                    z_a = _segment_z_range(a1, a2, ta)
                    z_b = _segment_z_range(b1, b2, tb)
                    z_gap = abs(z_a - z_b)
                    if z_gap >= min_vertical_clearance:
                        skipped_by_elevation += 1
                        continue

                key = (round(point[0], 3), round(point[1], 3), tuple(sorted((sys_a, sys_b))))
                if key in seen:
                    continue
                seen.add(key)
                muc_do = (f"Cách nhau {z_gap:.0f}mm theo cao độ — CẦN kiểm tra (dưới khe hở tối thiểu)"
                         if z_gap is not None else "Chưa rõ cao độ (bản vẽ không khai báo Z) — cần kiểm tra thủ công")
                clashes.append({
                    "STT": len(clashes) + 1,
                    "Hệ 1": sys_a, "Layer 1": layer_a,
                    "Hệ 2": sys_b, "Layer 2": layer_b,
                    "Tọa độ X": round(point[0], 2), "Tọa độ Y": round(point[1], 2),
                    "Mức độ": muc_do,
                })

        if not clashes:
            systems = sorted({s for s, _, _, _ in segments})
            extra = f" ({skipped_by_elevation} giao điểm mặt bằng đã loại vì cách xa theo cao độ.)" if skipped_by_elevation else ""
            return (f"KHÔNG phát hiện xung đột giữa các hệ. "
                    f"Đã quét {len(segments)} đoạn tuyến thuộc {len(systems)} hệ: {', '.join(systems)}.{extra}")

        out_path = output_excel_path if output_excel_path.endswith(".xlsx") else output_excel_path + ".xlsx"
        out_safe = resolve_safe_path(out_path)
        parent = os.path.dirname(out_safe)
        if parent:
            os.makedirs(parent, exist_ok=True)
        pd.DataFrame(clashes).to_excel(out_safe, index=False)

        by_pair = {}
        for c in clashes:
            pair = f"{c['Hệ 1']} x {c['Hệ 2']}"
            by_pair[pair] = by_pair.get(pair, 0) + 1

        report = [
            f"PHÁT HIỆN {len(clashes)} ĐIỂM XUNG ĐỘT giữa các hệ MEPF (đã ghi file: {out_path}).",
            f"- Đã quét {len(segments)} đoạn tuyến.",
        ]
        for note in load_notes:
            report.append(f"- {note}")
        if has_any_elevation:
            report.append(f"- Bản vẽ có khai báo cao độ Z: đã loại {skipped_by_elevation} giao điểm mặt bằng "
                          f"cách nhau >= {min_vertical_clearance:.0f}mm theo chiều đứng (không phải xung đột thật).")
        else:
            report.append("- Bản vẽ KHÔNG khai báo cao độ Z (thuần 2D) — mọi giao điểm dưới đây "
                          "đều cần kỹ sư đối chiếu cao độ lắp đặt thủ công.")
        report.append("- Thống kê theo cặp hệ:")
        for pair, count in sorted(by_pair.items(), key=lambda x: -x[1]):
            report.append(f"  + {pair}: {count} điểm")
        report.append("- Chi tiết 10 điểm đầu:")
        for c in clashes[:10]:
            report.append(f"  {c['STT']}. {c['Hệ 1']} ({c['Layer 1']}) x {c['Hệ 2']} ({c['Layer 2']}) "
                          f"tại (X={c['Tọa độ X']}, Y={c['Tọa độ Y']}) — {c['Mức độ']}")
        if len(clashes) > 10:
            report.append(f"  ... và {len(clashes) - 10} điểm khác trong file Excel.")
        return "\n".join(report)
    except Exception as e:
        return f"Lỗi kiểm tra xung đột: {e}"


@tool
def read_ifc_model(file_path: str, output_excel_path: str = "ifc_report.xlsx") -> str:
    """Đọc thông tin từ mô hình 3D BIM định dạng IFC (.ifc) sử dụng thư viện ifcopenshell.

    Trích xuất danh sách các đối tượng thiết bị, ống, cáp (BuildingElement) và các thuộc tính cơ bản
    để xuất ra file Excel. Dùng cho nhiệm vụ bóc tách khối lượng hoặc phân tích dữ liệu từ mô hình 3D.
    """
    logger.info("Reading IFC model: %s", file_path)
    try:
        import ifcopenshell
        safe_path = resolve_safe_path(file_path)
        if not os.path.exists(safe_path):
            return f"Không tìm thấy file: {file_path}"

        model = ifcopenshell.open(safe_path)

        data = []
        # Lấy các loại entity thường dùng trong MEPF
        entities = model.by_type("IfcBuildingElement") + model.by_type("IfcDistributionElement")

        if not entities:
            return "Không tìm thấy thiết bị hoặc đường ống MEPF nào (IfcBuildingElement/IfcDistributionElement) trong file IFC."

        for entity in entities:
            guid = entity.GlobalId
            name = entity.Name or ""
            entity_type = entity.is_a()

            # Extract quantites if available
            length = ""
            area = ""
            volume = ""
            # Một số thuộc tính cơ bản
            properties = {}
            for relDefinesByProperties in entity.IsDefinedBy:
                if relDefinesByProperties.is_a("IfcRelDefinesByProperties"):
                    propSet = relDefinesByProperties.RelatingPropertyDefinition
                    if propSet.is_a("IfcPropertySet"):
                        for prop in propSet.HasProperties:
                            if prop.is_a("IfcPropertySingleValue"):
                                properties[prop.Name] = prop.NominalValue.wrappedValue if prop.NominalValue else ""

            data.append({
                "Loại (Type)": entity_type,
                "Tên (Name)": name,
                "GUID": guid,
                "Thuộc tính cơ bản": str(properties)[:200] if properties else ""
            })

        out_path = output_excel_path if output_excel_path.endswith(".xlsx") else output_excel_path + ".xlsx"
        out_safe = resolve_safe_path(out_path)
        parent = os.path.dirname(out_safe)
        if parent:
            os.makedirs(parent, exist_ok=True)

        df = pd.DataFrame(data)
        df.to_excel(out_safe, index=False)

        return f"Đã đọc thành công mô hình IFC. Tổng số đối tượng tìm thấy: {len(data)}. Dữ liệu chi tiết đã xuất ra file {out_path}."

    except ImportError:
        return "Thiếu thư viện ifcopenshell. Hãy cài đặt ifcopenshell để đọc file IFC."
    except Exception as e:
        return f"Lỗi đọc file IFC: {e}"
