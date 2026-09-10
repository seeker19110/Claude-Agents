# Nghiên cứu: tích hợp Hallmark (nutlope/hallmark) vào skill `ui-ux-design`

Ngày: 2026-09-05 · Nguồn: https://github.com/Nutlope/hallmark (MIT, v1.1.0, đọc bản `main` ngày 2026-09-05)

## Hallmark là gì
Skill thiết kế cho AI coding assistant (Claude Code / Cursor / Codex), mục tiêu hẹp: **làm UI do LLM sinh ra
không mang mùi LLM**. Quy mô ~6.200 dòng: `SKILL.md` (558 dòng) + 25 file `references/` + 21 macrostructure +
~60 file component archetype.

Bốn động từ: mặc định (build mới), `audit` (chấm điểm, không sửa), `redesign` (giữ nội dung, đổi cấu trúc thị
giác), `study` (trích "DNA" từ ảnh/URL tham chiếu).

Ba ý tưởng cốt lõi đáng lấy:
1. **Đa dạng cấu trúc, không chỉ đa dạng màu.** Chọn macrostructure TRƯỚC, ghi dấu (stamp) vào CSS và
   `.hallmark/log.json`, lần sau bắt buộc khác. "Vân tay cấu trúc" gồm 6 trục: vị trí tiêu đề mục, bố cục
   thân, ngôn ngữ đường phân cách, giọng nút, cách xử lý ảnh, kiểu reveal.
2. **58 cổng "slop-test"** chạy trước khi giao — mỗi cổng là câu hỏi phải trả lời "không".
3. **Tự chấm trước khi phát (pre-emit self-critique)** 6 trục 1–5: Philosophy, Hierarchy, Execution,
   Specificity, Restraint, Variety; dưới 3 ở bất kỳ trục nào thì sửa rồi mới chạy cổng.

## So với `ui-ux-design` v5 hiện có
Trùng đáng kể — phần "Quy tắc — tránh mặc định" của ta đã bắt: font mặc định Inter/Roboto, gradient tím→xanh,
`#6366F1`, khuôn hero + 3 cột feature + pricing, card lồng card, emoji làm icon, copy rỗng, Lorem ipsum,
bounce cho UI chức năng, fade-in-on-scroll toàn trang. Đây là hội tụ tự nhiên: cả hai cùng nguồn
(impeccable / frontend-design của Anthropic).

Khác biệt về mục đích: Hallmark là skill **sinh trang marketing/landing**, ta là skill **quy trình thiết kế
sản phẩm** trong công ty gia công (flow theo user story, token có version, gate a11y, checklist cho human
gate). Không nên nuốt nguyên Hallmark: 21 macrostructure + 60 archetype + hệ theme là tài sản trình bày
landing page, phần lớn vô dụng cho app nội bộ, và mâu thuẫn ADR-0008 (skill phải ngắn để nạp cho model).

## Quyết định
Lấy **delta**, không lấy kho tham chiếu. Tám nhóm được nhập vào `ui-ux-design` v6:

| Lấy | Vì sao |
|---|---|
| Tự chấm 6 trục trước khi giao | Rẻ, kiểm được, khớp vai supervisor/human gate |
| Vân tay cấu trúc 6 trục + cấm lặp cấu trúc giữa các màn/trang | Điểm mạnh riêng của Hallmark; ta chưa có |
| 8 trạng thái cho component tương tác (thêm hover, focus-visible, active, disabled vào 5 trạng thái màn hình) | Ta đang thiếu tầng component |
| Cổng contrast khi lật nền (ink-on-ink, chữ nút ≈ nền nút, `--color-accent-ink`) | Lỗi ship thật, đo được, bổ trợ skill `accessibility` |
| Token khoá: cấm ứng biến hex/font giữa chừng | Ta mới cấm hard-code, chưa cấm "lift giá trị mới không đặt tên" |
| Anti-pattern mới: heading in nghiêng, vẽ lại chrome (khung trình duyệt/điện thoại giả), số liệu bịa, trộn nhiều bộ icon, trang trí không có neo ngữ nghĩa, eyebrow đặt cạnh tiêu đề | Đều là "tell" của LLM, ta chưa liệt kê |
| Cổng responsive cụ thể: không cuộn ngang (`overflow-x: clip` cả `html` và `body`), chữ bấm được không xuống hai dòng, `minmax(0,1fr)` cho track chứa ảnh, `overflow-wrap: anywhere` cho display | Ta mới nói "kiểm ở 375px", chưa có cách sửa |
| Quy tắc trạng thái input (không đổi `border-width` giữa các trạng thái, focus bằng `outline`, input cao bằng nút, chừa chỗ helper text, disabled ba kênh) | Chỗ form hay hỏng nhất |

Bỏ, kèm lý do:
- **21 macrostructure + 60 component archetype + 21 theme**: quy mô kho tham chiếu, không hợp một skill
  markdown; nếu sau này cần thì mở skill riêng `design-catalog`, chủ quản `researcher`.
- **Bốn động từ `audit/redesign/study`**: ta đã có vai (`reviewer` chấm, `researcher` khảo sát); thêm động từ
  vào skill sẽ giẫm lên phân vai của ADR-0009.
- **`.hallmark/log.json` + stamp trong CSS**: cơ chế bộ nhớ riêng của Hallmark; ta ghi vào namespace `design`
  có version thay vì đẻ thêm file trạng thái.
- **Pre-flight scan**: ta đã có quy tắc "đọc token và component hiện có trước khi đề xuất".
- **Nhánh theme tuỳ biến OKLCH + cặp font miễn phí**: gắn với catalog, bỏ theo catalog.

## Giấy phép và ghi nguồn
Hallmark là MIT. Ta không sao chép nguyên văn — diễn đạt lại thành quy tắc tiếng Việt và ghi vào `sources:`
của skill, đúng cách đã làm với `impeccable` và `ui-ux-pro-max-skill`.

## Thay đổi kèm theo
- `skills/ui-ux-design.md`: v5 → v6 (các mục ở bảng trên).
- Golden test `tests/golden/agents/*` sinh lại (`make golden`) vì bốn agent nạp skill này ở mức đầy đủ hoặc core.

## Lan sang các skill khác (đợt 2)
Phần "tốt cho dự án" không chỉ nằm ở thiết kế — nó nằm ở chỗ code và chỗ review. Đặt quy tắc ở đúng skill
của người làm, mỗi quy tắc một nơi, các skill khác dẫn chiếu:

- `frontend` v2 → v3: token khoá khi code, đổi nền phải đổi màu chữ trong cùng rule, 8 trạng thái component
  kèm trang demo 8 trạng thái, quy tắc trạng thái input, và mục mới "chất lượng giao diện" — cấm
  `transition: all` / hover-scale đồng loạt / animate thuộc tính bố cục, `overflow-x: clip` hai cấp, chữ bấm
  được không xuống hai dòng, `minmax(0, 1fr)`, một sticky top, không vẽ lại chrome, một bộ icon, không bịa số liệu.
- `accessibility` v2 → v3: đo tương phản với nền thực tế của từng khối (chữ trong card đổi nền, chữ mờ trên
  bề mặt phụ, viền focus), chữ nút ≈ nền nút là block, focus ring không fade, nội dung tự xoay dừng khi hover
  và focus (WCAG 2.2.2), tooltip focus 0ms, disabled ba kênh, SVG trang trí phải `aria-hidden`.
- `code-review` v2 → v3: thêm "giao diện" vào trọng tâm cần soi — các lỗi trên đều là finding có `file:line`
  và cách sửa, không phải nhận xét thẩm mỹ.
- `mobile`: không đổi. Hallmark là skill web; phần nền tảng của mobile đã dẫn chiếu `ui-ux-design`.

Bản ghi eval cần chạy lại (ADR-0010): frontend, mobile, qa-debugger, researcher, reviewer, spec-writer.
