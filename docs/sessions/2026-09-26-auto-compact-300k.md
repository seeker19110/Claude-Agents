# Phiên 2026-09-26 — auto-compact 300k

PR: [#352](https://github.com/seeker19110/X-Agents/pull/352).
Nhánh: `feat/claude-auto-compact-300k-20260926`.
Nền: `b50a29d64bb248eba4dc797cb53879a1442b040f`.
Commit cấu hình và test: `be8afd530393499e0ff48d52026dd257fd2aa8ec`.

## Yêu cầu và phạm vi

Chủ dự án chốt cửa sổ auto-compact native 300000 token mỗi phiên và yêu cầu tích hợp, tạo PR cho phiên.
Thêm autoCompactEnabled và CLAUDE_CODE_AUTO_COMPACT_WINDOW vào project settings; thêm Compact Instructions,
hướng dẫn kiểm tra/hoàn tác và 7 test cấu hình. Không đổi runtime, fit/prune, ngân sách, gate, sandbox,
permissions, hooks hoặc cấu hình cá nhân. Không tự merge PR.

PR dùng ngoại lệ `no-changelog` có sẵn trong PR policy cho cấu hình công cụ phát triển/tài liệu; CHANGELOG.md
gốc không bị ghi đè. Nội dung thay đổi được ghi tại đây và trong PR. Không miễn kiểm thử code hay coverage.

## Bằng chứng đã đo trong phiên

Không clone được từ môi trường thực thi: `Could not resolve host: github.com`. Đọc file qua GitHub connector,
dựng tập file để chạy kiểm tra cấu hình offline, không phải toàn bộ checkout. Hai file nền khớp Git blob SHA:

- `.claude/settings.json`: `9bcaf43b9fe4c41d8ff2fa0a5374b7c47dc83698`.
- `CLAUDE.md`: `b3278f0d1272300c14846f799c436ecc65867723`.

Lệnh: `python -m pytest -q platform/console/tests/test_auto_compact_config.py`.

| Phép đo | Kết quả |
|---|---|
| Test trước sửa | 4 failed, 3 passed — thiếu cấu hình bật, cửa sổ 300000, chỉ dẫn compact, hướng dẫn |
| Test sau sửa | 7 passed |
| Đổi cửa sổ thành chuỗi 300k | 2 failed, 5 passed |
| Tắt autoCompactEnabled | 2 failed, 5 passed |
| Xoá hook bảo vệ git | 1 failed, 6 passed |
| Khai giả CLAUDE_CODE_MAX_CONTEXT_TOKENS | 1 failed, 6 passed |
| Xoá Compact Instructions | 1 failed, 6 passed |
| Khôi phục toàn bộ thay đổi | 7 passed |
| compileall cho test mới | exit 0 |
| So sánh permissions/hooks với nền | Không đổi; CLAUDE.md chỉ thêm mục cuối |

Năm đột biến là thay đổi tạm để thử bộ test, đã khôi phục trước khi tạo commit. Không đưa cấu hình sai lên nhánh.

## Việc chưa xác nhận

Chưa chạy cổng đầy đủ `scripts/dev-task.sh gate console`, ruff/mypy hoặc toàn workspace trong môi trường này.
CI của commit cuối phải được kiểm riêng; không lấy CI xanh của commit nền làm bằng chứng cho PR.
Chưa chạy Claude Code thật và chưa quan sát auto-compact tự kích hoạt. Cần xác nhận phiên bản, cấu hình hiệu
lực và khả năng tiếp tục đúng task theo `docs/AUTO-COMPACT.md`. Test cấu hình offline không chứng minh hành vi
native hay bảo đảm không mất thông tin.

Trạng thái bàn giao: PR nháp, chưa báo sẵn sàng merge, không bật auto-merge. Chỉ nạp cấu hình này khi phiên
Claude Code thực sự mở checkout chứa thay đổi; main và máy cá nhân chưa được cập nhật bởi phiên này.
