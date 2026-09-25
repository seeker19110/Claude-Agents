# Product excellence — tích hợp đúng Claude-Agents

Ngày 2026-09-25 · căn cứ `main@b84dcb76b9085a686dafae97f47c988ac872446a` (#334).
Một hạng mục, hai package (company + core); đây là kế hoạch tích hợp contract, không thay kế hoạch H3–H7.

## A. Hiện trạng

Repo đích là `seeker19110/Claude-Agents`. Không dùng PR #113 của repo `X-Agents` làm bằng chứng đã tích hợp.
Workspace/6 agent/sàn tự duyệt/kernel đã tồn tại; giữ chúng. Profile sản phẩm và adapter exact-context còn thiếu.

| Đề bài cần | Đã có ở base | Việc |
|---|---|---|
| Core giữ state | `platform/xagents-core/src/xagents_core/execution.py:140–204,424–498`, RunSpec/journal | Q2 nối, không fork |
| Chất lượng trước tự duyệt | `companies/software-company/src/company/quality_floor.py:108–123` | Giữ sàn ADR-0043, không auto-bypass |
| Layout/UI/UX theo dự án/ngành | Skills hiện có; chưa có ProjectProfile/DesignBrief máy kiểm trong kernel adapter | Q1 |
| Một lệnh đi hết quy trình | `.claude/commands/thi-hanh.md:1–66`, state A–F hiện hành | Q3 nối entrypoint |
| Lỗi init journal không rò kết nối | `execution.py:424–430` trước sửa: PRAGMA/DDL không cleanup lỗi | Q4, hai test SQLite thật |

Số dòng tham chiếu base là điểm bắt đầu đọc, không thay đọc toàn hàm. ADR-0017 nói rõ H1/H2 foundation,
không coi còn đủ H3/H4/H5/H6/H7 hoặc driver browser/restore đã được triển khai.

## B. Kế hoạch

| Mã | Việc | Mảng | Hạng mục | Mức | Lợi ích / đánh đổi | Khi nào |
|---|---|---|---|---|---|---|
| Q1 | Profile, design, policy và receipt checker | company | product-excellence | C2 | Chuẩn rõ, cần trusted driver cung cấp bằng chứng | xong #335 |
| Q2 | RunSpec/TaskResult/journal adapter | company/core API | product-excellence | C3 | Tái dùng kernel, chưa thay worker/scheduler | xong #335 |
| Q3 | Command, charter, indexes và bản ghi tích hợp | docs | product-excellence | C1 | Một đường vào, thêm tài liệu cần giữ đồng bộ | xong #335 |
| Q4 | Cleanup journal init thất bại | core | product-excellence | C2 | Không rò connection, giữ nguyên lỗi/schema | xong #335 |
| Q5 | Atomic transition/CAS và kết quả quality bền | core/company | product-excellence | C3 | Chặn ghi trùng/sai state, cần coordinator tin cậy | xong #335 |
| Q6 | Test symlink không skip theo quyền OS | company tests | product-excellence | C2 | Giữ test ranh giới trên Windows/Linux, không tăng trần | xong #335 |
| Q7 | Tiếp thu chọn lọc projects-template: Ready/Done/Complete và design provenance | company/docs | product-excellence | C3 | Chặn thiếu kiểm tra/nhầm mức hoàn tất, giữ nguyên contract cũ khi không bật | xong #335 |

Cố ý không làm: đổi 6 prompt/golden/eval; bật cờ tự duyệt; cấp quyền production; scheduler/lease/bridge H7
thứ hai; chứng nhận ngành giả; dùng fixture receipt làm bằng chứng sản phẩm. Không migration run đang hoạt động.
Rủi ro chính: caller không đáng tin có thể tự truyền pins/registry — adapter phải nằm sau coordinator cách ly,
không dùng nó như chứng nhận tự chủ hoặc security boundary hoàn chỉnh.

## C. Gói việc

### Q1 — domain quality
1. Mục tiêu: contract theo goal, ngành, bề mặt, acceptance, target và Design Brief.
2. Scope: `company/product_quality.py`, test tương ứng và ví dụ; không sửa collector/runtime hiện tại.
3. Input: profile do director dựng, context/candidate/author/registry do coordinator giữ.
4. Output: contract hash + required checks + Assessment; không grant authority.
5. API: `compile_contract(profile)`, `required_checks(profile)`, `assess(profile, receipts, **pins)`.
6. Bất biến: missing/unknown/fail/stale/self-approval/artifact đổi → không pass; không nới ngưỡng.
7. Test: 84 ca kể cả CLI và key path; 100% line/branch. PR `feat(company): product excellence — native execution quality adapter`.

### Q2 — native execution
1. Mục tiêu: không tạo DAG/state/journal thứ hai.
2. Scope: `company/quality_execution.py`, tests, work spec ví dụ.
3. Input: `xagents_core.execution.RunSpec` gốc + profile; native TaskResult + trusted pins.
4. Output: graph giữ scope có task quality cuối; TaskResult đã đánh giá; CLI plan/register/status.
5. API: `compile_execution(profile, work) -> RunSpec`, `evaluate_result(...) -> TaskResult`.
6. Bất biến: không tự append success; pin/attempt/base/head/diff không khớp → fail; lặp register không nhân run.
7. Test: 30 ca; thực thi core journal restart và retry, không replay implementation đã xong. Chung PR Q1.

### Q3 — main-session contract
1. Mục tiêu: một goal, hợp đồng chất lượng đúng ngành, không đòi người dùng điền technical profile.
2. Scope: `.claude/commands/product-goal.md`, liên kết `/thi-hanh`, charter, README/CODEMAP/AGENTS/CLAUDE.
3. Input: goal của chủ dự án, constraints/quyền và quyết định đã có.
4. Output: A–F + profile + evidence plan; state hiện hành không đổi trước H7.
5. Giao diện: `/product-goal <mã> <mục tiêu>`; không che `/goal` native.
6. Bất biến: không claim daemon, không giả user research, không coi CI xanh là UX đẹp/đúng.
7. Test: cổng command frontmatter/path hiện có + readme counts; kiểm diff chỉ thêm đúng phạm vi. Chung PR Q1.

### Q4 — initialization failure
1. Mục tiêu: constructor SQLite lỗi không để connection sống.
2. Scope: init ExecutionJournal và một test file core; không đổi journal schema hoặc success transition.
3. Input: DB hỏng bytes hoặc execution_events schema hỏng.
4. Output: giữ SQLite exception, connection bị đóng.
5. Code: `try PRAGMA/DDL; except sqlite3.Error: close(); raise`.
6. Bất biến: happy path/replay không đổi; không nuốt lỗi và không fake success.
7. Test: 2 ca SQLite thật đỏ trước sửa; toàn core 544 đạt, 100% dòng/nhánh. Chung PR Q1 vì được phát hiện khi nối adapter.

### Q5 — atomic quality persistence
1. Mục tiêu: state và kết quả nghiệm thu không bị tách khi mất phản hồi hoặc restart.
2. Scope: execution.py, quality_execution.py và test, không đổi worker pool/scheduler.
3. Input: event count của run, stable submission ID, QualityBindings do coordinator giữ.
4. Output: RunState và event chứa TaskResult/receipt; không grant quyền bên ngoài.
5. API: `ExecutionJournal.transition(event, expected_count=...)`, `commit_quality_result(...)`.
6. Bất biến: stale/collision/attempt lệch bị chặn; duplicate chỉ ACK; không gọi model trong transaction.
7. Test: SQLite thật hai connections, rollback, restart, quality fail/retry, receipt serialization.

### Q6 — test đa nền tảng
1. Mục tiêu: không bỏ test ranh giới artifact khi tài khoản không được tạo symlink.
2. Scope: test_product_quality.py, không sửa guard/trần của console.
3. Input: symlink thật khi được hỗ trợ; mô phỏng có tên rõ khi OS từ chối quyền.
4. Output: cùng assertion từ chối artifact ngoài evidence_root.
5. API: không thay API production.
6. Bất biến: không skip/xfail thêm, hash nội dung ngoài khớp để chắc lỗi là path boundary.
7. Test: hai nhánh real/fallback; guard skip fail trước, xanh sau.

### Q7 — selective projects-template adoption
1. Mục tiêu: nghiên cứu khung nguồn, chỉ đưa điểm còn thiếu vào pipeline quality hiện có.
2. Scope: company delivery_contract/product_quality, tests, ví dụ và tài liệu; không sửa core/gate/agent registry.
3. Input: nguồn `seeker19110/projects-template@23accce8a4b830eb07690cbd39dded8bf3bc94ce`, profile, hồ sơ phê duyệt thật do coordinator cấp.
4. Output: Ready có AC/test mapping; receipt phân biệt Done/Complete, NOT_CONFIGURED và NOT_APPLICABLE; source lock trong contract hash.
5. API: `DeliveryContract`, `DeliveryReport`, `delivery_gaps`; nối `compile_contract`/assess và journal hiện có, không tạo journal mới.
6. Bất biến: exit0 nhưng không chạy check không là pass; không miễn 33 check cũ; không đổi hash/signature profile không bật tích hợp; metadata approval không tự cấp quyền.
7. Test: 60 ca mới, nhóm quality/floor/role 240 ca đạt 100% ba module; ký receipt → lưu journal → restart/ACK thật. CI trên head mới vẫn là cổng riêng.

## D. Điều phối

Q1 → Q2; Q3 độc lập khi API đã chốt; Q4 phát hiện từ integration test. Một PR cho cả hạng mục.
Phiên ChatGPT này không có công cụ spawn subagent thực thi; không ghi review độc lập giả. Test và đọc diff
đã làm trực tiếp; review độc lập vẫn là điều kiện trước merge. Không ép người dùng chạy lại bản tích hợp từ đầu.

## E. Kiểm chứng và phần còn lại

Bằng chứng đợt đầu (lịch sử, không là kết luận của head mới): core local 544/544, 100% dòng/nhánh. Company đã collect 1569 ca; riêng modules mới + quality_floor cũ:
158 ca đạt, 100% hai module mới. Một test integration cũ fail giống hệt khi chạy base và nhánh mới trong
môi trường thiếu toolchain đầy đủ. Full company local bị timeout; không gọi đó là toàn suite đạt.
Kết quả CI trên đúng SHA của PR là cổng độc lập và phải được cập nhật vào session/PR.

Đợt Q7: 60 test mới; company collect 1641 ca / 93 file. Nhóm quality/floor/role: 240 đạt;
repo/command guards: 111 đạt. Ba module quality/delivery: 596 statements, 236 branches, 100%.
Full toolchain local chưa chạy được do thiếu wheel librt trong cache offline; kết quả CI trên head Q7
phải cập nhật ở PR/session, không kế thừa dấu xanh của 74bd6de1. Bản đối chiếu nguồn:
`docs/reports/2026-09-25-projects-template-adoption.md`.

## F. Lệnh thi hành

`/thi-hanh productexcellence` — đọc bảng B/PR trước, tiếp phần chưa hoàn tất; không tạo lại Q1–Q7 đã có.
`/thi-hanh productexcellence --dung-sau-ke-hoach` — chỉ đọc trạng thái. Nâng H3–H7 theo ADR-0017, không
coi lệnh này tự cài worker daemon, driver browser, quyền deploy hoặc khóa ký.
