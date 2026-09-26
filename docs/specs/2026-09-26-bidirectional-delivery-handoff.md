# Feature spec: Cầu nối delivery hai chiều, không cấp quyền

| Thuộc tính | Giá trị |
| --- | --- |
| Issue / Goal | Yêu cầu tích hợp X-Agents và projects-template trong phiên 2026-09-26 |
| Spec owner | Phiên triển khai |
| State | Approved for implementation |
| Approver / date | Chủ repo yêu cầu triển khai trong hội thoại / 2026-09-26; chỉ phạm vi code opt-in, không phải approval runtime |
| Last updated | 2026-09-26 |

## 1. Problem, user và evidence

Người dùng cần hai repo bổ sung cho nhau, không tạo hai nguồn chính sách.
Compiler đang nhận câu Approved trong hướng dẫn nháp là trạng thái; test đã tái hiện.

## 3. Research current state

X-Agents đã có DeliveryContract, ApprovalLookup, quality receipts và journal.
Template có Standard Delivery, feature spec, profile và compiler; không cần fork runtime.
Bản đối chiếu: ../reports/2026-09-26-bidirectional-delivery-handoff.md.

## 4. Alternatives và decision

Không làm: vẫn nhập contract thủ công. Copy framework/runtime: trùng quyền và schema.
Chọn policy xuất từ native consumer, producer chỉ đóng gói, consumer kiểm lại.

## 5. Scope / non-goals

CLI offline opt-in, sửa false approval của compiler, test âm tính và tài liệu.
Không provider, scheduler, migration, auto-merge, deploy hoặc quyền gate mới.

## 9. Acceptance criteria

- AC-1 Native policy được xuất từ model/schema/source đang dùng, không bản sao viết tay.
- AC-2 Spec hash đúng bytes đã parse; AC mapping đầy đủ, duy nhất; pin cũ xung đột bị từ chối.
- AC-3 Consumer từ chối sai bundle pin/policy, thiếu AC, sai native schema hoặc spec bị sửa.
- AC-4 Dữ liệu không thực thi lệnh và không cấp quyền approval/Done/Complete.
- AC-5 Giới hạn kích thước, Unicode, JSON trùng/nonfinite/quá sâu và path escape có test.
- AC-6 Draft chứa hướng dẫn Approved không thành trạng thái approved.

## 11. Architecture và code touchpoints

Consumer: company.template_handoff cùng DeliveryContract hiện có.
Producer: delivery-handoff CLI và parser spec-compiler dùng chung parse_spec_text.
Không chỉnh journal, assessor hay policy version đã pin.

## 14. Security/privacy/abuse cases

Input luôn là dữ liệu không tin cậy. Coordinator cung cấp pin/AC độc lập; root ổn định.
Checksum không xác thực approval. Lookup/chữ ký/issuer policy hiện tại vẫn bắt buộc.
Không log nguyên văn dữ liệu lỗi; chỉ loại lỗi và gợi ý kiểm tra.

## 16. Test/eval plan

TDD, unit âm tính, đo branch coverage module mới, CLI trao đổi dùng native schema thật.
Full CI của từng repo và review bắt buộc trước merge. Không gọi model trả phí.

## 18. Rollout/rollback

Merge hai đầu độc lập vì opt-in. Chỉ dùng khi producer/consumer cùng protocol và policy.
Tắt đường mới bằng ngừng gọi CLI; không ghi đè profile đã đăng ký.

## 19. Risk, assumptions và open decisions

Chưa xác nhận full workspace/OS matrix ở môi trường thực thi này; PR giữ nháp.
Không kết luận chức năng sản phẩm cuối đã được nghiệm thu chỉ vì prepare thành công.
