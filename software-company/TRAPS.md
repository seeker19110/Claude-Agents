# TRAPS.md — bẫy riêng của software-company

Bốn khuôn lỗi chung và bẫy thao tác ở `../TRAPS.md`. Ở đây là chỗ cụ thể trong package này đã cắn người.

## Orchestrator / vòng lặp

| Bẫy | Đã xảy ra | Cách rà / chốt chặn |
|---|---|---|
| `poll()` chỉ khi hàng đợi rỗng | Quyết định gate nằm im khi công ty bận (#73) | Mọi vòng lặp dài nạp đầu vào ngoài ở mỗi nhịp |
| `partial[event_id]` nuốt lần gọi lại có chủ ý | Ký lại Gate 3 chỉ chạy được vì tình cờ vừa restart | `_recall(agent, env)` trước khi gọi lại chủ ý |
| Event cũ phát lại sau takeover | QLKH-004 mở lại 7 lần, 10.7M token (#55) | `_superseded`: `tasks` chỉ khi ticket còn `dispatched`; `pull-requests` chỉ khi là latest |
| `_rehydrate` đếm `gate.decide` chưa xử lý | Gate escalation trùng cho việc vừa duyệt (#57) | Phân biệt "đã thấy trong log" và "đã xử lý" |
| RC `pending_human`/`failed` không có route tiếp | 10 RC kẹt, status xanh (#77/#78); smoke failed (#90) | Mọi trạng thái "chờ người" mở gate; sweep mỗi nhịp; `_check_paused_releases` |
| Gate 3 gửi cho cả staging | release-engineer từ chối staging vì `gate_release=false` → 18/18 RC chết (#69) | Gate 3 chỉ gác production; `tests/test_staging_khong_doi_gate3.py` |
| Từ chối escalation RC cũ → ticket đã giao về rework | #80 | `_superseded_release` xét nội dung đã tới khách chưa |
| Xung đột merge đốt retry nội dung | Ticket `blocked` vì merge, không vì code (#63) | Bộ đếm riêng, ngưỡng riêng |
| Reset worktree vứt việc dở | 40 lượt tool viết devserver dở bị xoá, lần 2 lại từ 0 (#82) | `keep_wip` → commit WIP; HEAD là WIP mà lượt này không sửa → PR từ HEAD (#84) |

## Bằng chứng và lời khai

| Bẫy | Đã xảy ra | Chốt chặn |
|---|---|---|
| `deployed` là lời khai | 25 release, 0 điểm vào (2026-09-06) | ADR-0029 smoke do orchestrator chạy; `smoke.unverified` khi không có `runtime` |
| `env`/`release_id`/`ticket_id` do model khai | Gate 3 không mở (#72, #75) | Identity từ ROUTE; audit `*_overridden` |
| Lượt production không thấy staging/QA | "chưa qua staging" dù có (#80) | `_release_evidence` vào payload |
| Diff bị cắt mà reviewer không biết | security chặn QLKH-012 "thiếu diff" — openapi 804 dòng | `diff()` xếp mã nguồn trước, nói rõ file bị bỏ (#67); reviewer có tool đọc (#87) |
| `local_checks` pass giả từ lệnh không liên quan | frontend PR "pass" bằng ruff+pytest | `stacks.py` theo stack; không nhận ra stack → `unverified` (ADR-0013) |
| Test xanh trước khi có code | TDD chỉ là lời dặn | test-author lượt mù (ADR-0028); `tests_green_before_code` audit |

## Prompt / eval

| Bẫy | Đã xảy ra | Chốt chặn |
|---|---|---|
| Stash/checkout prompt trong lúc `eval-record` | Bản ghi v11, prompt v12 (2026-09-05) | `RecordingClient` chốt version lúc bắt đầu |
| Ghi đè cả file recording khi một ca lỗi | Mất ca đang tốt vì sự cố không liên quan | `save()` gộp, không ghi đè |
| Điểm chấm eval dao động | Một lần đỏ chưa phải hồi quy | CI chỉ đỏ khi bản ghi thiếu/lệch, không đỏ vì điểm |
| `claude -p` từ chối schema union ≥ 2 kiểu | Lỗi trước khi gọi model (#56) | Chuyển thành `anyOf` cho `--json-schema` |
| `claude -p` không tool cần > 1 lượt | `error_max_turns` ở effort low (#60, #62) | `CLI_NO_TOOL_TURNS = 6` |
| Prompt tĩnh nuốt ngân sách | Skill nhồi > 50% `budget_tokens_per_task` | `make assetbudget` |
| Sửa `checklists.md` không sinh lại subagent | `test_ban_dan_xuat_tren_dia_khop_nguon` đỏ | `make subagents`, commit `../.claude/agents/` |

## Vận hành

| Bẫy | Đã xảy ra | Lần sau |
|---|---|---|
| `status` xanh vì rỗng | `queue: 0, blocked: [], gates: {}` — 18/19 release chết | Hỏi "còn việc nào chạy được không"; xem `delivery`, phễu release trên console |
| `delivery: {}` | Nghĩa là chưa từng giao — nhìn suốt đêm không nhận ra | Console nay hiện "đã giao: n/m"; ở CLI đọc `metrics` |
| Nhãn `merged` ≠ đã gộp | 14/14 có merge commit, bảng hiện 4 `merged` | `merged` là nhãn FSM (sau staging deployed); sự thật git ở audit `integration.merged` |
| Ghi tay blackboard để mở khoá threat-model | Agent đọc blackboard chứ không đọc quyết định người | CR → đúng vai ghi đúng namespace |
| Duyệt gate trước, sửa tay sau | Backend dispatch lại, `workspace_reset` xoá phần chưa commit | Commit + takeover trước, duyệt sau |
| `--db` sau `publish`; thiếu `--key` | Lỗi lúc diễn tập dừng khẩn | `--db` trước subcommand; `supervisor-actions` cần `--key` |
| Agent không có tool xoá file | 4 vòng rework vô ích | Đọc `tools.py` trước khi ép |
| Quyết định kiến trúc bị né qua từng ticket | Framework/DB thật không ai chọn, 25 release không có server | ADR-0032: cùng mã nợ ≥ N review liên tiếp → gate escalation dự án (`tests/test_no_kien_truc_adr0032.py`); chưa *ngăn* từ plan — đề xuất 2 (`open_decisions`) |

## Bổ sung 2026-09-06 (ADR-0030)

| Bẫy | Đã xảy ra | Lần sau |
|---|---|---|
| Tưởng "đổi schema thì không phải eval lại" | Thêm `rulings` vào 19 schema → `test_committed_recordings_match_current_prompts` đỏ cho cả 21 agent: schema nằm trong prompt gửi model | Đổi bất cứ thứ gì model nhìn thấy (prompt, skill, schema, template nhúng) = `make eval-record` cho mọi agent bị chạm; ~2,5 phút/agent, chạy song song 3 luồng |
