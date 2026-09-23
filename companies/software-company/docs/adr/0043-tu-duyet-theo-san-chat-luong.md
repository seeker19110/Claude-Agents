# ADR-0043: sau khi người ký spec, công ty tự duyệt release và nghiệm thu khi bằng chứng MÁY đạt sàn chất lượng

Ngày: 2026-09-23 · Trạng thái: được chấp nhận · Nối tiếp: ADR-0011 §4 giai đoạn 3 (`docs/thi-hanh/adr113.md`,
cơ chế actor `"code"` + `RISK_RULES`), ADR-0029 (hồi quy trên staging do orchestrator chạy), ADR-0039/0041
(deploy thật bằng compose/script), ADR-0017 (gate nghiệm thu).

## Bối cảnh

Người dùng chốt (2026-09-23, qua `AskUserQuestion`): *"sau khi người dùng chốt yêu cầu, công ty phần mềm tự hoạt
động, tự duyệt tự động theo chất lượng tốt nhất đã chốt"*, với ba lựa chọn cụ thể:

1. **Gate tự duyệt**: `release`, `acceptance` (UAT), deploy production. **`spec` giữ người ký. `escalation`
   KHÔNG tự duyệt.**
2. **Ngưỡng chất lượng**: *cả hai* — một **sàn cứng trong code** (đổi sàn = PR + `sc-security`), cộng **mức
   nâng theo từng dự án** do người đặt lúc ký spec, không bao giờ hạ dưới sàn. **Thiếu bằng chứng → người
   duyệt.**
3. Thứ tự: ADR này trước, rồi TDD.

Hiện trạng đo trên `main@9f95960`:

| Thứ | Có gì | Ở đâu |
|---|---|---|
| Đường "code tự đóng gate" | có, đã qua `sc-security` 2 lượt (2026-09-10) — actor `"code"`, lý do tiền tố `auto-risk:`, tên hàng phải có thật trong `RISK_RULES`, cờ `COMPANY_GATE_AUTOAPPROVE` đọc lại mỗi lần `apply()` | `src/company/gate_risk.py:98-121`, `src/company/gate_cli.py:34-66` |
| Bảng luật | **rỗng có chủ đích** → không gate nào tự qua | `gate_risk.py:68` |
| Điểm mở gate | 13 lời gọi `request_gate(` (1 spec, 1 release, 1 acceptance, 10 escalation) | `delivery.py:345,360`, `orch/{gates_flow,ticket_fsm,verify,release_fsm}.py` |
| Ngữ cảnh luật nhìn thấy | `GateRiskContext(kind, subject_id, checklist, created_by, seq)` — **không có bằng chứng chất lượng nào** | `gate_risk.py:37-56` |
| Gate deploy production | **không tồn tại riêng**: duyệt gate `release` chính là lệnh deploy production (`_on_gate_decide` → `PROD_ROUTE`) | `orch/gates_flow.py:42-46` |
| Gate nghiệm thu | đóng bằng chữ ký khách trong `acceptance-results` (topic của NGƯỜI, producer `ops`); bản thân `gate.decide` của `UAT-*` **không kích hoạt gì** — đóng ticket là việc của `DeliveryLead._on_acceptance` khi có `acceptance-results` | `orch/gates_flow.py:223-238`, `delivery.py:446-455`, `core.py:55,60` |

Bằng chứng **do máy sinh** (không phải lời khai của model) đã có sẵn lúc gate release/nghiệm thu mở:

| Bằng chứng | Nguồn | `verified_by` |
|---|---|---|
| lint + test của từng PR ticket | `pull-requests.payload.local_checks` (`workspace.py:154`) | `workspace` |
| hồi quy trên sha RC đã staged | audit `regression.run` (actor `orchestrator`, `orch/verify.py:180-212`); bản chép trong `review-results.evidence.run` KHÔNG dùng (xem mục review `sc-security`) | `orchestrator` |
| deploy thật (kèm smoke) staging/production | `release-events.payload.evidence.deploy` (`orch/verify.py:126-177`, `deploy.py`) | `orchestrator` |
| smoke staging (khi không khai `runtime.deploy`) | `release-events{staging}.payload.smoke` (`orch/verify.py`, `smoke.py`) | `orchestrator` |

Và thứ **chỉ là lời khai** của model: `verdict`, `scan_summary`, `test_summary`, `perf`, `a11y`,
`mutation_score`, `sbom_ref` trong `ReviewResult` (`events.py:146`). **Coverage không được sinh ở đâu cả**
(`workspace.py:155` cố ý để trống "chứ không bịa"); SAST/pip-audit không chạy cho dự án khách.

Vì sao không giữ nguyên: bảng rỗng nghĩa là mỗi release đều chờ người ký dù mọi bằng chứng máy đều xanh — đúng
cái người dùng yêu cầu bỏ. Nhưng chỉ nhét một hàng "release → low" vào `RISK_RULES` thì sai theo hai cách: luật
không nhìn thấy bằng chứng nào (ngữ cảnh chỉ có tên và checklist), và nghiệm thu tự duyệt sẽ không đóng được
ticket nào (gate `UAT-*` không kích hoạt gì xuôi dòng).

## Quyết định

### 1. Sàn chất lượng là CODE, là điều kiện CẦN, và chỉ đọc bằng chứng máy

Module mới `company/quality_floor.py`:

- `QualityEvidence` (dataclass đóng băng) — thu từ bus bằng **một** hàm `collect(...)` cho mỗi loại gate, đọc
  đúng các nguồn ở bảng trên. Không đọc lời khai của model để CHỨNG MINH gì cả; verdict của QA/security chỉ được
  dùng theo chiều **chặn** (fail → không tự duyệt), không bao giờ theo chiều **cho qua**.
- `floor_gaps(kind, evidence, bar) -> list[str]` — **hàm thuần**, trả danh sách khoảng trống (mỗi dòng nói thiếu
  gì). Rỗng ⇔ đạt sàn. Không đạt ⇒ gate ở lại chờ người, và danh sách khoảng trống được ghi vào audit
  (`gate.auto_skipped`) để người ký biết vì sao máy không tự ký.

**Sàn release** (= sàn deploy production, vì duyệt release chính là lệnh deploy production) — đủ TẤT CẢ:

| Mã | Điều kiện | Thiếu bằng chứng thì |
|---|---|---|
| R1 | mọi ticket của RC có PR mới nhất với `local_checks.lint is True`, `tests is True`, `verified_by == "workspace"`, không `unverified` | người |
| R2 | sản phẩm **chạy được ở đúng sha đã staged**, do orchestrator chứng: audit `regression.run` (actor `orchestrator`) `ok is True` với `sha ==` sha RC, **hoặc** deploy staging (`release-events.evidence.deploy`, code điền) `ok is True`, không `skipped`, đúng sha | người |
| R3 | review QA trên release `verdict == "pass"`; nếu RC có ticket `risk_tags` (hoặc dự án nâng `security_review`) thì review security cũng `pass`. Chỉ tính review là **phản hồi** (`causation_id`) cho `release-events` (QA) / `release-candidates` (security) của chính release | người |
| R4 | **không có finding nào được miễn** (`release_waived` rỗng) — miễn là một quyết định chấp nhận rủi ro của người, máy không được thừa hưởng nó | người |
| R5 | release này **chưa từng** có gate `escalation` hay quyết định khác `approve` — có sự cố một lần thì các lần sau là việc của người | người |

**Sàn nghiệm thu** (`UAT-<rid>`) — đủ TẤT CẢ: gate `release` của `rid` đã được duyệt; deploy **production** do
orchestrator chứng `ok is True`, không `skipped`, đúng sha RC; và sàn release R1–R5 vẫn đúng khi thu lại lúc
mở gate nghiệm thu. Trần đã biết, ghi thẳng: "sản phẩm chạy và hồi quy xanh" không chứng minh từng tiêu chí nghiệm
thu của khách — nó chứng minh những gì QA đã viết thành test từ spec (pha `author`). Dự án cần khách tự ký thì
nâng `acceptance: human` (mục 2).

Hàng `RISK_RULES` đầu tiên: `release-quality-floor` và `acceptance-quality-floor`, tier `low`, `match` = "đúng
`kind` **và** `floor_gaps(...) == []`". `GateRiskContext` thêm trường `evidence: QualityEvidence | None` (mặc định
`None` ⇒ không luật nào khớp ⇒ người — đúng nghĩa "thiếu bằng chứng → người"). `request_gate(gate, req, *,
evidence=None)` nhận bằng chứng từ nơi gọi; 11 lời gọi còn lại (spec, escalation) **không truyền** nên hành vi
của chúng không đổi một bit nào.

Cờ tổng `COMPANY_GATE_AUTOAPPROVE` **vẫn mặc định tắt** và vẫn là điều kiện đầu tiên. Không bật cờ thì ADR này
không đổi gì ở runtime.

### 2. Mức nâng theo dự án: người đặt lúc ký spec, chỉ SIẾT, không nới

`gate_cli approve SPEC-<pid> --by human:<x> --quality-bar k=v[,k=v]` ghi thêm một bản ghi `audit-log`
`quality.bar_set` (`{project_id, bar, by}`) ngay sau `gate.decide`. Tập khoá **đóng**, mỗi khoá chỉ THÊM điều kiện:

| Khoá | Giá trị | Nghĩa |
|---|---|---|
| `release` | `human` | dự án này không bao giờ tự duyệt release/production |
| `acceptance` | `human` | dự án này nghiệm thu phải do khách ký |
| `security_review` | `required` | đòi review security `pass` cho MỌI RC, kể cả khi không ticket nào có `risk_tags` |

Không có khoá nào nới sàn, nên "không bao giờ hạ dưới sàn" là tính chất của **kiểu dữ liệu**, không phải của một
phép kiểm có thể quên. Khoá lạ → CLI từ chối. Bản ghi `quality.bar_set` chỉ được tin khi `env.actor` là người
(`human:*`) và khớp `by` — cùng luật với `trusted_decision` (ADR-0002) — và bus từ chối ngay lúc publish nếu
actor không phải người. Bản ghi không tin được, hoặc `evidence` không phải JSON (không gắn được vào dự án nào — CLI luôn ghi JSON hợp lệ), bị **bỏ qua** (bỏ qua không nới được gì: không có bản ghi nghĩa là
chỉ có sàn); bản ghi của người mà hỏng (khoá lạ, không phải object) khi replay ⇒ coi như `release: human` +
`acceptance: human` (hỏng thì đóng, không mở). Bản ghi mới nhất đáng tin thắng.

Coverage **không** có khoá, vì không có bằng chứng coverage nào do máy sinh (`workspace.py:155`). Thêm khoá cho
thứ không đo được thì khoá đó chỉ có một nghĩa là "luôn chờ người" — viết thẳng `release: human` thay vì giả vờ
có ngưỡng.

### 3. Nghiệm thu do máy KHÔNG BAO GIỜ trông như chữ ký khách

- Máy **không** publish `acceptance-results` (topic của người, `core.py:60`). Gate `UAT-*` được đóng bằng
  `decide(by="code", actor="code", reason="auto-risk:acceptance-quality-floor")` như mọi gate tự duyệt khác —
  đường `trusted_autoapprove`, **không** đường `orchestrator + UAT-*` của chữ ký khách (`gate_risk.py:114-118`
  đã khoá chuyện này).
- Đóng ticket: `_on_gate_decide` thấy `UAT-<rid>` được `approve` bởi `AUTOAPPROVE_ACTOR` → gọi
  `DeliveryLead.close_accepted(rid)` (tách ra từ nhánh `accepted` của `_on_acceptance`, không nhân bản logic)
  và audit `acceptance.auto`. `metrics` không đếm nó là "khách nghiệm thu".
- Khách vẫn còn nguyên quyền: `acceptance-results` `rejected`/`conditional` tới SAU khi máy đã nghiệm thu thì
  chữ ký khách thắng máy — ticket đã `closed` nên đường `_on_acceptance` cũ không còn gì để đẩy, vì vậy
  orchestrator ghi `acceptance.overridden` và mở gate `escalation` trên release cho NGƯỜI quyết làm lại hay chấp
  nhận (`orch/gates_flow._customer_overrides_auto`). Không im lặng nuốt chữ ký khách.
- Sau restart: `_rehydrate` áp lại `acceptance.auto` (không có `acceptance-results` nào để replay).
- Lỗ phát hiện khi nối: `scheduler._actionable` hỏi `trusted_decision` của core nên quyết định do `"code"` duyệt
  được ghi vào gate nhưng không bao giờ CHẠY (release "đã duyệt" mà không lên production) — nay hỏi
  `gate._trusted` của company, nơi duy nhất biết nhánh `trusted_autoapprove`.

### 4. Cái gì cố ý giữ nguyên

`spec` luôn cần người. `escalation` không bao giờ tự duyệt (không truyền `evidence`). Core
(`xagents_core/gate_cli.py`) không đổi. Four-eyes không đổi (`by="code"` không trùng `created_by` nào). Gate mở
tay qua `gate_cli request` không đi qua `request_gate`.

## Phương án đã loại

**Một hàng `RISK_RULES` "kind == release → low", không có bằng chứng.** Ưu: ba dòng, chạy ngay. Loại: nó tự
duyệt cả release có QA fail đã được ai đó miễn, cả release chưa từng chạy được — chất lượng "tốt nhất đã chốt"
biến thành "mọi thứ". Luật không nhìn thấy bằng chứng thì không phải luật chất lượng.

**Tin verdict của QA/security agent (`verdict == pass`) là đủ.** Ưu: đơn giản, QA đã đọc hết bằng chứng. Loại:
verdict là lời khai của model — `verdict_with_run` tồn tại chính vì QA từng khai `pass` trên sản phẩm không khởi
động được (`orch/verify.py:215-240`). Dùng verdict theo chiều chặn thì an toàn; theo chiều cho qua thì là "tin
lời khai" (`AGENTS.md` luật cấm 8).

**Máy publish `acceptance-results` `accepted` với `signed_by="code"`.** Ưu: không phải sửa `DeliveryLead`, mọi
đường xuôi dòng chạy sẵn. Loại: `acceptance-results` là topic của người; một bản ghi máy ở đó là đúng hình dạng
"code ký thay khách" mà `gate_risk.py:114-118` đã phải vá, và mọi thứ đọc topic đó (metrics, `gate_brief`,
bài học) sẽ đếm nó là chữ ký khách.

**Ngưỡng theo dự án là một con số tự do (vd. `min_score: 0.9`) có thể đặt thấp hơn sàn rồi bị kẹp lại.** Ưu:
linh hoạt. Loại: "kẹp về sàn" là một phép kiểm có thể quên ở một chỗ gọi; tập khoá chỉ-siết làm việc hạ sàn
**không biểu diễn được**.

**Dựng bằng chứng từ `gate_brief.build()`.** Ưu: đã thu rất nhiều thứ. Loại: nó dựng lại cả `Orchestrator` từ
replay, chạy subprocess (git, smoke), và cố ý chỉ trả `ok/gap/unknown` không phán quyết
(`gate_brief.py:600`); gọi nó từ `request_gate` là vòng nhập và chạy lại smoke giữa vòng xử lý event.

## Hệ quả

- **Phải sửa theo**: `gate_risk.py` (trường `evidence`, tham số `evidence=`, hai hàng luật), `quality_floor.py`
  (mới), `delivery.py` (gọi `collect` ở gate release; tách `close_accepted`), `orch/gates_flow.py` (gọi
  `collect` ở gate nghiệm thu; nhánh `UAT-*` do `"code"` duyệt), `gate_cli.py` (`--quality-bar`,
  `quality.bar_set`), `docs/HUONG-DAN-VAN-HANH.md` (bật cờ nghĩa là gì bây giờ), `ARCHITECTURE.md`/`CODEMAP.md`.
  PR đi qua `sc-security` trước khi mở — nó đổi đúng ranh giới tin cậy ADR-0011 §4 đã khoanh.
- **Khó hơn**: thêm một điều kiện vào sàn là PR có test đỏ trước + `sc-security`, không phải sửa cấu hình. Đó là
  chủ ý (người dùng chọn "sàn cứng trong code").
- **Trần đã biết**: `trusted_autoapprove` khi replay chỉ kiểm tên hàng có thật, không thu lại bằng chứng — bằng
  chứng được kiểm một lần, trong tiến trình, lúc `request_gate` chạy. Một actor giả mạo `"code"` trên bus vẫn là
  mô hình đe doạ ADR-0011 đã chấp nhận (bus ACL); khi có người dùng thứ hai ghi được vào `audit-log` thì phải
  thu lại bằng chứng lúc replay.
- **Nhận biết nếu quyết định này sai**: đếm `gate.auto_skipped` theo khoảng trống — một khoảng trống xuất hiện ở
  gần như mọi release (vd. R2 vì không dự án nào khai `runtime`) nghĩa là sàn đang đo thứ không ai sinh ra, và
  "tự duyệt" chỉ tồn tại trên giấy. Ngược lại, một release tự duyệt rồi khách `rejected` là tín hiệu sàn quá
  lỏng: thêm điều kiện vào sàn (PR + test), không nới mức nâng.

## Review `sc-security` (2026-09-23) — đã vá trong cùng PR

Năm khoảng trống, mỗi cái một test đỏ trước (`tests/test_quality_collect.py`, `tests/test_tu_duyet_bao_mat.py`):

1. QA duyệt PR tự khai được `ticket_id=<rid>` + `evidence.run` (route PR không ghi đè identity) → `run` nay chỉ lấy
   từ audit `regression.run` do orchestrator ghi; verdict QA/security chỉ tính khi `causation_id` là sự kiện
   `release-events`/`release-candidates` của chính release.
2. `_rehydrate` tin `acceptance.auto`/`release.staged` theo tên action → nay đòi `env.actor == "orchestrator"`.
3. Người/CLI/console ký `--by code` đi vào nhánh "máy nghiệm thu" → `PersistentGate.decide` từ chối `by="code"`
   khi actor không phải `"code"`; nhánh nghiệm thu trong `_on_gate_decide` đọc `env.actor`, không đọc `by`.
4. Tên hàng đóng được gate khác loại (vd. `spec`) → `RiskRule.kind`; `trusted_autoapprove` đối chiếu loại gate.
5. Bản ghi mức nâng không phải JSON bị bỏ qua (không gắn được dự án) — sửa lời ADR §2 cho khớp.

Ba việc "còn lại, có trước PR này" của bản đầu ADR đã đóng ở PR (#PR) (`tests/test_audit_gia_mao.py`,
`test_identity_tu_route.py`, `test_chu_ky_khach_chi_nguoi.py`):

1. `_rehydrate` tin action theo tên (và `actor` tự khai trong payload) → bảng `TRUSTED_WRITERS`
   (`orch/rehydrate.py`): mỗi action chỉ được áp khi `env.actor` là người ghi thật (orchestrator mặc định;
   `product` cho `plan.proposed`/`plan_rejected`; `delivery-lead` cho `ticket.blocked`/`release.finding_waived`).
   Gốc của lỗ: route `change-requests → product → audit-log` publish payload của model, model tự chọn `action` —
   nay code ép `action="change.impact"` + `actor`=agent (`output.action_overridden`).
2. Route PR không ghi đè `ticket_id` của model → đầu vào thuộc `tasks`/`pull-requests`/`test-suites` thì đầu ra
   mang đúng `ticket_id` đó (`output.subject_overridden`, `TICKET_TOPICS` ở `orch/routes.py`).
3. `ops` là producer của `acceptance-results` — đo: `runner.publish` chỉ phát lên `topic_out` của route và không
   route nào xuất `acceptance-results`; đường thật của khách là `orchestrator publish --actor human:*` (CLI từ chối
   actor không phải người). Agent KHÔNG tự ký được. Quyền `ops` trong ACL chỉ phản chiếu `writes` của
   `agents/operations/ops.md` (+ hai ca eval pha `account`); gỡ nó là đổi hợp đồng agent, cần `make eval-record`
   bằng model thật — để lại, và canh bằng test: thêm route cho agent xuất `acceptance-results` là CI đỏ.
