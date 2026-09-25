# Đối chiếu projects-template → Claude-Agents

Ngày: 2026-09-25. Yêu cầu: nghiên cứu kỹ nguồn và tích hợp điểm hữu ích, ưu tiên chất lượng.
Đích: `seeker19110/Claude-Agents`, nối tiếp PR #335 tại `74bd6de1`.
Nguồn: `seeker19110/project-template` trả redirect tới repository ID **1283493926**;
tên hiện tại **`seeker19110/projects-template`**, commit **23accce8a4b830eb07690cbd39dded8bf3bc94ce**.
Không sửa repo nguồn. Không lấy tên repo theo trí nhớ. SHA và blob ở `docs/integrations/projects-template.lock.json`.

## 1. Phương pháp và bằng chứng

Đọc README, CODEMAP, Standard Delivery, feature-spec template, quality-gates-by-profile,
ui-ux-intelligence-provider, adopt-from-outside, scripts/spec-compiler.py và scripts/dev-task.sh.
Đối chiếu với AGENTS/CLAUDE, scripts/dev-task.sh, product_quality/quality_execution/quality_floor,
execution journal và các test CI/role/skip/README đang chạy của đích, không chỉ văn xuôi.
Cây nguồn đích tái dựng từ snapshot + các patch trước khớp Git tree
`e4974aa54a040cd02286eee9a7838f2cc915b2ff` byte-for-byte trước chỉnh sửa.

### Đã có và sâu hơn — không nhập lại

| Ứng viên từ template | Đích đã có | Quyết định |
|---|---|---|
| Checkpoint/PROGRESS/Goal loop | ExecutionJournal atomic + result persistence, A–F cho luồng `/thi-hanh` trước H7 | Không thêm state machine/PROGRESS/Goal scheduler cạnh tranh. |
| Cổng dev theo stack | `scripts/dev-task.sh gate <gói>` cố định uv workspace và lệnh CI | Không thay bằng auto-detect; source header của đích đã ghi từng học template. |
| Evidence trong báo cáo PR | HMAC, principal, exact-head/context/contract, artifact hash, attempt/CAS | Giữ; bổ sung semantic report, không đổi sang tin Markdown/exit code. |
| Chặn skip/giảm coverage | `test_cong_repo`, fail_under, role guard, quality aggregate | Không copy detector/sổ cap khác. |
| Review độc lập/eval/model routing | 6 agent, pha, golden/recordings, routing và sàn quality_floor | Không nhập agent thứ bảy/coordinator thứ hai; không đổi model mặc định. |
| Security/supply-chain/release | CI audit/gitleaks/dependency review, exact-sha release và authority | Không copy toàn bộ workflow hoặc nới quyền. |

### Đã có nhưng còn điểm nông hơn — chỉ lấy đúng điểm thiếu

| Ứng viên | Khoảng trống cụ thể | Tích hợp |
|---|---|---|
| Ready vs Done vs Complete | Profile cũ không có metadata readiness/trace map hoặc mức task-vs-project | DeliveryContract opt-in, schema chặn Draft/placeholder/blocker/missing baseline và thiếu mapping. |
| Gate phải thực sự chạy | Assessor cũ xác minh chữ ký/status nhưng không kiểm report command có chạy check nào | `delivery.definition` yêu cầu đúng argv, exit0 và checks_executed>0 cho cổng command. |
| Tính áp dụng theo dự án | Không có semantic NOT_CONFIGURED vs NOT_APPLICABLE trong delivery report | N/A chỉ do contract khai trước; không tính N/A là PASS hoặc bù cho base check. |
| Reconcile hoàn tất | Backlog trống/Done dễ bị diễn giải thành hoàn tất sản phẩm | Complete còn chặn required work, blocking findings, thiếu goal measurement/guardrail; out-of-scope không chặn. |
| Thiết kế theo từng surface | DesignBrief có rationale nhưng chưa nêu cách xử lý nguồn provider và phạm vi redesign | Bổ sung hierarchy, mục tiêu surface và sửa hẹp vào chính tài liệu/command hiện hữu. |
| Sửa lỗi về đúng tầng | Retry bền đã có, nhưng hướng dẫn triage chưa phân biệt spec/design/code/tool/knowledge | Trước lần sửa thứ hai cùng lỗi phải ghi nguyên nhân/tầng, đưa specialist xử lý trong quyền. |

### Chưa có hoặc không phù hợp — chọn lọc, không tự mở rộng

| Ứng viên | Sự cố/điều kiện | Quyết định |
|---|---|---|
| Ghim phiên bản chuẩn nguồn mỗi run | Đã có nhầm repo ở PR113; source thay main có thể làm đổi nghĩa contract | Thêm nguồn canonical + ID + full commit + blob manifest; hash vào profile opt-in. |
| Chạy `copy-framework` nguyên khối | Sẽ cạnh tranh với AGENTS, hooks, CI và registry đang hoạt động | Không áp. Chỉ đọc ý tưởng, code adapter riêng. |
| Import generated contract tests từ spec-compiler | `approved` là substring match trên cả Markdown; template nháp chứa chính chuỗi Approved; metadata thiếu có đường skip | Không coi là approval hoặc gate tương đương. Dùng field exact-state + decision record; vẫn cần authority thật. |
| Vendor UI provider/dataset/hook mỗi lần edit | Chưa có failure cần một dependency/design engine cố định | Chưa cần; xem lại khi rubric và driver hiện hữu không tìm được nguyên nhân UX cụ thể. |
| Áp profile C1–C10/stack mặc định nguyên văn | Một số lời khuyên/provider/ngưỡng không hợp hệ trung lập model; mọi sản phẩm khác nhau | Tiếp thu cách chọn phép đo/rollback theo loại sản phẩm, không hardcode tool, model hay số universal. |

**Đính chính được giữ:** ban đầu cân nhắc import dev-task/spec compiler. Đọc code thật loại hai ứng viên:
dev-task của nguồn cố ý exit0 ở no-op; spec compiler chỉ kiểm cấu trúc/đường dẫn, không chứng minh behavior.
Không sửa detector nguồn hoặc che skip để gọi chúng là nghiệm thu đầy đủ.

## 2. Phần đã nối bằng code

`ProjectProfile.delivery` → kiểm Ready cấu trúc và AC→test → `compile_contract` ghim nguồn/policy →
`compile_execution` hiện có → quality barrier hiện có → `assess` kiểm receipt `delivery.definition` →
`commit_quality_result` lưu outcome/report qua journal atomic hiện có. Không thêm database hoặc execution task.

### Ready

Spec phải có state chính xác, approval record/principal/date + digest, research, phương án giữ nguyên,
trade-off, traceability và gate thực thi đã cấu hình. Brownfield cần baseline. Blocking decision không được
để lại trước compile. Đây chỉ là kiểm metadata; coordinator phải xác thực approval với nguồn quyền thật.
Không tự tạo chữ ký khách hoặc giả định “được code” đồng nghĩa “được deploy”.

### Done và Complete

Done: hoàn tất phạm vi task và các cổng done; không tuyên bố toàn project đã đóng.
Complete: đạt đích đã chọn và toàn cổng done+complete, không required item/P0-P1 còn mở, goal đã được đo,
guardrail không suy giảm. Các check product_quality trước đây vẫn bắt buộc theo tính áp dụng.
Các trường tổng hợp goal/guardrail phải lấy từ phép đo thật có artifact; đơn vị/điều kiện/giá trị vẫn được
kiểm riêng bởi QualityTarget và performance.budget, không thay bằng một boolean do model tự khai.

PASS của command cần đúng argv đã ghim, exit0 và số check thực thi dương. Inspection cần check thực tế
và tham chiếu bằng chứng, không bịa argv/exit code. FAIL/NOT_CONFIGURED chặn. NOT_APPLICABLE cần scope_reason
đã có trong contract trước chạy và không được ghi là đã thực thi. Reporter không tự miễn trừ cổng.

## 3. Thiết kế phù hợp dự án và ngành

Không thêm UI_SPEC.md/PRODUCT.md/DESIGN.md bắt buộc. Dùng DesignBrief và artifact design đang có.
Chọn mục tiêu **cho từng surface**, không cho toàn ngành một mẫu duy nhất:

| Mục tiêu surface | Cần ưu tiên và chứng minh |
|---|---|
| Thao tác/vận hành | Tốc độ hoàn thành nhiệm vụ, density theo vai, thứ bậc cảnh báo, chống thao tác nhầm. |
| Đọc/học | Nhịp đọc, typography/ngôn ngữ, tải nhận thức, tiến độ, trạng thái tiếp tục. |
| Khám phá/lựa chọn | So sánh, thông tin giá/giới hạn rõ, quyết định có căn cứ, không dark pattern. |
| Trải nghiệm/sáng tạo | Bản sắc, chất lượng nội dung/media, interaction phù hợp thiết bị và reduced-motion. |

Một ứng dụng giáo dục có thể vừa đọc/học (học viên) vừa vận hành (giáo viên); không nhân hai design system.
Chỉ ghi override có lý do cho page/role, còn semantic token/component chung được tái sử dụng.
Nguồn ngoài là dữ liệu tham khảo; không tự cài hoặc gửi secrets/PII; không để recommendation đổi ADR,
accessibility bắt buộc, token/component đã được dự án chọn. Chỉ sửa cả hệ khi mục tiêu thật yêu cầu.

## 4. Sửa đúng tầng, không làm lại mù

Trước lượt sửa thứ hai cùng failure: ghi lỗi, bằng chứng, giả thuyết và tầng product/spec, design/contract,
implementation, verifier/environment hoặc knowledge. Code sai thì sửa code; spec thiếu thì chốt phần thiếu;
CI thiếu binary không giao builder viết lại tính năng. Giữ patch/checkpoint tốt, vô hiệu hóa chỉ bằng chứng
chịu tác động. Trong quyền/ngân sách, phiên chính tự gọi đúng chuyên môn; thiếu authority hoặc tác động
khó đảo ngược mới là ngoại lệ cần người. Không chép luật hỏi người cho mọi vòng lặp từ nguồn.

## 5. Tương thích và giới hạn

Profile không chọn delivery giữ bytes/hash/signature v2; có test hash cố định đo từ parent thật.
Native journal/result fingerprint vẫn được kiểm ACK/restart. Update snapshot chuẩn qua PR review,
không tự fetch main lúc chạy. Field mới opt-in cho run mới; không tự di chuyển run đang làm.

Không có worker daemon, browser driver, deployment, lease hoặc identity service mới. Adapter không thực
thi argv hay tải nguồn. Đưa số check giả vào trusted signer vẫn là sai tại trust boundary; test không
thay independent review/driver qualification. File ví dụ và test là synthetic, không approval/evidence thật.

## 6. Nguồn

Tất cả đường dẫn nguồn sau ở `seeker19110/projects-template@23accce8a4b830eb07690cbd39dded8bf3bc94ce`:
`docs/framework/standard-delivery.md`, `quality-gates-by-profile.md`, `templates/FEATURE-SPEC.template.md`,
`ui-ux-intelligence-provider.md`, `adopt-from-outside.md`, `scripts/spec-compiler.py`, `scripts/dev-task.sh`.
Các đường dẫn rút gọn trong câu này tương đối với `docs/framework/` trừ `scripts/`.

GitHub xác nhận job bị skip có thể hiển thị Success:
https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions
Pydantic strict/revalidate:
https://docs.pydantic.dev/latest/api/config/
Những nguồn này hỗ trợ thiết kế xác minh; không tuyên bố đạt chứng nhận ngành.
