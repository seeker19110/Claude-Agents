"""Console một view (ADR-0011 §5 giai đoạn 5/5, `docs/thi-hanh/adr113.md`).

Trực ban trước đây là 8 màn ẩn/hiện qua sidebar (`.view{display:none}` + `.view.on{display:flex}`, toggle bằng
JS trong `showView`) — chỉ MỘT màn nhìn thấy tại một thời điểm. Sáu màn "thông tin" (Trực ban, Phễu sản phẩm,
Xưởng phần mềm, Công ty bảo trì, Chi phí, Nhật ký) nay LUÔN hiển thị cùng lúc trên một trang cuộn dài; sidebar
không còn ẩn/hiện nữa mà chỉ cuộn tới đúng mục (mục lục). `Cài đặt` và `Hướng dẫn` không phải "thông tin vận
hành" (một là form sửa cấu hình, một là tài liệu tĩnh) — giữ nguyên hành vi ẩn/hiện cũ để không đổi ngữ nghĩa
quyền hạn (`--allow-config`) hay lẫn tài liệu tĩnh vào giữa luồng cuộn theo dõi.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "src" / "console" / "static"
HTML = STATIC / "index.html"
ROUTER = STATIC / "js" / "router.js"

INFO_VIEWS = ("truc-ban", "phieu", "phan-mem", "bao-tri", "chi-phi", "nhat-ky")
TOGGLE_VIEWS = ("cai-dat", "huong-dan")


@pytest.fixture(scope="module")
def html() -> str:
    return HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def router() -> str:
    return ROUTER.read_text(encoding="utf-8")


def test_sau_man_thong_tin_luon_hien_khong_can_class_on(html: str) -> None:
    """CSS gốc của `.view` không còn `display:none` mặc định — nếu còn thì sáu màn thông tin biến mất cho tới
    khi JS gán `.on`, đúng lỗi cũ mà `console một view` phải sửa."""
    m = re.search(r"\.view\{[^}]*\}", html)
    assert m, "không tìm thấy khối CSS `.view{...}`"
    assert "display:none" not in m.group(0), "`.view` không được ẩn mặc định nữa — sáu màn thông tin phải luôn hiện"


def test_showview_khong_con_an_hien_bang_classlist_toggle(router: str) -> None:
    """`showView` cũ ẩn/hiện bằng `x.classList.toggle("on", x.id==="v-"+v)` trên MỌI `.view` — hành vi đó phải
    biến mất cho sáu màn thông tin (dòng `$$(\".view\")...classList.toggle` không còn áp dụng đồng loạt)."""
    assert 'x.classList.toggle("on",x.id==="v-"+v)' not in router, \
        "showView vẫn ẩn/hiện .view đồng loạt bằng classList.toggle — chưa chuyển sang cuộn"


def test_showview_cuon_toi_dung_muc_thay_vi_an_hien(router: str) -> None:
    """Nav giờ là mục lục: bấm một mục phải CUỘN tới đúng section, không còn nghĩa "chuyển màn" (ẩn màn khác)."""
    assert "scrollIntoView" in router, "showView phải cuộn tới section — nav giờ là mục lục, không phải công tắc ẩn/hiện"


@pytest.mark.parametrize("v", INFO_VIEWS)
def test_moi_man_thong_tin_co_section_that(html: str, v: str) -> None:
    assert f'id="v-{v}"' in html


def test_hai_man_khong_phai_thong_tin_van_an_hien_binh_thuong(router: str) -> None:
    """`cai-dat` (form sửa cấu hình, quyền `--allow-config`) và `huong-dan` (tài liệu tĩnh) KHÔNG phải "thông
    tin vận hành" nêu trong đề bài — giữ nguyên gọi `loadSettings`/`renderGuide` khi điều hướng tới, như trước
    khi đổi sang cuộn (test đã có `test_man_huong_dan_render_bang_quyen_theo_dung_co_dang_chay` canh phần này)."""
    for v, fn in (("cai-dat", "loadSettings"), ("huong-dan", "renderGuide")):
        assert f'if(v==="{v}") {fn}();' in router


def test_render_ban_dau_da_ve_ca_sau_man_thong_tin() -> None:
    """`render()` trong `main.js` đã gọi renderDelivery/renderQueue/renderKeeper/renderProductFunnel/renderTables
    v.v. KHÔNG điều kiện theo view — đây là lý do gộp một view rẻ (không cần vẽ lại gì thêm). Test này khẳng
    định bất biến đó KHÔNG bị vô tình bọc lại trong điều kiện `if(view===...)` khi ai đó "tối ưu" sau này."""
    main = (STATIC / "js" / "main.js").read_text(encoding="utf-8")
    for fn in ("renderDelivery", "renderQueue", "renderKeeper", "renderProductFunnel", "renderTables", "renderBoards"):
        assert f" {fn}();" in main, \
            f"{fn}() phải được gọi KHÔNG điều kiện trong render() — nếu không sáu màn cuộn chung sẽ có ô rỗng"
