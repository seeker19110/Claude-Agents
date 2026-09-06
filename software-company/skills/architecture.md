---
name: architecture
version: 3
standards: [C4 model, arc42, Clean/Hexagonal, DDD, ADR (Nygard), ISO/IEC 25010, Fitness functions, Back-of-the-envelope estimation]
---
# Skill: architecture

## Tiêu chuẩn tham chiếu
- C4 model (Context → Container → Component → Code)
- arc42 (khung tài liệu kiến trúc)
- Clean / Hexagonal (ports & adapters): nghiệp vụ không phụ thuộc hạ tầng
- DDD: bounded context, ubiquitous language, context map
- ADR theo Nygard: bối cảnh, quyết định, hệ quả, phương án bị loại
- ISO/IEC 25010 cho thuộc tính chất lượng; fitness function để giữ kiến trúc không trôi
- Ước lượng nháp (back-of-the-envelope): quy mô nghiệp vụ → tải kỹ thuật, trước khi chọn cấu trúc

## Quy trình (làm đúng thứ tự)
Đọc yêu cầu và NFR đã có số đo → **ước lượng tải nháp nếu NFR chưa có số** (mục dưới) → xác định bounded context và ngôn ngữ chung → vẽ C4 L1 (context) và L2 (container) → chọn kiểu tích hợp giữa container (đồng bộ hay event) → viết ADR cho mọi quyết định không hiển nhiên → chốt contract (`api-contract`) → định nghĩa fitness function và ngưỡng → viết mục "Hạn chế đã biết" → chỉ khi đó mới sinh ticket đầu tiên.
Không vẽ C4 L3/L4 trước khi code — mức đó sinh từ code, không vẽ tay.

## Quy tắc — ranh giới và phụ thuộc
- Ranh giới module theo bounded context nghiệp vụ, không theo lớp kỹ thuật; một context có một chủ sở hữu dữ liệu, các context khác đọc qua contract chứ không đọc thẳng bảng.
- Phụ thuộc chỉ hướng vào trong: domain không import framework, DB, HTTP client; hạ tầng cắm vào qua port. Kiểm bằng test phụ thuộc (import-linter, ArchUnit hoặc tương đương).
- Không vòng phụ thuộc giữa module; phát hiện vòng là finding block.
- Chia nhỏ dịch vụ chỉ khi có lý do rõ (nhịp triển khai, quy mô, ranh giới nhóm, cách ly rủi ro); mặc định là modular monolith. Mỗi lần tách phải trả lời được: dữ liệu chia thế nào, giao dịch xử lý ra sao, ai gọi ai khi lỗi.

## Quy tắc — thuộc tính chất lượng và đánh đổi
- Mỗi NFR quan trọng (hiệu năng, sẵn sàng, bảo mật, chi phí, khả năng thay đổi) phải chỉ ra được nó được thỏa mãn bằng cấu trúc nào; NFR không gắn được vào cấu trúc là NFR chưa đủ rõ, trả về `requirements-engineering`.
- Kiến trúc phải nêu đánh đổi bằng chữ: được gì, mất gì, ngưỡng nào thì quyết định này sai. Không có "tốt nhất", chỉ có "phù hợp trong bối cảnh này".
- Mỗi điểm lỗi đơn (single point of failure) hoặc phụ thuộc bên ngoài phải có cách xử lý khi hỏng: timeout, retry có backoff, circuit breaker, suy giảm chức năng có kiểm soát.
- Tính đúng đắn trước tính nhanh: đặt ranh giới giao dịch rõ ràng, nêu chỗ nào chấp nhận nhất quán cuối (eventual consistency) và hệ quả người dùng nhìn thấy.
- Chọn kỹ thuật theo `tech-evaluation`; ưu tiên thứ đã có trong stack nếu đáp ứng; mọi thứ mới đều là chi phí vận hành lâu dài.

## Quy tắc — ước lượng tải nháp (làm khi NFR chưa có số)
- Khách nói "khoảng 10.000 người dùng" là quy mô nghiệp vụ, không phải NFR. Đổi nó thành tải kỹ thuật TRƯỚC khi
  chọn cấu trúc, bằng số tròn và giả định ghi thành lời — đừng chờ `performance-testing` vì lúc đó code đã viết xong.
- Sáu số tối thiểu, theo đúng thứ tự này: DAU (từ MAU × tỉ lệ hoạt động) → QPS trung bình = DAU × số hành động ÷ 86.400
  → QPS đỉnh (mặc định 2× trung bình, ghi rõ nếu nhịp truy cập lệch hơn) → dung lượng lưu trữ mỗi ngày và sau N năm
  → dung lượng cache (mặc định 20% dữ liệu nóng) → số máy/instance cần, dùng Little's Law (concurrency = throughput × latency).
- Mọi giả định ghi thành dòng riêng có nguồn ("khách nói", "so với dự án X trong `knowledge`", "đoán"); phần "đoán"
  phải được đánh dấu là câu hỏi mở trong PRD §10, không trộn lẫn với phần có nguồn.
- Ghi đủ đơn vị và bậc độ lớn; sai một bậc là sai kiến trúc. Số tròn hơn số đẹp — mục tiêu là chọn đúng cấu trúc,
  không phải dự báo chính xác.
- Đối chiếu với mốc vật lý trước khi tin kết quả: bộ nhớ chính ~100 ns, đọc SSD ngẫu nhiên ~150 µs, round-trip trong
  một trung tâm dữ liệu ~500 µs, giữa các vùng ~150 ms. Thiết kế đòi hỏi nhanh hơn mốc vật lý là thiết kế sai.
- Mục tiêu sẵn sàng cũng phải quy ra thời gian chết để khách hiểu mình đang mua gì: 99% ≈ 3,65 ngày/năm,
  99,9% ≈ 8,8 giờ/năm, 99,99% ≈ 52 phút/năm, 99,999% ≈ 5,3 phút/năm. Mỗi số 9 thêm vào là chi phí vận hành thêm —
  nêu chi phí đó cùng lúc (`cost-estimation`, `finops`), đừng hứa suông.
- Kết quả ước lượng đi vào namespace `architecture` và quay ngược thành điều kiện đo của NFR trong PRD §6
  (`requirements-engineering`); `performance-testing` sau này kiểm chính những số này, không tự đặt số mới.

## Quy tắc — hạn chế đã biết (viết lúc thiết kế, không đợi review)
- Mỗi kiến trúc phải có mục "Hạn chế đã biết" trong namespace `architecture`, viết CÙNG LÚC với thiết kế: cái gì
  cố tình chưa làm, ngưỡng nào thì thiết kế này hết chịu được, và bước tiếp theo nếu chạm ngưỡng.
- Mỗi hạn chế có một mã nợ ổn định để supervisor đếm được qua nhiều review (ADR-0032); nợ đã khai từ đầu vẫn là nợ,
  nhưng nó là nợ có tên và có ngưỡng, khác với nợ bị né qua từng ticket.
- Hạn chế không có ngưỡng bằng số là hạn chế chưa viết xong: "chưa scale tốt" không dùng được, "trên 500 QPS thì
  tầng đọc phải tách replica" thì dùng được.
- Không dùng mục này để hợp thức hoá việc bỏ NFR bắt buộc: NFR Must mà thiết kế không đáp ứng thì trả về
  `requirements-engineering` để cắt phạm vi có chữ ký, không ghi xuống thành "hạn chế".

## Quy tắc — ADR và bảo trì kiến trúc
- ADR cho mọi quyết định không hiển nhiên: chọn CSDL, kiểu tích hợp, cách xác thực, chia dịch vụ, chấp nhận nợ kỹ thuật, chấp nhận rủi ro. Nêu tối thiểu hai phương án bị loại và lý do.
- ADR bất biến: thay đổi quan điểm thì viết ADR mới trạng thái `supersedes`, không sửa ADR cũ.
- Fitness function chạy trong CI: kiểm hướng phụ thuộc, kích thước bundle hoặc thời gian khởi động, ngân sách hiệu năng, số truy vấn cho luồng chính.
- Sơ đồ C4 sống trong repo dạng text (Mermaid/Structurizr), cập nhật cùng PR làm nó lệch; sơ đồ ảnh dán tay không được chấp nhận.
- Kiến trúc là đầu vào của `threat-modeling` và `cost-estimation`; đổi kiến trúc thì cập nhật cả hai.

## Checklist (supervisor và human gate dùng để chấm)
- [ ] C4 L1–L2 dạng text có trong repo trước ticket đầu tiên
- [ ] Có ước lượng tải nháp (DAU, QPS trung bình và đỉnh, lưu trữ, cache, số máy) với giả định ghi thành lời và nguồn của từng giả định
- [ ] Mục "Hạn chế đã biết" có mã nợ và ngưỡng bằng số cho từng hạn chế
- [ ] Bounded context và chủ sở hữu dữ liệu rõ; không context nào đọc thẳng dữ liệu của context khác
- [ ] Mọi quyết định không hiển nhiên có ADR với phương án bị loại và hệ quả
- [ ] Mỗi NFR quan trọng ánh xạ được vào một quyết định kiến trúc
- [ ] Mỗi phụ thuộc ngoài có timeout, retry, và hành vi khi hỏng
- [ ] Fitness function (hướng phụ thuộc, ngân sách hiệu năng) chạy trong CI
- [ ] Contract-first: contract chốt trước khi sinh ticket hiện thực
- [ ] Threat model và ước lượng chi phí cập nhật theo kiến trúc

## Ví dụ tốt
ADR-0007: chọn PostgreSQL thay MongoDB vì cần giao dịch đa bảng cho đặt hàng và hoàn tiền; loại MongoDB (yếu ACID đa document ở phiên bản đang dùng) và loại kiến trúc hai CSDL (chi phí vận hành gấp đôi, chưa đủ tải để bù). Hệ quả: đọc báo cáo nặng phải làm replica, ghi trong ADR-0011. Fitness function: `import-linter` chặn `domain` import `sqlalchemy`.
Ước lượng nháp kèm theo: 200k MAU × 40% = 80k DAU, 5 hành động/ngày → 4,6 QPS trung bình, đỉnh 10 QPS; đơn hàng 2 KB × 400k/ngày → 0,8 GB/ngày, 1,5 TB sau 5 năm; cache 20% dữ liệu nóng ≈ 300 GB. Giả định "5 hành động/ngày" là đoán, đã ghi thành câu hỏi mở PRD §10. Hạn chế đã biết: `AD-01` — tầng đọc dùng chung primary, trên 500 QPS đọc phải tách replica (ADR-0011).

## Ví dụ xấu
"Dùng Postgres." Không bối cảnh, không phương án loại, không hệ quả; sơ đồ kiến trúc là ảnh PNG vẽ từ 6 tháng trước; domain import trực tiếp ORM nên không test được nếu không có DB. Không ai đổi "10.000 người dùng" của khách ra QPS, nên chọn kiến trúc sự kiện cho tải 3 QPS; mục hạn chế viết "hiện tại chưa scale tốt" — không ngưỡng, không mã nợ, nên ba sprint sau không ai biết đã chạm chưa.
