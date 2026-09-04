# Design — SAOMAI (v1, 2026-09-04)

> CẢNH BÁO: đầu vào intake rỗng (`data={}`), `research-requests/SAOMAI` không tồn tại. Toàn bộ persona và flow dưới đây là **giả định**, cần xác nhận ở buổi làm rõ trước khi spec-writer dùng.

## 1. Persona (giả định)
- **Học vụ (Chị Hà)**: dùng máy tính để bàn, nhiều tác vụ/ngày → mật độ **dày**, bảng nhiều cột.
- **Giáo viên (Thầy Nam)**: dùng điện thoại, thao tác 1 phút đầu buổi → mật độ vừa, target lớn.
- **Phụ huynh (Chị Lan)**: dùng điện thoại, ít khi vào → mật độ thoáng, chữ ≥16px.

## 2. User flows
### FLOW-1 Điểm danh buổi học (giáo viên, mobile)
Chọn lớp hôm nay → danh sách học viên (mặc định 'Có mặt') → gạt sang 'Vắng'/'Muộn', nhập lý do nếu vắng → **CTA chính: Lưu điểm danh** → toast 'Đã lưu 18/20 có mặt · Hoàn tác' (10s).

### FLOW-2 Phụ huynh xem học phí (mobile)
Đăng nhập → chọn con (bỏ bước nếu chỉ 1 con) → thẻ công nợ + lịch sử thanh toán → **CTA chính: Xem chi tiết khoản thu**.

## 3. Màn hình và 5 trạng thái
### SCR-attendance
- empty: "Lớp này chưa có buổi học hôm nay." — hành động phụ: Tạo buổi học
- loading: skeleton 8 dòng (không spinner, chờ >1s)
- error: "Không tải được danh sách lớp. Kiểm tra kết nối rồi thử lại." + nút Thử lại
- success: toast có Hoàn tác; trạng thái mỗi dòng hiện icon + chữ (không chỉ màu)
- validation: "Buổi học đã khoá sau 24 giờ. Liên hệ học vụ để sửa." đặt ngay dưới dòng, `aria-live=polite`

### SCR-parent-tuition
- empty: "Chưa có khoản học phí nào cho học kỳ này."
- loading: skeleton 3 thẻ
- error: "Không tải được công nợ. Thử lại."
- success: thẻ 'Còn nợ 2.400.000 ₫ · Hạn 15/09' + danh sách biên nhận
- validation: (màn hình nhập của học vụ) "Số tiền phải từ 1.000 đến 50.000.000 ₫"

## 4. Design tokens v1
```yaml
spacing: {1: 4, 2: 8, 3: 12, 4: 16, 6: 24, 8: 32, 12: 48}
type_scale: [12, 14, 16, 18, 24, 32]   # body mobile 16, line-height 1.5
radius: {sm: 4, md: 8, lg: 12}
elevation: [0, 1, 2]                    # không shadow tuỳ hứng
motion: {enter: 200ms ease-out, exit: 140ms ease-in}  # tôn trọng prefers-reduced-motion
breakpoints: [375, 768, 1024, 1440]     # >=1024 sidebar; nhỏ hơn bottom nav <=5 mục
color_light:
  surface: "#FBFAF7"      # trung tính ấm — bối cảnh giáo dục, không nền trắng lạnh
  on-surface: "#1F2421"
  primary: "#1B5E4A"      # xanh lá đậm; contrast trên surface 8.1:1 (cần đo lại khi implement)
  on-primary: "#FFFFFF"
  error: "#B3261E"
  success: "#2E6B3A"
  warning: "#8A5A00"
color_dark:                # bộ token riêng, giảm bão hoà, KHÔNG đảo màu
  surface: "#14181A"
  on-surface: "#E6E9E7"
  primary: "#7FC6AC"
  error: "#F2B8B5"
icon: {set: "một bộ, stroke 1.5", sizes: {sm: 20, md: 24, lg: 32}}
```
Lý do phong cách: trung tâm giáo dục trẻ em → trung tính ấm, chữ rõ, ít hiệu ứng; **không** dùng gradient tím-xanh SaaS, không emoji làm icon.

## 5. A11y (WCAG 2.2 AA — tiêu chí đo được)
- Contrast text ≥4.5:1, UI component ≥3:1, đo ở cả light và dark
- Target ≥24 CSS px (web) / ≥48dp (Android), cách nhau ≥8px
- Trạng thái điểm danh: icon + nhãn chữ, không phân biệt chỉ bằng màu
- Label hiển thị, lỗi liên kết `aria-describedby`, error summary đầu form khi nhiều lỗi
- Đi hết FLOW-1 và FLOW-2 bằng bàn phím, focus visible, không bẫy focus
- Zoom 200% và reflow 320px không mất nội dung

## 6. Chưa kiểm
Chưa test 375px thật, chưa test screen reader (chưa có code). Cần làm ở ticket frontend đầu tiên.
