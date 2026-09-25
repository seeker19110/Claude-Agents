# ADR-0022: mở lại task sink đã `SUCCEEDED` khi candidate đổi

Ngày: 2026-09-25. Trạng thái: Accepted. Đây là mã N5 của `docs/thi-hanh/pe2.md`, thực hiện quyết định 5 trong ADR-0021.
Nó sửa máy trạng thái của ADR-0017 §4.

## Bối cảnh

**1. Máy trạng thái hiện có** (`platform/xagents-core/src/xagents_core/execution.py`, `main@1261080`). Core có 6
loại event. `task.succeeded` là trạng thái cuối của task, và chỉ `FAILED` mới được `task.retried` về `READY`.
Khi mọi task đã `SUCCEEDED` thì run cũng thành `SUCCEEDED`, và `run.cancelled` từ chối run này vì coi nó đã
terminal.

**2. Hệ quả ở company** (`companies/software-company/src/company/orch/quality_flow.py`, `_step_quality`). Nếu
`quality:accept` đã `SUCCEEDED` ở candidate `REL-a@X` mà sau đó RC mới staged `REL-b@Y`, bộ đối chiếu không mở được
attempt mới. Sàn R6 (`quality_floor.py`) thấy sha lệch và chặn tự duyệt, nên an toàn (hỏng thì đóng), nhưng việc
lại rơi cho người: người phải ký profile mới với `run_id` mới, tức mỗi lần sửa sau nghiệm thu lại có một run rác.
ADR-0021 ghi đây là trần (1) và giao cho N5.

**3. Cùng họ lỗi: định danh attempt trùng.** Attempt `quality:accept` có dạng `<rid>@<sha>` và các `event_id`
`start`/`result`/`retry` được suy ra từ nó. Khi RC mới bị huỷ (`void_releases`), candidate quay về một RC cũ đã
chấm rồi. Lúc đó `start:<rid>@<sha>` đã có trong journal nên `emit` bỏ qua, task nằm yên ở `READY` mãi. Lỗi này có
sẵn ở đường `FAILED → RETRIED` và sẽ lặp lại ở đường mở lại. Đo trên `main@1261080`: chuỗi hỏng A → hỏng B → huỷ
B (quay về A) để `quality:accept` kẹt `READY`, không có attempt nào đang chạy.

## Quyết định

### a. Core: event thứ bảy `task.reopened`

`ExecutionEventKind.TASK_REOPENED = "task.reopened"`. Hợp lệ khi đủ cả bốn điều kiện:

- Task đang `SUCCEEDED`.
- **Task là sink**: không task nào trong RunSpec phụ thuộc nó. Như vậy không có task hạ nguồn nào đã chạy trên kết
  quả cũ mà giờ thành vô căn cứ.
- Run đang `RUNNING` hoặc `SUCCEEDED`. Run `CANCELLED` là terminal thật. Run `BLOCKED` phải được xử lý (retry)
  trước.
- `payload.reason` không rỗng. Lịch sử phải nói vì sao kết quả đã chấp nhận bị mở lại.

Hiệu lực: task về `READY`, run `SUCCEEDED` về `RUNNING`, `attempts` giữ nguyên. Attempt kế tiếp vẫn là
`task.started` bình thường, tăng bộ đếm, và event cũ không bị sửa hay xoá.

Hệ quả cho ADR-0017: `SUCCEEDED` của run không còn là terminal tuyệt đối. Nó là terminal **cho tới khi** có một
`task.reopened` hợp lệ. `run.cancelled` vẫn từ chối run đang `SUCCEEDED`; run đã mở lại (tức `RUNNING`) thì cancel
được như mọi run đang chạy.

### b. Company: mở lại khi candidate đổi, attempt luôn có định danh mới

Trong `_step_quality`:

- Nếu `quality:accept` đang `SUCCEEDED` và candidate hiện tại khác candidate của attempt cuối, thì emit
  `task.reopened` (`<run>:quality:reopen:<attempt cũ>`, reason ghi candidate cũ → mới), rồi `task.started` cho
  attempt mới kèm bindings mới. Cùng candidate thì không làm gì, không bao giờ tự chấm lại thứ đã đạt.
- Định danh attempt: lần đầu một candidate xuất hiện thì là `<rid>@<sha>`, giữ nguyên dạng của N1 để journal cũ
  replay y hệt. Nếu định danh đó đã từng được `task.started` thì thêm `~<n>`, với `n` là số lần `quality:accept`
  đã start. So sánh "cùng candidate" dùng phần gốc (bỏ `~<n>`), nên RAM cache `_quality_done` và nhánh "đã chấm hỏng
  đúng candidate này" vẫn đúng.

**Một snapshot cho R6.** Mở lại làm `SUCCEEDED` không còn là trạng thái cuối, nên người đọc journal phải lấy trạng
thái và candidate từ **cùng một lần đọc** event. Hai lần đọc riêng có thể bị `task.reopened` + `task.started` chen
vào giữa. Khi đó `succeeded` của sha cũ bị ghép với sha mới, và R6 cho qua một sha chưa ai chấm (`sc-security` phát
hiện, có test tái hiện). `orch/quality_release.py` đọc mỗi run đúng một lần. Cache RAM `_quality_done` bị xoá khi một
attempt khác đang mở.

**Kết quả muộn của attempt cũ bị từ chối.** Driver và CLI `commit` đọc bindings của attempt mới nhất. Nếu kết quả
mang `attempt_id` cũ, `commit_quality_result` ném lỗi và không ghi gì. Trước đây kết quả đó bị chấm thành finding
`wrong_task_or_attempt` và đánh FAILED attempt đang chạy, rồi bộ đối chiếu chờ sha mới mãi. Kết quả sai `task_id` cho
đúng attempt hiện tại vẫn được chấm FAILED như trước.

R6 không đổi. Nó vẫn đòi `quality:accept` `succeeded` **ở đúng sha đã staged**. Giữa lúc mở lại và lúc có kết quả
mới, trạng thái là `running`, nên R6 vẫn chặn.

### Phương án đã loại

- **Cho `task.retried` nhận cả `SUCCEEDED`.** Ít code hơn, nhưng xoá ranh giới "sửa lỗi" với "mở lại thứ đã đạt".
  Người đọc journal không phân biệt được, và máy trạng thái của task không phải sink cũng bị nới theo.
- **Mở lại task bất kỳ, kéo theo huỷ task hạ nguồn.** Tổng quát hơn nhưng phải định nghĩa lại dependency đã mở
  khoá. Hiện chưa caller nào cần. Chỉ sink là đủ cho `quality:accept`, vì `compile_execution` đặt nó phụ thuộc mọi
  task công việc.
- **Ký profile/run mới mỗi lần sha đổi.** Đã loại ở ADR-0021 quyết định 5.

## Bất biến

- Journal cũ (không có `task.reopened`) replay ra đúng state cũ. Định danh attempt lần đầu giữ dạng `<rid>@<sha>`.
- Sàn ADR-0043 và R6 không nới. `SUCCEEDED` vẫn không phải quyền merge/deploy.
- Không sửa `agents/`, `skills/`, `topics/`, golden hay eval.

## Hệ quả

- Sửa sau nghiệm thu, rồi staged sha mới, sẽ tự được chấm lại trong cùng run khi có driver. Không có driver thì
  attempt mới đứng `RUNNING` chờ CLI `quality_execution commit`, như N1.
- Console (`platform/console/src/console/quality.py`) replay qua core nên hiểu event mới mà không cần sửa. Trong lúc
  mở lại, console hiện `running` và coi mọi check là chưa xác nhận.
- Test: core có ca thuận, bốn ca từ chối và ca cancel sau khi mở lại. Company có ca sha đổi sau `SUCCEEDED` thì
  chấm lại được, cùng sha thì không mở lại, và ca candidate quay về RC cũ vẫn mở được attempt mới (cả hai đường
  `SUCCEEDED` và `FAILED`).

## Liên quan

ADR gốc 0017 (kernel, §4 máy trạng thái), 0019 (commit nguyên tử), 0021 (nối orchestrator, quyết định 5);
`companies/software-company/docs/adr/0043-tu-duyet-theo-san-chat-luong.md`; `docs/thi-hanh/pe2.md` mã N5.
