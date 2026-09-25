# Product Excellence v2: nối adapter chất lượng vào runtime và đóng ranh giới tin cậy

Ngày 2026-09-25. Căn cứ `main@6d74ba3` (#335). Bản đánh giá đầu vào nằm ở `docs/reports/2026-09-25-danh-gia-pr335.md`.
Kế hoạch này nối tiếp `docs/thi-hanh/productexcellence.md` (Q1–Q7, đã merge), không thay thế nó. Nó cũng không
thay kế hoạch H3–H7 của ADR-0017.

## A. Hiện trạng

### A1. Kết luận

- #335 đã đưa vào repo contract chất lượng, assessor fail-closed, adapter `RunSpec`/`TaskResult` và `transition` CAS. Toàn bộ có test, coverage 100%.
- **Chưa có caller trong runtime.** Không file nào trong `src/` gọi `commit_quality_result` hay `ExecutionJournal`, và orchestrator không biết tới profile.
- Ranh giới tin cậy còn hai lỗ. Thứ nhất, HMAC khoá chung cho phép verifier ký thay reviewer. Thứ hai, pha Ready không kiểm người duyệt, thời điểm duyệt và hash của spec.
- Còn ba lỗi nhỏ hơn: CAS dựa vào `expected_count` do caller cấp, mọi target bị gom vào `performance.budget`, `append` vẫn công khai.
- #335 đã merge khi ô "Review độc lập trước merge" còn trống. Hiện không cổng nào chặn việc này.

### A2. Bảng đối chiếu

| Đề bài cần | Repo có | Ở đâu | Mã việc |
|---|---|---|---|
| Chặn merge khi DoD còn ô mở | không có (pr-policy chỉ kiểm CHANGELOG, ADR-0034, nhắc nhật ký phiên) | `.github/workflows/pr-policy.yml:35–80` | P0 |
| CAS gắn với snapshot mà quyết định dựa trên | `expected_count` do caller truyền, tách khỏi `history` | `companies/software-company/src/company/quality_execution.py:147,177–186,201` | P1 |
| Một đường ghi journal có validate | `append` công khai, không validate | `platform/xagents-core/src/xagents_core/execution.py:463` | P1 |
| Target gắn đúng check | `_targets_met` ép mọi target vào `performance.budget` | `companies/software-company/src/company/product_quality.py:326–335,407` | P2 |
| Policy evidence theo profile | hằng cứng `MAX_EVIDENCE_AGE`, `MAX_ARTIFACT_BYTES` | `product_quality.py:35–36` | P2 |
| Ready: người duyệt khác tác giả, không ở tương lai, hash spec thật | chỉ kiểm cấu trúc | `companies/software-company/src/company/delivery_contract.py:38–44`, `product_quality.py:409–412` | P3 |
| Chữ ký mà verifier không giả được | HMAC khoá chung, registry giữ khoá bí mật | `product_quality.py:271–291,423–439` | K1, K2 |
| Khoá đủ entropy | `len(key) < 32` trên byte thô | `product_quality.py:280` | K1 |
| Orchestrator đăng ký và chạy `quality:accept` | không có | không có (grep `ExecutionJournal` trong `src/`: chỉ `quality_execution.py`) | N1 |
| Release bị chặn khi quality chưa đạt | sàn ADR-0043 không biết profile | `companies/software-company/src/company/quality_floor.py:62–76,86–119,168–219` | N2 |
| Console hiển thị blocker quality | không có | không có | N3 |
| `AGENTS.md` ngắn, trỏ đúng chỗ | 15 dòng thuật ngữ dày | `AGENTS.md` mục "Mục tiêu chất lượng sản phẩm" | P0 |

## B. Kế hoạch

| Mã | Việc | Mảng | Hạng mục | Mức | Ưu | Nhược | Khi nào |
|---|---|---|---|---|---|---|---|
| P0 | pr-policy chặn DoD và khối xác thực còn `- [ ]`; rút gọn đoạn trong `AGENTS.md` | ci/docs | pe2-quytrinh | C1 | Rẻ, chặn lặp lại P2 của #335 | PR cũ đang mở phải sửa thân | xong #337 |
| P1 | CAS tự đếm từ snapshot; `append` thành `_append_unchecked` kèm alias deprecated; test cổng cấm `src/` gọi `append` | core/company | pe2-cung | C2 | Bỏ lệ thuộc kỷ luật caller | Đổi chữ ký công khai (giữ tương thích một vòng) | xong #338 |
| P2 | `QualityTarget.check_id`; `evidence_policy` có trần trong profile; `POLICY_VERSION` `/3` chỉ khi có trường mới | company | pe2-cung | C2 | Target đúng driver; policy theo rủi ro | Thêm trường schema | xong #338 |
| P3 | Ready thật: người duyệt không phải tác giả, `approved_at` hợp lệ, băm lại spec, `ApprovalLookup` | company | pe2-cung | C2 | Ready có nghĩa thật | Cần coordinator cấp lookup | xong #338 |
| K1 | ADR gốc 0020: chữ ký bất đối xứng, xoay khoá, lộ trình HMAC | docs | pe2-ky | C3 | Quyết định dependency trước code | Viết ADR tốn một vòng | ◐ PR #339 (ADR-0020 Accepted) |
| K2 | Ed25519 + `key_id` + `not_after`; registry chỉ chứa public key; HMAC chỉ cho contract ghim `legacy_hmac` | company | pe2-ky | C3 | Verifier hết ký giả được | Thêm dependency `cryptography` | ◐ PR #339 |
| N1 | ADR gốc 0021 và orchestrator: đăng ký RunSpec khi ticket có profile, giao `quality:accept` cho trusted driver, CLI `commit` | company | pe2-noi | C3 | Adapter có giá trị thật | Đụng runtime, rủi ro hồi quy | ◐ ADR-0021 Accepted (chủ dự án giao chốt chất lượng cao) |
| N2 | `quality_floor`: gap R6 khi run có profile mà `quality:accept` chưa `succeeded` | company | pe2-noi | C3 | Release không lọt khi thiếu nghiệm thu | Thêm một nguồn bằng chứng | chưa |
| N3 | Console hiển thị trạng thái `quality:accept` và blocker | console | pe2-noi | C2 | Người trực thấy lý do chặn | Thêm một view | chưa |
| N4 | Ghi chú ADR-0018 "Accepted, đã nối runtime"; `CODEMAP.md` có dòng quality | docs | pe2-noi | C1 | Tài liệu khớp thực tế | — | chưa |
| N5 | ADR core và code: `quality:accept` chạy lại được khi candidate sha đổi sau `SUCCEEDED` (attempt mới ràng sha mới, giữ lịch sử) | core/company | pe2-noi2 | C3 | Nghiệm thu lại không cần ký profile mới | Đổi máy trạng thái ADR-0017 | chưa (sau pe2-noi) |

Bốn hạng mục, theo thứ tự PR: **pe2-quytrinh → pe2-cung → pe2-ky → pe2-noi**. Mỗi hạng mục ≤ 8 mã và ≤ 2 package.

**Cố ý không làm:**
- Không bật daemon, autoapprove hay quyền production. Sàn ADR-0043 giữ nguyên, R6 chỉ **thêm** gap.
- Không migrate run v2 đang có. Hash và chữ ký của chúng phải giữ nguyên byte.
- Không sửa prompt, golden hay eval của 6 agent. Không mã nào chạm `agents/`/`skills/`.
- Không viết driver browser/restore thật (H3–H7). N1 chỉ nối **giao diện** trusted driver cùng một driver fake cho test.
- Không gỡ `append` trong hạng mục này, chỉ đổi tên kèm alias. Gỡ hẳn khi grep không còn caller, sau ít nhất một PR.

**Rủi ro của chính file này:**
- Số dòng trong A2 lấy từ `main@6d74ba3` và sẽ lệch khi các hạng mục trước merge. Gói sau phải đọc lại hàm, không tin số dòng.
- K2 phụ thuộc quyết định dependency trong K1. Nếu ADR chọn phương án không thêm dependency thì gói K2 phải viết lại trước khi giao.

## C. Gói việc

### P0 — cổng DoD và gọn AGENTS.md
1. **Mục tiêu:** PR không merge được khi mục "Definition of Done" hoặc khối "BÁO CÁO XÁC THỰC" còn ô `- [ ]`, trừ ô có nhãn `(sau merge)`.
2. **Scope:** `.github/workflows/pr-policy.yml`, một script `scripts/pr_dod_check.py` cùng test của nó, và `AGENTS.md` (đoạn "Mục tiêu chất lượng sản phẩm" rút còn ≤ 5 dòng, chi tiết trỏ sang `docs/PRODUCT-EXCELLENCE.md`).
3. **Input:** thân PR qua biến `BODY`, giống bước ADR-0034.
4. **Output:** exit 1 kèm danh sách ô còn mở, hoặc exit 0.
5. **Khung code:** `def open_items(body: str) -> list[str]` chỉ xét các mục `## Definition of Done` và `## BÁO CÁO XÁC THỰC`, tới heading `##` kế tiếp. `def main(argv: list[str] | None = None) -> int`.
6. **Bất biến:**
   - Ô ở mục khác (ví dụ "Loại thay đổi") không bị xét.
   - Thân rỗng hoặc không có mục DoD là pass. Cổng này không đòi template, chỉ chặn ô mở.
   - Script không in lại thân PR.
7. **Test:**
   - Ô mở trong DoD → 1.
   - Ô mở có `(sau merge)` → 0.
   - Ô mở ở "Loại thay đổi" → 0.
   - Chiều ngược: thân #335 nguyên văn (lưu thành fixture) → 1.
   - Test cổng README/command hiện có vẫn xanh.
   - PR: `ci: pe2-quytrinh — chặn merge khi Definition of Done còn ô mở`.

### P1 — CAS chặt và một đường ghi
1. **Mục tiêu:** quyết định và CAS dựa trên cùng một snapshot. `src/` chỉ ghi qua `transition`.
2. **Scope:** `platform/xagents-core/src/xagents_core/execution.py`, `companies/software-company/src/company/quality_execution.py` và test của hai file. Thêm một test cổng trong `platform/xagents-core/tests/`.
3. **Input:** journal SQLite thật, hai connection.
4. **Output:**
   - `commit_quality_result` tự dùng `len(history)`. `expected_count` thành tuỳ chọn: nếu truyền thì phải bằng, lệch thì ném `ExecutionJournalError`.
   - `ExecutionJournal._append_unchecked`. `append` còn lại như alias, phát `DeprecationWarning`.
5. **Khung code:** `def commit_quality_result(journal, profile, result, receipts, *, event_id: str, bindings: QualityBindings, trusted_issuers, evidence_root, expected_count: int | None = None, now=None) -> RunState`; `def _append_unchecked(self, event: ExecutionEvent) -> None`.
6. **Bất biến:**
   - Redelivery giống hệt vẫn ACK.
   - Collision vẫn fail.
   - Test cũ của #335 giữ nguyên assertion; chỉ đổi lời gọi nếu bắt buộc.
7. **Test:**
   - Chen `TASK_STARTED` attempt mới giữa lúc đọc và lúc ghi → `stale event count`.
   - Truyền `expected_count` lệch → lỗi.
   - `append` phát `DeprecationWarning`.
   - Test cổng: grep `\.append\(` trên đối tượng journal trong `src/` phải rỗng. Chiều ngược: thêm một lời gọi giả thì test đỏ.
   - PR (chung hạng mục): `fix(company): pe2-cung — CAS, target theo check và Ready thật cho quality contract`.

### P2 — target theo check, policy theo profile
1. **Mục tiêu:** mỗi `QualityTarget` được kiểm ở receipt của đúng check. Thời hạn và kích thước evidence cấu hình được trong trần.
2. **Scope:** `product_quality.py`, `tests/test_product_quality.py`, `examples/product-quality-profile.json`.
3. **Input:** profile. `QualityTarget.check_id` mặc định `performance.budget`. `ProjectProfile.evidence_policy: EvidencePolicy | None`.
4. **Output:** `_targets_met(profile, evidence, check_id)` chỉ lọc target của check đó. `assess` áp target cho mọi check có target.
5. **Khung code:**
   - `class EvidencePolicy(StrictModel)` với `max_age_seconds: int = Field(ge=3600, le=604800)` và `max_artifact_bytes: int = Field(ge=1, le=268435456)`.
   - Serializer bỏ `check_id` khi bằng mặc định, và bỏ `evidence_policy` khi `None`, để giữ byte của v2.
6. **Bất biến:**
   - Profile không dùng trường mới giữ nguyên `contract_hash` v2, đối chiếu với hằng số fixture có sẵn.
   - `check_id` phải thuộc `required_checks(profile)`.
7. **Test:**
   - Target gắn `accessibility.automated` được kiểm ở receipt a11y; receipt perf thiếu target đó vẫn pass.
   - `check_id` không bắt buộc → lỗi validate.
   - `max_age` ngoài trần → lỗi.
   - Chiều ngược: hash v2 của `examples/product-quality-profile.json` không đổi.

### P3 — Ready thật
1. **Mục tiêu:** pha Ready kiểm người duyệt, thời điểm và nội dung spec.
2. **Scope:** `delivery_contract.py`, `product_quality.py` (nhánh `delivery.definition`), `tests/test_delivery_contract.py`.
3. **Input:** `author_principals`, `now` và `evidence_root` sẵn có trong `assess`. Thêm `approval_lookup: ApprovalLookup | None`.
4. **Output:** thêm các gap `spec_self_approval`, `spec_approved_in_future`, `spec_approved_after_evidence`, `spec_artifact_changed` và `approval_record_unverified`.
5. **Khung code:**
   - `class ApprovalLookup(Protocol): def approved(self, record: str, artifact_sha256: str) -> str | None` (trả về principal đã duyệt).
   - `def ready_gaps(contract: DeliveryContract, *, authors: frozenset[str], now: datetime, earliest_evidence: datetime, evidence_root: Path, lookup: ApprovalLookup | None) -> tuple[str, ...]`.
6. **Bất biến:**
   - `lookup is None` → luôn có `approval_record_unverified`. Không có lookup thì không PASS.
   - Profile không có `delivery` không bị ảnh hưởng.
   - Dùng lại `_artifact_valid`, không viết bản thứ hai.
7. **Test:** mỗi gap có một ca đỏ riêng; một ca xanh với lookup fake được gắn cờ rõ. Chiều ngược: bỏ nhánh self-approval thì ca tự duyệt phải đỏ.

### K1 — ADR chữ ký bất đối xứng
1. **Mục tiêu:** quyết định scheme, dependency, xoay khoá và lộ trình rút HMAC trước khi viết code.
2. **Scope:** `docs/adr/0020-chu-ky-bat-doi-xung-receipt.md`. Nếu 0020 đã bị dùng thì lấy số kế tiếp.
3. **Input:** P3 trong `docs/reports/2026-09-25-danh-gia-pr335.md`, cùng hiện trạng đo được: số issuer, nơi giữ khoá.
4. **Output:** ADR theo `/adr`, với ít nhất ba phương án:
   - Ed25519 qua `cryptography`.
   - HMAC mỗi issuer với verifier tách tiến trình.
   - Sigstore/keyless (loại vì cần mạng).
5. **Khung:** các mục của `docs/adr/README.md`.
6. **Bất biến:** run v2 verify được mãi; contract mới không nhận HMAC.
7. **Test:** không có code. `sc-security` chấm ADR. PR (chung hạng mục): `feat(company): pe2-ky — receipt ký Ed25519, verifier không giả được reviewer`.

### K2 — Ed25519 và xoay khoá
1. **Mục tiêu:** ai chỉ giữ registry thì không tạo được receipt hợp lệ.
2. **Scope:** `product_quality.py`, `pyproject.toml` + `uv.lock` (thêm dependency theo K1), test, `examples/`.
3. **Input:** registry `{issuer: {principal_id, mode, allowed_checks, keys: [{key_id, public_key_pem, not_after}]}}`.
4. **Output:** `Receipt.signature_scheme` và `Receipt.key_id`. Verify theo scheme được contract cho phép.
5. **Khung code:**
   - `def sign_evidence(evidence, private_key: Ed25519PrivateKey, key_id: str) -> Receipt`.
   - `def verify_receipt(receipt, issuer: TrustedIssuer, *, now, allowed_schemes) -> str` (trả về chuỗi rỗng hoặc lý do).
   - Giữ `sign_evidence_hmac` cho test tương thích.
6. **Bất biến:**
   - Chữ ký v2 của fixture cũ giữ nguyên byte.
   - Key quá `not_after` bị từ chối.
   - Cùng một public key cho hai principal → blocker, như hiện tại.
7. **Test:**
   - Ký bằng mọi byte có trong registry → `invalid_signature`.
   - Key hết hạn → lỗi.
   - HMAC trên contract mới → `scheme_not_allowed`.
   - Chiều ngược: receipt HMAC v2 vẫn pass trên contract v2.

### N1 — orchestrator đăng ký và chạy quality
1. **Mục tiêu:** ticket có `ProjectProfile` thì được đăng ký RunSpec. Task `quality:accept` do trusted driver chạy, và kết quả đi qua `commit_quality_result`.
2. **Scope:**
   - ADR `docs/adr/0021-noi-quality-vao-orchestrator.md`, viết trước code.
   - Một module mới `companies/software-company/src/company/orch/quality_flow.py`.
   - Điểm gọi trong orchestrator.
   - CLI `quality_execution commit`.
   - Test e2e với provider `fake`.
3. **Input:** profile đính kèm lúc intake/spec. Thời điểm đọc sẽ chốt trong ADR 0021.
4. **Output:** journal có run, task công việc chạy như cũ, `quality:accept` pending tới khi driver nộp receipt.
5. **Khung code:**
   - `def register_quality_run(o: Orchestrator, ticket_id: str, profile: ProjectProfile) -> None`.
   - `def submit_quality(o: Orchestrator, run_id: str, result: TaskResult, receipts: list[Receipt]) -> RunState`.
   - `class TrustedDriver(Protocol): def run(self, run_id: str, checks: tuple[str, ...]) -> tuple[TaskResult, list[Receipt]]`.
6. **Bất biến:**
   - Ticket không có profile chạy y hệt trước: golden không đổi, toàn bộ test orchestrator cũ xanh.
   - Worker agent không bao giờ được giao `quality:accept`.
   - Khoá và registry không nằm trong worktree ticket.
7. **Test:**
   - E2E fake: đủ receipt → `succeeded`.
   - Thiếu một receipt → `failed` với `<check>:missing`.
   - Restart giữa chừng → resume đúng.
   - Chiều ngược: gỡ điểm gọi thì e2e đỏ.
   - PR: `feat(company): pe2-noi — orchestrator chạy nghiệm thu quality contract và chặn release khi chưa đạt`.

### N2 — gap R6 trong sàn chất lượng
1. **Mục tiêu:** release có ticket mang profile không được tự duyệt khi `quality:accept` chưa `succeeded` ở đúng staged sha.
2. **Scope:** `quality_floor.py` (`QualityEvidence`, `_release_gaps`, `collect_evidence`), `tests/test_quality_floor*.py`.
3. **Input:** trạng thái journal của các run gắn với ticket của release.
4. **Output:** gap `R6: nghiệm thu quality contract chưa đạt ở sha đã staged (<run_id>: <blockers>)`.
5. **Khung code:** thêm trường `product_quality: tuple[tuple[str, str | None, str | None], ...]` gồm `(run_id, status, head_sha)`, mặc định `()` để không vỡ các lời gọi cũ.
6. **Bất biến:** chỉ **thêm** gap, không gỡ gap nào. Release không có profile giữ nguyên kết quả `floor_gaps`.
7. **Test:**
   - Run failed → R6.
   - Run succeeded nhưng khác sha → R6.
   - Succeeded đúng sha → không có R6.
   - Chiều ngược: bỏ R6 thì ca đầu phải đỏ.

### N3 — console
1. **Mục tiêu:** trang trực ban hiển thị trạng thái `quality:accept` và blocker của từng release.
2. **Scope:** `platform/console/src/console/` (view hiện có của release) và test console.
3. **Input:** journal (chỉ đọc).
4. **Output:** một khối "Quality contract" liệt kê trạng thái, check đã pass và blocker.
5. **Khung code:** chốt sau khi đọc view release hiện có. Gói giao cho subagent phải ghi tên hàm thật.
6. **Bất biến:** console không ghi journal. Journal không tồn tại thì hiện "không có profile", không tạo file rỗng.
7. **Test:** render với journal fake có blocker; chiều ngược: journal thiếu thì không có file mới.

### N4 — tài liệu khớp runtime
1. **Mục tiêu:** ADR-0018 và `CODEMAP.md` nói đúng trạng thái sau N1–N3.
2. **Scope:** `docs/adr/0018-product-quality-execution-adapter.md` (thêm mục trạng thái), `CODEMAP.md`, `docs/PRODUCT-EXCELLENCE.md`.
3. **Input:** các PR đã merge.
4. **Output:** mỗi file thêm một hai dòng.
5. **Khung:** không có code.
6. **Bất biến:** cổng `test_codemap_duong_dan.py` xanh.
7. **Test:** cổng đường dẫn CODEMAP; README guard.

## D. Điều phối

| Đợt | Song song (phát triển) | Thứ tự PR | Điều kiện vào đợt |
|---|---|---|---|
| 1 | P0 | PR pe2-quytrinh | PR này merge |
| 2 | P1, P2, P3 (P3 sau P1 nếu cùng sửa `assess`) | PR pe2-cung | pe2-quytrinh merge |
| 3 | K1 → K2 | PR pe2-ky | pe2-cung merge; ADR K1 được người đồng ý dependency |
| 4 | N1 → N2, N3 → N4 | PR pe2-noi | pe2-ky merge; ADR 0021 viết xong |

- **Mức → model:** theo `docs/KHUON-THI-HANH.md` §2.
- **Ai chấm:** `sc-qa` chấm mọi gói C2/C3. `sc-security` chấm P3, K1, K2, N1. `sc-gate-release` chấm N2.
- **Khuôn giao việc:** §4 của khuôn.
- **Cần người:** chọn dependency ở K1 và duyệt ADR 0021. Nếu chưa có người thì ghi `chờ người` ở cột "Khi nào" và làm tiếp gói không phụ thuộc.

**Definition of Done cả đề bài:**
- Mọi mã `xong #n`.
- `scripts/dev-task.sh gate all` xanh trên head cuối, có output dán trong PR.
- Hash và chữ ký của run v2 có test đối chiếu cố định.
- Có review độc lập được ghi lại. Từ P0 trở đi, cổng sẽ chặn nếu ô đó trống.

## F. Lệnh thi hành

Điều kiện trước khi gõ: PR chứa file này đã merge, và không có PR nào khác đang mở.

`/thi-hanh pe2`: đọc bảng B, bỏ mã đã `xong`, tiếp từ hạng mục dở theo thứ tự ở mục D.
`/thi-hanh pe2 --dung-sau-ke-hoach`: chỉ in trạng thái, không thi hành.
