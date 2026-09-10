# ADR-0003: Mỗi ô trả lời một câu hỏi của người trực; ô không có dữ liệu là ô xám

Trạng thái: Accepted · Ngày: 2026-09-06 · Phạm vi: `console/` (đợt 3 của `docs/DAC-TA-NANG-CAP-2026-09.md`, mục C1–C10)

## Bối cảnh

Đêm 05–06/09/2026, một người trực vận hành dự án QLKH suốt đêm với console mở trước mặt. Console **không chạy sai**
một lần nào: mọi con số nó hiện đều đúng với dữ liệu trên bus. Người trực vẫn mất hàng giờ, vì đọc sai trạng thái.
Mười chỗ đã đánh lừa, ghi nguyên văn ở `console/TRAPS.md`:

1. Nhãn `merged` của máy trạng thái bị đọc thành "đã gộp vào nhánh tích hợp" — 14/14 ticket có merge commit thật
   trong khi bảng hiện 10 `approved`, 4 `merged`.
2. `status` xanh toàn tập khi dự án chết đứng: `queue: 0, blocked: [], gates: {}` — **xanh vì RỖNG**, 18/19 release
   không đi đâu được.
3. `delivery: {}` nghĩa là *chưa từng giao gì* (0 tag, 0 production), nhưng vẽ ra như một dict rỗng vô hại.
4. Không có phễu release: 4 staging/failed, 6 pending_human, 3 deployed, 5 void, 0 production — phải truy vấn tay
   mới biết.
5. Gate chỉ hiện "đang chờ", không hiện `kind` và hậu quả: duyệt `escalation` cho một REL-xxx và tưởng vừa giao hàng.
6. Quyết định ký lúc 01:34, orchestrator áp lúc 01:48 — 14 phút dashboard im lặng, chữ ký nhìn như vô tác dụng.
7. Ticket `blocked` mà không gate nào chờ (QLKH-010/014, khoá `once` trùng): **không ai được hỏi**, mà trang vẫn xanh.
8. Verdict chấm trên bằng chứng đã bị cắt: security chặn vì "thiếu diff", thật ra openapi 804 dòng ăn hết hạn mức —
   không chỗ nào trên trang nói là đã cắt.
9. Ngân sách so tổng token với ngưỡng tính theo token **đầu ra** — hai đại lượng khác nhau, đội lốt một con số.
10. Lý do duyệt `"ok"` đi lọt: agent nhận hint rỗng, hiểu là "không có gì để sửa", và lặp lại đúng việc vừa bị trả về.

Mẫu chung của cả mười: **trang trả lời câu hỏi của dữ liệu, không trả lời câu hỏi của người**. "Có bao nhiêu ticket
ở trạng thái `merged`" là câu hỏi của dữ liệu. "Khách đã có gì chạy được chưa" là câu hỏi của người. Và ở khắp nơi,
*không có dữ liệu* được vẽ giống hệt *không có vấn đề* — đó là lý do một dự án chết đứng nhìn như một dự án khoẻ.

#76 và #80 đã vá bốn chỗ (lớp "sự thật giao hàng", khoá lý do dưới 20 ký tự). ADR này chốt nguyên tắc chung cho cả
mười, để lần sau thêm màn mới không dựng lại đúng cái bẫy.

## Quyết định

1. **Mỗi ô trên trang phải trả lời được một câu hỏi mà người trực thật sự hỏi**, viết ra thành lời trước khi viết
   code. Không viết được câu hỏi thì không đưa ô đó lên. Ba câu kiểm bắt buộc (đã có ở cuối `TRAPS.md`, nay là luật):
   *nó đo cái gì đúng nghĩa đen?* · *nó xanh vì tốt hay vì rỗng?* · *người thấy nó sẽ làm gì tiếp, và làm thế có
   đúng không?*

2. **Ô không có dữ liệu là ô XÁM, không bao giờ là ô xanh.** Trong phễu sản phẩm, mọi bậc có `n == 0` mang cờ
   `empty=True` từ tầng dữ liệu (`Truth.product_funnel`) chứ không phải do CSS đoán, và trang tô nó nền trong,
   viền gạch đứt, kèm chữ "chưa có gì". "Không có gì để lo" và "không có gì để đo" phải nhìn khác nhau từ xa.

3. **Con số nào phán trạng thái giao hàng thì phải dựa trên bằng chứng máy sinh, không dựa trên lời khai.** Bậc
   *staging* và *production* của phễu chỉ đếm những lượt deploy có `payload.smoke` (ADR-0029 của company);
   `status: "deployed"` do agent tự khai mà không kèm smoke thì bậc đó vẫn XÁM. Kết quả smoke (`ok` / `fail` /
   `unverified`) hiện ngay trong ô.

4. **Mỗi quyết định hiện hậu quả CẢ HAI CHIỀU trước khi bấm**: duyệt thì điều gì xảy ra và **agent nào chạy lại**;
   từ chối thì ticket/RC **về trạng thái nào**. Trước đây chỉ có nửa "duyệt", nên không ai dám từ chối — không ai
   biết từ chối thì việc rơi đi đâu. Lý do người sắp gửi hiện **nguyên văn** ngay cạnh nút, dưới nhãn "Hint agent
   sẽ nhận", vì nó đúng là chuỗi mà agent nhận.

5. **Bế tắc im lặng là một loại cảnh báo riêng, màu đỏ, ở đầu trang.** Ticket kẹt *mà có gate đang chờ* là "đang
   chờ người" — bình thường. Ticket kẹt *mà không gate nào chờ* là "không ai được hỏi" — đây là loại duy nhất sẽ
   không bao giờ tự kêu lên, nên nó phải là thứ đầu tiên đập vào mắt, kèm số đếm.

6. **Nhãn của máy trạng thái và sự thật của git là hai cột khác nhau, không bao giờ trộn.** "Commit vượt
   integration" đo bằng `git rev-list --count company/integration..ticket/<id>` — **không** dùng
   `git branch --contains`: `--contains` trả cùng một câu trả lời cho nhánh rỗng và nhánh có commit chưa gộp, tức
   là mù đúng chỗ đang cần nhìn. `null` (không đo được) và `0` (đã gộp hết) là hai giá trị khác nhau và hiện khác
   nhau: `—` và `0`.

7. **Bằng chứng phải rẻ hơn chữ ký.** Hồ sơ `gate_brief` — nửa "người tự kiểm thêm" của checklist — dựng được ngay
   trong ngăn kéo gate, một cú bấm, `GET /api/gate/brief`, **không cần** `--allow-decide`. Console gọi thẳng
   `company.gate_brief.build` / `render_md`; hồ sơ trên trang và hồ sơ do CLI `/gate-brief` sinh ra là **cùng một
   văn bản** (có test so bằng). Nếu đọc bằng chứng khó hơn ký, người ta sẽ ký mà không đọc — đêm 05/09 đã vậy.

8. **Console không giữ nguồn sự thật nào của riêng nó.** Mọi thứ nó biết suy lại được từ hai file SQLite của hai
   công ty: kể cả đường dẫn repo khách (đọc từ audit `project.repo`) và tên nhánh tích hợp (từ audit
   `integration.merged`). Chỗ duy nhất trang nhớ giữa hai lần tải là **tên người duyệt** trong `localStorage`; chỗ
   đang đứng nằm ở hash (ADR-0002). F5 không mất gì, và hai lần đọc liên tiếp cho cùng một trạng thái.

## Đã cân nhắc và bỏ

- **Tô đỏ ô rỗng thay vì tô xám.** Đỏ là "có chuyện"; rỗng thường chỉ là "chưa tới lượt". Đỏ hoá mọi ô rỗng thì
  một dự án mới tinh sẽ đỏ rực và người ta học cách bỏ qua màu đỏ — mất luôn tín hiệu của mục 5.
- **Đếm bậc phễu theo trạng thái FSM cho gọn.** Đúng cái bẫy #1: FSM `released` chỉ nói lệnh deploy đã chạy xong,
  không nói dịch vụ có trả lời request nào không. Bậc phải neo vào smoke.
- **Cấu hình đường dẫn repo trong console (`--repo`).** Thêm một nguồn sự thật thứ ba, lệch với công ty ngay lần
  đầu ai đó đổi repo, và phá mục 8. Đọc từ bus thì không thể lệch.
- **Cache kết quả `git rev-list` trong RAM.** Rẻ hơn thật, nhưng là đúng khuôn lỗi "state chỉ sống trong RAM" đã ăn
  22 PR của company. Thay vào đó: chỉ đo ticket **chưa xong** — số tiến trình git bị chặn trên bằng số ticket đang
  chạy, thường dưới mười.
- **Dựng `gate_brief` sẵn cho mọi gate mỗi lần `collect()`.** Mỗi hồ sơ replay cả log; nhân với số gate và với mỗi
  lần bus đổi thì console thành gánh nặng cho chính con SQLite orchestrator đang ghi. Dựng khi có người bấm.
- **Một màn "sức khoẻ hệ thống" gộp mọi chỉ số.** Đó chính là cái `status` xanh toàn tập của bẫy #2: gộp đủ thứ vào
  một con số thì con số đó không trả lời câu hỏi nào cả.

## Hệ quả

- `truth.py` giữ thêm bốn câu trả lời: phễu sản phẩm (`product_funnel`), hậu quả từ chối (`gate_reject_effect`),
  quyết định chờ áp gắn theo subject (`pending_decision_of`), nguồn ngữ cảnh bị cắt (`review_trimmed_sources`).
  Nó vẫn **không đụng git** — phần git nằm ở `git_truth.py` và được gọi từ `collect.py`.
- Console giờ có thể chạy `git` (chỉ đọc: `rev-list`) trên repo của khách. Đây là bề mặt mới: chỉ những lệnh đọc,
  timeout 5 giây, và mọi thất bại trả `None` chứ không ném — trang không được đỏ vì máy thiếu git.
- `/api/gate/brief` là đường đắt nhất của server (replay cả log). Nó là `GET` và không có tác dụng phụ, nhưng đây
  là chỗ đầu tiên cần nhìn nếu console làm chậm orchestrator.
- Màn thứ bảy — **Phễu sản phẩm** (`#/phieu`) — vào thanh bên. `VIEWS`, `TITLES`, nút nav và `<section>` phải khớp
  nhau; test tĩnh đã kiểm bốn chỗ đó là cùng một tập.
- C9 (màn "Xưởng video") **chưa làm**: nó phụ thuộc `output/` và deep-link gate `PUB-*` của studio, mà đợt 4 chưa
  chạy. Nguyên tắc ở ADR này áp cho C9 khi tới lượt.
