# ADR-0002: `gate.request` tin `env.actor`, không tin `created_by` trong evidence

## Bối cảnh

`audit-log` là topic **MỞ**: mọi actor đều publish được (`OPEN_TOPICS`, `bus.py`). Luật riêng duy nhất của
company là agent không được ghi `action="gate.decide"` — `gate.request` không có luật nào cả, ở cả hai công ty.

Trạng thái gate không lưu riêng: `PersistentGate` dựng lại từ replay `audit-log` (`gate_cli.apply`). Với
`gate.decide`, bản vá 2026-09-09 đã bắt `apply()` đi qua `trusted_decision()` — allowlist mặc định từ chối,
đối chiếu `evidence.by` với `env.actor`, vì "evidence là lời khai của người ghi, `env.actor` mới là thứ bus
thật sự kiểm". Với `gate.request` thì không: `apply()` đọc thẳng `d.get("created_by")` từ evidence.

Hệ quả là four-eyes bị vô hiệu hoá bằng một envelope duy nhất. Actor `human:evil` publish một `gate.request`
mang `created_by="human:a"`; gate vào `pending` với người tạo là `human:a`; rồi chính `human:evil` gọi
`decide(..., by="human:evil")` — `req.created_by != by`, kiểm four-eyes qua, gate được duyệt bởi đúng người đã
tạo ra nó. `COMPANY_GATE_APPROVERS` không cứu được: `human:evil` nằm trong danh sách người duyệt mới làm nổi
việc này, mà đó chính là kịch bản four-eyes sinh ra để chặn (một người duyệt hợp lệ không được tự duyệt việc
của mình). Cùng cách ấy còn dựng được gate ma với `subject_id`/`kind` bất kỳ.

`sc-security` xếp NGHIÊM TRỌNG khi chấm K3.7 (PR #198). Đối chiếu `git show 34c4952:…/gate_cli.py` xác nhận
hành vi có từ trước K3.7 ở cả hai công ty — K3.7 chỉ hợp nhất hai bản giống nhau thành một. Vì thế nó không
được vá trong K3.7 (ngoài phạm vi "hợp nhất module") mà tách thành ADR này. ADR-0005 (`created_by` rỗng bị từ
chối ở `request()`) là **lỗ hổng khác**: ở đó gate không có chủ; ở đây gate có chủ nhưng chủ là bịa.

## Quyết định

`PersistentGate.apply()` lấy `created_by` từ **`env.actor`** khi áp một bản ghi `gate.request`, và bỏ qua
`created_by` tự khai trong evidence:

```python
kw = {**self._request_kwargs(d), "created_by": env.actor}
super().request(self.request_cls(created_at=env.ts, **kw))
```

Ghi đè, không phải "từ chối bản ghi lệch". Hai lý do: (1) đường ghi hợp lệ duy nhất là
`PersistentGate.request()`, ở đó `env.actor` **bằng** `req.created_by` theo dựng, nên ghi đè không đổi gì cho
bản ghi thật; (2) từ chối bản ghi lệch sẽ **đánh rơi gate cũ** trong `company.sqlite`/`studio.sqlite` đã ghi
trước ADR-0005 với `created_by=None` và `actor="human"` — mất gate đang chờ nguy hiểm hơn là ghi nhận nó dưới
tên actor thật đã publish nó. Đây vẫn là default-deny theo nghĩa của `trusted_decision`: giá trị tin được là
giá trị bus kiểm, giá trị tự khai không bao giờ được dùng.

## Hệ quả

- Four-eyes trở lại đúng nghĩa trên đường replay: người publish gate không tự duyệt được gate ấy, kể cả khi
  họ nằm trong `COMPANY_GATE_APPROVERS`. Ca chốt:
  `platform/xagents-core/tests/test_gate_cli.py::test_created_by_lay_tu_actor_that_khong_phai_evidence_tu_khai`
  (đo hai chiều: bỏ bản sửa → đỏ ở `assert g.pending["G9"].created_by == "human:evil"`).
- Gate ma vẫn **dựng được** (topic `audit-log` mở, không thể chặn ở tầng này) nhưng nay mang tên actor đã tạo
  ra nó, nên nhìn thấy được trong `gate_cli list` và console. Chặn hẳn cần ACL producer cho `gate.request`
  giống `gate.decide` — không làm ở đây vì `gate.request` là việc **hợp lệ của agent** (supervisor, ops,
  product đều tạo gate), nên ACL phải là allowlist theo vai, một gói riêng.
- Bản ghi cũ `created_by=None` nay dựng lại thành `created_by="human"` (actor đã publish) thay vì `None`. Với
  gate đã đóng thì không đổi gì; với gate đang chờ, "human" không trùng bất kỳ `by` thật nào nên four-eyes
  không bị nới.
- Sửa ở core một chỗ, cả company lẫn studio hưởng — đúng lý do hợp nhất ở K3.7.

## Liên quan

- `docs/adr/0001-loi-chung-xagents-core.md` §K3.7 — hợp nhất `gates`/`gate_cli` (PR #198).
- `docs/adr/0005-gate-request-tu-choi-created-by-rong.md` — nửa còn lại của cùng bất biến (PR #199).
- `platform/xagents-core/src/xagents_core/gate_cli.py` — `trusted_decision()`, `PersistentGate.apply()`.
- `docs/thi-hanh/k3.7.md` mục "Cố ý không vá trong gói này" — nơi phát hiện được ghi lại và hoãn.
