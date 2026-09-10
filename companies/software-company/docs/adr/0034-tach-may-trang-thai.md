# ADR-0034: Tách máy trạng thái khỏi `orchestrator.py`

Trạng thái: chấp nhận · Ngày: 2026-09-06 · Mục K1 của `docs/DAC-TA-TRIEN-KHAI-KICH-BAN-B.md` · Liên quan:
ADR-0007 (orchestrator), ADR-0011, ADR-0027, `TRAPS.md` §1

## Bối cảnh

`orchestrator.py` đã tới 2269 dòng, một class `Orchestrator` gồm hơn 90 phương thức trộn chung: CLI dispatch,
verify/smoke, bảng route, trạng thái phiên (30 trường), replay khi restart (`_rehydrate`), khoá worktree, lịch
chạy (`scheduler`), nhắc gate, và hai cỗ máy trạng thái nghiệp vụ (ticket, release). Phần lớn PR gần đây cùng họ
sửa file này — mỗi PR fix một góc nhưng đều phải đọc và hiểu toàn bộ 2269 dòng để không phá góc khác, và nhiều
lỗi bắt nguồn từ cùng dạng ("quên rehydrate một trường", "quên `_remember` sinh khoá mới sau retry").

## Quyết định

1. Gói `orch/` bên trong `company`, tách theo trách nhiệm: `ctx.py` (giao diện `OrchCtx` Protocol những gì các
   module còn lại cần từ `Orchestrator`), `cli.py` (dispatch CLI), `verify.py` (smoke/regression/evidence),
   `routes.py` (hằng số route + guard thuần, không giữ trạng thái), `state.py` (`OrchState` dataclass — mỗi
   trường có metadata `rehydrate` khai nó được replay từ đâu), `rehydrate.py` (nạp lại `OrchState` từ audit log
   khi restart), `worktree_flow.py` (khoá/merge worktree), `scheduler.py` (vòng lặp `tick`/`watch`), `gates_flow.py`
   (nhắc gate, escalation, nợ kiến trúc), `ticket_fsm.py` + `release_fsm.py` (hai máy trạng thái nghiệp vụ, có
   bảng chuyển trạng thái tra cứu thay vì rẽ nhánh rải rác).
2. `orchestrator.py` chỉ còn: dựng `Orchestrator` (implements `OrchCtx`), `process()` tra `ROUTES` rồi gọi đúng
   FSM, và các hàm tiện ích ngắn không thuộc module nào ở trên. Mục tiêu ≤ 300 dòng.
3. Bảng chuyển trạng thái (`Transition` frozen dataclass: `src`, `event`, `guard`, `dst`, `action`) là **driver**,
   không phải nguồn sự thật trạng thái — nguồn sự thật vẫn là `lead.state` (`delivery.py`) và các trường trong
   `OrchState`. Bảng chỉ làm rõ đường đi hợp lệ và bắt các cặp chuyển bị cấm (ví dụ `integrated` + `tasks` cũ)
   bằng audit `superseded`/`ignored` thay vì exception.
4. Vì 28 file test hiện gọi trực tiếp thuộc tính cũ (`o.processed`, `o.once`, …), giữ property alias từ
   `Orchestrator` sang `self.state.<tên>` cho toàn bộ 30 trường — tách module không được đổi hợp đồng test hiện
   có; test mới thêm cho hành vi mới.
5. Khoá `_remember` sinh theo **thế hệ** (ví dụ thêm `retries.get(tid, 0)` vào khoá `no-test-author:{tid}`) để
   một sự kiện lặp lại sau khi đã retry không bị khoá cũ chặn nhầm.

## Hệ quả

- Mỗi module ≤ 400 dòng, một trách nhiệm — sửa route không cần đọc `scheduler.py`, sửa nhắc gate không cần đọc
  `ticket_fsm.py`.
- Rủi ro cao nhất là `OrchState`/rehydrate (K1.3): bỏ sót một trường trong bảng rehydrate làm trạng thái "biến
  mất" sau restart nhưng không lỗi ngay — test bất biến bắt buộc mỗi trường phải có `metadata["rehydrate"]`, và
  test tham số hoá theo từng trường xác nhận nó sống sót qua audit replay.
- Luật CI mới (K8.3): PR `fix(company)` chạm `orchestrator.py`/`orch/` phải dẫn ADR-0037 (số PR trong đặc tả gốc;
  ở repo này là ADR-0034) trong thân PR, nói rõ đụng bảng chuyển nào.
- Không đổi hành vi nghiệp vụ nào trong PR tách module này — chỉ đổi cách code được tổ chức; hành vi mới (nếu
  có) đi PR riêng, dẫn ADR riêng.

## Liên quan

ADR-0007 (quyết định dựng orchestrator ban đầu), ADR-0011, ADR-0027 (tag phát hành), `TRAPS.md` §1 (họ lỗi cùng
khuôn), `docs/DAC-TA-TRIEN-KHAI-KICH-BAN-B.md` mục K1.
