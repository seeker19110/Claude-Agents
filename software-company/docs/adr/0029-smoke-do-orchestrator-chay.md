# ADR-0029: `deployed` phải có bằng chứng máy chạy — orchestrator tự khởi động sản phẩm và gọi một request thật

## Bối cảnh
Ngày 2026-09-06, dự án QLKH đi hết dây chuyền: 14/14 ticket vào nhánh tích hợp, 25 release, bốn gate xanh, 389 test
pass, khách ký nghiệm thu. Sản phẩm **không có điểm vào nào chạy được**: không server, không lệnh khởi động, quyết
định framework bị né qua từng ticket. Báo cáo `docs/reports/2026-09-06-ban-giao-khong-chay-duoc.md` chỉ ra vì sao
bốn gate không bắt được — và đáng chú ý là cả bốn đều hoạt động *đúng như thiết kế*:

- `release-events{status=deployed}` là **lời khai** của release-engineer. Nó không có tool deploy; nó mô tả một
  pipeline rồi trả `deployed`.
- `regression-staging` của qa-debugger là **verdict đọc diff** trên worktree tích hợp: test pass thật, nhưng test
  không cần server để pass.
- Gate 3 ký trên hai thứ trên. Gate 4 ký trên biên bản.

Đối chiếu với skill `verification-before-completion` (obra/superpowers) — bảng "claim nào cần bằng chứng nào" có
đúng hai dòng mô tả sự cố: *Bug fixed → chạy lại triệu chứng gốc*; *Agent completed → xem diff, "agent tự báo success"
là KHÔNG ĐỦ*. Công ty đã áp nguyên tắc này cho PR từ ADR-0010 (`local_checks.verified_by=workspace`: model chỉ khai,
code chạy lint/test thật), nhưng dừng ở PR. Từ RC trở đi mọi trạng thái đều là lời khai.

## Quyết định
1. **Spec khai `runtime`.** `approved-specs.payload.runtime = {command, port, health, timeout_s, expect_status}` —
   lệnh khởi động (có thể chứa `{port}`), cổng (0 = orchestrator tự chọn), đường GET kiểm. PRD template có mục 8b
   "Chạy ở đâu". Đây là câu hỏi của khách — *"chạy cho tôi xem"* — được hỏi ở Gate 1 thay vì ở lúc bàn giao.
2. **Orchestrator smoke sau mỗi `deployed` ở staging** (`src/company/smoke.py`, hook trong `Orchestrator._release`):
   khởi động `runtime.command` trong worktree tích hợp (`.worktrees/_integration`, đúng sha QA sẽ hồi quy), env đã
   lọc bí mật (`clean_env`), poll `http://127.0.0.1:<port><health>` tới `timeout_s`, giết tiến trình. Kết quả vào
   `release-events.payload.smoke` với `verified_by=orchestrator`: lệnh thật, cổng, mã HTTP, mã thoát nếu chết sớm,
   đuôi stderr, thời gian.
3. **Ba kết cục, không có kết cục thứ tư:**
   - `smoke.ok=true` → `deployed` giữ nguyên; audit `release.smoke`.
   - có `runtime` mà không chạy được (chết sớm / không trả lời / sai mã) → **status ghi đè thành `failed`**, audit
     `release.smoke_failed`, mở gate `escalation` cho RC (cùng checklist với `pending_human`). QA hồi quy không chạy,
     Gate 3 không mở — đúng: không có gì để hồi quy.
   - không có `runtime` hoặc dự án chạy không repo → `smoke = {unverified: true, reason}`, status giữ nguyên, audit
     `release.smoke_unverified` một lần mỗi RC. Không chặn dự án cũ, nhưng bằng chứng nói thẳng "chưa kiểm".
4. **Lượt production và Gate 3 thấy smoke.** `_release_evidence` mang `staging.smoke` vào payload của lượt
   production; checklist Gate 3 thêm dòng `smoke`. Người ký thấy `unverified` thì hỏi trước khi ký.
5. **Ranh giới tin cậy không đổi so với ADR-0013.** `runtime.command` là của spec (spec-writer viết, người ký Gate 1),
   chạy như lệnh lint/test của khách: cùng worktree, cùng env lọc, có timeout, không hook. Sandbox tiến trình vẫn là
   việc "Chưa có" của README.

## Hệ quả
- Ticket đầu tiên của một dự án dạng ứng dụng phải làm cho `runtime.command` trả lời được — điểm vào chạy được trở
  thành điều kiện để RC đầu tiên `deployed`, không phải việc "để sau".
- Prompt của release-engineer **không đổi**: bằng chứng do code sinh, không phải do model dặn thêm (bài học ADR-0010,
  ADR-0028). Không cần ghi lại eval.
- Smoke chỉ chứng minh "khởi động được và trả lời một request" — không thay QA hồi quy, không thay UAT. Nó là sàn,
  không phải trần: đúng thứ QLKH thiếu.
- Chưa làm: ảnh chụp giao diện cho ticket frontend (cùng hình dạng, khác kênh bằng chứng); sổ `Ruling:` cho quyết
  định agent tự đưa ra ngoài bốn gate. Mỗi cái một ADR riêng.

## Liên quan
ADR-0010 (ranh giới tool / eval replay), ADR-0013 (stack và lệnh kiểm của khách), ADR-0027 (giao hàng thật),
ADR-0028 (test-author độc lập), báo cáo `2026-09-06-ban-giao-khong-chay-duoc.md` (đề xuất 3 và 6),
báo cáo `2026-09-06-danh-gia-superpowers-va-skill-frontend.md`.
