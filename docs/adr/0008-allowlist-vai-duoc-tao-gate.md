# ADR-0008: Allowlist vai được TẠO gate (`gate.request`)

## Bối cảnh

ADR-0002 đóng nửa thứ nhất của lỗ hổng `gate.request`: `created_by` nay lấy từ `env.actor` chứ không tin
evidence tự khai, nên không ai bịa được người tạo gate để lách four-eyes. Nửa còn lại được ghi thẳng trong
"Hệ quả" của ADR-0002 và cố ý hoãn:

> Gate ma vẫn **dựng được** (topic `audit-log` mở, không thể chặn ở tầng này) nhưng nay mang tên actor đã tạo
> ra nó. Chặn hẳn cần ACL producer cho `gate.request` giống `gate.decide` — không làm ở đây vì `gate.request`
> là việc **hợp lệ của agent**, nên ACL phải là allowlist theo vai, một gói riêng.

Đây là gói ấy. Khác biệt cốt lõi so với `gate.decide` (chỉ NGƯỜI được ghi, luật một dòng ở `company/bus.py`):
`gate.request` là việc hợp lệ của agent — supervisor mở gate escalation, ops mở gate nghiệm thu, product mở
gate spec — nên không thể cấm agent, chỉ có thể **liệt kê vai nào**.

Rà `gate.request(` ở cả hai công ty cho ra đúng bốn vai mỗi bên:

| Công ty | Vai | Gate | Nơi gọi |
|---|---|---|---|
| company | `product` | `spec` | `orch/ticket_fsm.py` (`created_by=env.actor`, producer của `approved-specs` là `product`) |
| company | `supervisor` | `escalation` | `orch/gates_flow.py`, `orch/ticket_fsm.py` |
| company | `ops` | `acceptance`, `escalation` | `orch/gates_flow.py`, `orch/release_fsm.py` |
| company | `delivery-lead` | `release`, `escalation` | `delivery.py` (code, không phải agent) |
| studio | `channel-strategist` | `plan` | `orchestrator.py` |
| studio | `desk` | `publish` | `orchestrator.py` |
| studio | `community-manager` | `replies` | `orchestrator.py` |
| studio | `supervisor` | `escalation` | `orchestrator.py` |

**Đo trước khi siết** (không suy từ code hiện tại): quét `company.sqlite` thật — 18293 event — cho ra actor
của `gate.request` là `supervisor` (104), `delivery-lead` (40), `release-engineer` (19), `account-manager` (13),
`human:lead-repair` (4), `spec-writer` (1). Ba tên giữa là **vai TRƯỚC ADR-0037** (`ops`/`product` hôm nay).
Một allowlist chỉ gồm tên hôm nay sẽ đánh rơi 33 gate lịch sử khỏi replay, im lặng, không lỗi nào báo — đúng
cái bẫy mà ADR-0002 đã tránh khi chọn "ghi đè chứ không từ chối". Nên allowlist của company gồm cả
`LEGACY_GATE_ACTORS`. Studio không có DB nào trên máy để đo; nó chưa từng chạy thật.

## Quyết định

`PersistentGate` mang một thuộc tính lớp `REQUEST_ACTORS: frozenset[str] | None`; lớp con của mỗi công ty đặt
danh sách của mình (core không biết tên vai nào — ADR-0001 §2). `None` = không giới hạn, giữ nguyên hành vi
trước ADR này cho mọi `PersistentGate` khác (test, keeper về sau).

Ba luật:

1. **Người luôn được phép** và không cần có tên trong danh sách (`is_human(actor)`). Gate CLI là đường của
   người; allowlist này nói về **agent** nào được mở gate.
2. **Chiều ghi ném lỗi.** `PersistentGate.request()` ném `PermissionError` khi vai không có quyền — im lặng bỏ
   qua sẽ tạo ra một gate chỉ sống trong RAM của tiến trình đang chạy rồi biến mất khi tiến trình khác dựng lại
   từ replay (khuôn 2 `TRAPS.md`: state chỉ sống trong RAM). Cả hai CLI bắt lỗi này và trả mã 3 như mọi lỗi
   quyền khác, không để traceback ra màn hình người dùng.
3. **Chiều replay im lặng bỏ qua.** `apply()` bỏ bản ghi `gate.request` của actor lạ đúng như bỏ mọi bản ghi dị
   thường khác — một dòng log xấu không được làm sập replay của cả sổ gate (`gate_cli list` và console đều đi
   qua đường này).

**Không** đặt luật này ở ACL producer của bus, dù `gate.decide` nằm ở đó. Lý do: bus chặn theo `topic`, còn đây
là luật theo `action` **trong** payload của một topic mở, và nó phải áp cả với bản ghi đã nằm sẵn trong
`company.sqlite` từ trước — nơi duy nhất thấy được cả hai chiều là `PersistentGate`, chỗ ADR-0002 đã đặt phép
kiểm anh em của nó.

## Hệ quả

- Agent ngoài bốn vai không mở được gate, ở cả chiều ghi lẫn chiều replay: gate ma không vào được sổ của ai.
- Thêm một vai mở gate về sau = thêm một dòng vào `REQUEST_ACTORS` của công ty đó. Quên thì `PermissionError`
  nổ ngay ở call site chứ không âm thầm — chọn ném ở chiều ghi chính là để có tính chất này.
- Bản ghi cũ trong `company.sqlite`/`studio.sqlite` do vai ngoài danh sách tạo (nếu có) sẽ **không** dựng lại
  nữa. Rà bốn vai từ chính call site nên không có bản ghi thật nào rơi; suite của cả hai công ty là phép đo.
- `HumanGate` (không bền vững) **không** đổi: nó không có bus, không có khái niệm actor của envelope. Luật này
  thuộc về lớp có bus.

**Một fixture bịa bị lộ.** `platform/console/tests/conftest.py` dựng gate `publish` với `created_by="publisher"`, nhưng
`publisher` chưa từng mở gate nào: gate `publish` do `desk` mở (`studio/orchestrator.py`), và tên `publisher`
chỉ xuất hiện đúng một lần trong lịch sử — chính commit tạo fixture ấy (#91). Đã sửa fixture về `desk` thay vì
nới allowlist để chiều nó: nới allowlist cho một cái tên không có thật là cấp quyền cho một vai không dùng.

## Liên quan

- `docs/adr/0002-gate-request-tin-actor-cua-bus.md` — nửa thứ nhất (PR #212), nơi ghi việc hoãn gói này.
- `docs/adr/0005-gate-request-tu-choi-created-by-rong.md` — `created_by` rỗng (PR #199).
- `platform/xagents-core/src/xagents_core/gate_cli.py` — `REQUEST_ACTORS`, `_request_actor_allowed()`.
- `companies/software-company/src/company/gate_cli.py` — danh sách của company. (Sửa 2026-09-12 khi đối chiếu audit
  A4: dòng gốc còn trỏ `Studio-creators/src/studio/gate_cli.py` — công ty `studio` đã chuyển sang repo riêng từ
  #259, đường dẫn đó không còn tồn tại trong repo này; nội dung "Quyết định"/"Hệ quả" ở trên vẫn khớp mã thật.)
