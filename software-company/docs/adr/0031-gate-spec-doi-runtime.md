# ADR-0031: `runtime` là điều kiện cần của Gate 1 — spec ứng dụng không có lệnh khởi động thì không mở gate

## Bối cảnh
Báo cáo `docs/reports/2026-09-06-ban-giao-khong-chay-duoc.md`: QLKH đi hết dây chuyền, bốn gate xanh, 389 test pass,
25 release, **không có điểm vào nào chạy được**. ADR-0029 vá ở cuối chuỗi — orchestrator tự khởi động sản phẩm theo
`approved-specs.payload.runtime` sau mỗi `deployed` staging — nhưng để `runtime` là tuỳ chọn: thiếu thì
`smoke.unverified`, status giữ nguyên. Nghĩa là câu hỏi *"chạy cho tôi xem"* vẫn có thể bị né suốt dự án, chỉ khác là
bằng chứng nói thẳng "chưa kiểm". Đề xuất B1 của `docs/DAC-TA-NANG-CAP-2026-09.md`: hỏi câu đó ở **Gate 1**, chỗ rẻ
nhất để trả lời và đắt nhất để bỏ qua.

## Quyết định
1. **Spec khai `kind`**: `application | library | docs` (`topics/schemas/approved-specs.json`). `library`/`docs` được
   miễn `runtime` nhưng phải khai rõ; **thiếu `kind` tính là `application`** — im lặng không phải miễn trừ, vì im
   lặng chính là cách QLKH đi qua bốn gate.
2. **`application` phải có `runtime` hợp lệ** theo đúng `smoke.parse_runtime` (ADR-0029): `command` (có thể chứa
   `{port}`), `port`, `health`, và `dependencies` (phụ thuộc ngoài: DB, cache, cloud). PRD template mục 8b khớp 1-1.
3. **Orchestrator chặn trước khi gate mở** (`spec_runtime_gap`, `Orchestrator._spec_runtime_missing`): spec ứng dụng
   thiếu runtime → **không** `gate.request(kind="spec")`; audit `spec.runtime_missing`; gọi lại spec-writer trên đúng
   event nguồn (`causation_id`) với `hint` + `previous_spec` — cùng nghĩa với `request_changes` của người. Tối đa
   `SPEC_RUNTIME_REWORKS = 1` lần tự động; lần sau vẫn thiếu → audit `spec.runtime_escalated`, gate `escalation`
   cấp dự án (`approve` = chạy lại event nguồn qua `unhandled`, `reject` = bỏ) — cùng khuôn với kế hoạch bị
   `_check_plan` từ chối. Bộ đếm theo dự án dựng lại từ audit (khuôn 2 `TRAPS.md`); khoá theo `event_id` của spec
   nên lần publish sau không bị khoá cũ nuốt (khuôn 3).
4. **Gate 1 thấy runtime**: checklist `gates/checklists.md` thêm mục tự kiểm "Có runtime chạy được…"; nguồn bằng
   chứng `spec.runtime` trong `gate_checklists.py`; `gate_brief` in lệnh/cổng/health/phụ thuộc và số lần spec bị
   trả lại. Gate đã duyệt trước ADR này không bị chạm: kiểm chỉ chạy lúc **mở** gate.
5. **spec-writer v9** biết luật này trong prompt (nó không đọc được `templates/prd.md`), và biết sửa theo `hint`.

## Hệ quả
- Dự án ứng dụng không có ticket nào được lập khi spec chưa nói sản phẩm khởi động bằng gì. Ticket đầu tiên của
  plan vì thế có mục tiêu rõ: làm `runtime.command` trả lời được (nối vào B2 và ADR-0029).
- Test/fixture publish `approved-specs` tay phải khai `kind` (`library` khi không cần smoke) — chủ ý, để test
  không đi qua đường tắt mà sản phẩm thật không có.
- Chưa làm: kiểm `runtime.command` thật sự chạy ngay ở Gate 1 (chưa có code để chạy); ảnh chụp UI (ADR-0033 dự kiến).

## Liên quan
ADR-0029 (smoke do orchestrator chạy), ADR-0030 (sổ Ruling), ADR-0010/0013 (model khai, code chứng), B1 trong
`docs/DAC-TA-NANG-CAP-2026-09.md`, báo cáo `2026-09-06-ban-giao-khong-chay-duoc.md`.
