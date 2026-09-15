# ADR-0042: scorer eval phải tự chứng minh nó bắt được lỗi (`--selftest`)

Trạng thái: Accepted · Ngày: 2026-09-15 · **Bổ sung** ADR-0010 (`REQUIRED.txt` gác bản ghi thiếu/lệch phiên bản
prompt) và ADR-0015 / `evals/thresholds.yaml` (gác **điểm chấm** không được tụt). Hai cổng đó giữ nguyên, không
thay đổi gì — chúng gác **đầu vào** và **đầu ra** của phép đo; ADR này gác thứ ở giữa mà chưa ai gác: **chính
cái thước**.

## Bối cảnh

Bộ eval của software-company có **59 ca** trên 6 agent (đo 2026-09-15: builder 13 · product 16 · security 10 ·
ops 9 · qa 8 · supervisor 3). Mọi ca chấm bằng `check(payload, expect)` —
`platform/xagents-core/src/xagents_core/evals.py:72-89` — sáu assertion tất định: `equals`, `contains`,
`min_len`, `max_len`, `one_of`, `any_of`. Không có model nào chấm, và đó là chủ ý (ADR-0004: prompt là code;
`AGENTS.md` luật cấm 4: không gọi provider trả phí trong test).

Vấn đề không nằm ở `check()`. Nó nằm ở chỗ **chưa bao giờ có ai bắt một `expect:` chứng minh nó bác được một
output sai**. Một `expect:` lỏng biến ca đó thành **xanh vĩnh viễn** — và như thế nó còn tệ hơn việc không có
ca, vì nó vẫn được đếm vào mẫu số `min_pass_ratio` như một ca thật, làm số điểm đẹp lên bằng một phép đo rỗng.

Ba ví dụ đo được, dẫn `file:dòng` (`companies/software-company/evals/`):

1. `builder.yaml:84` — `expect: {equals: {ticket_id, branch}, contains: {summary: i18n}}`. Hai `equals` chỉ so
   trường **định danh** (chép thẳng từ input), còn `contains: {summary: i18n}` cho qua bất cứ PR nào **nhắc
   chữ "i18n"**. `check()` không phân biệt hoa thường và **không phân biệt khẳng định với phủ định**
   (`evals.py:77-78`), nên một PR hard-code toàn bộ chuỗi rồi viết *"chưa làm i18n"* trong `summary` vẫn PASS —
   đúng cái mà tên ca (`de-bai-co-chuoi-cung-van-khong-duoc-hard-code`) nói là phải bắt.
2. `builder.yaml:230` — cùng khuôn: `equals` trên `ticket_id`/`branch` + `contains: {summary: policy}`. Từ
   "policy" xuất hiện trong bất kỳ câu nào, kể cả *"chưa thêm policy-as-code"*.
3. `qa.yaml:32` — `min_len: {acceptance_covered: 2, files: 1}` chỉ **đếm độ dài** (`evals.py:79-80`): hai phần
   tử rỗng, hoặc hai chuỗi vô nghĩa, đủ qua.

Ba ca còn lại cùng khuôn: `security.yaml:156` (`any_of` — chỉ cần **một** nhánh đạt, `evals.py:85-88`, nên
nhánh lỏng nhất quyết định cả ca), `supervisor.yaml:43`, `ops.yaml:58`. Tổng cộng **6/59 ca đã điểm mặt**; con
số thật có thể cao hơn — hôm nay không có cách nào đo, và đó chính là vấn đề.

Cổng hiện có không chạm tới chuyện này, và không phải vì chúng hỏng:

- `--replay --strict` (`company/evals.py:220,226-228,239-240`) đỏ khi **bản ghi** thiếu hoặc lệch phiên bản
  prompt. Nó gác việc *có đo hay không*, không gác việc *thước có chia vạch hay không*.
- `evals/thresholds.yaml` gác **điểm** không tụt dưới sàn. Một ca luôn-xanh làm điểm **đi lên**, nên cổng này
  không bao giờ thấy nó — nó còn bị ca lỏng đánh lừa theo đúng chiều mà nó không kiểm được.

Nói gọn: repo có cổng cho đầu vào của phép đo và cho kết quả của phép đo, nhưng không có cổng nào hỏi *"thước
này có bao giờ chỉ sai không?"*. Đây đúng là khuôn "cổng chết im lặng" mà `platform/console/tests/test_cong_repo.py`
sinh ra để chặn ở chỗ khác — người ta vẫn tin nó canh.

## Quyết định

1. **Mỗi ca eval mang theo một bản `bad:`** — một payload **hợp lý về hình dạng nhưng sai về nội dung**, cùng
   cấp với `expect:` trong file yaml. Đây là đối chứng của chính ca đó: `expect:` tả output đúng, `bad:` tả một
   output sai **thật** mà ca đó sinh ra để bắt.
2. **`check()` phải bác được `bad:` của chính ca đó.** `check(bad, expect)` trả danh sách rỗng ⇒ ca hỏng, nhãn
   `khong-bat-duoc`. Dùng lại đúng `check()` đang chấm thật, **không viết bộ so khớp thứ hai** — một thước thứ
   hai thì lại phải tự kiểm lần nữa, không có đáy.
3. **Ca thiếu `bad:` là ca chưa chứng minh được gì**, nhãn `chua-chung-minh`, và **cũng đỏ** khi chạy `all`.
   Nếu chỉ cảnh báo, ca mới viết lỏng lại lọt đúng bằng con đường cũ, và ADR này thành tài liệu.
4. **`--selftest` không gọi model, không đọc bản ghi.** Nó là phép kiểm tĩnh trên yaml, nên chạy được ở mọi
   máy, mọi lúc, không tốn đồng nào — cùng nhóm cờ loại trừ với `--record`/`--replay` (`company/evals.py:189`),
   vì nó không phải một chế độ chạy model.
5. **Chạy trong CI cạnh `--replay --strict`**, không thay nó. Ba cổng, ba câu hỏi khác nhau: có bản ghi đúng
   phiên bản không (`--strict`) · thước có chia vạch không (`--selftest`) · điểm có tụt không (`thresholds.yaml`).
6. **Chiều sửa chỉ có một.** Thấy `khong-bat-duoc` thì siết `expect:` cho tới khi nó bác được `bad:`. **Không
   nới `bad:` cho vừa `expect:`** — `bad:` tả sự thật về một output sai, `expect:` là bản chép của cái thước.
   Nới `bad:` là tự làm dễ đề, và là cách duy nhất khiến ADR này vô dụng.

Phạm vi: ADR này chỉ nói về **scorer tự kiểm**. "Đo chất lượng agent nói chung" rộng hơn nhiều và cần ADR riêng.

## Từ chối

- **Judge LLM chấm như ponytail làm.** Thêm một model vào đường chấm là thêm đúng một thứ nữa phải tự kiểm
  trước khi tin — và nó không có `--selftest`, nó có sự đồng thuận. Cũng đụng `AGENTS.md` luật cấm 4 (không
  gọi provider trả phí trong test). Thứ đang thiếu là **phần tự kiểm cho scorer tất định đã có**, không phải
  một scorer mới.
- **Siết tay từng ca trong 6 ca đã điểm mặt, không cần cơ chế.** Vá được 6 ca hôm nay và **không chống được ca
  thứ 60** viết lỏng vào tuần sau. Vấn đề là không có phép kiểm, không phải là sáu ca cụ thể.
- **Coi `--replay --strict` là đủ.** Nó gác bản ghi, không gác scorer (xem Bối cảnh) — hai câu hỏi khác nhau,
  và câu thứ hai hiện không ai hỏi.
- **Sinh `bad:` tự động bằng đột biến payload đúng.** Nghe rẻ, nhưng đột biến máy sinh ra thường sai ở chỗ
  `equals` bắt được ngay (đổi `ticket_id`), tức nó chứng minh đúng phần thước đã chặt sẵn và bỏ qua đúng phần
  lỏng. `bad:` viết tay là chỗ người nói ra *"đây là cách ca này bị lừa"* — giá trị nằm ở câu đó.
