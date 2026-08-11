"""Kiểm tra xung đột (Clash Detection) giữa các hệ MEPF trên bản vẽ DXF.

Prompt của `bim_agent_node` từ trước tới nay vẫn tuyên bố BIM Agent "kiểm tra xung đột",
nhưng KHÔNG hề có tool nào làm việc đó — nghĩa là agent chỉ có thể nói suông. Module này
bù đúng khoảng trống ấy bằng thuật toán hình học thuần (giao điểm đoạn thẳng 2D), không
cần LLM suy luận, nên chạy tốt cả với model yếu/offline.

Phạm vi: xung đột mặt bằng 2D giữa các tuyến (LINE/LWPOLYLINE/POLYLINE) thuộc HAI HỆ
KHÁC NHAU. Đây là loại va chạm phổ biến nhất khi chồng bản vẽ MEPF, và cũng là giới hạn
trung thực của dữ liệu DXF 2D: cao độ (elevation) thường không có trong bản vẽ mặt bằng,
nên tool báo "nghi vấn xung đột cần kiểm tra cao độ", không kết luận thay kỹ sư.
"""
import logging
import math
import os

import ezdxf
import pandas as pd
from langchain_core.tools import tool

from src.workspace import resolve_safe_path

logger = logging.getLogger(__name__)

# Nhận diện hệ kỹ thuật từ tên Layer. Khớp theo thứ tự, từ khóa đặc thù đứng trước.
SYSTEM_KEYWORDS = [
    ("PCCC", ("pccc", "fire", "sprinkler", "ff_", "-ff", "chua chay", "hydrant")),
    ("HVAC", ("hvac", "duct", "gio", "air", "me_", "-me", "chiller", "fcu", "refrigerant")),
    ("Điện", ("elec", "dien", "power", "cable", "tray", "el_", "-el", "light", "lighting")),
    ("Cấp thoát nước", ("plumb", "nuoc", "water", "drain", "waste", "pl_", "-pl", "upvc", "ppr")),
]


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


def _extract_segments(msp):
    """Mọi đoạn thẳng của bản vẽ kèm layer và hệ kỹ thuật tương ứng."""
    segments = []
    for entity in msp:
        layer = entity.dxf.layer
        system = classify_layer_system(layer)
        if not system:
            continue
        dxftype = entity.dxftype()
        try:
            if dxftype == "LINE":
                s, e = entity.dxf.start, entity.dxf.end
                segments.append((system, layer, (s.x, s.y), (e.x, e.y)))
            elif dxftype == "LWPOLYLINE":
                pts = entity.get_points(format="xy")
                for i in range(1, len(pts)):
                    segments.append((system, layer, (pts[i - 1][0], pts[i - 1][1]), (pts[i][0], pts[i][1])))
            elif dxftype == "POLYLINE":
                pts = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
                for i in range(1, len(pts)):
                    segments.append((system, layer, pts[i - 1], pts[i]))
        except Exception:  # pragma: no cover - entity dị dạng trong file thực tế
            continue
    return segments


@tool
def detect_clashes(file_path: str, output_excel_path: str = "bao_cao_xung_dot.xlsx",
                   min_distance: float = 0.0) -> str:
    """Kiểm tra XUNG ĐỘT (clash detection) giữa các hệ MEPF trên bản vẽ CAD (.dxf).

    Quét toàn bộ tuyến ống/gió/cáp, phân loại theo hệ dựa trên tên Layer (HVAC, Điện,
    Cấp thoát nước, PCCC) và tìm mọi điểm hai hệ KHÁC NHAU cắt nhau trên mặt bằng, rồi
    xuất danh sách tọa độ xung đột ra file Excel. Thuần hình học, không cần LLM suy luận.
    Dùng khi khách hàng yêu cầu "kiểm tra xung đột", "clash", "va chạm giữa các hệ".
    """
    logger.info("Detecting clashes: %s", file_path)
    try:
        safe_path = resolve_safe_path(file_path)
        doc = ezdxf.readfile(safe_path)
        segments = _extract_segments(doc.modelspace())

        if not segments:
            return ("Không tìm thấy tuyến nào thuộc các hệ MEPF trong bản vẽ (dựa trên tên Layer). "
                    "Hãy đặt tên Layer theo quy ước có chứa từ khóa hệ (VD: 'HVAC_DUCT', 'ELEC_TRAY', "
                    "'PCCC_SPRINKLER', 'PLUMB_WASTE') rồi kiểm tra lại.")

        clashes = []
        seen = set()
        for i in range(len(segments)):
            sys_a, layer_a, a1, a2 = segments[i]
            for j in range(i + 1, len(segments)):
                sys_b, layer_b, b1, b2 = segments[j]
                if sys_a == sys_b:
                    continue  # xung đột trong cùng một hệ là chuyện bình thường (nhánh rẽ)
                point = _segment_intersection(a1, a2, b1, b2)
                if point is None:
                    continue
                # Gom các giao điểm sát nhau về cùng một xung đột để không báo trùng.
                key = (round(point[0], 3), round(point[1], 3), tuple(sorted((sys_a, sys_b))))
                if key in seen:
                    continue
                seen.add(key)
                clashes.append({
                    "STT": len(clashes) + 1,
                    "Hệ 1": sys_a, "Layer 1": layer_a,
                    "Hệ 2": sys_b, "Layer 2": layer_b,
                    "Tọa độ X": round(point[0], 2), "Tọa độ Y": round(point[1], 2),
                    "Mức độ": "Cần kiểm tra cao độ",
                })

        if not clashes:
            systems = sorted({s for s, _, _, _ in segments})
            return (f"KHÔNG phát hiện xung đột mặt bằng giữa các hệ. "
                    f"Đã quét {len(segments)} đoạn tuyến thuộc {len(systems)} hệ: {', '.join(systems)}.")

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
            "- Thống kê theo cặp hệ:",
        ]
        for pair, count in sorted(by_pair.items(), key=lambda x: -x[1]):
            report.append(f"  + {pair}: {count} điểm")
        report.append("- Chi tiết 10 điểm đầu:")
        for c in clashes[:10]:
            report.append(f"  {c['STT']}. {c['Hệ 1']} ({c['Layer 1']}) x {c['Hệ 2']} ({c['Layer 2']}) "
                          f"tại (X={c['Tọa độ X']}, Y={c['Tọa độ Y']})")
        if len(clashes) > 10:
            report.append(f"  ... và {len(clashes) - 10} điểm khác trong file Excel.")
        report.append(
            "- LƯU Ý: Đây là xung đột trên MẶT BẰNG 2D. Hai tuyến cắt nhau trên mặt bằng vẫn có thể "
            "hợp lệ nếu khác cao độ. Cần đối chiếu cao độ lắp đặt từng tuyến trước khi kết luận."
        )
        return "\n".join(report)
    except Exception as e:
        return f"Lỗi kiểm tra xung đột: {e}"
