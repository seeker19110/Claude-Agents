# CODEMAP.md — muốn đổi X thì sửa ở đâu

Bảng tra cứu, không phải tài liệu đọc từ đầu. Mỗi dòng: **muốn gì → chạm file nào → phải chạy lại gì**. Chi tiết
từng package ở `<pkg>/CODEMAP.md`.

## Toàn hub

| Muốn | Sửa | Rồi chạy |
|---|---|---|
| Thêm phụ thuộc Python | `<pkg>/pyproject.toml` → `uv lock` ở gốc (một lock cho cả bốn) | `uv sync`, CI `audit` |
| Thêm job CI | `.github/workflows/ci.yml` + nối vào `needs` của job `quality` | mở PR để chạy thật, đọc thời gian job |
| Đổi quy tắc tiêu đề PR | `.github/workflows/pr-policy.yml` (job `metadata`) | — |
| Đổi bảo vệ nhánh `main` | ruleset trên GitHub **và** file đối chiếu trong `protection-guard` (ci.yml) | job `protection-guard` đối chiếu hai chiều |
| Đổi quy trình git | `docs/QUY-TRINH-GIT.md` | — |
| Thêm bẫy đã mắc | `TRAPS.md` (hub) hoặc `<pkg>/TRAPS.md` | — |
| Ghi việc đã đổi | `CHANGELOG.md` | — |
| Cấu hình dev server cho browser pane | `.claude/launch.json` | — |
| Thêm slash command cho Claude Code | `.claude/commands/<tên>.md` | — |
| Trợ lý kiểm duyệt `sc-*` | **không sửa tay** — `software-company/agents/`, `skills/`, `gates/checklists.md` → `make subagents` | commit `.claude/agents/` |

## software-company (`company`) — tóm tắt; đầy đủ ở `software-company/CODEMAP.md`

| Muốn | Sửa | Rồi chạy |
|---|---|---|
| Đổi hành vi một agent | `agents/<khối>/<id>.md` (+ `version`) | 7 bước `CONTRIBUTING.md` §3 |
| Đổi quy tắc chuyên môn dùng chung | `skills/<tên>.md` (+ `version`) | như trên |
| Agent nào nhận topic nào | `ROUTES` trong `src/company/orchestrator.py`; front matter `reads`/`writes` | `tests/test_routing.py`, `test_security_review_fixes.py` |
| Thêm/đổi trường event | `topics/schemas/<topic>.json` **và** model Pydantic trong `src/company/events.py` | `tests/test_schema_consistency.py` |
| Checklist gate | `gates/checklists.md` → nguồn bằng chứng trong `src/company/gate_checklists.py` | `make subagents` |
| Template tài liệu agent viết | `templates/<tên>.md` | — |
| Tool agent được cấp / allowlist `run` | `src/company/tools.py` | `tests/test_tools_and_agentic.py` |
| Lệnh lint/test theo stack khách | `src/company/stacks.py` | — |
| Smoke sau deploy staging | `src/company/smoke.py`, hook `_smoke` trong orchestrator | `tests/test_smoke_evidence.py` |
| Giao hàng (tag, nhánh release) | `Integration.deliver` trong `src/company/workspace.py`, `_deliver` orchestrator | `tests/test_delivery_real.py` |
| Ngân sách, watchdog, escalate | `src/company/supervisor.py` | `tests/test_supervisor*.py` |
| Adapter provider mới | `src/company/llm.py`; chọn theo tier: `routing.py` | `tests/test_llm_errors_and_misc.py` |
| Ca eval | `evals/<agent>.yaml` → `make eval-record AGENT=<id>` | commit `evals/recordings/` |

## Studio-creators (`studio`) — đầy đủ ở `Studio-creators/CODEMAP.md`

| Muốn | Sửa |
|---|---|
| Agent / skill / route / schema / gate | cùng cấu trúc với software-company: `agents/`, `skills/`, `orchestrator.py`, `topics/schemas/`, `gates/checklists.md` |
| TTS / ảnh / ghép video | `src/studio/media.py` (adapter), `renderer.py` (pipeline), `timeline.py` (mốc cảnh, SRT, chapter) |
| Đo file media thật | `src/studio/qc.py` (ffprobe/ffmpeg) |
| Đăng YouTube, lấy số liệu | `src/studio/platform.py` (adapter), `youtube.py` (CLI login/sync) |
| Vòng đời video, rework có hint | `src/studio/desk.py` |
| Preflight khả năng được tìm thấy | `src/studio/preflight.py` |

## gateway — đầy đủ ở `gateway/CODEMAP.md`

| Muốn | Sửa |
|---|---|
| Cooldown, xoay tài khoản, refresh token | `src/gateway/auth.py` |
| Dịch OpenAI ⇄ Google Code Assist, retry, stream | `src/gateway/client.py` |
| Endpoint HTTP, daemon | `src/gateway/server.py` |
| CLI `start/stop/status/login/setup/models` | `src/gateway/manage.py`, `__main__.py` |

## console — đầy đủ ở `console/CODEMAP.md`

| Muốn | Sửa |
|---|---|
| Đọc thêm dữ liệu từ bus hai công ty | `src/console/collect.py` |
| "Sự thật giao hàng" (phễu release, bế tắc im lặng) | `src/console/truth.py` |
| Duyệt gate | `src/console/decide.py` |
| Giao việc mới (form → bus) | `src/console/submit.py` |
| Đổi model/backend từ trang | `src/console/settings.py` |
| Route HTTP, SSE, token phiên | `src/console/server.py` |
| Giao diện | `src/console/static/index.html` (một file, không framework) |
| Hợp đồng nội bộ giữa các lớp | `console/API.md` |
