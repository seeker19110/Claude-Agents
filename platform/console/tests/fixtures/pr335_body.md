## Tóm tắt

Product excellence trong đúng repo `seeker19110/Claude-Agents`, tiếp tục theo yêu cầu chủ dự án. Giữ uv workspace, 6 agent, quality_floor/QualityBar ADR-0043 và execution kernel hiện có; không fork scheduler/journal hoặc thay agent prompts/registry/golden. X-Agents#113 mở nhầm đã đóng, không merge.

Phần nền: ProjectProfile/DesignBrief, kiểm bằng chứng theo contract/revision/context/principal, native execution adapter, atomic transition/CAS và commit_quality_result; `/product-goal` nối `/thi-hanh`.

**Lượt mới — tiếp thu chọn lọc projects-template:**
- `project-template` redirect tới cùng repository ID1283493926, canonical `seeker19110/projects-template`; ghim commit `23accce8a4b830eb07690cbd39dded8bf3bc94ce` và năm document blobs. Repo nguồn không bị sửa.
- `company.delivery_contract`: Ready có research/baseline/approval metadata/AC→test mapping; phân biệt Done của task với Complete của sản phẩm; PASS phải thực sự có check, không coi exit0/no-op là nghiệm thu.
- Nối vào Profile → compile_contract → native graph → assess → commit_quality_result hiện có, không thêm task điều phối hoặc DB riêng. Delivery report được ký/kiểm và lưu cùng kết quả.
- NOT_CONFIGURED không là PASS; NOT_APPLICABLE phải khai trước trong contract và không miễn các check nền. Complete chặn required work/finding còn mở, thiếu đo goal hoặc giảm guardrail.
- Profile không bật delivery giữ hash/signature v2 và đường ACK cũ; nguồn/policy adapter chỉ vào hash khi opt-in. Không tự migrate run đang làm.
- Thiết kế theo từng surface, ưu tiên quyết định/token/component của dự án; provider chỉ là tham khảo. Trước sửa lần hai cùng lỗi phải phân loại đúng tầng spec/design/code/verifier/knowledge.
- Không copy nguyên template, không chạy copy-framework, không nhập gate no-op hay substring-based spec approval, không cài provider/dataset/hook, không đổi workflow hoặc sàn CI.

## Issue / outcome

Chủ dự án giao mục tiêu; phiên chính/harness tự thực hiện trong quyền, ưu tiên chất lượng cao, công nghệ bền vững, dễ vận hành/bảo trì và UI/UX phù hợp dự án/ngành. Yêu cầu mới: nghiên cứu kỹ `seeker19110/project-template` và tích hợp điểm hữu ích vào Claude-Agents.

## Đặc tả / ADR

- Root ADR-0018 (native quality adapter), ADR-0019 (atomic result persistence).
- Company `docs/adr/0045-selective-template-delivery.md`, viết trước module mới.
- `docs/reports/2026-09-25-projects-template-adoption.md`: đối chiếu ba nhóm, quyết định lấy/giữ/loại và lý do.
- `docs/integrations/projects-template.lock.json`; `docs/PRODUCT-EXCELLENCE.md`.
- Cùng kế hoạch `docs/thi-hanh/productexcellence.md` Q7; session `docs/sessions/2026-09-25-template-adoption.md`.

## Loại thay đổi

- [x] feat
- [x] fix
- [x] docs
- [x] test
- [ ] breaking change

## BÁO CÁO XÁC THỰC — ae552c4bf2c82b3c9ff3fdc9c74964a34918d191

Cây Git `14bf194c71fc654d0c9163e1133ac464dd722646` khớp bản local đã kiểm. Commit nối tiếp head cũ, không force push. Lượt này 16 file, 60 ca mới; cả PR thêm 211 ca so với main, tổng 30 file thay đổi. Company 1641 ca/93 file; core không đổi trong lượt mới này.

- [x] TDD: import module mới đỏ trước code; negative cases cho thiếu readiness, PASS không chạy check, Done/Complete lệch và compatibility.
- [x] Nhóm delivery/quality/floor/role local: **240 passed**; ba module liên quan **596 statements/236 branches, 100% dòng và nhánh**.
- [x] Repo/command guards local **111 passed**, README data guard **1 passed**; không thêm skip hoặc thay cap.
- [x] Native graph/atomic commit/restart/ACK có delivery report được test; không worker thật được gọi.
- [x] Hash profile cũ đo bằng code parent và đối chiếu test cố định; signature bytes cũ giữ nguyên.
- [x] CLI schema/plan/register/register lặp/status exit0; run vẫn pending, không giả vờ đã thực thi worker.
- [x] **CI931 run36085819862: completed / success trên đúng head mới**, gồm company Windows và các cổng tổng hợp; không kế thừa dấu xanh của parent.
- [x] **CI company Ubuntu/Python3.13.15: 1641 passed in137.47s**, 6989 statements/2260 branches, 0 missed/partial, **100% coverage**; đã đọc log job107917364568.
- [x] Company Ubuntu3.11/3.13 và Windows3.13; core, Console, gateway, keeper trên các cấu hình CI đều đạt.
- [x] Ruff/mypy, audit/gitleaks, asset-scan, golden/eval, drift và protection guard đã đạt.
- [x] PR policy36085852382 và Dependency review36085819893: **success**.
- [x] Compare parent74bd6de1… → head mới đúng16 file; không dependency/model/provider hoặc workflow mới. Helper truyền patch đã tự gỡ khỏi nhánh phụ và không nằm trong cây/lịch sử PR.
- [ ] Review độc lập trước merge.

Local Python3.13.5. Locked gate offline dừng trước lint vì cache thiếu librt0.15.0; không tuyên bố toàn toolchain/full workspace local đạt. Các kết quả full toolchain ở trên là CI thật, được phân biệt với local. Các số test theo nhóm có giao nhau, không cộng thành một tổng duy nhất.

## Definition of Done

- [x] Source/test/docs cùng PR; source provenance, Ready/Done/Complete nối vào pipeline kiểm chứng hiện hữu.
- [x] Negative tests và compatibility; journal cũ không bị thay thế.
- [x] Toàn CI và PR policy trên head hiện tại đã đạt; PR không còn là bản nháp.
- [ ] Review độc lập trước merge; chưa tự merge hoặc bật runtime.

## Ranh giới

Approval metadata chỉ là cấu trúc, không xác thực/cấp quyền: coordinator phải lấy record thật. Gate observations phải do trusted driver đo; signed report không tự chứng minh phương pháp kiểm đúng. Fixture không là approval/user research/browser/product evidence thật. Artifact/keys/registry/pins giữ ngoài quyền worker.

Phần mới opt-in cho run mới, không tự đổi run đang làm hoặc chặn mọi Orchestrator release. Không bật daemon/autoapprove/production, không ký thay khách hoặc tự merge. H3–H7 và trusted execution/browser drivers vẫn là phạm vi riêng. Source template không trở thành runtime dependency hoặc state store mới. CI xanh của harness không chứng nhận chất lượng mọi sản phẩm do harness tạo.
