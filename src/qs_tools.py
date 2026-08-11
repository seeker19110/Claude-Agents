"""Dự toán chi phí (QS): tra đơn giá vật tư/nhân công và tính giá trị dự toán.

Trước module này, bộ phận QS mới chỉ *đếm khối lượng* (`auto_quantity_takeoff`) chứ
chưa hề *lập dự toán* — không có đơn giá thì bảng khối lượng không ra được con số tiền,
tức là chưa dùng được cho hồ sơ thầu. Ở đây:

- `data/unit_prices.csv` là CSDL đơn giá (vật tư / nhân công / máy) tra theo TỪ KHÓA,
  cố ý để dạng CSV để chủ đầu tư tự sửa giá theo thời điểm và theo vùng.
- `calc_boq_cost` đọc thẳng file Excel khối lượng do `auto_quantity_takeoff` xuất ra,
  ghép đơn giá và tính ra bảng BOQ theo cấu trúc quen thuộc của hồ sơ Việt Nam
  (chi phí trực tiếp -> chi phí chung -> thu nhập chịu thuế tính trước -> VAT).

Toàn bộ phép tính là Python xác định, LLM không tham gia tính tiền.
"""
import logging
import os
import unicodedata

import pandas as pd
from langchain_core.tools import tool

from src.workspace import resolve_safe_path, get_project_root

logger = logging.getLogger(__name__)

UNIT_PRICE_CSV = os.path.join("data", "unit_prices.csv")

# Định mức tỷ lệ mặc định theo Thông tư 11/2021/TT-BXD (có thể chỉnh khi gọi tool).
DEFAULT_OVERHEAD_PERCENT = 6.5   # chi phí chung, % trên chi phí trực tiếp
DEFAULT_PROFIT_PERCENT = 5.5     # thu nhập chịu thuế tính trước, % trên (trực tiếp + chung)
DEFAULT_VAT_PERCENT = 10.0       # thuế GTGT


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(text)) if unicodedata.category(c) != "Mn")


def _norm(text: str) -> str:
    """Chuẩn hóa để so khớp: bỏ dấu, thường hóa, gom khoảng trắng."""
    return " ".join(_strip_accents(text).lower().replace("_", " ").split())


def load_unit_prices(csv_path: str = None) -> pd.DataFrame:
    """Nạp bảng đơn giá. Đọc từ project root (tài nguyên dùng chung), không phải
    workspace của phiên — mọi phiên tra cùng một bảng giá."""
    path = csv_path or os.path.join(get_project_root(), UNIT_PRICE_CSV)
    df = pd.read_csv(path)
    for col in ("don_gia_vat_tu", "don_gia_nhan_cong", "don_gia_may"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


def match_unit_price(item_name: str, prices: pd.DataFrame):
    """Tìm dòng đơn giá khớp nhất với tên hạng mục bóc tách được.

    Khớp theo từ khóa (cột `tu_khoa`, ngăn cách bằng '|'): từ khóa nào xuất hiện trong
    tên hạng mục thì tính điểm bằng độ dài từ khóa — từ khóa dài hơn là bằng chứng
    khớp mạnh hơn ('bom chua chay' thắng 'bom'). Không khớp thì trả về None thay vì
    đoán bừa một mức giá.
    """
    name_norm = _norm(item_name)
    best_row, best_score = None, 0
    for _, row in prices.iterrows():
        for keyword in str(row.get("tu_khoa", "")).split("|"):
            kw = _norm(keyword)
            if kw and kw in name_norm and len(kw) > best_score:
                best_row, best_score = row, len(kw)
    return best_row


@tool
def lookup_unit_price(keyword: str) -> str:
    """Tra đơn giá vật tư/nhân công của một hạng mục MEPF trong CSDL đơn giá nội bộ."""
    logger.info("Lookup unit price: %s", keyword)
    try:
        prices = load_unit_prices()
        kw_norm = _norm(keyword)
        hits = [
            row for _, row in prices.iterrows()
            if kw_norm in _norm(row["ten_cong_tac"])
            or any(_norm(k) and _norm(k) in kw_norm for k in str(row["tu_khoa"]).split("|"))
        ]
        if not hits:
            return (f"Không tìm thấy đơn giá cho '{keyword}' trong CSDL ({UNIT_PRICE_CSV}). "
                    f"Hãy bổ sung dòng đơn giá mới vào file CSV này trước khi lập dự toán.")

        lines = [f"Đơn giá tra được cho '{keyword}' (đơn vị: VNĐ):"]
        for row in hits[:10]:
            total = row["don_gia_vat_tu"] + row["don_gia_nhan_cong"] + row["don_gia_may"]
            lines.append(
                f"- [{row['ma_hieu']}] {row['ten_cong_tac']} ({row['don_vi']}): "
                f"VT {row['don_gia_vat_tu']:,.0f} + NC {row['don_gia_nhan_cong']:,.0f} + "
                f"M {row['don_gia_may']:,.0f} = {total:,.0f}/{row['don_vi']}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Lỗi tra đơn giá: {e}"


@tool
def calc_boq_cost(takeoff_excel_path: str, output_excel_path: str = "du_toan_chi_phi.xlsx",
                  overhead_percent: float = DEFAULT_OVERHEAD_PERCENT,
                  profit_percent: float = DEFAULT_PROFIT_PERCENT,
                  vat_percent: float = DEFAULT_VAT_PERCENT) -> str:
    """Lập BẢNG DỰ TOÁN CHI PHÍ (BOQ) thật từ file Excel khối lượng đã bóc tách.

    Đọc file Excel do `auto_quantity_takeoff` xuất ra (các cột STT / Hạng mục / Đơn vị /
    Khối lượng), tự tra đơn giá trong `data/unit_prices.csv`, nhân khối lượng x đơn giá
    và xuất file Excel dự toán theo cấu trúc hồ sơ Việt Nam: chi phí trực tiếp (vật tư,
    nhân công, máy) -> chi phí chung -> thu nhập chịu thuế tính trước -> thuế GTGT ->
    tổng giá trị dự toán. Hạng mục không tra được đơn giá vẫn được liệt kê và đánh dấu
    rõ "CHƯA CÓ ĐƠN GIÁ" thay vì bị bỏ qua âm thầm.
    """
    logger.info("Calculating BOQ cost: %s -> %s", takeoff_excel_path, output_excel_path)
    try:
        src_path = resolve_safe_path(takeoff_excel_path)
        if not os.path.exists(src_path):
            return (f"Không tìm thấy file khối lượng '{takeoff_excel_path}'. "
                    f"Hãy chạy `auto_quantity_takeoff` trước để tạo bảng khối lượng.")

        df = pd.read_excel(src_path)
        name_col = next((c for c in df.columns if _norm(c) in ("hang muc", "ten cong tac", "noi dung")), None)
        qty_col = next((c for c in df.columns if _norm(c) in ("khoi luong", "so luong")), None)
        unit_col = next((c for c in df.columns if _norm(c) == "don vi"), None)
        if not name_col or not qty_col:
            return (f"File '{takeoff_excel_path}' không có cột 'Hạng mục' và 'Khối lượng' cần thiết. "
                    f"Các cột hiện có: {list(df.columns)}")

        prices = load_unit_prices()
        rows, missing = [], []
        for i, item in df.iterrows():
            name = str(item[name_col])
            try:
                qty = float(item[qty_col])
            except (TypeError, ValueError):
                qty = 0.0
            match = match_unit_price(name, prices)

            if match is None:
                missing.append(name)
                rows.append({
                    "STT": len(rows) + 1, "Mã hiệu": "", "Hạng mục": name,
                    "Đơn vị": item[unit_col] if unit_col else "", "Khối lượng": qty,
                    "Đơn giá VT": 0, "Đơn giá NC": 0, "Đơn giá M": 0,
                    "Thành tiền VT": 0, "Thành tiền NC": 0, "Thành tiền M": 0,
                    "Thành tiền": 0, "Ghi chú": "CHƯA CÓ ĐƠN GIÁ - cần bổ sung vào data/unit_prices.csv",
                })
                continue

            vt, nc, m = match["don_gia_vat_tu"], match["don_gia_nhan_cong"], match["don_gia_may"]
            rows.append({
                "STT": len(rows) + 1, "Mã hiệu": match["ma_hieu"], "Hạng mục": name,
                "Đơn vị": match["don_vi"], "Khối lượng": qty,
                "Đơn giá VT": vt, "Đơn giá NC": nc, "Đơn giá M": m,
                "Thành tiền VT": round(qty * vt), "Thành tiền NC": round(qty * nc),
                "Thành tiền M": round(qty * m),
                "Thành tiền": round(qty * (vt + nc + m)),
                "Ghi chú": match["ten_cong_tac"],
            })

        if not rows:
            return "File khối lượng rỗng, không có hạng mục nào để lập dự toán."

        direct_cost = sum(r["Thành tiền"] for r in rows)
        overhead = direct_cost * overhead_percent / 100.0
        profit = (direct_cost + overhead) * profit_percent / 100.0
        before_vat = direct_cost + overhead + profit
        vat = before_vat * vat_percent / 100.0
        total = before_vat + vat

        summary_rows = [
            ("I", "CHI PHÍ TRỰC TIẾP (Vật tư + Nhân công + Máy)", direct_cost),
            ("II", f"CHI PHÍ CHUNG ({overhead_percent}% x I)", overhead),
            ("III", f"THU NHẬP CHỊU THUẾ TÍNH TRƯỚC ({profit_percent}% x (I+II))", profit),
            ("IV", "GIÁ TRỊ TRƯỚC THUẾ (I+II+III)", before_vat),
            ("V", f"THUẾ GTGT ({vat_percent}%)", vat),
            ("VI", "TỔNG GIÁ TRỊ DỰ TOÁN SAU THUẾ", total),
        ]

        out_path = output_excel_path if output_excel_path.endswith(".xlsx") else output_excel_path + ".xlsx"
        out_safe = resolve_safe_path(out_path)
        parent = os.path.dirname(out_safe)
        if parent:
            os.makedirs(parent, exist_ok=True)

        detail_df = pd.DataFrame(rows)
        summary_df = pd.DataFrame(
            [{"Khoản mục": code, "Nội dung": label, "Giá trị (VNĐ)": round(value)}
             for code, label, value in summary_rows]
        )
        with pd.ExcelWriter(out_safe, engine="openpyxl") as writer:
            detail_df.to_excel(writer, sheet_name="Chi tiết dự toán", index=False)
            summary_df.to_excel(writer, sheet_name="Tổng hợp", index=False)

        report = [
            f"LẬP DỰ TOÁN CHI PHÍ THÀNH CÔNG — đã ghi file Excel: {out_path}",
            f"- Số hạng mục: {len(rows)} (tra được đơn giá: {len(rows) - len(missing)})",
            "",
            "TỔNG HỢP GIÁ TRỊ DỰ TOÁN:",
        ]
        for code, label, value in summary_rows:
            report.append(f"  {code}. {label}: {round(value):,} VNĐ")
        if missing:
            report.append("")
            report.append(f"- CẢNH BÁO: {len(missing)} hạng mục CHƯA CÓ ĐƠN GIÁ nên đang tính bằng 0, "
                          f"tổng dự toán vì vậy còn THIẾU. Cần bổ sung vào data/unit_prices.csv: "
                          + ", ".join(missing[:8]) + ("..." if len(missing) > 8 else ""))
        return "\n".join(report)
    except Exception as e:
        return f"Lỗi lập dự toán chi phí: {e}"
