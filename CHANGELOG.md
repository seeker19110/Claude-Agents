# Changelog

Theo [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/). Mỗi PR merge vào `main` một dòng, scope trong
ngoặc, số PR ở cuối. Chi tiết và lý do nằm trong PR và ADR; ở đây chỉ trả lời "đã đổi gì, khi nào".
Phiên bản: repo chưa gắn tag phiên bản cho chính nó (tag `v*` là của sản phẩm khách, ADR-0027) — nhóm theo ngày.

## Chưa phát hành

- docs(gateway): 3 ADR (xoay vòng, giữ cổng, ranh giới bảo mật) + bộ khung CLAUDE/TRAPS/CODEMAP/ARCHITECTURE (E4) (#101)
- chore: đợt 0 đặc tả nâng cấp — CHANGELOG đủ số PR, gitignore `*.yaml.bak*`, mốc lịch sử repo trong ARCHITECTURE, CI `PR policy` bắt PR phải có dòng CHANGELOG (nhãn `no-changelog` để miễn) (#98)
- fix(company): `watch()` không nuốt `ReloadRequested` thành `tick_error` (#95)
- fix(company): audit `invalid_output` ghi kèm lời agent — "không sửa file nào" phải nói vì sao (#94)
- fix(company): delivery-lead v10 — kế hoạch là ticket trong `items` ngay lượt planning; trả rỗng để chờ duyệt là bị từ chối (#93)
- fix(company): duyệt escalation "kế hoạch bị từ chối" = delivery-lead lập lại kế hoạch, không "reopen" ticket ma (#92)
- feat(company): sổ Ruling — agent tự quyết ngoài bốn gate, ghi decision/why/cost_if_wrong vào audit; `status`, CLI `rulings`, mọi hồ sơ gate hiện sổ (ADR-0030) (#97)
- docs: đặc tả nâng cấp tháng 9/2026 — sáu đợt, 40 mục, bốn câu hỏi đo "hoàn thiện" (`docs/DAC-TA-NANG-CAP-2026-09.md`) (#96)
- docs: bộ khung repo 9 file — AGENTS/CLAUDE/TRAPS, ARCHITECTURE/CODEMAP/CHANGELOG, task pack/prompt sheet/session log; mỗi package con có CLAUDE/TRAPS/CODEMAP/ARCHITECTURE riêng (#91)
- feat(company): `deployed` ở staging phải qua smoke do orchestrator tự chạy — lời khai thành bằng chứng (ADR-0029) (#90)
- feat(company): `trace <id>` — dòng thời gian một ticket/release từ intake tới deploy (B7 đặc tả nâng cấp) (#99)

## 2026-09-06

- fix(company): tool ghi được `.env.development/.env.example/.env.sample/.env.test` — file mặc định công khai (#88)
- fix(company): reviewer và security-engineer có tool chỉ-đọc khi chấm PR — diff bị cắt thì đọc file, không BLOCK mù (#87)
- docs(git): mỗi phiên agent một worktree riêng, không dùng chung một clone (#86)
- docs(company): đối chiếu superpowers và các skill thiết kế web với quy trình công ty (#85)
- fix(company): HEAD là commit WIP mà lượt này không sửa gì → PR từ HEAD, không invalid_output (#84)
- feat(company): orchestrator tự khởi động lại khi mã nguồn đổi (`run --watch`) (#83)
- fix(company): lần giao lại giữ việc dở của lượt trước thành WIP, không vứt (#82)
- fix(company): agent lỗi trên event không phải ticket → duyệt escalation là chạy lại event, không "reopen" ticket ma (#81)
- fix(company,console): huỷ RC đã bị bản giao vượt qua; lượt production nhận bằng chứng; console khoá duyệt escalation lý do ngắn (#80)
- docs(company): báo cáo "bản giao đầu tiên không chạy được" — 6 đề xuất (#79)
- fix(company): sweep RC `pending_human` không gate ở mỗi nhịp (#78)
- fix(company): release-engineer tự dừng → gate escalation; duyệt là chạy lại ngay (#77)
- feat(console): lớp "sự thật giao hàng" — phễu release, bế tắc im lặng, quyết định chưa áp (#76)
- fix(company): review trên release lấy `ticket_id` từ ROUTE (#75)
- fix(company): CLI publish suy key: `change_id` trước `project_id` (#74)
- fix(company): `run()` nạp event tiến trình khác ở mọi vòng (#73)
- fix(company): `env`/`release_id` của release-event là của ROUTE (#72)

## 2026-09-05

- fix(company): `redeploy` cần client thật (#71); lệnh `redeploy <REL-xxx>` (#70)
- fix(company): Gate 3 chỉ gác production — gỡ deadlock giao hàng (#69)
- ci(software-company): pytest-xdist `-n auto` — job unit 346 s → ~100 s (#68)
- fix(company): giữ hint của người qua các lượt retry; ưu tiên mã nguồn khi cắt diff (#67)
- fix(company): trạng thái "đã tích hợp" sống sót qua restart (#66); duyệt escalation đánh dấu XONG khi code đã ở nhánh tích hợp (#65)
- fix(company): release bị chặn không tự đá ticket đã merged về rework (#64); xung đột merge không đốt retry nội dung (#63)
- fix(company): `CLI_NO_TOOL_TURNS` 3 → 6 (#62); `claude -p` không tool cần > 1 lượt (#60); phân loại thoát mã 1 theo thông điệp (#58); schema union → anyOf (#56)
- ci: guard đối chiếu file ruleset với rule đang áp (#61)
- fix(company): không mở gate escalation trùng sau khi mở lại bus (#57); duyệt escalation do review lỗi thì chạy lại review thiếu (#59); task cũ không giao lại sau takeover (#55)

## Trước 2026-09-05

- ci: canh gác bảo vệ nhánh `main` (#40); docs: runbook trực ban và dừng khẩn (#47); test: phủ 100% dòng cả bốn package (#48)
- feat(company): ADR-0028 vai viết test độc lập (#45, #50); docs: nhập Hallmark vào bốn skill giao diện (#49)
- fix(studio): TTS nhận đúng tiếng Việt trên Windows (#54); fix: số liệu README khớp thực tế (#46)
- Lịch sử đầy đủ: `git log --oneline main`.
