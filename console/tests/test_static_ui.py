"""Trang tĩnh `index.html` là toàn bộ giao diện (một file, chỉ thư viện chuẩn phục vụ). Không có bước build nên
không có gì bắt lỗi "thêm màn mà quên khai vào routing" — mấy test dưới đây làm việc đó: đọc file và kiểm những
ràng buộc mà một màn mới phải thoả, để tab Hướng dẫn (và tab thêm sau này) không thành liên kết chết."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PAGE = Path(__file__).resolve().parents[1] / "src" / "console" / "static" / "index.html"


@pytest.fixture(scope="module")
def page() -> str:
    return PAGE.read_text(encoding="utf-8")


def _views(page: str) -> list[str]:
    m = re.search(r"const VIEWS=\[(.*?)\];", page)
    assert m, "không tìm thấy khai báo VIEWS"
    return re.findall(r'"([^"]+)"', m.group(1))


def test_moi_nut_nav_deu_co_man_va_tieu_de_va_nam_trong_routing(page: str) -> None:
    """Ba chỗ phải khớp nhau: nút nav, `<section id="v-...">`, và VIEWS + TITLES trong JS."""
    nav = re.findall(r'class="nav" data-v="([^"]+)"', page)
    sections = re.findall(r'<section class="view(?: on)?" id="v-([^"]+)"', page)
    titles = re.findall(r'^ ?"([a-z-]+)":\(\)=>\[', page, re.M)
    views = _views(page)
    assert "huong-dan" in nav, "tab Hướng dẫn phải có nút ở thanh bên"
    for v in nav:
        assert v in sections, f"nút {v} không có màn tương ứng"
        assert v in views, f"{v} thiếu trong VIEWS → mở bằng địa chỉ #/{v} sẽ rơi về Trực ban"
        assert v in titles, f"{v} thiếu tiêu đề trong TITLES → titles() sẽ ném khi mở màn"
    assert sorted(nav) == sorted(sections) == sorted(views), "nav, section và VIEWS phải là cùng một tập"


def test_man_huong_dan_render_bang_quyen_theo_dung_co_dang_chay(page: str) -> None:
    """Bảng quyền phải đọc trạng thái thật của phiên (READONLY / can_submit / CFG.can_edit), không phải chữ chết:
    người mở console mà không bấm được nút nào cần thấy ngay lý do."""
    assert 'if(v==="huong-dan") renderGuide();' in page, "showView phải gọi renderGuide khi mở tab"
    caps = page[page.index("const CAPS=["):page.index("function renderGuide")]
    for flag, src in (("--allow-decide", "!READONLY"), ("--allow-submit", "CONSOLE.can_submit"),
                      ("--allow-config", "CFG.can_edit")):
        assert flag in caps and src in caps, f"{flag} phải lấy trạng thái từ {src}"
    assert 'id="guide-caps"' in page, "màn phải có chỗ để renderGuide đổ bảng vào"


def test_man_huong_dan_noi_dung_khop_hanh_vi_that_cua_he(page: str) -> None:
    guide = page[page.index('id="v-huong-dan"'):page.index('<section class="view" id="v-nhat-ky"')]
    for gate in ("spec", "plan", "release", "acceptance"):
        assert f"<code>{gate}</code>" in guide, f"thiếu gate {gate} trong bảng bốn điểm dừng"
    assert "escalation" in guide, "gate bất thường phải được nhắc"
    assert "local_checks.unverified" in guide, "phải nói rõ hệ quả khi dự án không có repo"
    assert "--allow-decide" in guide and "--allow-submit" in guide


def test_nut_dien_yeu_cau_mau_do_du_truong_bat_buoc(page: str) -> None:
    """Mẫu phải điền được đúng những ô mà form yêu cầu phần mềm đang có, và mô tả phải đủ dài để `intake` có việc
    làm — mẫu hai dòng thì spec-writer sẽ hỏi lại năm lần, đúng thứ nút này sinh ra để tránh."""
    m = re.search(r"const REQ_SAMPLE=(\{.*?\});\n", page, re.S)
    assert m, "không tìm thấy REQ_SAMPLE"
    sample = json.loads(m.group(1))
    assert sample["project_id"] and len(sample["description"]) > 800
    desc = sample["description"].lower()
    for phan in ("bối cảnh", "mục tiêu", "người dùng", "phạm vi", "ngoài phạm vi", "ràng buộc",
                 "phi chức năng", "nghiệm thu"):
        assert phan in desc, f"yêu cầu mẫu thiếu phần {phan!r}"
    assert "repo" not in sample, "đường dẫn repo tuỳ máy người dùng: để trống cho họ tự điền"
    # ô nào mẫu điền cũng phải tồn tại trong định nghĩa form `req`
    form = page[page.index('{id:"req"'):page.index('{id:"ans"')]
    for k in sample:
        assert f'k:"{k}"' in form, f"mẫu điền ô {k} nhưng form không có ô đó"
    assert "sample:true" in form and "data-sample" in page, "form yêu cầu phần mềm phải có nút điền mẫu"


def test_mau_trong_giao_dien_va_mau_tren_dia_cung_mot_bo_khung(page: str) -> None:
    """`examples/yeu-cau-mau-web-app.json` (dùng cho CLI) và REQ_SAMPLE (dùng cho form) là hai bản của cùng một
    mẫu — lệch nhau thì người đọc tài liệu và người bấm nút nhận hai đề bài khác nhau."""
    disk = PAGE.parents[4] / "software-company" / "examples" / "yeu-cau-mau-web-app.json"
    if not disk.exists(): pytest.skip("không có software-company trong workspace này")
    on_disk = json.loads(disk.read_text(encoding="utf-8"))
    in_ui = json.loads(re.search(r"const REQ_SAMPLE=(\{.*?\});\n", page, re.S).group(1))
    assert on_disk["project_id"] == in_ui["project_id"]
    for phan in ("BỐI CẢNH", "NGOÀI PHẠM VI", "RÀNG BUỘC", "NGHIỆM THU"):
        assert phan in on_disk["description"], f"mẫu trên đĩa thiếu {phan}"
        assert phan.lower() in in_ui["description"].lower() or phan in in_ui["description"]
