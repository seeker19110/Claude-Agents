# CODEMAP.md — console: muốn đổi X thì sửa ở đâu

Hợp đồng nội bộ giữa các lớp (hình dạng dữ liệu, route, hash): [`API.md`](API.md) — sửa lớp nào thì sửa mục đó cùng PR.

| Muốn | Sửa | Ghi chú |
|---|---|---|
| Đọc thêm bảng/topic từ bus hai công ty | `src/console/collect.py` | mở SQLite `mode=ro`; mỗi công ty một nhánh đọc |
| Phễu release, bế tắc im lặng, quyết định chưa áp, "đã giao n/m" | `src/console/truth.py` | lớp "sự thật giao hàng" (#76): tách sự thật git khỏi nhãn FSM |
| Phễu **sản phẩm** (yêu cầu → … → nghiệm thu), ô rỗng là ô xám, smoke từng bậc | `src/console/truth.py` `product_funnel()`; màn `#/phieu` trong `index.html` | ADR-0003 mục 2–3: `empty=True` đến từ tầng dữ liệu, không do CSS đoán |
| Hậu quả gate CẢ HAI CHIỀU (duyệt → agent nào; từ chối → về đâu) | `src/console/truth.py` `gate_effect` / `gate_reject_effect` / `gate_next_agent` | mỗi xưởng tự khai; không biết thì trả `""`, không đoán |
| Cảnh báo bế tắc im lặng riêng ở đầu trang | `truth.py` `silent_ticket_deadlocks()`; `#s-silent` trong `index.html` | ticket kẹt **không gate nào chờ** ≠ "đang chờ người" |
| Cột "commit vượt integration" | `src/console/git_truth.py` (+ `CompanyView._ahead` trong `collect.py`) | `git rev-list --count`, KHÔNG `branch --contains`; repo đọc từ audit `project.repo` |
| Hồ sơ `gate_brief` trong ngăn kéo gate | `src/console/brief.py`; route `GET /api/gate/brief` | gọi thẳng `company.gate_brief`; không chép lại logic, không cần `--allow-decide` |
| Duyệt / từ chối gate, kiểm lý do, four-eyes | `src/console/decide.py` | gọi `HumanGate` của công ty; không tự dựng event |
| Form giao việc (yêu cầu phần mềm + repo, trả lời làm rõ, brief kênh) | `src/console/submit.py` | publish qua `SQLiteBus` công ty → JSON Schema kiểm |
| Xem/đổi model, backend, `prefer`, tắt backend | `src/console/settings.py`; CLI `python -m console models` | ghi `llm.yaml` giữ `.bak`; "tắt phải tắt thật" |
| Route HTTP, SSE `/api/stream`, token phiên, cờ `--allow-*`, `--i-know` | `src/console/server.py` | 403 khi không có cờ |
| Giao diện, màn, ngăn kéo, tìm/lọc, phím tắt, PWA, hash `#/<màn>/gate/<id>` | `src/console/static/index.html` | một file, không framework; SW chỉ cache icon |
| Tab Hướng dẫn, "Điền yêu cầu mẫu" | `index.html`; mẫu lấy từ `software-company/examples/yeu-cau-mau-web-app.json` | giữ hai bản khớp |
| Kiến trúc | `docs/adr/` 0001–0003 | 0003: mỗi ô trả lời một câu hỏi, ô rỗng là ô xám |
| Bẫy hiển thị | `TRAPS.md` | 10 chỗ đã đánh lừa người trực |
