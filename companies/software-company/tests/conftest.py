import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@contextmanager
def serving(handler_cls: type[BaseHTTPRequestHandler]):
    """Server HTTP cục bộ cho test, tự đóng socket khi ra khỏi khối.

    Trước đây mỗi test tự `HTTPServer(...)` rồi bỏ đó: socket không đóng làm pytest cảnh báo ResourceWarning
    (nay là lỗi, xem `filterwarnings` trong pyproject) và cổng đọng lại giữa các test trên CI."""
    srv = HTTPServer(("127.0.0.1", 0), handler_cls)
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    try:
        yield srv, f"http://127.0.0.1:{srv.server_port}"
    finally:
        srv.shutdown(); t.join(timeout=5); srv.server_close()


@pytest.fixture
def local_server():
    """Fixture bản của `serving`: `with local_server(Handler) as (srv, base):`"""
    return serving


@pytest.fixture(autouse=True)
def home_rieng(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """MỌI ca chạy với `$HOME` riêng — bộ test không bao giờ đọc cấu hình thật của người đang chạy nó.

    Từ ADR-0016, `load_config()` đọc tầng máy ở `~/.config/xagents/llm.yaml` **dù có truyền `path` hay không**.
    Nên bất kỳ ca nào chạm `load_config`/`explain_config` mà không tự đặt `XAGENTS_LLM_CONFIG` đều lệ thuộc vào
    việc máy chạy test có file ấy hay không. Đo 2026-09-15 ngay sau khi tạo file theo đúng ADR: 3 ca đỏ, trong
    đó `test_khong_co_file_thi_van_ra_cau_hinh_mac_dinh` có từ TRƯỚC ADR-0016 — tức bản vá cũ làm hỏng phép thử
    cũ mà CI không thấy.

    Vì sao đặt ở `conftest.py` chứ không vá từng ca: xanh trên CI (máy sạch) và đỏ trên máy người phát triển đã
    làm theo ADR — cổng phạt đúng người làm đúng, ở chỗ khó đoán nhất. Vá từng ca thì ca thứ tư chỉ là chuyện
    thời gian.

    Ca nào cần một tầng máy THẬT vẫn tự trỏ `XAGENTS_LLM_CONFIG` vào `tmp_path`; fixture này không đụng tới.
    """
    # Tao MOT lan roi tra ve chinh no: `mktemp` goi moi lan mot thu muc khac, nen `Path.home()` trong test
    # va `Path.home()` ben trong `may_config_file` se ra hai duong dan khac nhau — dung cai bay minh vua chan.
    nha = tmp_path_factory.mktemp("home")
    monkeypatch.setattr(Path, "home", lambda: nha)
