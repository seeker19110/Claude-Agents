# ADR-0002: Console đẩy trạng thái bằng SSE, và địa chỉ mang trạng thái màn hình

Trạng thái: Accepted · Ngày: 2026-09-03

## Bối cảnh
ADR-0001 chọn `fetch` mỗi 10 giây và một trang không có định tuyến, với lý do "trang này là bảng số và vài biểu đồ
SVG". Sau một thời gian dùng thật, ba chỗ đau lộ ra và đều thuộc về *thao tác*, không phải về dữ liệu:

1. **Trễ tới 10 giây trên đúng thứ gấp nhất.** Console tồn tại vì hàng đợi human gate: công việc của cả công ty
   dừng cho tới khi người chủ dự án quyết. Một gate mới xuất hiện mà mặt kính im lặng mười giây là mười giây
   người vận hành ngồi nhìn màn hình cũ, và họ học cách bấm F5 — đúng thứ mà một mặt kính phải làm cho họ khỏi làm.
2. **Địa chỉ không mang chỗ đang đứng.** F5 văng về Trực ban, không gửi được link tới đúng một gate cho người khác,
   nút Back của trình duyệt rời hẳn trang thay vì đóng ngăn kéo.
3. **Không lọc được.** Mọi bảng đổ hết ra; muốn tìm một ticket thì dùng Ctrl+F của trình duyệt, mà nó không biết
   bảng nào đang bị ẩn.

Ràng buộc của ADR-0001 vẫn còn nguyên hiệu lực: chỉ thư viện chuẩn, không framework, không bước build.

## Quyết định
1. **Thêm `GET /api/stream` (Server-Sent Events), giữ nguyên `GET /api/state`.** Server dò dấu vân tay
   `(st_mtime_ns, st_size)` của hai file bus mỗi giây; đổi thì `collect()` và đẩy một khung `event: state`.
   Nhịp tim `: ping` 15 giây giữ kết nối và là chỗ duy nhất phát hiện client đã đóng.
   Chọn SSE chứ không WebSocket: luồng một chiều, server→client, `http.server` phục vụ được bằng chính
   `wfile` mà không cần thư viện nào; WebSocket phải tự viết handshake và framing, tức là tự viết một thư viện.
   Chọn dò `stat()` chứ không `sqlite3` hook hay watchdog: rẻ, không thêm phụ thuộc, và không đụng vào file
   mà một tiến trình khác đang ghi.
2. **Trang đọc stream bằng `fetch` + `ReadableStream`, không dùng `EventSource`.** `EventSource` không đặt được
   header, mà token phiên chỉ được đi ở `X-Console-Token`: nhét token vào query string là ghi thẳng token ra log
   server, vì `log_message` ghi nguyên dòng request. Bảo mật của ADR-0001 thắng sự tiện của API sẵn có.
3. **Stream là đường nhanh, không phải đường duy nhất.** Nối hỏng hoặc đứt giữa chừng thì trang lùi về hỏi
   `/api/state` mỗi 10 giây — đúng hành vi cũ — và thử nối lại với backoff gấp đôi, trần 60 giây. Trang nói rõ
   đang ở chế độ nào (*trực tiếp* / *hỏi lại 10s*). Mất SSE là chậm hơn, không phải hỏng.
4. **Không vẽ đè dưới tay người đang đọc.** Ngăn kéo đang mở hoặc đã bấm Tạm dừng thì trạng thái mới được giữ
   lại và trang hiện nút *Có dữ liệu mới — xem*. Trước đây vấn đề này được giải bằng cách ngưng hẳn việc làm mới;
   với luồng đẩy thì không ngưng được nguồn, nên phải ngưng ở chỗ vẽ.
5. **Địa chỉ mang trạng thái màn hình**: `#/<màn>` và `#/<màn>/<gate|ticket|video>/<id>`. Dùng hash chứ không
   `history.pushState` vì server chỉ phục vụ một đường `/`; đẩy đường dẫn thật vào thanh địa chỉ thì F5 ăn 404.
   Địa chỉ trỏ tới id không còn tồn tại thì tự rút về màn tương ứng.
6. **Lọc, tìm và sắp xếp hoàn toàn phía client**, trên dữ liệu `/api/state` đã có. Không thêm tham số truy vấn nào
   vào API: bộ dữ liệu là hàng chục tới hàng trăm dòng, lọc trong bộ nhớ là tức thì, còn đẩy việc lọc xuống server
   sẽ biến một API đọc-tất-cả thành một API có trạng thái truy vấn — đắt hơn nhiều so với thứ nó giải.

## Đã cân nhắc và bỏ
- **Rút nhịp hỏi xuống 1–2 giây.** Không thêm code, nhưng biến một mặt kính chỉ đọc thành nguồn tải đều đặn lên
  chính con SQLite mà orchestrator đang ghi, kể cả khi chẳng có gì đổi. SSE đắt hơn đúng một `stat()` mỗi giây.
- **WebSocket.** Hai chiều, nhưng ở đây không có chiều nào từ client (quyết định gate vẫn là POST bình thường,
  và phải như vậy để đi qua đúng `HumanGate`). Đổi lại là tự viết handshake và framing bằng tay.
- **Lật ADR-0001 để dùng React/Vue + router.** Bốn chỗ đau ở trên đều giải được bằng ~150 dòng JS thuần. Đổi lấy
  một bước build, một cây `node_modules` và một dòng CVE mới trong hub Python thuần là không tương xứng.
- **`history.pushState` cho địa chỉ đẹp hơn.** Cần server trả `index.html` cho mọi đường dẫn con, tức là một
  catch-all làm nhoè ranh giới "đường nào có thật" mà `do_GET` đang giữ rất rõ. Hash không cần server biết gì.
- **Lọc phía server.** Xem quyết định 6.

## Hệ quả
- `/api/stream` giữ một thread cho mỗi tab đang mở (`ThreadingHTTPServer`, `daemon_threads`). Console là công cụ
  một người dùng chạy cục bộ nên số tab là một chữ số; nếu sau này không còn đúng thì phải xem lại chỗ này trước.
- Console giờ đọc `collect()` mỗi khi bus đổi chứ không phải mỗi 10 giây. Bus bận thì đọc dày hơn trước — vẫn chỉ
  đọc, vẫn append-only, nhưng đây là chỗ đầu tiên cần nhìn nếu console làm chậm orchestrator.
- `ConsoleServer` có thêm `stream_max_seconds` để test bó vòng lặp đẩy; chạy thật luôn là `None`.
- Hợp đồng ba lớp trong `API.md` phải tả cả sơ đồ địa chỉ, vì nó là bề mặt người dùng dán link cho nhau.
