# TRAPS.md — bẫy riêng của console

Console không chạy sai; nó **hiển thị đúng số nhưng người đọc hiểu sai**. Đêm 2026-09-05/06 vận hành QLKH mất hàng
giờ vì đọc sai trạng thái. Mười chỗ dưới đây là chuyện thật, ghi để không thiết kế lại cùng cái bẫy. Một số đã sửa
ở #76/#80; cột cuối nói còn gì.

| # | Bẫy hiển thị | Đã xảy ra | Trạng thái |
|---|---|---|---|
| 1 | Nhãn `merged` ≠ đã gộp vào nhánh tích hợp | 14/14 ticket có merge commit thật; bảng hiện 10 `approved`, 4 `merged` — `merged` chỉ đổi khi release deploy | #76 tách sự thật git; giữ nguyên tắc khi thêm cột |
| 2 | `status` xanh toàn tập khi dự án chết đứng | `queue: 0, blocked: [], gates: {}` — xanh vì RỖNG; 18/19 release không đi đâu | #76 "bế tắc im lặng"; cần chỉ số "còn việc nào chạy được không" |
| 3 | `delivery: {}` | Nghĩa là chưa từng giao — 0 tag, 0 production — nhìn suốt đêm không nhận ra | #76 "đã giao n/m" lên tiêu đề |
| 4 | Không thấy phễu release | 4 staging/failed, 6 pending_human, 3 deployed, 5 void, 0 production — phải truy vấn tay | #76 phễu RC → staging → qa → gate 3 → production → tag |
| 5 | Chỉ hiện "gate chờ", không hiện `kind` và hậu quả | Duyệt `escalation` cho REL-xxx tưởng đã giao hàng; chỉ `kind=release` mới deploy | #76 gate kèm hậu quả; giữ khi thêm gate mới |
| 6 | Quyết định xếp sau lượt model dài, nhìn như vô tác dụng | Duyệt 01:34, áp 01:48; dashboard im | #76 "quyết định chưa áp" + việc đang chạy bao lâu |
| 7 | Ticket `blocked` không có gate = im lặng chết | QLKH-010/014: khoá `once` trùng, không ai được hỏi, vẫn xanh | Cảnh báo riêng — là bế tắc, không phải "đang chờ người" |
| 8 | Verdict trên bằng chứng đã bị cắt, không ai thấy là cắt | security chặn vì "thiếu diff" — openapi 804 dòng ăn hết hạn mức | company #67/#87; console nên hiện "diff bị cắt: n file" cạnh verdict |
| 9 | Ngân sách so tổng token với đầu ra | Số "vượt ngân sách" sai bản chất | #76: mỗi con số ghi rõ đo cái gì (`tokens` vs `output_tokens`) |
| 10 | Lý do duyệt "ok" đi qua | Agent nhận hint rỗng (13:05 2026-09-06) | #80 khoá < 20 ký tự cho escalation; cân nhắc áp cho mọi kind |

## Bẫy kỹ thuật

| Bẫy | Vì sao | Chốt chặn |
|---|---|---|
| Service worker cache `/` hoặc `/api/*` | `/` mang token phiên sinh mới mỗi lần chạy → lần sau 401 toàn tập; `/api` cũ là số liệu cũ | SW chỉ cache 2 icon; test kiểm |
| Bind ra ngoài loopback | SW không đăng ký, PWA không cài; và mở cửa cho mạng | `--i-know` bắt buộc; mặc định 127.0.0.1 |
| `enabled: false` cho backend không tắt thật | `company.llm.load_config` bỏ qua khoá lạ | `settings.py` "tắt phải tắt thật" — xoá khỏi `backends` hoặc cơ chế công ty hiểu |
| Vẽ đè dữ liệu mới lên ngăn kéo đang mở | Người đang đọc mất chỗ | Giữ lại + nút "Có dữ liệu mới — xem" |

## Nguyên tắc rút ra cho mọi màn mới

Trước khi thêm một con số lên trang, trả lời ba câu: *nó đo cái gì đúng nghĩa đen?* · *nó xanh vì tốt hay vì rỗng?*
· *người thấy nó sẽ làm gì tiếp — và làm thế có đúng không?* Không trả lời được câu ba thì chưa đưa lên.
