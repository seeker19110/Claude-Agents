from langchain_core.tools import tool
import math
import logging

logger = logging.getLogger(__name__)

@tool
def calc_sprinkler_qty(area_m2: float, hazard_class: str = "light") -> str:
    """Tính số lượng đầu phun Sprinkler tối thiểu dựa trên diện tích."""
    logger.info(f"Calculating Sprinklers: Area={area_m2}, Hazard={hazard_class}")
    try:
        coverage = 12.0
        if hazard_class.lower() == "light":
            coverage = 12.0
        elif hazard_class.lower() == "ordinary":
            coverage = 9.0
        elif hazard_class.lower() == "extra":
            coverage = 6.0
            
        qty = math.ceil(area_m2 / coverage)
        return (f"Tính đầu phun Sprinkler ({area_m2} m2, Nguy cơ {hazard_class}):\n"
                f"- Diện tích bảo vệ mỗi đầu: {coverage} m2/đầu\n"
                f"- Số lượng tối thiểu: {qty} đầu")
    except Exception as e:
        return f"Lỗi tính sprinkler: {e}"

# Áp suất làm việc tối thiểu tại đầu phun bất lợi nhất (bar), TCVN 7336.
SPRINKLER_MIN_PRESSURE_BAR = 0.5
# Áp suất tối thiểu tại họng nước vách tường (bar), TCVN 3890.
HYDRANT_MIN_PRESSURE_BAR = 2.0


@tool
def calc_fire_pump(hazard_class: str = "ordinary", static_head_m: float = 0,
                   pipe_length_m: float = 0, has_hydrant: bool = False,
                   friction_loss_per_100m: float = 5.0) -> str:
    """Chọn bơm chữa cháy: tính CẢ lưu lượng Q và cột áp H (đủ dữ liệu để chọn bơm thật).

    - static_head_m: chiều cao hình học từ bể/hút bơm tới đầu phun bất lợi nhất (m).
    - pipe_length_m: tổng chiều dài tuyến ống tới điểm bất lợi nhất (m).
    - has_hydrant: có họng nước vách tường hay không (quyết định áp yêu cầu tại đầu ra).
    - friction_loss_per_100m: tổn thất ma sát đường ống (m cột nước / 100 m ống).
    """
    logger.info(f"Calculating Fire Pump: Hazard={hazard_class}, H_static={static_head_m}m")
    try:
        if hazard_class.lower() == "light":
            flow_gpm = 500
        elif hazard_class.lower() == "ordinary":
            flow_gpm = 1000
        else:
            flow_gpm = 1500

        flow_lps = flow_gpm * 0.06309
        flow_m3h = flow_lps * 3.6

        report = [
            f"Chọn Cụm bơm PCCC (Nguy cơ {hazard_class}):",
            f"- Lưu lượng Q: {flow_gpm} GPM (~ {flow_lps:.1f} L/s ~ {flow_m3h:.1f} m3/h)",
        ]

        if static_head_m <= 0 and pipe_length_m <= 0:
            report.append(
                "- CẢNH BÁO: Chưa có chiều cao hình học (static_head_m) và chiều dài tuyến ống "
                "(pipe_length_m) nên CHƯA tính được cột áp H. Thiếu H thì KHÔNG thể chọn bơm thực tế "
                "— hãy hỏi lại hai thông số này rồi tính lại."
            )
            return "\n".join(report)

        # H = cột áp hình học + tổn thất ma sát (+ tổn thất cục bộ 20%) + áp yêu cầu tại đầu ra
        friction_m = pipe_length_m * friction_loss_per_100m / 100.0
        local_loss_m = friction_m * 0.20
        required_bar = HYDRANT_MIN_PRESSURE_BAR if has_hydrant else SPRINKLER_MIN_PRESSURE_BAR
        required_m = required_bar * 10.2
        total_head_m = static_head_m + friction_m + local_loss_m + required_m

        report += [
            f"- Cột áp hình học (Hhh): {static_head_m:.1f} m",
            f"- Tổn thất ma sát đường ống ({pipe_length_m:.0f} m x {friction_loss_per_100m} m/100m): {friction_m:.1f} m",
            f"- Tổn thất cục bộ (co, tê, van - lấy 20% ma sát): {local_loss_m:.1f} m",
            f"- Áp yêu cầu tại điểm bất lợi nhất: {required_bar:.1f} bar (~ {required_m:.1f} m) "
            f"[{'họng vách tường, TCVN 3890' if has_hydrant else 'đầu phun sprinkler, TCVN 7336'}]",
            f"- CỘT ÁP BƠM YÊU CẦU (H): {total_head_m:.1f} m",
            f"=> Chọn bơm chữa cháy: Q ~ {flow_m3h:.1f} m3/h, H ~ {total_head_m:.1f} m "
            f"(chọn bơm catalog có điểm làm việc bao trùm điểm này).",
            "- Ghi chú: Cần bơm bù áp (jockey) và bơm dự phòng động cơ diesel theo TCVN 3890.",
        ]
        return "\n".join(report)
    except Exception as e:
        return f"Lỗi tính bơm PCCC: {e}"

@tool
def calc_extinguisher_qty(area_m2: float) -> str:
    """Bố trí số lượng bình chữa cháy xách tay."""
    logger.info(f"Calculating Extinguishers: Area={area_m2}")
    try:
        qty = math.ceil(area_m2 / 50.0)
        return (f"Bố trí bình chữa cháy ({area_m2} m2):\n"
                f"- Tiêu chuẩn: 50 m2/bình\n"
                f"- Số lượng: {qty} bình (kết hợp bình bột ABC và khí CO2)")
    except Exception as e:
        return f"Lỗi tính bình chữa cháy: {e}"
