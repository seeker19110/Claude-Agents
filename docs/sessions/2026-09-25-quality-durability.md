# 2026-09-25 — gia cố chất lượng và phục hồi, cùng PR #335

Người dùng yêu cầu rà phần thiếu và bổ sung ngay, repo đích Claude-Agents.
Base PR: 3624a8b1013a2092e357ebc6fac0ab4b31e29b67, tree 338abbde26100a1bc72d2c65e0721150be2f6721.
Bản source cục bộ dựng từ archive đã đính kèm, git write-tree khớp nguyên tree trên GitHub.

## Đã tìm thấy và xử lý

CI run 36078539727 thất bại ở console trên cả 3 chân OS/Python do thêm pytest.skip trong test symlink.
Không còn “đang chạy”: company/core của run đó đã đạt. Sửa test symlink thật/fallback không bỏ kiểm tra,
không tăng TRAN_SKIP hoặc giảm coverage.

Hai kết nối SQLite cùng register một run tái hiện UNIQUE constraint failed. Thêm BEGIN IMMEDIATE trước
read/compare/write. transition mới đọc spec/state, kiểm expected_count, áp FSM và ghi trong một giao dịch.
Duplicate cùng nghĩa ACK, khác JSON (kể cả True và 1) collision. NaN/Infinity, identity rỗng, thời gian thiếu
múi giờ và run event mang task_id bị từ chối. append low-level cũ giữ tương thích, không dùng cho runtime mới.

commit_quality_result nối assessor thật vào journal thật, giữ result + receipt + bindings + request hash,
không giữ key hoặc raw command output. Spec/graph ghim, attempt phải được start, concurrent cancel/retry
bị CAS chặn. Gửi lại sau expiry chỉ đọc lại quyết định cũ, không phát hành chứng nhận mới.

## Bằng chứng local trong lượt này

TDD atomic: 15 fail trước code (gồm race register thật); validation bổ sung 8 fail trước sửa.
TDD quality commit: import thiếu QualityBindings trước triển khai. Skip guard: 1 fail/4 pass trước sửa,
5 pass sau sửa; hai nhánh symlink đều có assertion.
Core toàn package: 567 passed, 2706 statements +728 branches, 100% cả dòng/nhánh.
Nhóm company quality + quality_floor + roles: 180 passed, hai module quality 439 statements +168 branches, 100%.
Không phải chứng nhận sản phẩm chạy thật hoặc toàn bộ khả năng tự chủ H3–H7.

Lệnh gate core đúng repo được thử với UV_OFFLINE=1: dừng do pydantic 2.13.5 chưa có trong cache;
ruff/mypy/xdist của lockfile không cài sẵn. Không giả kết quả lint; CI trên head mới là cổng toolchain đầy đủ.
Không sửa agents/skills/generated recordings, không thêm dependency hoặc thay CI/branch protection.
Không có reviewer subagent độc lập trong phiên; review độc lập chưa được tuyên bố đạt.

## Bàn giao

Tiếp tục cùng PR #335, không mở PR cạnh tranh, không tự merge trước bằng chứng CI/review.
Chưa bật daemon, lease worker, công cụ browser, production hay đổi quyền người dùng.
Giữ contract/trust store/journal ngoài quyền worker. API mới không bảo vệ được caller tự ghi SQL/raw append.
