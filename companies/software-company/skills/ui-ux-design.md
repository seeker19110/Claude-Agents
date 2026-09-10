---
name: ui-ux-design
version: 6
standards: [ISO 9241-210, WCAG 2.2 AA, Nielsen 10 heuristics, Material 3 / HIG, Design tokens W3C]
sources: [ui-ux-pro-max-skill (MIT) — rule sinh thiết kế, ui-ux-craftsman (dự án Đồng Hành) — quy trình và quy tắc form, impeccable (pbakaus, MIT) — danh mục anti-pattern mặc định của AI, hallmark (Nutlope, MIT) — vân tay cấu trúc, tự chấm trước khi giao, cổng chống "mùi LLM"]
---
# Skill: ui-ux-design

## Tiêu chuẩn tham chiếu
- ISO 9241-210 (thiết kế lấy người dùng làm trung tâm)
- WCAG 2.2 AA (chi tiết a11y xem skill `accessibility`)
- Nielsen 10 heuristics
- Material 3 / Apple HIG (nền tảng)
- W3C Design Tokens Community Group format

## Quy trình (làm đúng thứ tự)
Bối cảnh và phân loại màn hình → chọn vân tay cấu trúc → tokens và bố cục → đủ 5 trạng thái → vi tương tác → tự chấm 6 trục → cổng kiểm chứng (a11y + gate).
Tự chấm trước khi giao: chấm 1–5 sáu trục — triết lý (có lý do vì sao trang trông thế này), phân cấp (2 giây nhìn ra chính/phụ), thi công (chi tiết đúng spec), riêng biệt (giống bản brief này chứ không giống trang bất kỳ), tiết chế (bỏ hết thứ không làm việc gì), đa dạng (khác cấu trúc các màn đã làm). Dưới 3 ở bất kỳ trục nào thì sửa rồi mới chạy checklist; ghi sáu điểm vào `design`.
Trước khi đề xuất token hay component: ĐỌC file token và thư mục component hiện có, dùng đúng tên đang có (chống bịa tên);
thiếu thì đề xuất bổ sung vào nguồn token, không hard-code và không vẽ lại component đã có.

## Quy tắc — flow
- Mỗi flow bám một user story; mỗi màn hình đủ 5 trạng thái: empty, loading, error, success, và phản hồi khi người dùng nhập/thao tác (validation).
- Wireframe mức thấp (text/mermaid) đủ để frontend code, không cần Figma.
- Mỗi màn hình đúng MỘT primary CTA; hành động phụ hạ cấp thị giác. Hành động phá hủy tách khỏi CTA chính, dùng màu danger; ưu tiên undo trong toast hơn hộp thoại "chắc chưa?", chỉ hỏi xác nhận khi thật sự không hoàn tác được.
- Copy chính viết sẵn trong flow; lỗi nói nguyên nhân + người dùng làm gì tiếp ("Thẻ bị từ chối → thử thẻ khác"), không phải "Dữ liệu không hợp lệ".
- Form: label hiển thị (không dùng placeholder thay label), validate khi blur, lỗi đặt ngay dưới field; form dài tự lưu nháp; nhiều lỗi thì có error summary ở đầu.
- Nút submit disable + hiện loading khi đang gửi (chặn double-submit); gửi thất bại phải giữ nguyên dữ liệu người dùng đã nhập.
- Không giấu chức năng sau cử chỉ; mọi thao tác vuốt/kéo có nút tương đương.

## Quy tắc — vân tay cấu trúc (không rập khuôn)
- Chọn cấu trúc trước khi chọn màu và font. Vân tay gồm sáu trục, ghi rõ lựa chọn từng trục vào `design`: vị trí tiêu đề mục (trên / lề trái / trong dòng), bố cục thân (một cột / hai cột lệch / lưới / bảng), đường phân cách (khoảng trắng / hairline / đổi nền), giọng nút (đặc / viền / chữ có gạch chân), xử lý ảnh (tràn lề / cắt sát lưới / trong dòng / không ảnh), kiểu xuất hiện (không animation / fade-up / số đếm).
- Hai màn hình hoặc hai trang khác mục đích phải khác vân tay ở ít nhất hai trục; đổi màu không tính là khác. Lặp lại đủ sáu trục là dấu hiệu chép khuôn.
- Cấu trúc bám việc người dùng đến để làm; cấm khuôn hero → 3 cột feature → CTA → footer bốn cột liên kết, trừ khi brief nêu lý do.
- Component tương tác phải có mã cho đủ 8 trạng thái: mặc định, hover, `:focus-visible`, active, disabled, loading, error, success — 5 trạng thái ở trên là mức màn hình, 8 trạng thái là mức component.

## Quy tắc — design tokens (nguồn duy nhất, frontend/mobile không hard-code)
- Spacing theo nhịp 4/8; tầng khoảng cách khối: 16/24/32/48.
- Type scale rời rạc: 12 14 16 18 24 32; body mobile ≥ 16px; line-height 1.5–1.75; độ dài dòng 35–60 ký tự (mobile) / 60–75 (desktop).
- Màu khai báo dạng semantic (primary, surface, on-surface, error, success), không hex rải trong component. Dark mode là bộ token riêng, giảm bão hòa — không đảo màu — và đo contrast lại độc lập.
- Icon: một bộ, một stroke width, kích thước theo token (icon-sm/md 24/lg); không dùng emoji làm icon; không PNG.
- Có thang elevation/radius/motion dùng chung; không shadow tùy hứng.
- Breakpoint hệ thống: 375 / 768 / 1024 / 1440; ≥1024 ưu tiên sidebar, nhỏ hơn dùng bottom/top nav.
- Token khoá sau khi chốt: mọi màu và font trong mã phải trỏ về token có tên. Cần giá trị mới thì thêm token đặt tên rồi mới dùng, không viết thẳng hex/oklch/`font-family` giữa chừng.
- Nền lật màu thì chữ lật theo trong cùng rule: khối nền tối phải đặt lại `color`; nền màu nhấn phải có token chữ đi kèm (`on-primary`) và đo contrast với chính nền đó. Chữ nút gần trùng nền nút là lỗi block.
- Độ dài dòng đo bằng `ch` (45–75) chứ không bằng px; màu trung tính lấy sắc độ từ màu chủ đạo, không dùng xám tuyệt đối.

## Quy tắc — nền tảng và chuyển động
- Tap target ≥ 44×44pt (iOS) / 48×48dp (Android) / 24×24 CSS px (web), cách nhau ≥ 8px; phản hồi khi chạm trong ≤ 100ms.
- Tôn trọng safe area, cử chỉ hệ thống, back predictable (giữ scroll + filter khi quay lại); bottom nav ≤ 5 mục, icon kèm chữ, có trạng thái active.
- Animation chỉ dùng transform/opacity, tối đa 1–2 phần tử mỗi màn, ngắt được, exit ngắn hơn enter, tôn trọng `prefers-reduced-motion`; chuyển động phải diễn đạt quan hệ nhân–quả, không trang trí.
- Không `transition: all`, không hover-scale đồng loạt, không chồng nhiều hiệu ứng hover trên một phần tử; không animate `width/height/top/left/margin/padding`; focus ring hiện ngay, không fade.
- Tooltip: trễ 800–1000ms khi hover, 0ms khi focus. Nội dung tự xoay (carousel, băng số liệu) phải dừng khi hover và khi focus. Toast chúc mừng chỉ dùng cho việc người dùng không tự thấy kết quả.
- Form và input: không đổi `border-width` giữa các trạng thái (đổi nền / `outline` / `border-color`); focus dùng `outline` + `outline-offset`, không dùng border; input và nút cùng hàng cao bằng nhau, tối thiểu 44px; chừa sẵn chỗ cho dòng helper/lỗi để không đẩy layout; disabled báo bằng ba kênh — mờ, `cursor: not-allowed`, thuộc tính `disabled`/`aria-disabled`.
- Thao tác > 400ms phải có chỉ báo tiến trình; chờ > 1s dùng skeleton thay spinner; đặt sẵn kích thước ảnh/khối async để không nhảy layout.
- Biểu đồ: chọn loại theo dữ liệu (xu hướng→line, so sánh→bar), không pie > 5 nhóm, luôn có empty/error state, kèm bảng hoặc text summary cho screen reader, không phân biệt bằng màu đơn thuần.

## Quy tắc — chọn phong cách
- Phong cách và palette suy ra từ ngành và loại sản phẩm, ghi rõ lý do; một phong cách cho toàn sản phẩm.
- Hiệu ứng (shadow, blur, radius) phải khớp phong cách đã chọn; blur dùng để báo nền bị chặn (modal/sheet), không để trang trí.
- Ưu tiên control hệ thống; chỉ tùy biến khi thương hiệu yêu cầu.

## Quy tắc — tránh mặc định
Không có chỉ dẫn thì thiết kế trôi về khuôn landing page SaaS. Các mặc định dưới đây chỉ dùng khi nêu được lý do gắn với ngành trong `design`.
- Không lấy Inter/Roboto/system-ui làm mặc định; typeface chọn theo ngành và chất giọng. Khác biệt heading/body phải là quyết định, không phải cùng font phóng to.
- Không gradient tím→xanh, không mặc định `#6366F1`. Màu nhấn dùng ít và có việc (CTA, trạng thái); phần lớn bề mặt là trung tính có nhiệt độ.
- Cấu trúc trang bám nhiệm vụ người dùng đến để làm, không bám khuôn hero + ba cột feature + bảng giá.
- Không card lồng card; mỗi tầng phân tách dùng đúng MỘT tín hiệu — ưu tiên khoảng trắng, rồi nền, cuối cùng mới viền.
- Không bounce/elastic cho UI chức năng: ease-out khi vào, ease-in khi ra, 120–240ms. Không fade-in-on-scroll toàn trang.
- Không emoji làm icon hay bullet; không copy rỗng ("Nhanh chóng · Mạnh mẽ"); dữ liệu mẫu lấy từ miền của khách, không Lorem ipsum hay "John Doe".
- Không heading in nghiêng (kể cả một từ nhấn `<em>` trong tiêu đề đứng); nhấn bằng độ đậm, màu nhấn hoặc gạch chân. In nghiêng chỉ còn dùng trong đoạn văn.
- Không vẽ lại chrome: khung trình duyệt giả (thanh URL + ba chấm), khung điện thoại giả, khung terminal/IDE giả. Dùng ảnh chụp thật trong `<figure>` hoặc bỏ khung.
- Không bịa số liệu, logo khách, lời chứng thực. Chưa có số thì để ô trống có nhãn "chờ số liệu" hoặc đổi bố cục khác, không lấy "+47% chuyển đổi" lấp chỗ.
- Một bộ icon cho toàn sản phẩm; trộn hai thư viện icon là lỗi. Trang trí phải có neo ngữ nghĩa (con số là số hiệu phiên bản/kỳ, con trỏ nằm trong lệnh đang gõ); hình trang trí bâng quơ thì bỏ.
- Nhãn mục (eyebrow) đặt ngay trên tiêu đề cùng cột, không đặt thành cột bên cạnh tiêu đề.
- Màu nhấn chiếm ≤ ~5% diện tích một khung nhìn; phần lớn bề mặt là trung tính.
- Không cuộn ngang ở mọi bề rộng 320–1920px: `overflow-x: clip` ở cả `html` và `body` (không dùng `hidden`); chữ bấm được (nút, liên kết nav, CTA) không bao giờ xuống hai dòng — rút ngắn nhãn hoặc gộp menu; track lưới có ảnh dùng `minmax(0, 1fr)` chứ không `1fr`; tiêu đề lớn thêm `overflow-wrap: anywhere` để từ dài không tràn.
- Mật độ theo lượng thông tin và tần suất dùng: công cụ nội bộ dày, trang giới thiệu thoáng. Một mật độ cho mọi màn hình là dấu hiệu chưa cân nhắc.

## Checklist (supervisor và human gate dùng để chấm)
- [ ] 100% story Must có flow
- [ ] Mọi màn hình đủ 5 trạng thái, mỗi màn một primary CTA
- [ ] Token và component đề xuất khớp tên đang có trong dự án (đã đọc nguồn, không bịa)
- [ ] Tokens có version trong `design`: spacing, type scale, màu semantic, dark mode, elevation, motion
- [ ] Tiêu chí a11y đo được (contrast, focus, target, label, không chỉ dựa vào màu)
- [ ] Thông báo lỗi có nguyên nhân + cách khắc phục
- [ ] Vân tay cấu trúc đã ghi đủ sáu trục và khác các màn trước ở ≥ 2 trục
- [ ] Component tương tác có đủ 8 trạng thái trong mã
- [ ] Đã tự chấm 6 trục, không trục nào dưới 3
- [ ] Không bịa số liệu / lời chứng thực / logo khách
- [ ] Đã kiểm ở 320 và 375px (không cuộn ngang, chữ bấm được không xuống hai dòng), landscape, dark mode, cỡ chữ hệ thống lớn nhất, reduced-motion
- [ ] Giả định người dùng đã liệt kê

## Ví dụ tốt
Flow "Thanh toán" US-07: 5 bước, một CTA "Thanh toán"; lỗi "Thẻ bị từ chối → Thử thẻ khác / Liên hệ ngân hàng" đặt dưới field và có aria-live; token `spacing.4=16`, `color.error` đo contrast 7.2:1 ở cả hai theme.

## Ví dụ xấu
"Làm giống Shopee" — không flow, không trạng thái lỗi, không tiêu chí; nút icon emoji 32×32 hard-code màu #FF5722, dark mode đảo màu.
