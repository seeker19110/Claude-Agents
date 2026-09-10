# ADR-0040: Production `deploy` skipped thì không giao hàng — thu hẹp quyết định 5 của ADR-0039

Trạng thái: Proposed · Ngày: 2026-09-10 · Thu hẹp phạm vi của ADR-0039 quyết định 5, không đảo ngược nó.
Chưa cài — xem "Đã thử và dừng lại" cuối file trước khi lấy quyết định 2 làm code.

## Bối cảnh

ADR-0039 cố ý để `deploy_release()` giữ `status=deployed` khi không thể xác minh máy (thiếu `runtime` trong spec,
thiếu file compose, thiếu worktree tích hợp) — gọi là **"skipped: đường lùi, giữ nguyên hành vi cũ"** — để một
repo đang chạy không gãy khi dự án chưa khai đủ (`tests/test_deploy_release_fsm.py` phần "skipped"). Quyết định
đó đúng cho **staging**: staging là nơi QA hồi quy, `skipped` không tự nó gây hậu quả không đảo ngược được.

Nhưng `_act_production_deploy_or_rollback` (`orch/release_fsm.py:278`) chỉ đọc `status == "deployed"` để gọi
`_deliver()` — tag phiên bản, fast-forward nhánh `company/release`, mở gate nghiệm thu cho khách ký. Nó không
đọc `evidence.deploy.skipped`. Kết quả: một release production thiếu `runtime` (hoặc thiếu compose, thiếu
worktree) vẫn mang `status=deployed` từ ADR-0039 quyết định 5, và `_deliver()` tag + giao hàng như thể có container
thật đang chạy — đúng hình dạng "389 test pass, 0 điểm vào" mà ADR-0029/0039 đã bỏ công dập ở staging, nhưng lọt
qua ở production vì `_deliver` không kiểm evidence.

Khác biệt cốt lõi: `skipped` ở staging là trạng thái tạm, sửa được (khai `runtime` rồi chạy lại). `skipped` ở
production dẫn tới **hành động không đảo ngược** — tag, fast-forward, mời khách ký nghiệm thu trên thứ chưa ai
xác minh chạy được.

## Quyết định

1. **Không đổi `deploy_release()` / ADR-0039 quyết định 5.** Staging vẫn `skipped` → `status=deployed`, hành vi
   giữ nguyên, ba test hiện có (`test_khong_co_compose_file_thi_skipped_va_giu_hanh_vi_cu`,
   `test_khong_khai_runtime_thi_skipped_noi_ly_do`, `test_khong_co_repo_thi_skipped_noi_ro_worktree`) không đổi.

2. **`_deliver()` thêm một điều kiện chặn**: trước khi tag/giao hàng, đọc `env.payload["evidence"]["deploy"]`.
   Có khoá `skipped` (nghĩa là chưa xác minh được máy thật) → **không** tag, không fast-forward, không mở gate
   nghiệm thu. Ghi `delivery.skipped` vào audit-log kèm lý do skip, và mở gate `escalation` (cùng khuôn với
   `deploy_failed` — RC không đi tiếp được thì phải có người được hỏi, không được nằm im).

3. **Chỉ áp cho production** (`_deliver` vốn chỉ chạy trên nhánh `env=="production"` qua guard của
   `production_deploy_or_rollback`, `orch/release_fsm.py:303`) — không cần thêm điều kiện env vì `_deliver` không
   bao giờ nhận event staging.

4. **Người đã ký gate `release` (Gate 3) không bị coi là "đã tự khai sai"** — gate ký dựa trên `status=deployed`
   của route trước khi biết evidence chi tiết; `_deliver` là lớp kiểm SAU cùng nguyên tắc với gate đã có
   (`o.gate.is_approved` không tin lời khai `deployed` của agent — đây thêm một tầng không tin `skipped`).

## Hệ quả

- Release production thiếu `runtime`/compose/worktree giờ dừng đúng chỗ (`_deliver`), không lặng lẽ trôi qua
  thành một bản giao có tag nhưng không ai xác minh chạy được.
- `gate_brief`/`console` đọc `delivery.skipped` như một tín hiệu vận hành thật (khác `delivery.error` — lỗi
  workspace — và `delivery.skipped` cũ do thiếu nhánh tích hợp).
- Dự án `legacy: true` hay `kind` khác `application` vẫn có thể rơi vào nhánh này ở production nếu quên khai
  `runtime` — đây là điểm cố ý: production giao hàng luôn cần bằng chứng máy, bất kể `kind`/`legacy` (khác
  `smoke()` ở staging, vốn tha `library`/`legacy` — ADR-0031 K1.5 kịch bản B — vì staging chỉ là kiểm, chưa giao
  gì cho khách).

## Đo hai chiều (ghi trong commit khi cài)

- Production `deploy_release` trả `evidence.deploy.skipped` (vd. runtime rỗng dù đã qua Gate 3) → `_deliver`
  không tag, `orch.delivered == {}`, gate `escalation` mở, `delivery.skipped` có trong audit-log.
- Bỏ điều kiện mới trong `_deliver` (coi `skipped` như `deployed` bình thường) → ca trên ĐỎ: tag vẫn được tạo,
  `orch.delivered` không rỗng.
- Ba test staging "skipped" ở `test_deploy_release_fsm.py` không đổi — vẫn xanh nguyên trạng, chứng minh quyết
  định 5 của ADR-0039 không bị đảo ngược, chỉ bị thu hẹp phạm vi tác dụng.

## Đã thử và dừng lại (2026-09-10)

Cài quyết định 2 (thêm điều kiện trong `_deliver`, test đỏ→xanh, ruff/mypy sạch, 13/13 test của
`test_deploy_release_fsm.py` xanh) rồi chạy `uv run pytest -q -n auto --cov` toàn package: **10 test đỏ**, không
liên quan tới compose/runtime — chúng đo cơ chế git thuần (tag, push, rollback, mở PR) qua fixture dùng chung
`_orch_da_giao` (`tests/test_coverage_100.py:121`) và tương đương trong `tests/test_delivery_real.py`. Cả hai
**chưa từng khai `runtime`** trong spec giả — từ trước ADR-0039 tới giờ chúng ngầm định `status=deployed` (dù
`evidence.deploy.skipped`) là đủ để giao hàng, vì lúc viết chúng compose/runtime chưa tồn tại.

Tức là quyết định 2 đúng về mặt hành vi (production skipped không nên giao hàng), nhưng **đổi một khế ước ngầm
mà gần như toàn bộ mặt test giao hàng/rollback/PR đang dựa vào**, không chỉ ba test staging đã liệt kê ở trên.
Vá tiếp (thêm `runtime` vào từng fixture) là khả thi nhưng đổi phạm vi từ "sửa một hàm" thành "sửa lại giả định
nền của ~10 test có sẵn" — đúng ranh giới AGENTS.md luật bắt buộc 6 nói dừng lại hỏi người, không tự ý mở rộng.

**Code đã revert về nguyên trạng** (`git checkout -- src/company/orch/release_fsm.py
tests/test_deploy_release_fsm.py`). Người kế tiếp cầm ADR này cần quyết trước khi code:
1. Sửa cả `_orch_da_giao` và fixture tương đương trong `test_delivery_real.py` để khai `runtime` — giữ đúng tinh
   thần quyết định 2, nhưng là một PR lớn hơn ("~30-40 phút" theo ước lượng ban đầu, thực tế có thể hơn vì số
   test chạm tới rộng hơn 10 ca đã thấy — chưa rà hết `test_mcp_bridge.py`/`test_review_fixes_2026_09.py` cũng đỏ
   cùng lượt, có thể không liên quan quyết định 2 hoặc có liên quan gián tiếp qua số liệu README/test count).
2. Thu hẹp điều kiện chặn: chỉ áp khi `deploy_fn` thật được cấu hình (môi trường đã bật compose) — giữ nguyên
   toàn bộ test git thuần, đổi ít hơn nhưng vòng bảo vệ hẹp hơn (dự án bật compose nhưng runtime rỗng vẫn lọt).
