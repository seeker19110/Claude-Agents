# ADR-0028: Vai viết test độc lập (`test-author`) — test sinh từ đặc tả, không sinh từ diff

Trạng thái: Đề xuất · Ngày: 2026-09-05 · Bổ sung ADR-0010, ADR-0021 · Liên quan ADR-0003, ADR-0016

> Đã đối chiếu với `main` tại `6f72cd4`: ADR-0026 (adapter CLI) và ADR-0027 (giao hàng git sau production)
> không đụng luồng ticket. Bốn dữ kiện ADR này dựa vào vẫn đúng ở đó: route `tasks → $assignee` với `tools="rw"`,
> `BASE_REVIEWS = {reviewer}`, `Toolbox(allow_write: bool)` (chưa phân vùng), `Stack` chưa có khái niệm thư mục test.

## Bối cảnh

Hôm nay engineering agent **vừa viết code vừa viết test cho chính code đó**, trong cùng một worktree,
cùng một lượt gọi model (`Route("tasks", "$assignee", "pull-requests", tools="rw")`). Reviewer được giao
việc chấm "test có phủ Gherkin của ticket không" — nhưng bộ test nó chấm do chính tác giả code sinh ra.

Đó là **cùng một tác nhân sinh ra cả code lẫn tiêu chí kiểm tra code**. Khi model hiểu sai `acceptance`,
nó hiểu sai *nhất quán* ở cả hai chỗ: code sai và test khẳng định đúng cái sai đó. Không lớp nào phía sau
bắt được, vì mọi lớp phía sau đều đọc cùng bộ test ấy.

ADR-0021 vừa làm rủi ro này tăng thêm một bậc, có chủ đích và có lý do tốt: với ticket **không** có
`risk_tags`, `required_reviews` còn đúng `{reviewer}` — reviewer là **lượt kiểm thử duy nhất trước
release** — và `model_tier` của reviewer đồng thời hạ `strong → standard`. Hai thay đổi đó tiết kiệm thật,
nhưng chúng dồn toàn bộ gánh nặng "test có ý nghĩa không" lên một lượt đọc diff.

Ba dữ kiện nữa từ chính repo này:

1. **ADR-0010 đã dạy đúng bài học một lần rồi.** Trước nó, prompt bắt khối kỹ thuật "TDD, chạy lint + test
   trước khi publish PR" trong khi runtime không cho agent chạm file nào — hệ thống *"sinh ra bằng chứng
   chất lượng giả, tệ hơn là không có tính năng"*. Cách sửa không phải viết prompt chặt hơn mà là **đổi cấu
   trúc**: bằng chứng do code điền. Ở đây cũng vậy — "hãy viết test trung thực" là câu chữ; **người viết
   test khác người viết code** là cấu trúc.
2. **TDD hiện chỉ là lời dặn.** Không có gì trong runtime buộc test tồn tại *trước* code, nên `local_checks.tests = true`
   chỉ nói "bộ test do tác giả chọn đã xanh", không nói "code khớp đặc tả".
3. **Nguyên tắc này đã có sẵn trong repo, chỉ chưa áp cho test:** ADR-0003 tách `security-engineer` khỏi
   `reviewer` đúng vì *separation of duties*. Test là chỗ còn lại chưa được tách.

## Quyết định

Thêm agent thứ 21 **`test-author`** (khối `quality`), và đổi thứ tự trong chuỗi ticket để test **có trước** code.

### 1. Luồng mới của một ticket có repo

```
tasks ──► test-author  (lượt MÙ: chỉ acceptance + prd + api-contract; KHÔNG có diff, KHÔNG có code)
             │  ghi CHỈ file test, commit vào branch ticket/<id>
             ▼
        test-suites ──► $assignee  (viết code cho tới khi test xanh; KHÔNG ghi được file test)
                            │
                            ▼
                     pull-requests ──► reviewer (+ qa/security khi có risk_tags — ADR-0021 giữ nguyên)
```

**Test đỏ ngay sau lượt test-author là kết quả ĐÚNG, không phải lỗi.** Nó là tín hiệu duy nhất chứng minh
bộ test thật sự ràng buộc một hành vi chưa tồn tại. Runner ghi `audit-log` `tests_red_as_expected` và đi tiếp;
test **xanh** ngay khi chưa có code mới là dấu hiệu đáng ngờ (test rỗng, assert vô nghĩa) → audit
`tests_green_before_code`, reviewer nhận cờ này trong đầu vào.

### 2. Phân vùng ghi trong worktree — cưỡng chế ở `tools.py`, không bằng prompt

`Toolbox` hiện có `allow_write: bool` (toàn worktree hoặc chỉ đọc). Thêm `write_scope`:

| `write_scope` | Ai dùng | Ghi được |
|---|---|---|
| `"tests"` | `test-author` | **chỉ** đường dẫn khớp `Stack.test_globs` |
| `"src"` | engineering agent | mọi thứ **trừ** đường dẫn khớp `Stack.test_globs` |
| `"all"` | (mặc định cũ, giữ cho đường không có test-author) | như hiện tại |

Kiểm tra đặt tại `_path(rel, for_write=True)` — **một chỗ duy nhất** mà mọi tool ghi đã đi qua, cùng nơi
đang chặn `..`, symlink, `.git/`, `SECRET_FILES`.

`Stack` thêm `test_globs`: PY `tests/**`, `test_*.py`, `*_test.py` · NODE `test/**`, `tests/**`, `__tests__/**`,
`*.test.*`, `*.spec.*` · GO `*_test.go` · RUST `tests/**` · GRADLE/MAVEN `src/test/**`.

### 3. Fail closed khi không phân vùng được

`UNKNOWN` stack không có `test_globs` ⇒ **không** chạy test-author (không thể cưỡng chế ranh giới thì đừng
giả vờ có nó). Ticket đi đúng luồng cũ, và PR mang `tests_authored_by: "assignee"` để reviewer biết bộ test
này **không** độc lập. Cùng tinh thần với `local_checks.unverified` của ADR-0010: nói thẳng là chưa có, không
im lặng. Không có `--repo` cũng vậy.

### 4. Tranh chấp test — assignee không được tự sửa

Assignee cho rằng test sai thì **không** sửa được (tool chặn). Nó ghi `test_dispute` trong payload
`pull-requests`; route mới đưa việc về `test-author` (lượt này **được** xem diff) để sửa test hoặc bác bỏ kèm
lý do. Đây là chỗ duy nhất test được đổi sau khi đã viết, và nó luôn để lại vết trong bus.

### 5. Đặc tả agent

```yaml
id: test-author
block: quality
model_tier: standard
reads: [tasks, pull-requests]      # pull-requests chỉ để xử lý test_dispute
writes: [test-suites]
context_namespace_write: null
context_namespace_read: [prd, api-contract]   # KHÔNG có architecture/threat-model: không cần, và giữ lượt gọn
max_input_chars: 60000
skills: [testing]                  # nạp đầy đủ; qa-debugger vẫn giữ đầy đủ — ADR-0016 đòi ≥ 1 chủ quản, không cấm 2
skills_core: [engineering-common, api-contract, accessibility]
budget_tokens_per_task: 60000
max_retries: 1
timeout_minutes: 60
```

Topic mới `test-suites` (thứ 19), key = `ticket_id`, payload: `ticket_id`, `project_id`, `branch`,
`files[]` (đường dẫn test đã ghi), `acceptance_covered[]` (ánh xạ **1-1** với `acceptance` của ticket),
`blind` (true ở lượt đầu), `notes`.

## Lý do

- **Chi phí đúng chỗ.** Thêm 1 lượt/ticket ở tier `standard`. ADR-0021 vừa cắt 2 lượt khỏi ticket thường
  (qa + security), nên ticket thường vẫn còn **3 lượt** thay vì 4 như trước ADR-0021 — rẻ hơn hiện trạng cũ,
  và đổi lại là lớp bảo vệ mà ADR-0021 vừa gỡ mất.
- **Biến TDD thành cấu trúc.** Test tồn tại trước code không còn là lời dặn: nó là thứ tự của bảng route.
- **`local_checks.tests` có nghĩa mới.** Trước: "test của tôi xanh". Sau: "test do người khác viết từ đặc tả
  đã xanh". Cùng một trường, giá trị chứng minh khác hẳn.
- **Đúng bài học ADR-0010.** Ràng buộc nằm ở runtime (`tools.py`), không ở prompt.

## Các phương án đã cân nhắc

- **A. Giữ nguyên, siết prompt reviewer.** Rẻ nhất, và đã làm ở ADR-0021 (reviewer phải chấm test theo Gherkin).
  Nhược: reviewer vẫn chấm bộ test do tác giả code chọn; nó không thấy được **test lẽ ra phải có mà không ai viết**.
  Không chọn — đây đúng là "viết prompt chặt hơn" mà ADR-0010 đã chỉ ra là không đủ.
- **B. Đưa việc viết test về `qa-debugger`.** Không cần agent mới. Nhược: qa-debugger là vai *chẩn đoán khi
  test fail* trên staging — trộn vào đó thì nó vừa viết test vừa phân tích lỗi của chính test mình, lặp lại
  đúng vấn đề đang sửa; và `reads`/`writes` của nó phình ra khắp chuỗi. Không chọn.
- **C. Chạy test-author SONG SONG với assignee.** Không thêm độ trễ. Nhược: hai agent ghi cùng worktree cùng lúc —
  đúng loại "concurrent modification" mà kiến trúc này tránh bằng key=ticket_id; và mất luôn tính chất TDD
  (code không bao giờ phải làm cho test đỏ thành xanh). Không chọn.
- **D. Sinh test bằng code, không dùng model** (từ Gherkin → khung test). Xác định, rẻ. Nhược: chỉ ra được
  khung rỗng, không ra ca biên — mà ca biên mới là chỗ test có giá trị. Có thể làm **thêm** sau, không thay thế.

## Hệ quả

**Tích cực**
- Bộ test không thể bị uốn theo cách cài đặt: tác giả của nó không có quyền ghi vào code, và ngược lại.
- Có tín hiệu mới, đo được: `tests_red_as_expected` (lành mạnh) vs `tests_green_before_code` (đáng ngờ).
- Reviewer được giảm tải đúng phần ADR-0021 vừa chất lên nó.

**Đánh đổi phải chấp nhận**
- +1 lượt model mỗi ticket (~+25% lượt của ticket thường), +độ trễ tuần tự.
- Test-author viết mù có thể hiểu sai `acceptance` → test sai → tốn một vòng tranh chấp. **Đó là chi phí có
  chủ đích**: một test sai lộ ra ở vòng tranh chấp còn hơn một test đúng-với-code-sai lọt tới production.
- `UNKNOWN` stack mất lớp bảo vệ này. Chấp nhận, nhưng phải **nhìn thấy được** (`tests_authored_by`).

**Việc cần làm tiếp (tách PR như ADR-0020 → ADR-0021)**
1. **PR 1 (ADR này)** — chốt thiết kế.
2. **PR 2** — `Stack.test_globs` + `Toolbox.write_scope` + test cưỡng chế ranh giới (ghi sai vùng ⇒ `ToolError`).
3. **PR 3** — agent `test-author`, topic + schema `test-suites`, route, `make golden`, `make eval-record`.
4. **PR 4** — cờ `tests_authored_by` / `test_dispute` vào payload PR + prompt reviewer đọc chúng; cập nhật
   `docs/architecture.md` (bảng topic, vòng đời ticket) và `docs/DIEU-PHOI-MODEL.md` (bảng agent → tier).
5. Sau 4 tuần: đối chiếu `review_catch_rate` và số lỗi lọt; nếu test-author `standard` bỏ sót ca biên rõ rệt
   thì nâng `strong` — ghi lại kèm bằng chứng eval như đã làm với `researcher`.
