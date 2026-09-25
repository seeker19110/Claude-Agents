# ADR-0021: nối nghiệm thu quality contract vào orchestrator của software-company

Ngày: 2026-09-25. Trạng thái: **Proposed** — người phải duyệt (mục "Câu hỏi cho người") trước khi viết code N1.
Mở rộng ADR-0018 và ADR-0019; dùng chữ ký receipt của ADR-0020 (pe2-ky, `docs/adr/0020-chu-ky-bat-doi-xung-receipt.md`
trên nhánh `wt/pe2-ky`, chưa merge). Gói N1 của `docs/thi-hanh/pe2.md`. Chạm hai package (`company` gọi
`xagents_core.execution`) nên nằm ở dãy ADR gốc. Không có code trong ADR này.

## Bối cảnh

Đo trên `wt/pe2-noi@22bf757`. Số dòng sẽ lệch khi pe2-cung/pe2-ky merge — gói code phải đọc lại hàm, không tin số dòng.

**1. Orchestrator đọc gì ở từng pha** (đường đi của một dự án):

| Pha | Chỗ | Đọc/ghi |
|---|---|---|
| intake → research → spec (draft) → câu hỏi → PRD | `src/company/orch/routes.py:160–168` (7 `Route`) | chỉ bus; không có khái niệm profile |
| mở gate spec | `orch/ticket_fsm.py:75` (trong `_plan`, topic `approved-specs`) | `request_gate(kind="spec", SPEC-<pid>)` |
| người ký spec | `src/company/gate_cli.py:150–170` | `--quality-bar` → audit `quality.bar_set` (actor người, bus chặn agent ở `bus.py:51`) |
| kế hoạch → ticket | `orch/ticket_fsm.py:143–151` (`plans_ok.add` dòng 149, `_dispatch_plan` dòng 151) → `_dispatch_plan` 255–269 → `DeliveryLead.dispatch` (`delivery.py:125`) | ticket = `Task` (`events.py:85`), không trường nào mang profile |
| replay kế hoạch sau restart | `orch/rehydrate.py:65–73` (`plan.proposed` → `_dispatch_plan(replaying=True)`) | |
| trạng thái ticket | `delivery.py:92–96` (`_set`, điểm đổi state duy nhất), bảng `events.py:236–242`, `DONE_STATES` `delivery.py:15` | nguồn sự thật = `lead.state` (ADR-0034 §3) |
| tạo RC | `delivery.py:288–294` | `release-candidates` |
| sha đã staged | `orch/release_fsm.py:67–70` → `o.release_sha[rid]` + audit `release.staged`; replay `rehydrate.py:78` | |
| mở gate release | `delivery.py:349–360` → `_quality_evidence` 340–347 → `collect_evidence` | |

Kết luận: **0** chỗ trong `orchestrator.py` (520 dòng) và `orch/` (15 module) đọc `ProjectProfile`. Dự án không có
nơi nào lưu profile ngoài file JSON người tự đưa vào CLI.

**2. Ai gọi journal/adapter.** `grep -rn "ExecutionJournal\|commit_quality_result\|ProjectProfile" src/` (trừ
`product_quality.py`): **chỉ** `src/company/quality_execution.py` (dòng 25, 142, 237, 247). CLI của nó có
`plan`/`register`/`status` (dòng 222–257), **chưa có `commit`**. Orchestrator chưa từng mở journal.

**3. Bảng chuyển (ADR-0034).** `TICKET_TRANSITIONS` `orch/ticket_fsm.py:298–305` — 4 hàng (`superseded`,
`learn_repo`, `plan`, `clarification_fallback`). `RELEASE_TRANSITIONS` `orch/release_fsm.py:307–315` — 5 hàng
(`integrate_rc`, `integrate_approved`, `production_deploy_or_rollback`, `release_pending_human`,
`acceptance_close`). Dispatcher `orchestrator.py:278–283`. `scheduler._mark` (`orch/scheduler.py:256–261`) là hàm
duy nhất đánh dấu một event đã xử lý xong, có 12 chỗ gọi.

**4. Sàn ADR-0043 lấy bằng chứng ở đâu.** `quality_floor.collect_evidence` (`quality_floor.py:168–219`) đọc
`audit-log` (`release.staged`, `regression.run`, chỉ actor `orchestrator`), `pull-requests` mới nhất của từng
ticket, `release-events`, `review-results` (lọc theo `causation_id`), `release-candidates`, và `gate.history`.
**0** lần đọc journal. `_release_gaps` 86–105 có R1–R5.

**5. Dữ liệu nằm đâu.** Bus: `--db company.sqlite` (`orch/cli.py:64`), bảng `events`
(`xagents_core/sqlite_bus.py:45`). Artifact: `<db>.artifacts/` (`runner.py:107–109`). Worktree ticket:
`<repo khách>/.worktrees/<ticket>` (`workspace.py:101`), tích hợp `.worktrees/_integration` (299), bản staged
`.worktrees/_releases/<sha>` (404). Journal dùng bảng `execution_runs`/`execution_events`
(`xagents_core/execution.py:410–414`) — không trùng tên bảng bus. `.gitignore` đã chặn `*.sqlite` (dòng 33) và
`company.artifacts/` (dòng 19).

**6. Ràng buộc có sẵn quyết định thay ta.** `compile_contract` băm cả `profile.model_dump()` (gồm `run_id`) vào
`contract_hash` (`product_quality.py:257–269`); `compile_execution` đòi `work.run_id == profile.run_id`
(`quality_execution.py:48`); `ExecutionJournal.register` chỉ idempotent với spec **giống hệt**
(`execution.py:439`). Tức là: **một profile ⇔ một run ⇔ một DAG cố định lúc đăng ký**. Core có 6 loại event
(`execution.py:65–71`); task `SUCCEEDED` là trạng thái cuối, chỉ `FAILED` mới `RETRIED` được (ADR-0017 §4).

## Quyết định

### a. Profile được ghim lúc người ký spec, đọc lúc kế hoạch được nhận

- Người ký: `gate_cli approve SPEC-<pid> --by human:<x> --quality-profile <file>` (cùng khuôn `--quality-bar`,
  kiểm hợp lệ TRƯỚC khi ký). CLI validate `ProjectProfile`, đòi `profile.project_id == <pid>`, chép file vào
  `<db>.artifacts/quality/<pid>/<sha256>.json` (định danh theo nội dung), rồi ghi audit
  `quality.profile_set {project_id, run_id, profile_sha256, contract_hash, by}`. Bus từ chối action này nếu actor
  không phải `human:*` (như `BAR_ACTION`, `bus.py:51`); `_rehydrate` chỉ tin nó với actor người.
- Đọc: ngay khi `_check_plan` nhận kế hoạch đầu tiên của dự án từ `approved-specs` (`ticket_fsm.py:149`). Đọc lại
  file, băm lại, lệch `profile_sha256` ⇒ không đăng ký, audit `quality.profile_invalid` (N2 biến nó thành gap).
- Loại **ghim lúc intake**: profile khi đó chưa ai ký, và spec còn đổi qua câu hỏi làm rõ. Ghim thứ chưa chốt
  là ghim sai hash.
- Loại **để `product` pha plan sinh profile**: profile thành lời khai của model, mà contract là thứ dùng để
  chấm chính công việc model làm. Trái `AGENTS.md` luật cấm 8.
- Loại **lưu profile trên blackboard hoặc trong worktree**: cả hai là chỗ agent ghi được, nên worker sửa được
  hợp đồng nghiệm thu của chính mình.

**Hạt run: một run cho mỗi profile, DAG = ticket của kế hoạch đầu tiên dự án nhận sau khi profile được ghim.**
TaskSpec `task_id = ticket_id`, `dependencies` = `depends_on` trong cùng kế hoạch (dependency sang kế hoạch cũ bị
bỏ vì nó đã xong ở run khác), `acceptance = Task.acceptance`, `complexity = C2`. `quality:accept` do
`compile_execution` thêm. Kế hoạch sinh từ `change-requests`/`incidents` (`PLAN_INPUTS`, `routes.py:235–239`)
**không** vào run cũ. Muốn nghiệm thu chúng thì người ký một profile mới với `run_id` mới.
- Loại **một run mỗi ticket** (đúng chữ ký gói việc `register_quality_run(o, ticket_id, …)`): muốn vậy phải đổi
  `run_id` của profile cho từng ticket, tức đổi `contract_hash` mà người đã ký. Hash người ký không còn phủ thứ
  được chấm.
- Loại **một run nối dài cho cả dự án**: RunSpec không đổi được sau `register`. Mỗi CR phải huỷ run rồi đăng ký
  lại, và mất lịch sử nghiệm thu.

### b. Module `companies/software-company/src/company/orch/quality_flow.py`

```python
class TrustedDriver(Protocol):
    def run(self, run_id: str, checks: tuple[str, ...]) -> tuple[TaskResult, list[Receipt]]: ...

def register_quality_run(o: Orchestrator, plan_id: str, profile: ProjectProfile) -> None: ...
def sync_quality(o: Orchestrator) -> None: ...
def submit_quality(o: Orchestrator, run_id: str, result: TaskResult, receipts: list[Receipt]) -> RunState: ...
```

- `register_quality_run` nhận **`plan_id`**, không nhận `ticket_id` (lý do ở mục a). Dựng RunSpec từ
  `o.plans[plan_id]["tickets"]`, gọi `compile_execution`, `journal.register`. Lặp lại thì idempotent.
- `sync_quality` là **bộ đối chiếu**, không phải hook theo sự kiện. Nó chiếu `lead.state` sang journal bằng
  `journal.transition` với `event_id` tất định:

  | `lead.state` / điều kiện | Event journal | `event_id` |
  |---|---|---|
  | ticket `dispatched` lần thứ n (`Task.retry`) | `TASK_STARTED` attempt `<tid>#<n>` | `<run>:<tid>:start:<n>` |
  | ticket `changes_requested` khi task đang `RUNNING` | `TASK_FAILED` rồi `TASK_RETRIED` | `<run>:<tid>:fail:<n>` / `:retry:<n>` |
  | ticket trong `DONE_STATES` **và** đã vào nhánh tích hợp (`lead.integrated`) | `TASK_SUCCEEDED` | `<run>:<tid>:ok` |
  | mọi task công việc `SUCCEEDED` **và** có RC chứa các ticket đó với `o.release_sha[rid]` | `TASK_STARTED` cho `quality:accept`, attempt `<rid>@<sha>`, payload mang `QualityBindings` | `<run>:quality:start:<rid>@<sha>` |

  Bindings do coordinator điền, ghi vào payload của `TASK_STARTED`: `candidate_sha = release_sha[rid]` (đúng thứ
  N2 so), `base_sha` = gốc nhánh tích hợp, `diff_hash` = sha256 của `git diff base..candidate`, `context_hash` =
  sha256 chuẩn hoá của `(contract_hash, plan_id, rid, tickets)`, `author_principals` = `env.actor` (bus đã kiểm)
  của mọi `pull-requests`/`test-suites` thuộc ticket của run. Không lấy trường nào từ kết quả của worker.
- Phép chiếu cố ý chỉ đi một chiều: ticket từng `SUCCEEDED` rồi bị rollback (`delivery.py:322–324`) thì không mở
  lại task công việc, vì core không cho. Candidate thật được khoá ở `quality:accept`: sha mới ⇒ attempt mới
  (`FAILED` → `RETRIED`). Trần đã biết: nếu `quality:accept` đã `SUCCEEDED` ở sha X mà sau đó staged sha Y, run
  này không kiểm lại được Y. N2 thấy lệch sha thì báo R6, và việc chuyển cho người.
- `submit_quality` đọc bindings từ `TASK_STARTED` đang chạy trong journal, rồi gọi `commit_quality_result` với
  `event_id = <run>:quality:result:<attempt>`, registry của ADR-0020 và `ApprovalLookup` do coordinator cấp.
  Nộp lại cùng kết quả thì ACK (ADR-0019).
- Driver: `Orchestrator(..., quality_driver: TrustedDriver | None = None)`. Khi có driver, `sync_quality` vừa mở
  attempt xong thì gọi `driver.run(run_id, checks)` rồi `submit_quality`. Mặc định `None`: `quality:accept` đứng
  `RUNNING` cho tới khi coordinator chạy CLI mới `python -m company.quality_execution commit <run_id> --journal …
  --result … --receipts … --trust …`. CLI đọc bindings từ journal, không nhận bindings qua đối số. N1 chỉ nối
  **giao diện** kèm driver fake cho test. Driver browser/restore thật (H3–H7) nằm ngoài N1.
- Loại **hook vào `DeliveryLead._set`**: `_set` cũng chạy lúc replay, và nó nằm ở lớp nghiệp vụ không biết
  journal. Như vậy là cài I/O SQLite vào giữa một phép chuyển trạng thái thuần.
- Loại **thêm hàng `Transition` "quality"**: bảng tra theo topic bus, còn quality không có topic nào. Thêm topic
  mới lại đòi đổi `topics/` và ACL agent, tức chạm hợp đồng agent (phải qua 7 bước `CONTRIBUTING.md` §3), vượt
  phạm vi gói.

### c. Một điểm gọi, không đụng bảng chuyển nào

Điểm gọi duy nhất: cuối `scheduler._mark` (`orch/scheduler.py:256`), sau audit `orchestrated`, gọi
`quality_flow.sync_quality(o)`. Mọi event xử lý xong đều đi qua đây, kể cả `_plan` (`ticket_fsm.py:153`). Khi dự án
chưa có `quality.profile_set` nào, `sync_quality` trả về ngay: không mở file journal, không ghi audit.
Lỗi `ExecutionJournalError`/`sqlite3.Error` trong sync ⇒ audit `quality.sync_error` + `supervisor.escalate_gate`
một lần. Vòng xử lý ticket không bị chặn; release bị chặn ở N2.

Theo ADR-0034 (luật K8.3): **không** thêm, bớt hay đổi thứ tự hàng nào trong `TICKET_TRANSITIONS`,
`RELEASE_TRANSITIONS`, hoặc bảng trạng thái ticket `events.py:236`. `lead.state` vẫn là nguồn sự thật của ticket.
Journal chỉ là phép chiếu, cộng thêm chủ sở hữu duy nhất của kết quả `quality:accept`. PR code phải dẫn ADR-0034 và
ghi rõ "không đụng bảng chuyển".

- Loại **gọi ở cuối `process()`**: nhánh `plan` trả về sớm (`orchestrator.py:278`), nên phải thêm điểm gọi thứ
  hai trong `_act_plan`.
- Loại **vòng `tick` của scheduler riêng**: thêm một nhịp chạy nền, gần với daemon mà bất biến cấm bật.

### d. Ranh giới tin cậy

- `quality:accept` không bao giờ là một `Task` trên topic `tasks`. Không `Route` nào dẫn tới nó, nên không agent
  nào nhận được. `_check_plan` (`orch/guards.py:309`) thêm một problem cho `ticket_id` mở đầu bằng `quality:`
  (`compile_execution` đã cấm namespace này, `quality_execution.py:53`), để model không đặt tên ticket trùng.
- Journal, registry khoá công khai, evidence root và `ApprovalLookup` đều do coordinator giữ, nằm ngoài mọi
  worktree:
  - journal: `<db>.quality.sqlite` (cạnh `company.sqlite`, khớp `*.sqlite` trong `.gitignore`)
  - evidence: `<db>.artifacts/quality/<run_id>/`
  - registry: đường dẫn do người trực cấp (`--quality-trust`)

  `register_quality_run` từ chối nếu bất kỳ đường dẫn nào ở trên resolve vào trong `<repo>/.worktrees/`. Registry
  chỉ chứa public key và `key_id`/`not_after` (ADR-0020 (pe2-ky)); private key thuộc driver/reviewer, không
  thuộc orchestrator.
- Không agent nào có tool đọc/ghi các đường dẫn trên. Sandbox builder chỉ thấy worktree của nó (ADR-0010 công ty).

### e. Resume, và dự án không có profile

- Restart: `_rehydrate` dựng lại `lead.state`, `release_sha`, `plans`, và profile đã ghim (từ
  `quality.profile_set` actor người, thêm vào `TRUSTED_WRITERS`, `orch/rehydrate.py:28`). `sync_quality` ở `_mark`
  đầu tiên đối chiếu lại. Mọi `event_id` đều tất định, nên event đã có thì ACK và event thiếu thì ghi thêm.
  Attempt `quality:accept` đang `RUNNING` được driver chạy lại với **cùng** attempt/bindings.
- Không profile ⇒ không `register`, không file journal, không audit mới. Log `orchestrated` giống từng byte, test
  orchestrator cũ giữ nguyên assertion. `tests/golden/` (prompt agent) không liên quan và không đổi.

### f. Ranh giới với N2 và N3

- N2 (`quality_floor`, gap R6): N1 cung cấp `quality_flow.runs_for_release(o, rid) ->
  tuple[tuple[str, str | None, str | None], ...]` (`run_id`, trạng thái `quality:accept`, `candidate_sha`), chỉ đọc
  journal. `DeliveryLead._quality_evidence` truyền nó vào `collect_evidence`. N1 không đổi `floor_gaps`.
- N3 (console): đọc `<db>.quality.sqlite` ở chế độ chỉ đọc, như cách đọc bus. N1 chỉ bảo đảm đường dẫn suy ra
  được từ `--db`.

## Bất biến

- Không bật daemon, `COMPANY_GATE_AUTOAPPROVE`, hay quyền production. Mặc định `quality_driver=None`.
- Sàn ADR-0043 chỉ được **thêm** gap (R6 ở N2). Không gỡ hay nới gap nào. `quality:accept` `SUCCEEDED` không phải
  quyền merge/deploy (ADR-0018 §4).
- Không migrate run v2 đã có. Hash và chữ ký của chúng giữ nguyên byte.
- Không sửa `agents/`, `skills/`, `topics/`, golden hay eval.

## Hệ quả

- Ticket của dự án có profile mới có một nghiệm thu do máy chứng thật, ràng vào đúng sha đã staged.
- Thêm một file SQLite runtime cho mỗi bus (tạo lười). Người trực phải backup cùng `company.sqlite`.
- `sync_quality` quét `lead.state` của run ở mỗi `_mark`. Code phải ghi dòng
  `no-ky-thuat: quét toàn bộ ticket của run mỗi lần _mark, ổn tới ~500 ticket/run, quay lại khi _mark chậm quá 50ms`.
- Có hai trần đã biết. (1) Không kiểm lại được sha mới sau khi đã `SUCCEEDED`. (2) Ticket từ CR/incident nằm
  ngoài run nếu người chưa ký profile mới. Cả hai đều rơi về người, không rơi về "cho qua".
- Test N1: e2e provider `fake` + driver fake, gồm bốn ca: đủ receipt → `succeeded`; thiếu một receipt → `failed`
  kèm `<check>:missing`; restart giữa `TASK_STARTED` và submit → resume đúng; gỡ điểm gọi ở `_mark` → e2e đỏ.

## Câu hỏi cho người

1. **Hạt run và chữ ký.** Đồng ý đổi `register_quality_run(o, ticket_id, …)` của gói việc thành
   `register_quality_run(o, plan_id, …)` (một run cho mỗi profile, ứng với kế hoạch đầu tiên sau khi ký)?
2. **Chỗ ký profile.** Dùng `--quality-profile` đi kèm `approve SPEC-<pid>`, hay tách thành lệnh riêng sau khi
   ký spec? Lệnh riêng thì linh hoạt hơn, nhưng sẽ có khoảng hở: ticket được dispatch trước khi có profile.
3. **Ticket ngoài run.** Dự án có profile nhưng RC chứa ticket từ CR/incident mà chưa có profile mới: N2 báo R6
   (đề xuất, hỏng thì đóng), hay bỏ qua ticket đó?
4. **Candidate.** Ràng `quality:accept` vào sha đã staged của RC (đề xuất, khớp R6), hay vào đầu nhánh tích hợp
   lúc ticket cuối được integrate?
5. **Sha đổi sau `SUCCEEDED`.** Chấp nhận trần (1) ở mục Hệ quả, tức phải ký profile/run mới, hay mở ADR core
   riêng cho phép `quality:accept` chạy lại (đổi state machine ADR-0017)?

## Liên quan

ADR gốc 0017 (kernel), 0018 (adapter), 0019 (commit nguyên tử), 0020 (pe2-ky, chữ ký Ed25519);
`companies/software-company/docs/adr/0034-tach-may-trang-thai.md` (bảng chuyển, luật dẫn ADR),
`companies/software-company/docs/adr/0043-tu-duyet-theo-san-chat-luong.md` (sàn chỉ thêm gap);
`docs/thi-hanh/pe2.md` §C N1–N3.
