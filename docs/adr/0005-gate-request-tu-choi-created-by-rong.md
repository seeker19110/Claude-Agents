# ADR-0005: `HumanGate.request()` từ chối `created_by` rỗng/None

## Bối cảnh

`xagents_core.gates.HumanGate` (K3.7, ADR-0001) bảo vệ four-eyes ở `decide()`:

```python
if req.created_by and req.created_by == by:
    raise PermissionError("người duyệt phải khác người tạo (four-eyes)")
```

Điều kiện `req.created_by and ...` là allowlist ngược đời: nó CHỈ kiểm four-eyes khi `created_by` đã có giá
trị thật (truthy). Nếu `req.created_by` là `None` hoặc chuỗi rỗng/toàn khoảng trắng — dù do quên truyền, do
bug ở call site, hay do cố ý — điều kiện ngắn mạch ở vế đầu, `decide()` bỏ qua hoàn toàn kiểm tra four-eyes,
và bất kỳ ai gọi `decide()` cũng tự duyệt được gate mình vừa tạo.

`request()` không kiểm gì cả: nó nhận thẳng `GateRequest` bất kể `created_by` là gì. Đây là lỗ hổng nằm ở
nơi tạo dữ liệu (`request()`), không phải nơi dùng dữ liệu (`decide()`) — sửa `decide()` một mình vẫn để
`request()` chấp nhận gate không có chủ, và một bug ở call site tương lai (quên `created_by`) sẽ vô hiệu hoá
four-eyes ngay lập tức mà không có lỗi nào báo.

Rà `GateRequest(` trong `companies/software-company/src`, `Studio-creators/src`, `platform/xagents-core/src`: mọi call site thật
hiện có (`delivery.py`, `demo.py`, `gate_cli.py`, `orch/*.py` của company; `gate_cli.py`, `orchestrator.py` của
studio) đều đã truyền `created_by` có giá trị. Lỗ hổng là pre-existing (có trước K3.7, xác nhận bằng `git show`
ở commit trước #198) và chưa bị khai thác qua các call site đang có, nhưng không có gì chặn call site tương
lai — hoặc gọi trực tiếp `HumanGate.request(GateRequest(...))` từ script/test — bỏ sót `created_by`.

## Quyết định

`HumanGate.request()` bắt buộc `req.created_by` phải là chuỗi khác rỗng sau khi `.strip()` — allowlist mặc
định từ chối (default-deny), không phải blocklist các giá trị xấu đã biết. `None`, `""`, và chuỗi toàn khoảng
trắng đều bị từ chối bằng `PermissionError`, cùng loại lỗi mà `decide()` đã dùng cho vi phạm four-eyes, vì đây
là cùng một bất biến bảo mật nhìn từ hai phía (ai tạo / ai duyệt phải khác nhau) chứ không phải hai lỗi khác
loại.

Kiểm tra đặt ở `request()` — nơi gate được tạo ra — thay vì chỉ vá lại điều kiện ở `decide()`, để lỗi lộ ra
sớm nhất (khi tạo gate sai) thay vì chờ tới lúc duyệt mới phát hiện, và để không có đường nào tạo được một
`GateRequest` "mồ côi" nằm trong `pending`.

## Hệ quả

- Mọi call site gọi `HumanGate.request()` — kể cả call site tương lai — bắt buộc phải truyền `created_by` là
  actor thật (tên người, hoặc định danh agent/role). Rà soát tại thời điểm viết ADR này cho thấy không có call
  site thật nào cần sửa.
- Test hoặc script gọi `HumanGate.request()` trực tiếp mà không set `created_by` sẽ vỡ ngay bằng
  `PermissionError`, thay vì âm thầm tạo ra một gate có thể tự duyệt.
- `decide()` giữ nguyên `if req.created_by and req.created_by == by` — vế `req.created_by` giờ luôn truthy
  (được `request()` đảm bảo), nên biểu thức tương đương `if req.created_by == by`; không đổi để diff nhỏ và vì
  `request()` là nơi chịu trách nhiệm chính.

## Liên quan

- ADR gốc `docs/adr/0001-loi-chung-xagents-core.md` — hợp nhất `gates.py` vào `xagents_core` (K3.7, PR #198).
- `platform/xagents-core/src/xagents_core/gates.py` — `HumanGate.request()`, `HumanGate.decide()`.
- `platform/xagents-core/tests/test_gates.py` — ca test four-eyes.
