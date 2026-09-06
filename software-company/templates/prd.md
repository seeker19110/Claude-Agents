# PRD: <tên dự án> — v<x.y>

## 1. Bối cảnh
## 2. Mục tiêu (có số đo)
## 3. Phạm vi
### In-scope
### Out-of-scope
## 4. User story
- US-01 (REQ-xx): Là <ai>, tôi muốn <gì> để <tại sao>
  ```gherkin
  Given ... When ... Then ...
  ```
## 5. Trải nghiệm người dùng (link `design`)
| US | Flow | Màn hình | Trạng thái (empty/loading/error/success) | A11y |
## 6. Yêu cầu phi chức năng (map ISO 25010)
| ID | Đặc tính | Số đo | Điều kiện đo (tải, cỡ dữ liệu, phân vị) |
### 6b. Ước lượng tải nháp (nguồn của cột "Điều kiện đo"; xem skill `architecture`)
| Đại lượng | Giá trị | Giả định | Nguồn giả định (khách / `knowledge` / đoán) |
| MAU → DAU | | | |
| QPS trung bình | | | |
| QPS đỉnh | | | |
| Lưu trữ / ngày → sau N năm | | | |
| Cache (dữ liệu nóng) | | | |
| Sẵn sàng mục tiêu → thời gian chết/năm | | | |
Giả định nguồn "đoán" phải xuất hiện lại ở §10 dưới dạng câu hỏi mở.
## 7. Dữ liệu cá nhân
| Trường | Phân loại | Mục đích | Cơ sở pháp lý | Retention |
## 8. Quyết định công nghệ (link ADR)
## 8b. Chạy ở đâu / runtime (điều kiện cần của Gate 1 — ADR-0031; orchestrator dùng để smoke — ADR-0029)
| Trường | Giá trị |
| `kind` | <`application` (có điểm vào chạy được — BẮT BUỘC `command`) \| `library` \| `docs` — library/docs miễn runtime nhưng PHẢI khai rõ; bỏ trống = application> |
| `command` | <lệnh khởi động, vd `python -m app --port {port}`> |
| `port` | <0 = tự chọn> |
| `health` | <đường GET trả 200 dùng cho smoke, vd `/health`> |
| `dependencies` | <phụ thuộc ngoài: DB, cache, cloud — hoặc "không, chạy in-memory được"> |
Bảng này khớp 1-1 với `approved-specs.payload.kind` và `payload.runtime`; thiếu (khi `kind=application`) thì
orchestrator không mở gate spec mà trả lại spec-writer.
## 9. Rủi ro đã chấp nhận (link threat-model, người ký)
## 10. Giả định và câu hỏi mở
## 11. Bảng truy vết
| REQ | US | Ticket | Test |
