---
name: frontend
version: 3
standards: [WCAG 2.2 AA, Core Web Vitals, CSP Level 3, OWASP client-side, W3C Design Tokens, Progressive enhancement]
---
# Skill: frontend

## Tiêu chuẩn tham chiếu
- WCAG 2.2 AA (chi tiết ở skill `accessibility`)
- Core Web Vitals: LCP < 2.5s, INP < 200ms, CLS < 0.1 (đo ở p75, thiết bị và mạng thực tế)
- CSP Level 3, Trusted Types, SameSite cookie
- OWASP client-side: XSS, CSRF, clickjacking, lộ dữ liệu qua bộ nhớ trình duyệt
- Design tokens W3C làm nguồn duy nhất cho màu/chữ/khoảng cách (xem `ui-ux-design`)
- Progressive enhancement: chức năng lõi chạy được khi JS chậm hoặc lỗi

## Quy trình (làm đúng thứ tự)
Đọc flow và token từ thiết kế → dựng HTML ngữ nghĩa và trạng thái tĩnh trước → nối dữ liệu qua contract đã chốt (mock từ OpenAPI) → xử lý đủ 5 trạng thái (loading, empty, error, success, validation) → bàn phím và screen reader → đo hiệu năng theo ngân sách → kiểm ở 375px, dark mode, cỡ chữ lớn, reduced-motion → mở PR.
Component mới chỉ được tạo sau khi đã tìm trong thư viện hiện có; dùng lại trước, thêm sau.

## Quy tắc — cấu trúc và trạng thái
- HTML ngữ nghĩa trước, ARIA sau; `div` có `onClick` là lỗi block (xem `accessibility`).
- Mỗi màn hình xử lý đủ 5 trạng thái; trạng thái lỗi nói nguyên nhân và việc cần làm tiếp, giữ nguyên dữ liệu người dùng đã nhập.
- Phân biệt rõ trạng thái máy chủ (dữ liệu lấy về, có cache và vòng đời) với trạng thái UI cục bộ; không nhân bản dữ liệu máy chủ vào store toàn cục nếu không cần.
- Không hard-code màu, khoảng cách, cỡ chữ: dùng token; thiếu token thì đề xuất bổ sung vào nguồn, không tự đặt giá trị.
- Token khoá trong lúc code: mọi `color` và `font-family` trỏ về token có tên. Cần giá trị chưa có thì thêm token rồi dùng, không viết thẳng hex/oklch/rgb giữa file.
- Khối nào đổi nền thì đổi luôn màu chữ trong cùng rule (chữ tối trên nền tối là lỗi block); nền màu nhấn phải dùng token chữ đi kèm và đo tương phản với chính nền đó.
- Component tương tác phải có mã cho đủ 8 trạng thái: mặc định, hover, `:focus-visible`, active, disabled, loading, error, success. Kèm một trang demo dựng đủ 8 trạng thái để soi bằng mắt, không đưa vào bản chạy thật.
- Input: giữ nguyên `border-width` giữa các trạng thái (đổi nền / `outline` / `border-color`); focus dùng `outline` + `outline-offset`, không dùng border; input và nút cùng hàng cao bằng nhau (≥ 44px); chừa sẵn chỗ dòng helper/lỗi; disabled báo bằng ba kênh (mờ + `cursor: not-allowed` + thuộc tính `disabled`/`aria-disabled`).
- Form: label hiển thị, validate khi blur, lỗi ngay dưới field, chặn double-submit, giữ dữ liệu khi gửi thất bại (chi tiết ở `ui-ux-design`).
- Xử lý điều kiện mạng thật: mất mạng, chậm, request đến sai thứ tự (hủy request cũ), thử lại có giới hạn.

## Quy tắc — chất lượng giao diện (chống mã sinh máy móc)
- Không `transition: all`: liệt kê đúng thuộc tính. Không hover-scale đồng loạt, không chồng nhiều hiệu ứng hover trên một phần tử. Không animate `width/height/top/left/margin/padding` — chỉ `transform`/`opacity`.
- Focus ring hiện tức thì, không có transition; mọi keyframe/transform có nhánh `prefers-reduced-motion`.
- Không cuộn ngang ở mọi bề rộng 320–1920px: `overflow-x: clip` ở cả `html` và `body` (dùng `clip`, không `hidden`, để giữ `position: sticky`).
- Chữ bấm được (nút, liên kết nav, CTA, breadcrumb) không xuống hai dòng: rút nhãn, `white-space: nowrap`, hoặc gộp vào menu.
- Track lưới có chứa ảnh dùng `minmax(0, 1fr)` chứ không `1fr`; tiêu đề cỡ lớn thêm `overflow-wrap: anywhere; min-width: 0`.
- Chỉ một sticky ở `top: 0` cho thanh trên cùng; sticky trong trang neo theo `--banner-height` và z-index thấp hơn thanh trên cùng.
- Không vẽ lại chrome bằng HTML/CSS (khung trình duyệt, khung điện thoại, khung terminal/IDE giả): dùng ảnh chụp thật trong `<figure>` hoặc bỏ khung.
- Một bộ icon cho toàn dự án; không trộn hai thư viện icon, không emoji làm icon. SVG trang trí có `aria-hidden="true"`, SVG mang nghĩa có `aria-label`.
- Không tự bịa số liệu, logo hay lời chứng thực để lấp bố cục; thiếu dữ liệu thì để ô trống có nhãn và hỏi lại.

## Quy tắc — hiệu năng
- Ngân sách hiệu năng khai báo trong repo (kích thước JS/CSS ban đầu, số request, LCP/INP/CLS) và kiểm trong CI; vượt ngân sách là finding block.
- Chia mã theo route, tải lười phần nặng, nạp trước có chọn lọc; không tải thư viện lớn cho một tính năng nhỏ.
- Ảnh có kích thước khai báo, định dạng hiện đại, `srcset` theo màn hình, lazy load ngoài khung nhìn; font tự host, `font-display: swap`, giới hạn số face.
- Tránh dịch chuyển bố cục: đặt sẵn kích thước cho khối bất đồng bộ, skeleton đúng cỡ nội dung thật.
- INP: tách việc nặng khỏi luồng chính (web worker, chia lô), tránh handler dài, không chặn cuộn.
- Đo bằng dữ liệu người dùng thật (RUM) chứ không chỉ phòng thí nghiệm; đo ở p75 trên thiết bị tầm trung.

## Quy tắc — an toàn phía client
- Không secret, không khóa API riêng tư trên client; mọi kiểm quyền thật nằm ở server — ẩn nút không phải là phân quyền.
- CSP chặt (không `unsafe-inline`, có nonce/hash), Trusted Types nếu nền tảng hỗ trợ; báo cáo vi phạm CSP về máy chủ.
- Không dựng HTML từ chuỗi chưa escape; `dangerouslySetInnerHTML`/`v-html` chỉ dùng với nội dung đã làm sạch và phải nêu lý do trong PR.
- Token phiên ưu tiên cookie `HttpOnly` + `Secure` + `SameSite`; nếu buộc lưu ở client thì nêu rõ rủi ro XSS và cách giảm nhẹ trong ADR.
- Không đưa PII vào URL, localStorage, hay log phía client; công cụ phân tích chỉ nhận dữ liệu đã thỏa thuận (xem `privacy-compliance`).
- Phụ thuộc bên thứ ba (script quảng cáo, chat, analytics) là bề mặt tấn công: giới hạn, dùng SRI, và có thể tắt.

## Quy tắc — kiểm chứng
- Test: unit cho logic, test component theo hành vi người dùng (không test chi tiết cài đặt), e2e cho luồng Must; giả lập mạng chậm và lỗi API.
- axe trong CI: 0 lỗi critical/serious; luồng Must đi hết bằng bàn phím.
- Kiểm trực quan ở 375/768/1024/1440, dark mode, cỡ chữ hệ thống lớn nhất, `prefers-reduced-motion`.
- Bắt lỗi runtime và gửi về hệ thống giám sát kèm phiên bản build; theo dõi tỉ lệ phiên có lỗi.

## Checklist (supervisor và human gate dùng để chấm)
- [ ] axe 0 lỗi critical/serious; luồng Must đi hết bằng bàn phím
- [ ] Đủ 5 trạng thái mỗi màn hình; lỗi giữ nguyên dữ liệu người dùng
- [ ] LCP/INP/CLS đạt ngưỡng ở p75; ngân sách bundle được kiểm trong CI
- [ ] Không hard-code màu/khoảng cách/cỡ chữ ngoài token
- [ ] CSP có và không dùng `unsafe-inline`; không secret trên client
- [ ] Không dựng HTML từ chuỗi chưa làm sạch
- [ ] Không PII trong URL/localStorage/log client
- [ ] Đã kiểm 375px, dark mode, cỡ chữ lớn nhất, reduced-motion
- [ ] Test có ca mạng chậm và ca API lỗi

## Ví dụ tốt
Nút dùng `<button>` có nhãn, focus ring tương phản 3:1, màu lấy từ `color.primary`; danh sách đơn hàng có skeleton đúng cỡ nên CLS 0.02; bundle route checkout 92KB (ngân sách 120KB) kiểm trong CI; API lỗi hiện "Thẻ bị từ chối → thử thẻ khác" và giữ nguyên form; CSP có nonce, không `unsafe-inline`.

## Ví dụ xấu
`<div onClick>` không focus được; màu `#FF5722` rải trong 12 component; ảnh không đặt kích thước làm trang nhảy; token phiên lưu trong `localStorage` và render nội dung khách bằng `innerHTML`; đo hiệu năng bằng máy dev đời mới rồi kết luận "nhanh".
