"""Hình học CAD dùng chung: chiều dài THẬT của tuyến, cao độ Z, và suy ra phụ kiện ống.

Trước module này, mọi tool đo chiều dài đều cộng khoảng cách thẳng giữa các vertex. Ba
hệ quả sai số trong hồ sơ thật:

1. **Cung cong bị đo hụt.** Đoạn cong trong LWPOLYLINE được mã hóa bằng `bulge` ở vertex
   đầu đoạn; cộng khoảng cách hai đầu là đo DÂY CUNG chứ không phải cung tròn. Với co 90°
   bán kính R, dây cung ngắn hơn cung thật khoảng 10%.
2. **Entity ARC bị bỏ hẳn.** Ống vẽ bằng ARC rời (rất phổ biến khi vẽ tay) không được
   tính một mét nào.
3. **Cao độ bị bỏ qua.** Tuyến đi xiên giữa hai cao độ (ống lên/xuống trục kỹ thuật) bị
   đo bằng hình chiếu bằng, luôn ngắn hơn chiều dài thật.

Toàn bộ hàm ở đây là hình học thuần, không phụ thuộc LLM.
"""
import math

# Sai số tọa độ coi như trùng điểm (đơn vị bản vẽ). Bản vẽ MEPF thường vẽ theo mm nên
# 1 đơn vị là đủ chặt để nối tuyến mà vẫn bỏ qua lệch do làm tròn khi vẽ.
JOINT_TOLERANCE = 1.0

# Góc đổi hướng tối thiểu để coi là một co (elbow). Dưới ngưỡng này chỉ là tuyến gần
# thẳng bị chia nhỏ vertex, không phải chỗ lắp phụ kiện.
ELBOW_MIN_ANGLE_DEG = 15.0

# Chiều dài một cây ống thương phẩm (đơn vị bản vẽ giống bản vẽ). Dùng để suy số măng
# sông (nối ống): cứ hết một cây là phải có một mối nối.
DEFAULT_PIPE_STOCK_LENGTH = 6000.0  # 6 m theo mm


def bulge_arc_length(x1: float, y1: float, x2: float, y2: float, bulge: float) -> float:
    """Chiều dài CUNG giữa hai vertex của LWPOLYLINE theo hệ số `bulge`.

    Trong DXF, `bulge = tan(θ/4)` với θ là góc ở tâm của cung. Từ đó:
        θ = 4·atan(|bulge|),  R = dây cung / (2·sin(θ/2)),  cung = R·θ
    `bulge = 0` nghĩa là đoạn thẳng, trả về chính chiều dài dây cung.
    """
    chord = math.hypot(x2 - x1, y2 - y1)
    if not bulge or chord == 0:
        return chord
    theta = 4.0 * math.atan(abs(bulge))
    half = math.sin(theta / 2.0)
    if half == 0:
        return chord
    radius = chord / (2.0 * half)
    return radius * theta


def _polyline_vertices(entity):
    """(x, y, z, bulge) của từng vertex, thống nhất cho LWPOLYLINE và POLYLINE."""
    dxftype = entity.dxftype()
    if dxftype == "LWPOLYLINE":
        elevation = getattr(entity.dxf, "elevation", 0.0) or 0.0
        return [(p[0], p[1], elevation, p[4]) for p in entity.get_points(format="xyseb")]
    if dxftype == "POLYLINE":
        result = []
        for v in entity.vertices:
            loc = v.dxf.location
            result.append((loc.x, loc.y, getattr(loc, "z", 0.0) or 0.0,
                           getattr(v.dxf, "bulge", 0.0) or 0.0))
        return result
    return []


def polyline_segments(entity):
    """Các đoạn của một polyline: tọa độ hai đầu, bulge, chiều dài thật, có cong hay không.

    Polyline đóng (`closed`) được nối thêm đoạn từ vertex cuối về vertex đầu — bỏ sót
    đoạn này là đo hụt đúng một cạnh của mọi tuyến ống chạy vòng khép kín.
    """
    verts = _polyline_vertices(entity)
    if len(verts) < 2:
        return []

    pairs = list(zip(verts[:-1], verts[1:]))
    if getattr(entity, "closed", False) or getattr(entity.dxf, "flags", 0) & 1:
        pairs.append((verts[-1], verts[0]))

    segments = []
    for (x1, y1, z1, bulge), (x2, y2, z2, _) in pairs:
        planar = bulge_arc_length(x1, y1, x2, y2, bulge)
        dz = z2 - z1
        # Cung cong nằm trong mặt phẳng polyline nên chỉ đoạn thẳng mới cộng thêm dz.
        length = math.hypot(planar, dz) if (not bulge and dz) else planar
        segments.append({
            "start": (x1, y1, z1),
            "end": (x2, y2, z2),
            "bulge": bulge,
            "length": length,
            "is_arc": bool(bulge),
        })
    return segments


def arc_entity_length(entity) -> float:
    """Chiều dài của entity ARC rời (trước đây bị bỏ qua hoàn toàn khi đo khối lượng)."""
    radius = float(entity.dxf.radius)
    start = float(entity.dxf.start_angle)
    end = float(entity.dxf.end_angle)
    sweep = (end - start) % 360.0
    if sweep == 0:
        sweep = 360.0
    return radius * math.radians(sweep)


def entity_segments(entity):
    """Chuẩn hóa mọi entity đo được về cùng một danh sách đoạn.

    Hỗ trợ LINE (kể cả xiên theo Z), LWPOLYLINE/POLYLINE (kể cả cung bulge và polyline
    đóng), ARC và CIRCLE. Entity không đo được trả về danh sách rỗng.
    """
    dxftype = entity.dxftype()
    try:
        if dxftype == "LINE":
            s, e = entity.dxf.start, entity.dxf.end
            z1 = getattr(s, "z", 0.0) or 0.0
            z2 = getattr(e, "z", 0.0) or 0.0
            length = math.sqrt((e.x - s.x) ** 2 + (e.y - s.y) ** 2 + (z2 - z1) ** 2)
            return [{"start": (s.x, s.y, z1), "end": (e.x, e.y, z2),
                     "bulge": 0.0, "length": length, "is_arc": False}]

        if dxftype in ("LWPOLYLINE", "POLYLINE"):
            return polyline_segments(entity)

        if dxftype == "ARC":
            center = entity.dxf.center
            radius = float(entity.dxf.radius)
            z = getattr(center, "z", 0.0) or 0.0
            a1 = math.radians(float(entity.dxf.start_angle))
            a2 = math.radians(float(entity.dxf.end_angle))
            start = (center.x + radius * math.cos(a1), center.y + radius * math.sin(a1), z)
            end = (center.x + radius * math.cos(a2), center.y + radius * math.sin(a2), z)
            return [{"start": start, "end": end, "bulge": None,
                     "length": arc_entity_length(entity), "is_arc": True}]

        if dxftype == "CIRCLE":
            center = entity.dxf.center
            radius = float(entity.dxf.radius)
            z = getattr(center, "z", 0.0) or 0.0
            point = (center.x + radius, center.y, z)
            return [{"start": point, "end": point, "bulge": None,
                     "length": 2 * math.pi * radius, "is_arc": True}]
    except Exception:  # pragma: no cover - entity dị dạng trong file thực tế
        return []
    return []


def entity_length(entity) -> float:
    """Tổng chiều dài THẬT của một entity (đã tính cung cong và chênh cao độ)."""
    return sum(seg["length"] for seg in entity_segments(entity))


def collect_segments(entities):
    """Gom toàn bộ đoạn đo được của một tập entity, kèm layer của mỗi đoạn."""
    collected = []
    for entity in entities:
        layer = getattr(entity.dxf, "layer", "0")
        for seg in entity_segments(entity):
            item = dict(seg)
            item["layer"] = layer
            collected.append(item)
    return collected


def _angle(p1, p2) -> float:
    return math.atan2(p2[1] - p1[1], p2[0] - p1[0])


def _same_point(p1, p2, tol: float = JOINT_TOLERANCE) -> bool:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1]) <= tol


def _point_on_segment_interior(point, seg, tol: float = JOINT_TOLERANCE) -> bool:
    """Điểm có nằm trên THÂN đoạn (không phải hai đầu) hay không — dấu hiệu của chỗ rẽ tê."""
    (ax, ay, _), (bx, by, _) = seg["start"], seg["end"]
    px, py = point[0], point[1]
    if _same_point(point, seg["start"], tol) or _same_point(point, seg["end"], tol):
        return False
    l2 = (bx - ax) ** 2 + (by - ay) ** 2
    if l2 == 0:
        return False
    t = ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / l2
    if not (0.0 < t < 1.0):
        return False
    dist = math.hypot(px - (ax + t * (bx - ax)), py - (ay + t * (by - ay)))
    return dist <= tol


def detect_fittings(segments, stock_length: float = DEFAULT_PIPE_STOCK_LENGTH,
                    tolerance: float = JOINT_TOLERANCE) -> dict:
    """Suy ra số phụ kiện ống (co / tê / măng sông) từ hình học tuyến, theo từng layer.

    Với bản vẽ chỉ có LINE/POLYLINE thuần (không chèn Block phụ kiện), cách duy nhất để
    không bóc thiếu phụ kiện là suy từ chính hình học:

    - **Co (elbow)**: mỗi chỗ tuyến đổi hướng quá `ELBOW_MIN_ANGLE_DEG`, gồm cả khúc nối
      giữa hai đoạn thẳng lẫn mỗi đoạn cung (bulge/ARC — bản thân cung chính là một co).
    - **Tê (tee)**: đầu mút của một tuyến chạm vào THÂN của tuyến khác cùng layer.
    - **Măng sông (coupling)**: ống bán theo cây `stock_length`, cứ hết một cây phải có
      một mối nối, nên số măng sông ≈ ceil(tổng chiều dài / cây) - số tuyến.

    Trả về `{layer: {"co": n, "te": n, "mang_song": n}}`. Đây là ƯỚC TÍNH hình học, kỹ sư
    vẫn phải đối chiếu bản vẽ chi tiết — nhưng ước tính có căn cứ vẫn tốt hơn bỏ trắng.
    """
    by_layer = {}
    for seg in segments:
        by_layer.setdefault(seg["layer"], []).append(seg)

    result = {}
    for layer, segs in by_layer.items():
        elbows = sum(1 for s in segs if s["is_arc"])

        # Co tại chỗ hai đoạn thẳng nối nhau và đổi hướng đáng kể.
        for i, a in enumerate(segs):
            if a["is_arc"]:
                continue
            for b in segs[i + 1:]:
                if b["is_arc"] or not _same_point(a["end"], b["start"], tolerance):
                    continue
                turn = abs(math.degrees(_angle(b["start"], b["end"]) - _angle(a["start"], a["end"])))
                turn = min(turn % 360, 360 - (turn % 360))
                if turn >= ELBOW_MIN_ANGLE_DEG:
                    elbows += 1

        # Tê: đầu mút tuyến này chạm thân tuyến kia.
        tees = 0
        for i, a in enumerate(segs):
            for j, b in enumerate(segs):
                if i == j:
                    continue
                if _point_on_segment_interior(a["start"], b, tolerance) or \
                        _point_on_segment_interior(a["end"], b, tolerance):
                    tees += 1
                    break

        total_length = sum(s["length"] for s in segs)
        runs = max(1, len(segs))
        couplings = max(0, math.ceil(total_length / stock_length) - runs) if stock_length > 0 else 0

        result[layer] = {"co": elbows, "te": tees, "mang_song": couplings}
    return result


def block_scale(entity):
    """Tỷ lệ (xscale, yscale, zscale) của một INSERT, mặc định 1.0 khi không khai báo."""
    return (
        float(getattr(entity.dxf, "xscale", 1.0) or 1.0),
        float(getattr(entity.dxf, "yscale", 1.0) or 1.0),
        float(getattr(entity.dxf, "zscale", 1.0) or 1.0),
    )


def _subdivide_bulge(x1, y1, x2, y2, bulge, n=8):
    """Rời rạc hóa một cung bulge thành `n` điểm trung gian, để dùng cho giao cắt
    hình học (thẳng-thẳng) mà không phải giải phương trình đường tròn."""
    if not bulge:
        return [(x1, y1), (x2, y2)]
    theta = 4.0 * math.atan(abs(bulge))
    chord = math.hypot(x2 - x1, y2 - y1)
    half = math.sin(theta / 2.0)
    if half == 0 or chord == 0:
        return [(x1, y1), (x2, y2)]
    radius = chord / (2.0 * half)
    # Tâm cung: vuông góc với dây cung, lệch về phía xác định bởi dấu bulge.
    mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    dx, dy = x2 - x1, y2 - y1
    dist_to_center = math.sqrt(max(radius ** 2 - (chord / 2.0) ** 2, 0.0))
    nx, ny = -dy / chord, dx / chord
    sign = 1.0 if bulge > 0 else -1.0
    cx, cy = mx + sign * nx * dist_to_center, my + sign * ny * dist_to_center

    a1 = math.atan2(y1 - cy, x1 - cx)
    a2 = math.atan2(y2 - cy, x2 - cx)
    sweep = theta if bulge > 0 else -theta
    points = []
    for i in range(n + 1):
        a = a1 + sweep * (i / n)
        points.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
    return points


def entity_points_3d(entity, arc_segments: int = 12):
    """Chuỗi điểm (x, y, z) xấp xỉ hình dạng một entity, RỜI RẠC HÓA cung cong.

    Dùng cho các phép toán chỉ cần giao cắt/hình chiếu gần đúng (clash detection) mà
    không cần chiều dài chính xác — ở đó việc quy cung về nhiều đoạn thẳng ngắn là đủ,
    tránh phải giải giao điểm đường tròn-đường tròn.
    """
    dxftype = entity.dxftype()
    try:
        if dxftype == "LINE":
            s, e = entity.dxf.start, entity.dxf.end
            z1 = getattr(s, "z", 0.0) or 0.0
            z2 = getattr(e, "z", 0.0) or 0.0
            return [(s.x, s.y, z1), (e.x, e.y, z2)]

        if dxftype in ("LWPOLYLINE", "POLYLINE"):
            verts = _polyline_vertices(entity)
            if len(verts) < 2:
                return []
            pairs = list(zip(verts[:-1], verts[1:]))
            if getattr(entity, "closed", False) or getattr(entity.dxf, "flags", 0) & 1:
                pairs.append((verts[-1], verts[0]))
            points = []
            for (x1, y1, z1, bulge), (x2, y2, z2, _) in pairs:
                sub = _subdivide_bulge(x1, y1, x2, y2, bulge, n=arc_segments) if bulge else [(x1, y1), (x2, y2)]
                for k, (px, py) in enumerate(sub):
                    t = k / max(1, len(sub) - 1)
                    points.append((px, py, z1 + (z2 - z1) * t))
            return points

        if dxftype == "ARC":
            center = entity.dxf.center
            radius = float(entity.dxf.radius)
            z = getattr(center, "z", 0.0) or 0.0
            a1 = math.radians(float(entity.dxf.start_angle))
            a2 = math.radians(float(entity.dxf.end_angle))
            sweep = (a2 - a1) % (2 * math.pi) or (2 * math.pi)
            return [(center.x + radius * math.cos(a1 + sweep * i / arc_segments),
                    center.y + radius * math.sin(a1 + sweep * i / arc_segments), z)
                   for i in range(arc_segments + 1)]

        if dxftype == "CIRCLE":
            center = entity.dxf.center
            radius = float(entity.dxf.radius)
            z = getattr(center, "z", 0.0) or 0.0
            return [(center.x + radius * math.cos(2 * math.pi * i / arc_segments),
                    center.y + radius * math.sin(2 * math.pi * i / arc_segments), z)
                   for i in range(arc_segments + 1)]
    except Exception:  # pragma: no cover - entity dị dạng trong file thực tế
        return []
    return []


def is_scaled(entity, tolerance: float = 1e-6) -> bool:
    """Block có bị insert với tỷ lệ khác 1 hay không.

    Đếm đúng số lượng nhưng bỏ qua tỷ lệ là bẫy thật: một đèn 600x600 chèn ở scale 1.5 vẫn
    được đếm là "1 bộ đèn 600x600" trong khi kích thước thực tế trên bản vẽ là 900x900.
    """
    return any(abs(s - 1.0) > tolerance for s in block_scale(entity))
