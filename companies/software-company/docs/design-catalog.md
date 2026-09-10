# Sổ mẫu thiết kế — chỉ mục bài toán hạ tầng thường gặp

Mục đích: khi spec chạm một bài toán đã có lời giải chuẩn trong ngành, `product` (pha `research` và `plan`) có **tên mẫu**
để so, thay vì nghĩ lại từ đầu. Đây là **chỉ mục khái niệm**, không phải hướng dẫn: mỗi dòng cho tên bài toán,
mẫu thường dùng, đánh đổi phải nêu trong ADR, và skill giữ luật chi tiết.

Cách dùng: thấy bài toán trong PRD → tra dòng tương ứng → nêu ít nhất hai mẫu và lý do loại một mẫu trong ADR
(`architecture`, quy tắc ADR). Không có mẫu nào ở đây là bắt buộc; chọn sai mà có lý do ghi lại vẫn tốt hơn chọn
đúng mà không ai biết vì sao.

| Bài toán | Mẫu thường dùng | Đánh đổi phải nêu trong ADR | Skill giữ luật |
|---|---|---|---|
| Giới hạn tần suất (rate limit) | token bucket · leaking bucket · fixed window · sliding window log/counter | độ chính xác biên cửa sổ ↔ bộ nhớ; đặt ở gateway hay trong dịch vụ; hành vi khi kho đếm chết | `backend`, `api-contract` |
| Sinh ID duy nhất phân tán | UUIDv7 · Snowflake · sequence tập trung | ID có sắp thứ tự theo thời gian ↔ lộ thông tin nghiệp vụ; phụ thuộc đồng hồ | `database` |
| Phân bố dữ liệu theo node | consistent hashing · range partition · hash tĩnh | chi phí khi thêm/bớt node ↔ độ đều tải; hot key | `database`, `architecture` |
| Kho khóa–giá trị / cache | write-through · write-back · cache-aside; TTL và invalidation | nhất quán ↔ độ trễ; hành vi khi cache lạnh và khi cache chết (đừng để cache thành SPOF) | `database`, `observability` |
| Hàng đợi / hệ sự kiện | outbox · consumer idempotent · dead-letter queue · replay | at-least-once + idempotent ↔ exactly-once giả tưởng; thứ tự trong partition; tác dụng phụ khi phát lại | `event-driven-architecture` |
| Thông báo (push/email/SMS) | fan-out lúc ghi ↔ lúc đọc · nhà cung cấp có retry · chống trùng | chi phí ghi ↔ độ trễ đọc; người dùng đông người theo dõi | `backend` |
| Tìm kiếm / gợi ý | index đảo · trie tiền tố · công cụ tìm kiếm ngoài | độ tươi của index ↔ chi phí; đồng bộ index với nguồn sự thật | `backend`, `data-engineering` |
| Lưu trữ tệp lớn / đối tượng | upload nhiều phần · URL ký sẵn · dedupe theo băm · phiên bản | băng thông ↔ lưu trữ; xoá thật hay xoá mềm; quét mã độc | `platform`, `security` |
| Dữ liệu theo vị trí | geohash · quadtree · index không gian của CSDL | độ chính xác ↔ tốc độ truy vấn; cập nhật vị trí liên tục là tải ghi lớn | `backend`, `database` |
| Đo lường và cảnh báo | pull ↔ push · TSDB · lấy mẫu · cardinality | độ chi tiết ↔ chi phí lưu trữ; nhãn cardinality cao làm sập kho đo | `observability` |
| Gộp sự kiện theo thời gian | cửa sổ nhảy/trượt · watermark cho dữ liệu đến muộn · lambda/kappa | độ tươi ↔ độ đúng; xử lý dữ liệu đến muộn và dữ liệu trùng | `data-engineering` |
| Đặt chỗ / tồn kho có hạn | giữ chỗ có hạn dùng · khoá lạc quan theo version · idempotency key | chống bán vượt ↔ tranh chấp và độ trễ; hết hạn giữ chỗ | `backend`, `database` |
| Thanh toán | idempotency-key trên mọi lệnh ghi · đối soát (reconciliation) định kỳ với PSP · retry có backoff · sổ cái append-only | đồng bộ ↔ bất đồng bộ; tiền không được mất kể cả khi hệ thống hai bên lệch — đối soát là bắt buộc, không phải tuỳ chọn | `security`, `backend`, `privacy-compliance` |
| Bảng xếp hạng thời gian thực | sorted set trong bộ nhớ · gộp theo lô định kỳ | độ tươi ↔ chi phí; công bằng khi có gian lận | `backend` |

## Ghi chú
- Bảng này là điểm khởi đầu, không thay `tech-evaluation`: mẫu nào cũng phải so với thứ đã có trong stack trước khi
  thêm thành phần mới.
- Bài toán không có trong bảng thì làm theo `architecture` như thường; thấy bài toán lặp lại ≥ 2 dự án thì thêm
  một dòng vào đây trong cùng PR.
- Đối chiếu với hiện trạng của chính hệ thống này ở `docs/standards.md` mục "Công ty tự áp dụng gì" — dòng "hàng đợi"
  và "thanh toán" là hai chỗ hệ thống này đang tự nhận còn thiếu (outbox, idempotency key mức consumer).
