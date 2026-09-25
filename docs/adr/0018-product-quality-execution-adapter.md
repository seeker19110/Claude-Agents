# ADR-0018: chất lượng sản phẩm nối vào execution kernel, không fork harness

Ngày: 2026-09-25. Trạng thái: Accepted. Đã nối runtime ở ADR-0021 (pe2-noi): orchestrator đăng ký run theo plan, chạy `quality:accept` qua trusted driver, và sàn ADR-0043 thêm gap R6.
Cơ sở: `seeker19110/Claude-Agents@b84dcb76b9085a686dafae97f47c988ac872446a`, ADR-0017.

## Bối cảnh

Chủ dự án đính chính repo đích là **Claude-Agents**, không phải `seeker19110/X-Agents`.
PR #113 ở repo kia là nguồn tham khảo phần chất lượng, không phải thay đổi đã tích hợp ở đây.
Repo này đã có uv workspace, sáu agent công ty, `/thi-hanh`, và kernel
`xagents_core.execution` (RunSpec, TaskSpec, TaskResult, EvidenceReceipt, ExecutionJournal).
H1/H2 đã có; H3–H7 chưa được coi là vận hành đầy đủ theo ADR-0017.
Company đã có `quality_floor` + QualityBar + tự duyệt release/acceptance theo ADR-0043; giữ nguyên,
không mô tả nhầm như repo cũ hoàn toàn thiếu tự duyệt. Lớp mới chưa tự chen vào mọi quyết định Orchestrator.

## Quyết định

1. Giữ core chỉ chứa cơ chế. Đặt policy ngành/thiết kế ở `company.product_quality`,
   kết nối bằng `company.quality_execution`; không tạo scheduler, journal hay state machine khác.
2. Chuyển profile, Design Brief, acceptance, chỉ tiêu đo và kiểm bằng chứng từ phần nghiên cứu
   trước; không sao chép AGENTS.md, ADR-0024, cấu trúc cũ hoặc 20-agent registry.
3. `compile_execution` nhận RunSpec thật, giữ graph/scope, ghim contract hash trong context
   của mọi task, thêm một task nghiệm thu cuối phụ thuộc tất cả công việc. Không bắt 33 lần
   gọi model: các check có thể được driver/reviewer đủ quyền thực hiện theo nhóm.
4. `evaluate_result` dùng TaskResult của core; ràng buộc task/attempt/base/head/diff do coordinator
   cấp và mọi receipt chất lượng. Worker ghi succeeded không đủ. Adapter không tự append success,
   cấp quyền merge/deploy, xác thực principal hoặc bỏ HumanGate của run cũ.
5. CLI `plan`/`register`/`status` dùng serialization/journal hiện hữu. Đây là giao diện nối kernel,
   không phải daemon gọi model. `/thi-hanh` vẫn giữ trạng thái vận hành A–F cho tới H7; journal
   quality opt-in là execution plan thử nghiệm, không âm thầm thay nguồn chuẩn của run đang chạy.
6. Thêm `/product-goal` cho hợp đồng sản phẩm và tham chiếu trong `/thi-hanh`. Không tạo lệnh
   `/goal` trùng với lệnh tích hợp của Claude Code; native `/goal` chỉ điều khiển vòng phiên,
   không phải chứng nhận chất lượng hay quyền mở rộng.
7. Duy trì 100% line + branch coverage, không thêm dependency hoặc sửa generated subagents.
   Thay prompt agents/skills thực sự phải làm đủ golden/eval/subagent pipeline trong PR riêng.

## Ranh giới tin cậy và triển khai

Coordinator giữ contract pin, candidate, context, attempt, authors, registry/key và artifact store
ngoài vùng ghi của worker. HMAC xác thực nguồn cấp bằng chứng, không chứng minh test đúng phương pháp.
EvidenceReceipt của core giữ phép đo lệnh; Receipt miền bổ sung check/contract/principal. Không đồng nhất
hai lớp và không biến chuỗi tự khai thành verified_by. Journal hiện tại không cấp lease đa tiến trình;
chỉ coordinator được phép ghi sự kiện, phải apply_event trước append, không đưa DB cho worker.

Không migrate/approve hàng loạt gate cũ; không giả chữ ký khách. Điều kiện chất lượng và quyền hành động
là hai điều kiện độc lập. Native /goal không bảo đảm tiếp tục sau khi toàn bộ runtime dừng.

## Kiểm chứng

TDD: test import/adapter đỏ trước khi port/viết module. Sau đó kiểm schema, hash, authority,
self-approval, stale result, graph, native journal restart và CLI. Dữ liệu test là tổng hợp,
không là user research, browser audit hoặc chứng nhận sản phẩm. CI toàn repo là cổng riêng.

## Tiếp nối đúng kế hoạch

H3 lease/scheduler → H4 worker sandbox → H5/H6 trusted driver/exact-head review → H7 bridge
phiên chính. Module này cung cấp contract/result adapter cho các bước ấy, không tuyên bố đã thay thế chúng.

## Phát hiện qua kiểm thử tích hợp

DB hỏng hoặc schema `execution_events` không đúng làm constructor ExecutionJournal ném SQLite error
nhưng để kết nối sống. Hai test đỏ dùng SQLite thật tái hiện; sửa đóng kết nối khi PRAGMA/DDL lỗi, rồi
ném lại chính lỗi đó. Không nuốt lỗi, không thay schema/state machine.

## Bổ sung cùng PR theo ADR-0019

Những đoạn trên mô tả adapter ban đầu chỉ đọc/đánh giá. ADR-0019 thêm đường **tường minh**
`commit_quality_result` cho coordinator: lưu kết quả qua `ExecutionJournal.transition` nguyên tử.
`evaluate_result` vẫn không ghi DB. Không bật luồng Orchestrator hoặc quyền tự duyệt mới; không thay
sàn ADR-0043. Đây là bổ sung kiểm soát persistence, không tuyên bố H3–H7 đã hoàn thành.

## Nhãn miền không phải tên agent

CI toàn company đã bắt các literal trùng agent cũ trong schema được port. Không mở rộng miễn trừ
hoặc sửa bộ dò `test_roles.py`. Đổi surface thành `mobile_app`, chế độ đánh giá thành
`independent_review`, các dimension thành `product_fitness`, `application_security`, `data_integrity`.
Đây là nhãn sản phẩm/loại bằng chứng, không phải ID agent hoặc pha builder; không gán nhầm `ROLE.*`
để ghép nghĩa không liên quan. Policy tăng thành `product-excellence/2` để contract/receipt cũ không
được tái sử dụng dưới từ vựng mới. Profile và receipt của PR chưa phát hành nên không hỗ trợ alias
v1; caller phải biên dịch lại hợp đồng. Không đổi bất kỳ agent, topic hay gate đang vận hành.
