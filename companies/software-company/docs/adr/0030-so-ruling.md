# ADR-0030: Sổ Ruling — agent tự quyết ngoài bốn human gate và ghi lại "sai thì mất gì"

## Bối cảnh
Công ty có bốn human gate cố định (`spec`, `plan`, `release`, `acceptance`) cộng `escalation`. Nhưng agent còn một
đường dừng thứ sáu, nằm trong "Quy tắc chung" của mọi prompt: *"công việc cần quyết định thuộc về người hoặc agent
khác → trả kết quả hiện có kèm lý do, KHÔNG thử tiếp"*. Đường này không phải gate: không có checklist, không có hạn,
không có người được chỉ định. Nó là chỗ mọi thứ bí đều đổ về.

Đo được:
- REL-019 (2026-09-06): release-engineer tự từ chối deploy production với `pending_human`, không gate nào mở; kích lại
  được chỉ sau khi người đi vòng qua CR-OPS-001 + request/approve gate release tay.
- QLKH cả dự án: quyết định framework, DB thật, cloud bị **né qua từng ticket** — không ai quyết, cũng không ai
  ghi là chưa quyết; 25 release sau vẫn không có server (báo cáo `2026-09-06-ban-giao-khong-chay-duoc.md`).
- 10 RC `pending_human` kẹt với `status` xanh (#77/#78) trước khi có sweep mở escalation.

Ba repo skill được nhiều người dùng nhất (obra/superpowers `subagent-driven-development`, addyosmani `/build auto`,
karpathy-skills "Think Before Coding") cùng chỉ vào một chỗ: **kế hoạch đang chạy thì không đợi người**. Superpowers
diễn đạt rõ nhất — *"Rulings, not stalls"*: mâu thuẫn, chỗ mơ hồ, khiếm khuyết của plan → agent tự quyết, ghi
`Ruling: <quyết gì> — <vì sao> — <sai thì mất gì>`, đi tiếp. Chỉ bốn thứ được dừng: thao tác không đảo ngược được;
nhạy cảm bảo mật; tác động ra ngoài worktree (merge/push/publish); kế hoạch hỏng tới mức mọi hướng đều là đoán. Bốn
thứ đó trùng gần khít với bốn gate của công ty. Cái thiếu là **sổ** cho mọi thứ còn lại.

## Quyết định
1. **Trường `rulings` trên mọi topic.** `payload.rulings: [{decision, why, cost_if_wrong}]` — thêm vào cả 19 JSON
   Schema (cùng một định nghĩa) và 8 model Pydantic (`Ruling` trong `events.py`). Ba phần đều bắt buộc: thiếu
   `cost_if_wrong` là một quyết định không soát được. Mô tả trong schema chính là chỉ dẫn cho model (schema đi vào
   `--json-schema` / structured output của mọi provider). **Schema là một phần của prompt**: đổi schema làm khoá bản
   ghi eval của cả 21 agent lệch → phải `make eval-record` lại toàn bộ (đo được ngay khi làm PR này: ~2,5 phút/agent).
   Không có "kênh không cần eval lại" — đúng như ADR-0010 đã nói, chỉ là lần này thấy rõ bằng đồng hồ.
2. **Sổ nằm trên bus, không trong RAM.** `Runner.publish` ghi một audit `ruling` cho mỗi mục (actor = agent, kèm
   `ticket_id`/`project_id`, `topic`, `key`, `event_id` của payload chứa nó). `Orchestrator.rulings()` đọc lại từ
   audit-log — không có state mới để mất khi mở lại bus (khuôn 2, `TRAPS.md`).
3. **Người phải thấy.** `status` đếm `rulings`; CLI `orchestrator rulings [--project|--ticket]` in sổ; **mọi hồ sơ
   `gate_brief`** có mục "Sổ Ruling" liệt kê quyết định agent đã tự đưa ra trong dự án — người ký gate đọc để biết
   những chỗ *không ai hỏi họ*, và lật lại cái nào đáng lật.
4. **Prompt đổi ở bước sau, không phải bước này.** Câu "công việc cần quyết định thuộc về người → dừng" trong Quy tắc
   chung của 21 agent sẽ được thay bằng bốn-việc-được-dừng + ruling. Đó là sửa prompt 21 agent → 7 bước
   `CONTRIBUTING.md` §3 (tăng version, golden, eval-record). Tách thành PR riêng để đo trước: sau vài ngày chạy
   thật, sổ có mục nào không khi mới chỉ có schema nhắc? Nếu có → prompt chỉ cần bỏ câu "dừng"; nếu không → prompt
   phải nói rõ hơn. Đổi prompt mà chưa đo là sửa mù.

## Không làm (và vì sao)
- **Không tự phân loại `pending_human` thành "đáng lẽ phải ruling"** rồi chạy lại agent với hint. Phân loại cần
  model, và vòng "chạy lại tới khi nó chịu quyết" là đúng khuôn 4 (lặp mãi trong im lặng). Người soát sổ Ruling
  và gate escalation là đủ; nếu sau vài tuần thấy một loại `pending_human` lặp đều, đó là lúc viết rule cụ thể.
- **Không cho ruling ghi đè gate.** Ruling là quyết định *trong phạm vi việc đang làm*; merge/push/production vẫn
  là gate. Một ruling nói "tôi quyết deploy production" là vô nghĩa — orchestrator không đọc ruling để hành động.

## Hệ quả
- Agent có chỗ để nói "tôi đã chọn X vì Y, sai thì mất Z" thay vì chọn im lặng (khuôn 1) hoặc dừng (REL-019).
- Người ký gate có thêm một mục đọc; mục rỗng cũng là tín hiệu: *agent vẫn dừng ở chỗ đáng lẽ phải quyết*.
- Console chưa hiện sổ Ruling — `console/TRAPS.md` nguyên tắc "mỗi con số nói nó đo gì" áp khi thêm.
- Việc kế tiếp: PR đổi Quy tắc chung của 21 agent (cần hạn mức eval); `open_decisions` trong `plan.proposed`
  (đề xuất 2 báo cáo 2026-09-06) là một dạng ruling ở cấp kế hoạch, có thể dùng cùng trường này.

## Liên quan
ADR-0010 (ràng buộc ở runtime, không ở prompt), ADR-0029 (bằng chứng máy chạy), `TRAPS.md` khuôn 1/2/4,
báo cáo `2026-09-06-danh-gia-superpowers-va-skill-frontend.md` §2.2, `docs/reports/2026-09-06-ban-giao-khong-chay-duoc.md`.
