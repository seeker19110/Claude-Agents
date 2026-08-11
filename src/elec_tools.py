from langchain_core.tools import tool
import math
import logging

logger = logging.getLogger(__name__)

# Tiết diện ruột dẫn tiêu chuẩn (mm2) theo IEC 60228.
STANDARD_CABLE_SIZES = [1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240, 300, 400]

# Điện trở suất đồng ở nhiệt độ làm việc ~70 độ C (Ohm.mm2/m).
RHO_COPPER = 0.0225

# Giới hạn sụt áp cho phép (%) theo TCVN 9206 / IEC 60364-5-52.
VOLTAGE_DROP_LIMIT_LIGHTING = 3.0   # mạch chiếu sáng
VOLTAGE_DROP_LIMIT_POWER = 5.0      # mạch động lực


def _voltage_drop_percent(current_a: float, length_m: float, section_mm2: float,
                          voltage: float, phase: int, cos_phi: float) -> float:
    """Sụt áp (%) trên một tuyến cáp đồng, bỏ qua thành phần cảm kháng.

    3 pha: dU = sqrt(3) * I * L * rho / S * cos_phi
    1 pha: dU = 2 * I * L * rho / S * cos_phi   (đi và về => nhân 2)
    """
    if section_mm2 <= 0 or length_m <= 0:
        return 0.0
    factor = math.sqrt(3) if phase == 3 else 2.0
    drop_v = factor * current_a * length_m * RHO_COPPER / section_mm2 * cos_phi
    return drop_v / voltage * 100.0


def _select_by_current(current_a: float) -> float:
    """Tiết diện nhỏ nhất đủ tải theo mật độ dòng ~4 A/mm2 (cáp Cu/XLPE đi trong ống)."""
    s_estimate = current_a / 4.0
    for c in STANDARD_CABLE_SIZES:
        if c >= s_estimate:
            return c
    return STANDARD_CABLE_SIZES[-1]


@tool
def calc_voltage_drop(current_a: float, length_m: float, section_mm2: float,
                      voltage: float = 380, phase: int = 3, cos_phi: float = 0.85,
                      circuit_type: str = "power") -> str:
    """Kiểm tra độ sụt áp (%) của một tuyến cáp đồng theo chiều dài thực tế.

    circuit_type: 'power' (động lực, giới hạn 5%) hoặc 'lighting' (chiếu sáng, 3%).
    """
    logger.info(f"Calculating Voltage Drop: I={current_a}A, L={length_m}m, S={section_mm2}mm2")
    try:
        if phase != 3:
            voltage = 220
        drop_pct = _voltage_drop_percent(current_a, length_m, section_mm2, voltage, phase, cos_phi)
        limit = VOLTAGE_DROP_LIMIT_LIGHTING if circuit_type.lower().startswith("light") else VOLTAGE_DROP_LIMIT_POWER
        verdict = "ĐẠT" if drop_pct <= limit else "KHÔNG ĐẠT - phải tăng tiết diện cáp"

        return (f"Kiểm tra sụt áp tuyến cáp (I = {current_a:.1f} A, L = {length_m} m, S = {section_mm2} mm2):\n"
                f"- Sụt áp tính toán: {drop_pct:.2f} %\n"
                f"- Giới hạn cho phép ({circuit_type}): {limit:.1f} % (TCVN 9206 / IEC 60364-5-52)\n"
                f"- Kết luận: {verdict}")
    except Exception as e:
        return f"Lỗi tính sụt áp: {e}"


@tool
def calc_cable_size(power_kw: float, voltage: float = 380, cos_phi: float = 0.85, phase: int = 3,
                    length_m: float = 0, circuit_type: str = "power") -> str:
    """Chọn tiết diện cáp theo công suất phụ tải VÀ kiểm tra sụt áp theo chiều dài tuyến.

    `length_m` là chiều dài tuyến cáp từ tủ điện tới phụ tải (m). Nếu bỏ trống, tool chỉ
    chọn cáp theo dòng điện và cảnh báo rằng kết quả CHƯA kiểm tra sụt áp.
    """
    logger.info(f"Calculating Cable Size: P={power_kw}kW, L={length_m}m")
    try:
        if phase == 3:
            current_a = (power_kw * 1000) / (math.sqrt(3) * voltage * cos_phi)
        else:
            voltage = 220
            current_a = (power_kw * 1000) / (voltage * cos_phi)

        selected_cable = _select_by_current(current_a)
        report = [
            f"Tính cáp điện (P = {power_kw} kW, {phase} pha):",
            f"- Dòng điện tính toán (Ib): {current_a:.1f} A",
            f"- Tiết diện theo điều kiện phát nóng: {selected_cable} mm2",
        ]

        if not length_m or length_m <= 0:
            report.append(
                "- CẢNH BÁO: Chưa nhập chiều dài tuyến (length_m) nên CHƯA kiểm tra được sụt áp. "
                "TCVN 9206 bắt buộc kiểm tra %sụt áp; với tuyến dài, tiết diện trên có thể KHÔNG ĐỦ. "
                "Hãy hỏi lại chiều dài tuyến cáp rồi tính lại."
            )
            report.append(f"- Đề xuất cáp Cu/XLPE/PVC: {selected_cable} mm2 (chưa kiểm tra sụt áp)")
            return "\n".join(report)

        limit = VOLTAGE_DROP_LIMIT_LIGHTING if circuit_type.lower().startswith("light") else VOLTAGE_DROP_LIMIT_POWER
        drop_initial = _voltage_drop_percent(current_a, length_m, selected_cable, voltage, phase, cos_phi)

        # Tăng dần tiết diện cho tới khi sụt áp nằm trong giới hạn.
        final_cable = selected_cable
        for c in STANDARD_CABLE_SIZES:
            if c < selected_cable:
                continue
            if _voltage_drop_percent(current_a, length_m, c, voltage, phase, cos_phi) <= limit:
                final_cable = c
                break
        else:
            final_cable = STANDARD_CABLE_SIZES[-1]

        drop_final = _voltage_drop_percent(current_a, length_m, final_cable, voltage, phase, cos_phi)
        report.append(f"- Sụt áp nếu dùng {selected_cable} mm2 trên {length_m} m: {drop_initial:.2f} % "
                      f"(giới hạn {limit:.1f} %)")
        if final_cable > selected_cable:
            report.append(f"- PHẢI TĂNG TIẾT DIỆN do sụt áp vượt giới hạn.")
        report.append(f"- Đề xuất cáp Cu/XLPE/PVC: {final_cable} mm2 (sụt áp {drop_final:.2f} % - ĐẠT)")
        if drop_final > limit:
            report.append("- CẢNH BÁO: Ngay cả tiết diện lớn nhất vẫn vượt giới hạn sụt áp. "
                          "Cần chia tuyến, đặt tủ phân phối gần phụ tải hơn hoặc nâng cấp điện áp.")
        return "\n".join(report)
    except Exception as e:
        return f"Lỗi tính cáp: {e}"

@tool
def calc_breaker_size(power_kw: float, phase: int = 3) -> str:
    """Tính chọn dòng định mức cho Aptomat (MCB/MCCB) dựa trên công suất."""
    logger.info(f"Calculating Breaker: P={power_kw}kW")
    try:
        cos_phi = 0.85
        voltage = 380 if phase == 3 else 220
        if phase == 3:
            current_a = (power_kw * 1000) / (math.sqrt(3) * voltage * cos_phi)
        else:
            current_a = (power_kw * 1000) / (voltage * cos_phi)
            
        design_current = current_a * 1.25
        standard_breakers = [6, 10, 16, 20, 25, 32, 40, 50, 63, 80, 100, 125, 160, 200, 250, 320, 400, 500, 630, 800, 1000]
        selected_breaker = standard_breakers[-1]
        for b in standard_breakers:
            if b >= design_current:
                selected_breaker = b
                break
                
        return (f"Tính Aptomat (P = {power_kw} kW):\n"
                f"- Dòng làm việc: {current_a:.1f} A\n"
                f"- Chọn MCCB/MCB định mức: {selected_breaker} A")
    except Exception as e:
        return f"Lỗi tính aptomat: {e}"

@tool
def calc_lighting_qty(area_m2: float, required_lux: float, lumen_per_lamp: float = 3000) -> str:
    """Tính số lượng đèn chiếu sáng bằng phương pháp quang thông."""
    logger.info(f"Calculating Lighting: Area={area_m2}, Lux={required_lux}")
    try:
        UF = 0.6  
        MF = 0.8  
        N = (required_lux * area_m2) / (lumen_per_lamp * UF * MF)
        
        return (f"Tính chiếu sáng (Diện tích {area_m2}m2, Yêu cầu {required_lux} Lux):\n"
                f"- Dùng đèn có quang thông {lumen_per_lamp} Lm\n"
                f"- Số lượng tối thiểu cần thiết: {math.ceil(N)} bộ đèn")
    except Exception as e:
        return f"Lỗi tính đèn: {e}"
