# ADR-0022: nghiệm thu lại `quality:accept` khi candidate sha đổi sau `SUCCEEDED`

Ngày: 2026-09-25. Trạng thái: **Accepted** 2026-09-25, code trong PR #342. Xem mục "Quyết định của người" và "Điểm lệch khi thi hành".

Đây là gói N5 của `docs/thi-hanh/pe2.md` (hạng mục pe2-noi2). Nó thực hiện quyết định 5 của người trong ADR-0021
("sha đổi sau `SUCCEEDED`: nghiệm thu lại được, nhưng không nhét vào N1") và gỡ trần (1) ở mục Hệ quả của ADR đó.
ADR này đổi máy trạng thái của ADR-0017 §4, và chạm hai package (`xagents_core` cùng `company`), nên nằm ở dãy ADR
gốc.

## Bối cảnh

Số liệu đo trên `main@1261080` (#340). Số dòng sẽ lệch khi có PR khác merge, nên gói code phải đọc lại hàm, không
tin số dòng.

**1. Máy trạng thái core** (`platform/xagents-core/src/xagents_core/execution.py`)

| Handler | Dòng | Điều kiện nhận | Kết quả |
|---|---|---|---|
| `_task_started` | 325–335 | run `RUNNING` **và** task `READY` | task `RUNNING`, `attempts += 1` |
| `_task_succeeded` | 348–357 | task `RUNNING` | task `SUCCEEDED`, mở khoá dependent; mọi task `SUCCEEDED` ⇒ run `SUCCEEDED` |
| `_task_failed` | 360–369 | task `RUNNING` | task `FAILED`, run `BLOCKED`, ghi `failures[task]` |
| `_task_retried` | 372–383 | run `BLOCKED` **và** task `FAILED` | task `READY`; `failures.pop(task_id)` **không có mặc định** (381) |
| `_run_cancelled` | 315–322 | run khác `SUCCEEDED`/`CANCELLED` | giữ task `SUCCEEDED`, còn lại `CANCELLED` |

Có 6 loại event (`ExecutionEventKind`, 65–71) và `_HANDLER` (386–393) ánh xạ đủ 6. `apply_event` (396–402) là hàm
thuần. `RunState.replay` (294–298) dựng state chỉ từ `RunSpec` và event.

Task `SUCCEEDED` không nhận `TASK_STARTED` vì hai chốt chặn cùng lúc. Task phải `READY` (dòng 329). Với run
`quality:*`, `quality:accept` là task cuối, phụ thuộc mọi task còn lại (`quality_execution.py:71–82`), nên khi nó
`SUCCEEDED` thì run cũng thành `SUCCEEDED`, và `_task_started` còn bị chặn thêm ở điều kiện run `RUNNING` (dòng 327).
Đo bằng `apply_event` trên một run đã `SUCCEEDED`:

```
task.started  -> task_started: run phải RUNNING, hiện là succeeded
task.retried  -> task_retried: run phải BLOCKED, hiện là succeeded
task.failed   -> task_failed: task phải RUNNING, hiện là succeeded
RUN_CANCELLED -> không cancel run terminal: succeeded
```

Vậy là **0/4** event hiện có đưa được `quality:accept` ra khỏi `SUCCEEDED`. Đây là thiết kế cố ý của ADR-0017 §4,
không phải lỗi.

**2. Phía company** (`companies/software-company/src/company/orch/quality_flow.py`, 399 dòng)

- `_step_quality` (364–379) chỉ làm việc khi `quality:accept` đang `READY` hoặc `FAILED` (dòng 368). Nếu task
  `FAILED` và candidate mới khác attempt cũ, nó ghi `TASK_RETRIED` với id `<run>:quality:retry:<prev>` rồi ghi
  `TASK_STARTED` với id `<run>:quality:start:<rid>@<sha>` (376–379). Test
  `test_quality_hong_roi_sha_moi_duoc_staged_thi_attempt_moi` (`tests/test_quality_flow.py:399`) phủ đường này.
- `_candidate` (353–361) chọn RC đã staged mới nhất, không bị huỷ, mà cùng các RC trước nó phủ đủ ticket của run.
- `_sync_project` (261–297) thoát sớm khi `_quality_done[run]` trùng attempt của candidate hiện tại (dòng 268).
  Khi có candidate mới thì nó chạy tiếp tới `_step_quality`.
- **Hiện nay, khi `quality:accept` đã `SUCCEEDED` ở `REL-a@X` và RC mới staged `REL-b@Y`:** `_candidate` trả
  `(REL-b, Y)`. `_sync_project` không thoát sớm, nhưng `_step_quality` return ở dòng 368 vì `q` là `SUCCEEDED`.
  Journal không được ghi thêm event nào, driver không được gọi, và cũng không có audit hay escalation nào. Run nằm
  im ở `SUCCEEDED@X` mãi mãi.

**3. R6** (`companies/software-company/src/company/quality_floor.py:124–133`, nguồn ở `orch/quality_release.py:19–39`
và `quality_flow.runs_for_release` 219–234)

- `runs_for_release` lấy `candidate_sha` từ bindings của `TASK_STARTED` **mới nhất** (`bindings_from_journal`,
  `quality_execution.py:257–274`).
- `_quality_gaps` chỉ bỏ qua một run khi `status == "succeeded"` **và** `sha == staged_sha` (128–131).
- Với tình huống ở mục 2, RC `REL-b` có gap `R6 (<run>: đạt ở 'X', sha đã staged là 'Y')`. Ca này có test
  `test_r6_succeeded_nhung_khac_sha_staged_thi_co_khoang_trong` (`tests/test_quality_floor_r6.py:42`). Tức là hiện
  trạng **đóng đúng** (hỏng thì đóng), nhưng không có đường nào để đi tiếp.

**4. Chi phí của lối thoát duy nhất hiện có** (ký profile mới)

- `note_profile` (`quality_flow.py:109–116`) ghi đè `o.quality_profiles[pid]`, khoá theo dự án, và đặt
  `plans_before` bằng số kế hoạch hiện có.
- `_plan_for` (145–152) chỉ ghép run với kế hoạch `approved-specs` **đến sau** mốc đó.
- Hệ quả:
  - Ký profile mới làm run cũ biến khỏi `runs_for_release`, vì hàm này lặp theo `quality_profiles` (dòng 225).
  - Ticket của RC trở thành `quality_unrun`, và R6 vẫn đóng cho tới khi dự án đi lại cả vòng spec → kế hoạch mới.
  - Ticket cũ nằm ở kế hoạch cũ, không bao giờ vào run mới.
- Như vậy "ký profile mới" thực chất là "làm lại cả dự án" hoặc "người tự duyệt gate". Nó không phải thao tác nhỏ.

**5. Ràng buộc byte**

- `compile_contract` băm `profile.model_dump()`, trong đó có `run_id` (`product_quality.py:280–297`). Đo: đổi
  `run_id` từ `run-example` thành `run-example@abcdef012345` thì `contract_hash` đổi (`True`).
- `assess` đòi `evidence.run_id == profile.run_id` (`product_quality.py:556`). Chữ ký receipt phủ `Evidence`, nên
  phủ luôn cả `run_id`.
- `compile_execution` đòi `work.run_id == profile.run_id` (`quality_execution.py:61`).
- `RunSpec.to_json` (173–194) ghi đúng 8 khoá cho mỗi task (`acceptance, allowed_tools, complexity, context_refs,
  dependencies, objective, task_id, write_scope`). `ExecutionJournal.register` từ chối khi body lệch dù một byte
  (dòng 453–454). Mỗi `_mark` lại gọi lại `register_quality_run` (`quality_flow.py:269`).
- Hệ quả: nếu thêm một khoá luôn có vào `to_json`, **mọi run đã đăng ký** sẽ ném `ExecutionJournalError` ở mỗi
  `_mark`, tức thành `quality.sync_error` kèm escalation.

**6. Trần khác cần biết**

- `quality_flow.py` có 399 dòng. `test_orch_khuon_loi.py:202` giới hạn mỗi module `orch/` ở 400 dòng
  (`MAX_DONG_MODULE_ORCH`), nên code N5 phía company không thể thêm vào module này.
- Console (`platform/console/src/console/quality.py:65`) dựng state bằng `RunState.replay` của core. Nó nhận event
  mới mà không phải sửa code, nhưng một bản core cũ gặp `"task.reopened"` sẽ ném `ValueError` ở
  `ExecutionEventKind(...)` (`execution.py:255`).

## Phương án

### (a) Event mới `TASK_REOPENED`, chỉ cho task `reopenable` trong `RunSpec` (đề xuất)

**Core**

- Thêm `ExecutionEventKind.TASK_REOPENED = "task.reopened"`, là loại thứ 7.
- Thêm `TaskSpec.reopenable: bool = False`.
  - `to_json` **chỉ ghi khoá `reopenable` khi `True`**. Nhờ vậy body của mọi RunSpec hiện có giữ nguyên byte, và
    `register` vẫn idempotent.
  - `from_json` đọc bằng `row.get("reopenable", False)`.
- `RunSpec.__post_init__` từ chối task `reopenable` có task khác phụ thuộc vào nó. Chỉ task lá được mở lại, để
  không có dependent nào đã `SUCCEEDED` dựa trên một kết quả vừa bị mở lại.
- `_task_reopened` nhận event khi đủ bốn điều kiện:
  - task `SUCCEEDED`;
  - `spec` đánh dấu task đó `reopenable`;
  - run đang `RUNNING` hoặc `SUCCEEDED`;
  - `payload["reason"]` là chuỗi khác rỗng.

  Kết quả: task về `READY`, run về `RUNNING`, `attempts` và `failures` giữ nguyên. Attempt kế tiếp tăng số qua
  `TASK_STARTED` như cũ.
- Event cũ không đổi nghĩa. Journal có trước N5 không chứa `task.reopened`, nên replay đi qua đúng 6 handler cũ.

**Company**

- `compile_execution(profile, work, *, reopenable=True)` đánh dấu barrier `quality:accept`.
- `register_quality_run` giữ nguyên spec đã có nếu nó khớp bản compile **legacy** (`reopenable=False`). Như vậy
  không migrate, và run cũ giữ hành vi cũ.
- `commit_quality_result` chấp nhận spec đã đăng ký khi nó khớp một trong hai bản compile.
- Module mới `orch/quality_reopen.py` (vì trần 400 dòng) đảm nhận việc mở lại. Khi `quality:accept` `SUCCEEDED`,
  attempt cuối khác `<rid>@<sha>` của candidate hiện tại, và spec có đánh dấu `reopenable`, module này ghi:
  1. `TASK_REOPENED`, id `<run>:quality:reopen:<prev_attempt>`, payload
     `{reason, from_attempt, from_sha, to_attempt}`;
  2. `TASK_STARTED`, id `<run>:quality:start:<rid>@<sha>`, kèm bindings mới.

  Nếu attempt mới trùng một attempt `quality:accept` đã có trong journal, module ném `ExecutionJournalError`, tức
  thành `sync_error` và không mở lại.

**Đo được**

| | Kết quả |
|---|---|
| Byte của contract/chữ ký v2/v3/v4 | Không đổi: `compile_contract`, `Evidence` và `Receipt` không bị chạm |
| RunSpec đã đăng ký | Không đổi byte |
| Run mới | Thêm đúng một khoá ở một task |
| Phạm vi core | Một handler, một khoá, một kiểm tra DAG |
| Lịch sử | Event `SUCCEEDED@X` cùng payload receipt của nó vẫn nằm trong journal |

**Nhược**

- Đổi máy trạng thái ADR-0017 §4, nên có thêm một mũi tên `SUCCEEDED → READY`.
- Rollback code về trước N5 sau khi đã ghi `task.reopened` sẽ làm replay ném `ValueError`. Lỗi này đóng lại an toàn:
  sync thành `sync_error` vì `ValueError` nằm trong `_SYNC_ERRORS`, và R6 thành `quality_error`. Nhưng người trực
  phải biết: đã chạy N5 thì không hạ code được.
- Run đăng ký trước N5 không được hưởng tính năng này (xem câu hỏi 2).

### (b) Run con dẫn xuất `run_id = <run>@<sha12>` cùng contract

- Khi candidate đổi, đăng ký một RunSpec mới có journal key là `<run>@<sha12>`.
- Muốn giữ `contract_hash`, profile và evidence phải giữ `run_id` gốc, vì đổi `run_id` thì hash đổi (đo ở Bối
  cảnh 5). Khi đó phải tách "khoá journal" khỏi `profile.run_id` ở ít nhất 5 chỗ:
  - `compile_execution:61`;
  - `commit_quality_result`, gồm `load_spec(profile.run_id)` ở 181 và `run_id` của event ở 227;
  - `runs_for_release:225`;
  - `bindings_from_journal`;
  - console, nơi mỗi run con sẽ thành một hàng riêng.
- `compile_execution` đòi work DAG khác rỗng và barrier phụ thuộc mọi ticket (65–72). Run con vì vậy phải ghi lại
  `TASK_STARTED`/`TASK_SUCCEEDED` giả cho toàn bộ ticket. Các event đó không còn là phép chiếu của `lead.state`, và
  cùng một ticket bị đếm là "xong" ở N run.
- Ưu điểm: core không đổi dòng nào, và ADR-0017 giữ nguyên.
- Nhược điểm:
  - Hoặc phá byte `contract_hash`/chữ ký (nếu để `run_id` dẫn xuất đi vào profile), hoặc tạo hai khái niệm
    `run_id` song song trong company.
  - Mỗi lần đổi sha lại sinh một run mới. Đó chính là "run rác" mà quyết định 5 của ADR-0021 đã loại.
- **Loại.**

### (c) Giữ nguyên, bắt người ký profile/run mới (hiện trạng)

- Ưu điểm: 0 dòng code, và đã đóng đúng (R6).
- Chi phí đo ở Bối cảnh 4: không phải một lệnh ký. Ký profile mới làm run cũ rời khỏi R6, ticket thành
  `quality_unrun`, và R6 chỉ mở lại sau một vòng spec → kế hoạch mới. Mỗi hotfix sau khi đã đạt biến thành "làm lại
  kế hoạch", hoặc "người tự duyệt gate như trước ADR-0043". Cách thứ hai bỏ qua nghiệm thu máy, đúng thứ pe2 dựng
  ra để có.
- Quyết định 5 của người đã loại phương án này làm đường chính. Nó vẫn là **đường dự phòng** cho run đăng ký trước
  N5.

### (d) Cho `TASK_RETRIED` áp lên `SUCCEEDED`

- Ưu điểm: không thêm loại event.
- Nhược điểm:
  - Đổi nghĩa một event đang có. `retried` hiện có nghĩa là "sau thất bại": `_step_quality` ghi nó sau `FAILED`, và
    console coi nó là lượt làm lại.
  - `_task_retried` đòi run `BLOCKED` và gọi `failures.pop(task_id)` không mặc định (381). Áp lên `SUCCEEDED` sẽ
    ném `KeyError` nếu không viết lại handler, tức vẫn là viết lại, chỉ khác là dưới tên cũ.
  - Journal cũ không có `retried` trên `SUCCEEDED` (event đó từng bị từ chối), nên replay không vỡ. Nhưng mọi đoạn
    code đọc journal (R6, console, `_findings`) sẽ phải tự phân biệt hai nghĩa của cùng một chuỗi `task.retried`.
- **Loại**, vì bất biến "event cũ không đổi nghĩa" là bất biến về ngữ nghĩa, không chỉ về replay.

### (e) Luật cấu trúc: mọi task lá mở lại được, không cần cờ

- Ưu điểm: run đăng ký trước N5 cũng dùng được ngay, không cần đổi `RunSpec`.
- Nhược điểm: áp cho **mọi** caller của core, kể cả H3–H7/`/thi-hanh` sau này. Tác dụng là mở quyền cho những task
  không ai xin quyền đó. Core là cơ chế (ADR-0001), còn ai được mở lại là chính sách, nên chính sách phải được khai
  báo trong spec.
- **Loại.**

## Quyết định (đề xuất)

Chọn **(a)**. Có hai lý do:

1. Đó là phương án duy nhất giữ được cả bốn bất biến dưới đây mà không cần tới khái niệm `run_id` thứ hai.
2. Việc thường ngày (hotfix sau khi đạt) chạy bằng máy, qua đúng đường nghiệm thu sẵn có: bindings do coordinator
   điền, receipt ký Ed25519, rồi `commit_quality_result`.

### Bất biến bắt buộc (mỗi bất biến có test)

1. **Replay journal cũ cho đúng state như trước.** Journal fixture ghi bằng code `1261080` phải cho ra cùng
   `RunState` (status, tasks, attempts, failures). Không event cũ nào đổi handler hay đổi nghĩa.
2. **`contract_hash` và chữ ký v2/v3/v4 giữ nguyên byte.** N5 không sửa `product_quality.py`. Hash fixture của cả ba
   phiên bản vẫn xanh. `RunSpec.to_json` của spec không `reopenable` giữ nguyên byte.
3. **Không attempt nào "hồi sinh" `SUCCEEDED` cũ cho candidate mới.**
   - Sau `TASK_REOPENED`, task là `READY` và `bindings_from_journal` trả bindings của attempt mới.
   - Nộp lại kết quả của attempt cũ bằng cùng `event_id` chỉ ACK và trả state hiện tại (`RUNNING`), không trả
     `SUCCEEDED`.
   - Nộp kết quả khác cho attempt cũ bị từ chối (`quality_execution.py:210`).
   - Attempt id trùng với attempt đã có thì fail closed.
4. **R6 vẫn đóng khi chưa có attempt đạt ở đúng sha mới.**
   - Trong lúc attempt `@Y` đang `RUNNING` hoặc đã `FAILED`, RC `Y` có R6.
   - RC cũ `X`, sau khi đã mở lại, cũng có R6, vì bindings mới nhất là `Y`.
   - `_quality_gaps` giữ nguyên, không nới điều kiện nào.

Giữ nguyên:

- Không đụng `TICKET_TRANSITIONS`/`RELEASE_TRANSITIONS` hay bảng trạng thái ticket (ADR-0034).
- Không mở lại task công việc: ticket bị rollback vẫn theo mục b của ADR-0021.
- Không bật daemon hay autoapprove. Sàn ADR-0043 chỉ thêm gap.

## Kế hoạch gói

Hạng mục `pe2-noi2`, một nhánh, hai package, làm tuần tự core trước rồi company.

### N5.core — C3 — `platform/xagents-core`

**Scope:** `execution.py`, `tests/test_execution.py`, và fixture journal cũ. Không cần thêm ADR vì chính ADR này
là ADR cho gói.

Ca test bắt buộc, viết đỏ trước theo luật bắt buộc 4:

1. `TASK_REOPENED` trên task `reopenable` đã `SUCCEEDED` (run `SUCCEEDED`) cho task `READY`, run `RUNNING`,
   `attempts` không đổi. `TASK_STARTED` kế tiếp làm `attempts` tăng 1.
2. **Chiều ngược**, mỗi ý là một ca riêng. `TASK_REOPENED` bị `ExecutionTransitionError` khi:
   - task không `reopenable`;
   - task đang `READY`, `RUNNING` hoặc `FAILED`;
   - run `CANCELLED`, `PENDING` hoặc `BLOCKED`;
   - thiếu `reason` hoặc `reason` rỗng;
   - `task_id` không tồn tại.
3. `RunSpec` có task `reopenable` mà có dependent thì `ValueError`.
4. `TASK_RETRIED` trên `SUCCEEDED` **vẫn** bị từ chối, để khoá phương án (d) khỏi lọt vào qua đường vòng.
5. Byte: `to_json` của spec không `reopenable` bằng đúng chuỗi fixture chụp từ `1261080`. Round-trip `from_json`
   của body cũ cho `reopenable=False`. Round-trip body có `reopenable=True` giữ nguyên cờ.
6. Replay journal fixture cũ (SQLite thật) cho `RunState` bằng đúng giá trị đã chụp.
7. `transition` với `TASK_REOPENED` gửi lại cùng `event_id` thì ACK; cùng id nhưng khác payload thì collision.
8. Đo hai chiều: gỡ `TASK_REOPENED` khỏi `_HANDLER` thì ca 1 đỏ, bật lại thì xanh. Ghi kết quả cả hai chiều vào
   commit.

### N5.company — C2 — `companies/software-company`

**Scope:** `quality_execution.py` (`compile_execution`, phép so spec trong `commit_quality_result`), module mới
`orch/quality_reopen.py`, và một điểm gọi trong `_step_quality`. `quality_flow.py` phải giữ ≤ 400 dòng: nếu điểm
gọi làm vượt trần thì chuyển thêm hàm sang module mới, không nới `MAX_DONG_MODULE_ORCH`.

Ca test bắt buộc:

1. **E2E thuận** (provider `fake` + `FakeDriver`):
   - `SUCCEEDED` ở `REL-001@X`, sau đó staged `REL-002@Y`.
   - Journal có `…:quality:reopen:REL-001@X` rồi `…:quality:start:REL-002@Y`, và driver được gọi với `Y`.
   - Event `SUCCEEDED@X` cùng payload receipt của nó vẫn còn trong `j.events(RUN)`.
   - Cuối cùng run `SUCCEEDED` với bindings `Y`.
2. **Chiều ngược của 1:** gỡ điểm gọi reopen thì e2e đỏ, run đứng ở `SUCCEEDED@X` và R6 báo "đạt ở X".
3. **R6:**
   - Attempt `@Y` đang `RUNNING` thì RC `REL-002` có R6.
   - Attempt `@Y` `FAILED` thì RC `REL-002` có R6 kèm blocker.
   - Attempt `@Y` `SUCCEEDED` thì RC `REL-002` không có R6.
   - RC `REL-001` (sha `X`) sau khi mở lại thì có R6.
4. **Không hồi sinh:**
   - Nộp lại kết quả attempt `@X` bằng CLI `commit` hay `submit_quality` chỉ trả state hiện tại, không trả
     `succeeded`.
   - Kết quả khác cho `@X` bị từ chối.
   - Candidate quay về một attempt id đã có thì thành `quality.sync_error` và không ghi event.
5. **Run legacy** (spec đăng ký bằng bản compile trước N5):
   - `register` vẫn idempotent, không có `sync_error`.
   - Sha đổi sau `SUCCEEDED` thì không mở lại, R6 vẫn đóng (hiện trạng).
   - `commit_quality_result` vẫn nhận spec đó.
6. **Restart** giữa `TASK_REOPENED` và `TASK_STARTED`: resume ra đúng một `start:REL-002@Y`, không nhân đôi, và
   `event_id` tất định.
7. **Byte:** test hash contract v2/v3/v4 và chữ ký receipt hiện có vẫn xanh mà không sửa assertion. Thêm một
   assertion rằng `compile_contract(profile)` không đổi qua `compile_execution(..., reopenable=True)`.
8. `candidate is None` (RC mới bị huỷ, hoặc chưa phủ đủ ticket) thì không mở lại, và run giữ `SUCCEEDED@X`.

Cổng: `scripts/dev-task.sh gate core` rồi `scripts/dev-task.sh gate company`, coverage 100%. Console không nằm trong
hạng mục (giới hạn ≤ 2 package). Console đọc qua `RunState.replay` nên tự nhận event mới. Nếu muốn có một test
console cho state `running` sau khi mở lại thì mở hạng mục riêng.

## Hệ quả

- Hotfix sau khi đạt đi lại đúng đường nghiệm thu máy, không cần người ký lại hay lập kế hoạch lại. Người chỉ phải
  vào cuộc khi attempt mới hỏng, và R6 báo lý do.
- Máy trạng thái ADR-0017 §4 có thêm một mũi tên `SUCCEEDED --TASK_REOPENED--> READY`, chỉ cho task lá có khai báo
  `reopenable`. Ghi chú này phải thêm vào ADR-0017 khi ADR-0022 được Accepted.
- Một lần đổi sha thêm 2 event vào journal. Không có trần mới đáng ghi marker, vì journal vốn đã tăng một attempt cho
  mỗi RC.
- Đã ghi `task.reopened` thì không hạ code về trước N5 được. Nếu cố hạ, hệ đóng lại an toàn (R6 `quality_error`)
  chứ không cho qua. Cần ghi điều này vào `TRAPS.md` của core khi merge.
- Trần (1) của ADR-0021 được gỡ cho run đăng ký sau N5. Run đăng ký trước N5 vẫn giữ trần (1), trừ khi người chọn
  khác ở câu hỏi 2.

## Câu hỏi cho người

1. **Chọn phương án (a)**: event mới `TASK_REOPENED`, chỉ cho task lá có cờ `reopenable`, và chấp nhận đổi máy
   trạng thái ADR-0017 §4. Hay chọn phương án khác trong (b)–(e)?
2. **Run đã đăng ký trước N5**: giữ hành vi cũ (không mở lại, R6 đóng, lối thoát là ký profile mới hoặc người duyệt
   gate), như đề xuất để không migrate. Hay cho phép một lệnh `quality_execution upgrade <run>` do người chạy, ghi
   audit, để đăng ký lại spec có `reopenable`? Cách thứ hai đụng bất biến "không migrate run" của `pe2.md`.
3. **Ai kích hoạt mở lại**: tự động khi RC mới staged phủ đủ ticket (đề xuất, giống cách `FAILED → RETRIED` đang
   chạy). Hay chỉ mở lại khi người trực chạy lệnh? Chạy tự động thì không có cửa sổ hở, vì R6 đóng suốt cho tới khi
   có attempt mới đạt. Chạy thủ công thì thêm một bước người, nhưng thấy được từng lần mở lại.
4. **Giới hạn số lần mở lại mỗi run**: không giới hạn (đề xuất: mỗi lần đều phải qua nghiệm thu đủ receipt). Hay đặt
   trần N lần, vượt trần thì escalation?

## Quyết định của người (2026-09-25)

1. **Phương án:** chủ dự án giao phiên chính "cái nào tốt thì chọn". Phiên chính chọn **(a)**, cờ `reopenable` khai
   trong RunSpec. Lý do: đây là phương án duy nhất giữ bốn bất biến ở trên, và cũng là phương án duy nhất khớp câu
   trả lời số 2. Nếu chọn (e), mọi run cũ tự mở lại được, tức là migrate ngầm.
2. **Run đăng ký trước N5: không migrate.** Nhận diện bằng phép so khớp với `compile_execution(..., reopenable=False)`.
   Run đó giữ hành vi cũ: không mở lại, R6 chặn.
3. **Kích hoạt: tự động**, ngay khi RC mới staged phủ đủ ticket.
4. **Không có trần số lần mở lại.** Lần nào cũng phải qua nghiệm thu đủ receipt, và R6 đóng suốt tới khi có kết quả
   đạt ở đúng sha.

## Điểm lệch khi thi hành (PR #342)

- **Attempt id lặp lại có hậu tố `~<n>`, không thành `sync_error`.** Chủ dự án chọn phương án này. Ví dụ: RC mới bị
  huỷ, candidate quay về một RC đã chấm. Attempt lần đầu vẫn giữ dạng `<rid>@<sha>`. Lần lặp lại được id
  `<rid>@<sha>~<số lần start>` và được chấm lại tự động. Đo trên `main@1261080`: đường `FAILED → RETRIED` có sẵn đã kẹt
  `READY` mãi trong đúng ca này (`start:<rid>@<sha>` đã có, `emit` bỏ qua). Hậu tố sửa luôn lỗi đó. Phần gốc (bỏ
  `~<n>`) được dùng để so "cùng candidate".
- **Không tạo `orch/quality_reopen.py`.** `runs_for_release`/`release_quality` chuyển sang `orch/quality_release.py`
  (nguồn R6), nên `quality_flow.py` còn dưới 400 dòng. Điểm mở lại nằm ngay trong `_step_quality`.
- **Ba chỗ gia cố theo review `sc-security`** (mỗi chỗ có test đỏ trước):
  - R6 đọc trạng thái và candidate từ **một** snapshot journal. Hai lần đọc riêng có thể bị mở lại chen giữa, ghép
    `succeeded` cũ với sha mới, và cho qua.
  - Cache RAM `_quality_done` bị xoá khi một attempt khác đang mở.
  - Kết quả mang `attempt_id` cũ (nộp muộn) bị từ chối và không ghi gì. Trước đây nó bị chấm thành
    `wrong_task_or_attempt` và đánh FAILED attempt đang chạy.
- Retry `quality:accept` sau FAILED giờ cũng mang `reason` trong payload.

## Liên quan

- ADR gốc 0017 (máy trạng thái kernel, §4), 0018 (adapter), 0019 (commit nguyên tử, ACK), 0020 (chữ ký Ed25519),
  0021 (quyết định của người 5, trần (1) ở mục Hệ quả).
- `companies/software-company/docs/adr/0034-tach-may-trang-thai.md` (không đụng bảng chuyển).
- `companies/software-company/docs/adr/0043-tu-duyet-theo-san-chat-luong.md` (sàn chỉ thêm gap).
- `docs/thi-hanh/pe2.md` bảng B, dòng N5.
