# CODEMAP.md — console: muốn đổi X thì sửa ở đâu

Hợp đồng nội bộ giữa các lớp (hình dạng dữ liệu, route, hash): [`API.md`](API.md) — sửa lớp nào thì sửa mục đó cùng PR.

| Muốn | Sửa | Ghi chú |
|---|---|---|
| Đọc thêm bảng/topic từ bus hai công ty | `src/console/collect.py` | mở SQLite `mode=ro`; mỗi công ty một nhánh đọc |
| Phễu release, bế tắc im lặng, quyết định chưa áp, "đã giao n/m" | `src/console/truth.py` | lớp "sự thật giao hàng" (#76): tách sự thật git khỏi nhãn FSM |
| Duyệt / từ chối gate, kiểm lý do, four-eyes | `src/console/decide.py` | gọi `HumanGate` của công ty; không tự dựng event |
| Form giao việc (yêu cầu phần mềm + repo, trả lời làm rõ, brief kênh) | `src/console/submit.py` | publish qua `SQLiteBus` công ty → JSON Schema kiểm |
| Xem/đổi model, backend, `prefer`, tắt backend | `src/console/settings.py`; CLI `python -m console models` | ghi `llm.yaml` giữ `.bak`; "tắt phải tắt thật" |
| Route HTTP, SSE `/api/stream`, token phiên, cờ `--allow-*`, `--i-know` | `src/console/server.py` | 403 khi không có cờ |
| Giao diện, màn, ngăn kéo, tìm/lọc, phím tắt, PWA, hash `#/<màn>/gate/<id>` | `src/console/static/index.html` | một file, không framework; SW chỉ cache icon |
| Tab Hướng dẫn, "Điền yêu cầu mẫu" | `index.html`; mẫu lấy từ `software-company/examples/yeu-cau-mau-web-app.json` | giữ hai bản khớp |
| Kiến trúc | `docs/adr/` 0001–0002 | |
| Bẫy hiển thị | `TRAPS.md` | 10 chỗ đã đánh lừa người trực |
