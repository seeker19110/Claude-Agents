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

import polars as pl
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


def load_unit_prices(csv_path: str = None) -> pl.DataFrame:
    """Nạp bảng đơn giá. Đọc từ project root (tài nguyên dùng chung), không phải
    workspace của phiên — mọi phiên tra cùng một bảng giá.
    Có tích hợp Cache Redis để giảm thời gian đọc I/O đĩa.
    """
    try:
        import redis
        import pickle
        r = redis.Redis(host='localhost', port=6379, db=0, socket_connect_timeout=1)
        cache_key = f"mep_unit_prices_{csv_path or 'default'}"
        cached_data = r.get(cache_key)
        if cached_data:
            return pickle.loads(cached_data)
    except Exception as e:
        r = None
        logger.debug(f"Redis cache không khả dụng: {e}")

    path = csv_path or os.path.join(get_project_root(), UNIT_PRICE_CSV)
    df = pl.read_csv(path)
    
    # Cast to float, fill nulls
    df = df.with_columns([
        pl.col("don_gia_vat_tu").cast(pl.Float64, strict=False).fill_null(0.0),
        pl.col("don_gia_nhan_cong").cast(pl.Float64, strict=False).fill_null(0.0),
        pl.col("don_gia_may").cast(pl.Float64, strict=False).fill_null(0.0),
    ])
        
    if r is not None:
        try:
            r.setex(cache_key, 3600, pickle.dumps(df))  # Cache 1 hour
        except Exception:
            pass

    return df


def match_unit_price(item_name: str, prices: pl.DataFrame):
    """Tìm đơn giá khớp nhất cho một tên hạng mục.
    Tích hợp AI Semantic Search bằng FAISS (Vector Database)."""
    
    # 1. Semantic Search (Độ chính xác cao nhất qua Ngữ nghĩa)
    try:
        faiss_idx = _get_faiss_index(prices)
        docs = faiss_idx.similarity_search_with_score(item_name, k=1)
        # Điểm L2 distance càng thấp càng tốt, ngưỡng 0.4 là khá gần
        if docs and docs[0][1] < 0.4:
            return docs[0][0].metadata
    except Exception as e:
        pass
        
    # 2. Rơi về (Fallback) Exact substring match
    name_norm = _norm(item_name)
    best_row, best_score = None, 0
    
    for row in prices.iter_rows(named=True):
        for keyword in str(row.get("tu_khoa", "")).split("|"):
            kw = _norm(keyword)
            if kw and kw in name_norm and len(kw) > best_score:
                best_row, best_score = row, len(kw)
                
    # 3. Fuzzy matching nếu không tìm thấy exact
    if best_row is None:
        try:
            from rapidfuzz import fuzz
            best_fuzz = 0
            for row in prices.iter_rows(named=True):
                for keyword in str(row.get("tu_khoa", "")).split("|"):
                    kw = _norm(keyword)
                    if kw:
                        score = fuzz.partial_ratio(kw, name_norm)
                        if score > 85 and score > best_fuzz:
                            best_fuzz = score
                            best_row = row
        except ImportError:
            pass

    return best_row


@tool
def lookup_unit_price(keyword: str) -> str:
    """Tra đơn giá vật tư/nhân công của một hạng mục MEPF trong CSDL đơn giá nội bộ."""
    logger.info("Lookup unit price: %s", keyword)
    try:
        prices = load_unit_prices()
        kw_norm = _norm(keyword)
        hits = []
        
        try:
            from rapidfuzz import fuzz
            has_fuzz = True
        except ImportError:
            has_fuzz = False
            
        for row in prices.iter_rows(named=True):
            row_name_norm = _norm(str(row.get("ten_cong_tac", "")))
            is_match = False
            if kw_norm in row_name_norm:
                is_match = True
            else:
                for k in str(row.get("tu_khoa", "")).split("|"):
                    k_norm = _norm(k)
                    if k_norm and k_norm in kw_norm:
                        is_match = True
                        break
                    elif has_fuzz and k_norm and fuzz.partial_ratio(k_norm, kw_norm) > 85:
                        is_match = True
                        break
            if is_match:
                hits.append(row)

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

        df = pl.read_excel(src_path)
        cols = df.columns
        name_col = next((c for c in cols if _norm(c) in ("hang muc", "ten cong tac", "noi dung")), None)
        qty_col = next((c for c in cols if _norm(c) in ("khoi luong", "so luong")), None)
        unit_col = next((c for c in cols if _norm(c) == "don vi"), None)
        
        if not name_col or not qty_col:
            return (f"File '{takeoff_excel_path}' không có cột 'Hạng mục' và 'Khối lượng' cần thiết. "
                    f"Các cột hiện có: {cols}")

        prices = load_unit_prices()
        rows, missing = [], []
        
        for item in df.iter_rows(named=True):
            name = str(item.get(name_col, ""))
            try:
                qty = float(item.get(qty_col, 0.0))
            except (TypeError, ValueError):
                qty = 0.0
                
            match = match_unit_price(name, prices)

            if match is None:
                missing.append(name)
                rows.append({
                    "STT": len(rows) + 1, "Mã hiệu": "", "Hạng mục": name,
                    "Đơn vị": str(item.get(unit_col, "")) if unit_col else "", "Khối lượng": qty,
                    "Đơn giá VT": 0, "Đơn giá NC": 0, "Đơn giá M": 0,
                    "Thành tiền VT": 0, "Thành tiền NC": 0, "Thành tiền M": 0,
                    "Thành tiền": 0, "Ghi chú": "CHƯA CÓ ĐƠN GIÁ - cần bổ sung vào data/unit_prices.csv",
                })
                continue

            vt, nc, m = match.get("don_gia_vat_tu", 0.0), match.get("don_gia_nhan_cong", 0.0), match.get("don_gia_may", 0.0)
            rows.append({
                "STT": len(rows) + 1, "Mã hiệu": str(match.get("ma_hieu", "")), "Hạng mục": name,
                "Đơn vị": str(match.get("don_vi", "")), "Khối lượng": qty,
                "Đơn giá VT": vt, "Đơn giá NC": nc, "Đơn giá M": m,
                "Thành tiền VT": round(qty * vt), "Thành tiền NC": round(qty * nc),
                "Thành tiền M": round(qty * m),
                "Thành tiền": round(qty * (vt + nc + m)),
                "Ghi chú": str(match.get("ten_cong_tac", "")),
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

        detail_df = pl.DataFrame(rows)
        summary_df = pl.DataFrame(
            [{"Khoản mục": code, "Nội dung": label, "Giá trị (VNĐ)": round(value)}
             for code, label, value in summary_rows]
        )
        
        import xlsxwriter
        with xlsxwriter.Workbook(out_safe) as workbook:
            detail_df.write_excel(workbook=workbook, worksheet="Chi tiết dự toán")
            summary_df.write_excel(workbook=workbook, worksheet="Tổng hợp")

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


# --- Xuất BOQ theo mẫu chuẩn hồ sơ thầu Việt Nam ---

# Nhận diện hệ kỹ thuật của từng hạng mục để gom nhóm theo chương mục quen thuộc.
SYSTEM_GROUPS = [
    ("A", "HỆ THỐNG ĐIỀU HÒA KHÔNG KHÍ & THÔNG GIÓ (HVAC)",
     ("ong gio", "duct", "diffuser", "mieng gio", "fcu", "ahu", "chiller", "dan lanh",
      "ong dong", "refrigerant", "quat", "hvac", "thong gio")),
    ("B", "HỆ THỐNG ĐIỆN (ELECTRICAL)",
     ("cap dien", "cable", "day dien", "den", "light", "socket", "o cam", "switch",
      "cong tac", "tu dien", "panel", "mang cap", "tray", "elec", "dien")),
    ("C", "HỆ THỐNG CẤP THOÁT NƯỚC (PLUMBING)",
     ("ong upvc", "upvc", "ppr", "cap nuoc", "thoat nuoc", "be nuoc", "bon nuoc", "bom",
      "pump", "water", "drain", "plumb", "nuoc")),
    ("D", "HỆ THỐNG PHÒNG CHÁY CHỮA CHÁY (PCCC)",
     ("sprinkler", "dau phun", "chua chay", "pccc", "hong nuoc", "hydrant", "binh bot",
      "extinguisher", "bao chay", "ong thep")),
]
OTHER_GROUP = ("E", "HẠNG MỤC KHÁC")


def classify_boq_group(item_name: str):
    """Xếp một hạng mục vào chương mục BOQ (A/B/C/D/E) theo từ khóa tên."""
    name = _norm(item_name)
    for code, title, keywords in SYSTEM_GROUPS:
        if any(kw in name for kw in keywords):
            return code, title
    return OTHER_GROUP


@tool
def export_boq_vietnam(boq_excel_path: str, output_excel_path: str = "BOQ_mau_chuan.xlsx",
                       project_name: str = "", contractor: str = "", location: str = "") -> str:
    """Xuất BẢNG TIÊN LƯỢNG - DỰ TOÁN theo MẪU CHUẨN hồ sơ thầu Việt Nam.

    Nhận file Excel dự toán do `calc_boq_cost` tạo ra (hoặc bảng khối lượng của
    `auto_quantity_takeoff`) và định dạng lại thành bảng quen thuộc với hồ sơ thầu:
    có tiêu đề công trình, hạng mục được gom theo CHƯƠNG MỤC từng hệ (A. HVAC, B. Điện,
    C. Cấp thoát nước, D. PCCC), đánh số STT theo chương, cộng tiểu tổng từng chương và
    tổng cộng cuối bảng. Dùng khi khách hàng cần bảng nộp thầu chứ không phải bảng thô.
    """
    logger.info("Exporting Vietnamese BOQ template: %s -> %s", boq_excel_path, output_excel_path)
    try:
        src = resolve_safe_path(boq_excel_path)
        if not os.path.exists(src):
            return (f"Không tìm thấy file '{boq_excel_path}'. Hãy chạy `auto_quantity_takeoff` và "
                    f"`calc_boq_cost` trước để có bảng dự toán nguồn.")

        df = pd.read_excel(src)
        name_col = next((c for c in df.columns if _norm(c) in ("hang muc", "ten cong tac", "noi dung")), None)
        qty_col = next((c for c in df.columns if _norm(c) in ("khoi luong", "so luong")), None)
        if not name_col or not qty_col:
            return f"File '{boq_excel_path}' thiếu cột 'Hạng mục'/'Khối lượng'. Cột hiện có: {list(df.columns)}"

        unit_col = next((c for c in df.columns if _norm(c) == "don vi"), None)
        total_col = next((c for c in df.columns if _norm(c) == "thanh tien"), None)
        code_col = next((c for c in df.columns if _norm(c) == "ma hieu"), None)
        unit_price_available = {
            "vt": next((c for c in df.columns if _norm(c) == "don gia vt"), None),
            "nc": next((c for c in df.columns if _norm(c) == "don gia nc"), None),
        }

        # Gom hạng mục theo chương mục.
        groups = {}
        for _, item in df.iterrows():
            code, title = classify_boq_group(str(item[name_col]))
            groups.setdefault((code, title), []).append(item)

        rows = []
        grand_total = 0.0
        for (code, title) in sorted(groups, key=lambda g: g[0]):
            items = groups[(code, title)]
            rows.append({"STT": code, "Mã hiệu": "", "Nội dung công việc": title,
                         "Đơn vị": "", "Khối lượng": None, "Đơn giá VT": None,
                         "Đơn giá NC": None, "Thành tiền": None})
            group_total = 0.0
            for i, item in enumerate(items, start=1):
                line_total = float(item[total_col]) if total_col and pd.notna(item.get(total_col)) else 0.0
                group_total += line_total
                rows.append({
                    "STT": f"{code}.{i}",
                    "Mã hiệu": item[code_col] if code_col and pd.notna(item.get(code_col)) else "",
                    "Nội dung công việc": item[name_col],
                    "Đơn vị": item[unit_col] if unit_col and pd.notna(item.get(unit_col)) else "",
                    "Khối lượng": item[qty_col],
                    "Đơn giá VT": item[unit_price_available["vt"]] if unit_price_available["vt"] else None,
                    "Đơn giá NC": item[unit_price_available["nc"]] if unit_price_available["nc"] else None,
                    "Thành tiền": line_total if total_col else None,
                })
            grand_total += group_total
            rows.append({"STT": "", "Mã hiệu": "", "Nội dung công việc": f"Cộng {title}",
                         "Đơn vị": "", "Khối lượng": None, "Đơn giá VT": None,
                         "Đơn giá NC": None, "Thành tiền": round(group_total) if total_col else None})

        rows.append({"STT": "", "Mã hiệu": "", "Nội dung công việc": "TỔNG CỘNG",
                     "Đơn vị": "", "Khối lượng": None, "Đơn giá VT": None,
                     "Đơn giá NC": None, "Thành tiền": round(grand_total) if total_col else None})

        out_path = output_excel_path if output_excel_path.endswith(".xlsx") else output_excel_path + ".xlsx"
        out_safe = resolve_safe_path(out_path)
        parent = os.path.dirname(out_safe)
        if parent:
            os.makedirs(parent, exist_ok=True)

        header = pd.DataFrame([
            {"Thông tin": "Công trình", "Nội dung": project_name or "(chưa nhập tên công trình)"},
            {"Thông tin": "Địa điểm", "Nội dung": location or "(chưa nhập địa điểm)"},
            {"Thông tin": "Đơn vị lập", "Nội dung": contractor or "(chưa nhập đơn vị)"},
            {"Thông tin": "Tên bảng", "Nội dung": "BẢNG TIÊN LƯỢNG - DỰ TOÁN HẠNG MỤC MEPF"},
            {"Thông tin": "Đơn vị tiền tệ", "Nội dung": "VNĐ"},
        ])
        with pd.ExcelWriter(out_safe, engine="openpyxl") as writer:
            header.to_excel(writer, sheet_name="Trang bìa", index=False)
            pd.DataFrame(rows).to_excel(writer, sheet_name="Tiên lượng - Dự toán", index=False)

        report = [
            f"XUẤT BOQ THEO MẪU CHUẨN VIỆT NAM THÀNH CÔNG: {out_path}",
            f"- Công trình: {project_name or '(chưa nhập)'}",
            f"- Số chương mục: {len(groups)}",
        ]
        for (code, title) in sorted(groups, key=lambda g: g[0]):
            report.append(f"  {code}. {title}: {len(groups[(code, title)])} hạng mục")
        if total_col:
            report.append(f"- TỔNG CỘNG: {round(grand_total):,} VNĐ")
        else:
            report.append("- Lưu ý: File nguồn chưa có cột 'Thành tiền' nên bảng chỉ có khối lượng, "
                          "chưa có giá trị tiền. Chạy `calc_boq_cost` trước để có dự toán đầy đủ.")
        return "\n".join(report)
    except Exception as e:
        return f"Lỗi xuất BOQ mẫu chuẩn: {e}"
