# Design — DHCB (v0.1, 2026-09-04) — CHẶN

## Trạng thái
**Không lập được flow, wireframe hay design tokens.** Lý do: `research-findings` từ intake có `data` rỗng — không có goal, không có user story, không biết ngành/loại sản phẩm/người dùng. Theo skill `ui-ux-design`, phong cách và palette phải **suy ra từ ngành và loại sản phẩm, ghi rõ lý do**; lập lúc này sẽ là bịa và sẽ trôi về khuôn landing page SaaS mặc định.

## Điều kiện để mở chặn
Cần trả lời (owner: clarifier):
1. DHCB làm gì; website phục vụ mục tiêu nghiệp vụ nào?
2. Persona chính và JTBD (họ đến để **làm gì**, không phải xem gì)?
3. Có thu thập dữ liệu cá nhân / nhận quyên góp / thanh toán? (ảnh hưởng form, xác nhận, trạng thái lỗi)
4. Có site hiện hữu và nội dung cần migrate?
5. Thiết bị chủ đạo của người dùng (mobile-first hay desktop)?

## Rào chắn đã chốt trước (áp dụng khi bắt đầu thiết kế)
- Mỗi màn hình đủ **5 trạng thái**: empty, loading, error, success, validation-feedback.
- Mỗi màn hình đúng **MỘT primary CTA**; hành động phá hủy tách riêng, ưu tiên undo qua toast.
- WCAG 2.2 AA: contrast đo ở cả light và dark; focus visible; tap target ≥44×44pt / ≥24 CSS px; label hiển thị (không dùng placeholder thay label); lỗi đặt dưới field + `aria-live`.
- Thông báo lỗi = nguyên nhân + hành động tiếp theo. Cấm "Dữ liệu không hợp lệ".
- Token là nguồn duy nhất, không hard-code: spacing nhịp 4/8 (16/24/32/48); type scale 12·14·16·18·24·32, body mobile ≥16px, line-height 1.5–1.75; màu semantic (primary/surface/on-surface/error/success); dark mode là bộ token riêng (giảm bão hòa, **không đảo màu**); có thang radius/elevation/motion.
- Breakpoint: 375 / 768 / 1024 / 1440.
- Motion: chỉ transform/opacity, 120–240ms, ease-out vào / ease-in ra, tôn trọng `prefers-reduced-motion`. Không bounce, không fade-in-on-scroll toàn trang.
- **Cấm mặc định**: không Inter/Roboto/system-ui mà không nêu lý do theo ngành; không gradient tím→xanh, không `#6366F1`; không emoji làm icon/bullet; không Lorem ipsum hay "John Doe" — dữ liệu mẫu lấy từ miền của khách; không card lồng card.

## Bằng chứng codebase liên quan tới frontend
Đã tìm toàn repo (`list_files **/*`, 5 file): **không có** template, static asset, CSS, file token hay thư viện component nào. Nghĩa là không có tên token/component sẵn để tuân theo — khi mở chặn, phải tạo nguồn token mới và ghi version vào namespace `design`.
