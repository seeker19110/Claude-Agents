# ADR-0007: tỉa `role=tool` cũ trong vòng tool

Ngày: 2026-09-09 · Trạng thái: được chấp nhận · Mẫu: evaluator-optimizer (vòng tự sửa hội thoại của chính nó
trước khi gửi tiếp) · Lớp: 3

## Bối cảnh

Vòng tool (`company/runner.py:_turns`, bản riêng chưa hợp nhất `studio/runner.py:_tool_loop`) chỉ **append**:
mỗi lượt gọi tool, kết quả (`role: "tool"`) nối thêm vào `msgs`, không bao giờ bớt. `context.py: fit()` (K3.1,
core) cắt NGỮ CẢNH (payload + blackboard) một lần TRƯỚC vòng — nó không biết, và không thể biết, `msgs` đã phình
tới đâu qua nhiều lượt tool, vì `msgs` sinh ra trong chính vòng lặp, sau khi `fit()` đã chạy xong.

Hệ quả đo được (4L-3, 2026-09-04): một ticket gọi tool 25 lượt, mỗi lượt gửi lại TOÀN BỘ lịch sử — output kết
quả tool của lượt 1 (vd. nội dung một file 6k ký tự) vẫn nằm nguyên trong request của lượt 25, dù model không
còn cần nó (đã đọc, đã dùng, hoặc đã bị `_stagnant`/4L-3 buộc đổi cách làm). Lượt cuối của một vòng dài đắt gần
bằng TỔNG các lượt trước cộng lại — không phải vì việc còn lại nhiều hơn, mà vì lịch sử đã đọc rồi vẫn bị gửi lại.

`max_input_chars` (ADR-0012) chặn MỖI lượt riêng lẻ không vượt trần, nhưng nó không cắt được `msgs` tích luỹ
qua các lượt — nó áp cho system+payload+blackboard của LƯỢT ĐÓ, còn `msgs` là tham số riêng truyền thẳng vào
`client.complete(messages=msgs, ...)`, ngoài phạm vi `fit()`.

`ToolBox.trace()` (4L-2, xagents_core.tools) đã ghi `out_hash` cho MỌI lời gọi tool, TRƯỚC khi cắt — đây là tiền
đề bắt buộc của ADR này: tỉa mất nội dung nhưng giữ được hash để model biết "đã gọi cái này, kết quả là X, gọi
lại `tool(args_hash=...)` nếu thật sự cần lại", thay vì phải đoán hoặc gọi lại mù.

## Quyết định

Thêm hàm thuần `_prune(msgs, keep_turns=3) -> tuple[msgs mới, số ký tự đã bỏ]` ở `xagents_core.context` (cạnh
`fit`/`trim_payload` — cùng họ "ép ngữ cảnh vào hạn mức", chỉ khác chỗ áp dụng: `fit` cắt MỘT LẦN trước vòng,
`_prune` cắt MỖI LƯỢT bên trong vòng). Gọi ở đầu mỗi lượt của `_turns` (company) và `_tool_loop` (studio) khi
`turn > keep_turns`.

1. **Giữ K=3 lượt gần nhất nguyên vẹn.** `keep_turns=3` = `NO_PROGRESS_WARN` (4L-3) — không phải trùng hợp: lượt
   thứ 3 là lượt model nhận cảnh báo lặp, nó cần thấy đủ ngữ cảnh gần nhất để đổi cách làm; tỉa sớm hơn K sẽ xoá
   đúng bằng chứng nó cần để tự sửa.
2. **`role=tool` cũ hơn K lượt → placeholder.** Nội dung thật thay bằng
   `[đã cắt: <tool> <chars> ký tự, hash <h>; gọi lại nếu cần]` — `<h>` chính là `out_hash` mà `ToolBox.trace()`
   đã ghi (4L-2), không tính lại. Model đọc placeholder biết: đã có kết quả, không cần đoán, gọi lại nếu thật sự
   cần xem lại toàn văn.
3. **Không tỉa `role=user` đầu tiên (msgs[0]).** Đây là yêu cầu gốc của ticket — chống trôi mục tiêu (TRAPS §1
   khuôn "state không sống sót qua vòng"): agent quên input ban đầu sau nhiều lượt tool là lỗi đã thấy ở nơi
   khác trong repo, không tạo thêm đường tới nó.
4. **`role=assistant` giữ nguyên, kể cả `tool_calls`.** Tỉa chỉ nhắm KẾT QUẢ tool (thứ có thể dài và có thể gọi
   lại), không nhắm QUYẾT ĐỊNH của model (lời gọi nó đã chọn) — xoá `tool_calls` sẽ làm lệch hình hội thoại so
   với những gì provider mong đợi (một `assistant` có `tool_calls` phải có đủ `tool` phản hồi tương ứng).
5. **Audit `context_pruned{turn, dropped_chars}` mỗi lần tỉa thật sự bớt ký tự** — người vận hành đọc trace thấy
   lượt nào bị tỉa bao nhiêu, không phải suy đoán từ token giảm.
6. **`_prune` là hàm thuần** (nhận `msgs`, trả `msgs` mới + số đo) — không side effect, không đọc `self`, để
   test được độc lập với `AgentRunner`/`ToolBox` như `fit`/`trim_payload` đã làm.

## Hệ quả

**Được.** Lượt cuối của một vòng dài không còn đắt gần bằng tổng các lượt trước; đo trên fake 10 lượt × 6k
ký tự/lượt: input lượt 10 < 3× input lượt 1 (tắt `_prune` → vượt, bật lại → đạt — số đo thật ghi trong PR
4L-4 phần "Bước B").

**Mất — đây là thay đổi có chủ ý, không phải tác dụng phụ.** `_prune` ĐỔI HÀNH VI của agent: từ lượt K+1 trở đi,
model KHÔNG còn thấy toàn văn kết quả tool cũ trong ngữ cảnh của nó — nó thấy placeholder + hash. Điều này đổi
CHÍNH XÁC nội dung `user`/`tool` gửi tới model ở các lượt sau, nên **khoá bản ghi eval** (`hash(system, user)`,
ADR-0010) của MỌI ca có từ 4 lượt tool trở lên đổi theo. `evals/recordings/*.json` của cả hai công ty phải ghi
lại bằng model thật sau PR này — không phải lỗi hồi quy, là hệ quả trực tiếp của quyết định ở đây; PR "Bước B"
nói rõ điều này thay vì để CI đỏ trông như một lỗi ai đó gây ra.

**Không thuộc phạm vi.** Hợp nhất `_turns` (company) và `_tool_loop` (studio) thành một hàm chung trên
`xagents_core.runner` — hai vòng vẫn là hai bản riêng (studio còn thiếu cả 4L-2/4L-3), chỉ CÙNG GỌI một hàm
`_prune` thuần từ core. Hợp nhất trọn vòng tool là việc khác, lớn hơn, ngoài ngân sách của 4L-4.

## Liên quan

- `docs/KIEN-TRUC-4-LOP.md` mục C "4L-4 · Tỉa tool output cũ" — khối 7 mục nguồn của quyết định này (đặt tên
  làm việc "ADR-0040"; số thật đặt ở đây theo đúng bài học #168 "số ADR đặt trước là bẫy").
- `xagents-core/src/xagents_core/context.py` — `fit`, `trim_payload`, nơi `_prune` được thêm vào.
- `software-company/src/company/runner.py:_turns` (4L-3, `_stagnant`, `NO_PROGRESS_WARN=3`) —
  `docs/adr` không có ADR riêng cho 4L-3; xem `docs/KIEN-TRUC-4-LOP.md` mục C "4L-3".
- `xagents-core/src/xagents_core/tools.py` — `ToolBox.trace()`, `out_hash` (4L-2), tiền đề của placeholder ở đây.
- `docs/adr/0001-loi-chung-xagents-core.md` — công ty là gốc lên core; ADR này theo đúng khuôn "core giữ cơ chế,
  package giữ nghĩa" (mục "Cái gì Ở LẠI package" của ADR-0001, áp dụng ngược: `_prune` là cơ chế, thuộc core).
