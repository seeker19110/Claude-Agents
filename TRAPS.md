# TRAPS.md — bẫy đã mắc trong repo này

Mỗi mục là chuyện **đã xảy ra thật**, có ngày, có PR. Không phải danh sách "nên tránh" chung chung. Đọc trước khi
sửa lỗi lạ: phần lớn lỗi mới là một thể hiện khác của khuôn cũ. Bẫy riêng của từng package nằm ở `<pkg>/TRAPS.md`.

Cách dùng: gặp triệu chứng → tìm khuôn ở §1 → xem cách rà → mới đi sửa. Sửa xong → thêm mục mới ở đây nếu là bẫy mới,
hoặc thêm ngày/PR vào mục cũ nếu là lần tái phát.

## 1. Bốn khuôn lỗi lặp lại (16 lỗi phiên 2026-09-04, 0 lỗi nghiệp vụ)

**Khuôn 1 — chế độ hỏng không tự khai báo.** Một tình huống riêng bị gói vào thông điệp chung, nên người và hệ
thống đều xử lý sai: timeout 120s báo `HTTP 500` thân rỗng; hết hạn mức đầu ra báo "không phải JSON"; structured
output trả qua `tool_calls` mà client đọc `content` rỗng **với mã 200**; hạn mức 82 giờ bị che bằng cooldown mặc
định 1 giờ. Hệ quả là retry vô ích, chờ thừa, đốt quota. *Cách rà*: mọi nhánh `except`/`else` chung — hỏi "nếu
là trường hợp X thì thông điệp này có nói X không?".

**Khuôn 2 — state chỉ sống trong RAM, mất khi mở lại bus.** Không hỏng ồn ào; dự án đứng im trong khi `status`
xanh: lệnh thử-lại trong `self.queue`, trạng thái `blocked` suy từ số retry, `Supervisor.actions` bị replay nuốt.
*Chốt chặn*: `test_moi_trang_thai_nghiep_vu_song_sot_qua_restart` trong `software-company/tests/test_orchestrator.py`.
*Cách rà*: mỗi thuộc tính mới của orchestrator — "mở lại bus thì dựng lại từ đâu?".

**Khuôn 3 — khoá chống-trùng nuốt lần hai HỢP LỆ.** `self.once`, `project_paused`, `_escalated_once`,
`partial[event_id]`: ticket bị chặn lần hai sinh đúng khoá lần một → không gate nào mở; `gate:{sid}` dùng chung
cho `remind` và `overdue`; `project_paused` không bao giờ gỡ → trần ngân sách chặn đúng một lần cả vòng đời. Rà
2026-09-04: 7 khoá, 3 hỏng. *Cách rà*: grep `in self.once` / `not in self.<set>`, hỏi "tình huống này có lặp lại
hợp lệ không?" — nếu có, khoá phải mang **giai đoạn/thế hệ**, không chỉ danh tính. Gỡ cờ thì coi chừng bật lại ngay.

**Khuôn 4 — event cũ trong hàng đợi phát lại như mới sau resume/restart.** Hàng đợi giữ event theo danh tính,
không theo thế hệ: task retry cũ + PR cũ nằm đó (hoãn vì paused), duyệt gate → phát lại → backend chạy trên worktree
đã commit → "không sửa gì" ×3 → blocked → escalation mở lại. QLKH-004 mở lại 7 lần, 10.7M token (PR #55). *Cách rà*:
"event này còn đúng với trạng thái HIỆN TẠI của chủ thể không?". *Hệ quả vận hành*: sửa tay thì **commit + takeover
trước, duyệt gate sau**.

Nguyên tắc rút ra: *không đường nào được kết thúc trong im lặng, và không đường nào được lặp mãi trong im lặng.*
Cơ chế cứu thường ĐÃ CÓ, chỉ là điều kiện kích hoạt quá hẹp (`_stall` chỉ lo `RESEARCH_TOPICS`, `_rework_after_error`
chỉ lo `tools="rw"`). Cái rơi ra ngoài luôn rơi vào im lặng.

## 2. Bẫy chẩn đoán (của người sửa, không phải của hệ)

| Bẫy | Đã xảy ra | Lần sau |
|---|---|---|
| **Suy từ thông điệp lỗi** | 2026-09-04: chẩn đoán sai 6 lần liên tiếp, mỗi lần đều nghe hợp lý; đúng ở mọi lần dựng phép thử đối chứng | Tái hiện lượt thật, tách từng biến, so một con số đặc trưng với lượt thật. Kết quả RỖNG chưa chắc là KHÔNG CÓ — có thể hỏi sai chỗ |
| **Test xanh cả hai chiều** | 3 test "xanh" mà vô dụng: kịch bản không đi qua nhánh sửa; đúng-sai theo nền tảng (đồng hồ Windows thô 15ms); test bất biến chạy vòng đời sạch | Tắt bản sửa → phải đỏ. Liệt kê rõ kịch bản KHÔNG đi qua |
| **Ép agent làm việc nó không có tool** | 4 vòng rework bắt reviewer xoá một file rác; bộ tool không có `rm`/`git rm`; agent không nói "tôi không xoá được" | Thất bại lặp ở đúng một loại thao tác → mở `tools.py` đọc allowlist TRƯỚC khi chỉnh hint |
| **Sửa một lỗi rồi dừng** | PR #30 sửa một khoá `once`; rà cả họ → thêm 3 khoá hỏng (#31, #32) | Rút một câu hỏi từ lỗi, áp cho mọi chỗ cùng cơ chế, ghi cả chỗ an toàn |
| **Tin dashboard xanh** | Đêm 2026-09-05: `queue: 0, blocked: [], gates: {}` trong khi 18/19 release không đi đâu; `delivery: {}` nghĩa là chưa giao gì; nhãn `merged` ≠ đã gộp | Hỏi "còn việc nào chạy được không?"; tách sự thật git khỏi nhãn FSM. Ghi nhận thiết kế lại: `console/TRAPS.md` |
| **Bốn gate xanh, sản phẩm không chạy** | 2026-09-06 QLKH: 389 test pass, 25 release, 0 điểm vào — `deployed` là lời khai, `regression-staging` là verdict đọc diff | "Chạy cho tôi xem" trước khi tin. Vá: ADR-0029 smoke do orchestrator chạy (PR #90) |

## 3. Bẫy thao tác git / CI

| Bẫy | Đã xảy ra | Lần sau |
|---|---|---|
| Hai phiên chung một clone | 2026-09-06 15:07: phiên B checkout `main`, commit của phiên A rơi vào `main`, nhánh A rỗng (#86) | `git worktree add` cho mỗi phiên; `git worktree list` trước khi bắt đầu |
| Push sau khi auto-merge đã bật | #77 thiếu sweep, commit rơi khỏi PR, phải mở #78 | `gh pr view --json commits` sau push; hoặc bật auto-merge sau commit cuối |
| Chạy test không `--cov` rồi tin là xanh | CI Linux đỏ coverage (#78) | Chạy đúng lệnh CI: `pytest -n auto --cov` |
| Scope PR hai từ | `fix(company,console)` bị `metadata` chặn (#80) | Một từ, chữ thường |
| Sửa `checklists.md` mà không `make subagents` | `test_ban_dan_xuat_tren_dia_khop_nguon` đỏ (#90) | Sửa nguồn → sinh lại → commit `.claude/agents/` |
| Thêm file test / ADR mà không sửa README | `test_readme_khop_so_lieu_that` đỏ: README ghi 43 file, thực tế 44 | README của software-company/Studio ghi số ca/file test và ADR mới nhất — test đếm lại từ đĩa |
| Thêm job CI mà không nối `needs` của `quality` | Kết quả job không được tính | `quality` là required check bất biến; nối job mới vào `needs` |
| Khởi động lại orchestrator quên lock | Tiến trình mới thoát ngay, tưởng đã restart | Kiểm `company.sqlite.lock` đổi PID và có audit mới. Nay `run --watch` tự khởi động lại (#83) |
| `--db` đặt sau `publish` | `unrecognized arguments` lúc diễn tập dừng khẩn | `--db` đứng TRƯỚC subcommand; `--key` bắt buộc với `supervisor-actions` |
| `status`/`gate_cli` chạy ở gốc repo | Gốc có `company.sqlite` rỗng → nhìn như không có gì | Chạy trong `software-company/` |
| Heredoc chứa `'''`/backtick | Vỡ parse 2 lần | Ghi file scratchpad rồi `python file.py` |
| `git stash`/`checkout` trong lúc `make eval-record` | Bản ghi mang version prompt sai (2026-09-05) | Không đụng file prompt khi đang ghi eval; `RecordingClient` nay chốt version lúc bắt đầu |

## 4. Bẫy vận hành công ty (người trực)

| Bẫy | Đã xảy ra | Lần sau |
|---|---|---|
| Duyệt gate lý do "ok" | 2026-09-06 13:05 → agent nhận hint rỗng | root_cause + decision + hint; console khoá < 20 ký tự (#80) |
| Duyệt nhầm loại gate | Duyệt `escalation` cho REL-xxx tưởng đã giao hàng; chỉ `kind=release` mới deploy | Đọc `kind` và hậu quả trước khi bấm |
| Ghi tay blackboard để mở khoá | Threat-model cũ chặn mọi RC | Đổi qua đúng vai: CR → spec-writer ghi `prd`, security ghi `threat-model` |
| Console mở, orchestrator tắt | Việc giao nằm im | Bật `run --watch` cùng lúc |
| Agent tự dừng `pending_human` không ai xử lý | 10 RC kẹt, status xanh (#77/#78) | Mọi "chờ người" của agent phải mở gate; sweep mỗi nhịp |
| Trường identity do model khai | `env`/`release_id`/`ticket_id` lệch → Gate 3 không mở (#72, #75) | Identity lấy từ ROUTE; model chỉ điền nội dung; audit `*_overridden` |
| Lượt production không thấy bằng chứng staging | Agent nói "chưa qua staging" dù có (#80) | Agent không có tool đọc bus → payload phải mang đủ bằng chứng |
| Từ chối escalation của RC cũ = trả ticket đã giao về làm lại | #80 `_superseded_release` | Hành vi "đóng" phải xét nội dung đã tới khách chưa |
| Reviewer chấm trên diff đã bị cắt mà không biết | security-engineer chặn QLKH-012 vì "thiếu diff" — openapi 804 dòng ăn hết hạn mức | Diff ưu tiên mã nguồn, nói rõ file bị bỏ (#67); reviewer có tool đọc (#87) |

## 5. Cách thêm mục mới

Một bẫy đủ điều kiện vào đây khi: (a) đã xảy ra thật, (b) tốn ít nhất một giờ hoặc một PR, (c) có câu "lần sau"
cụ thể mà người khác làm theo được. Ghi ngày + PR. Mục cũ tái phát thì thêm ngày, đừng tạo mục mới.
