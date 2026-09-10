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
