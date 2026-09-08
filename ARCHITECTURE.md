# ARCHITECTURE.md — bản đồ hệ thống X-Agents

Đọc để biết **thứ gì nằm ở đâu và vì sao**. Chi tiết từng package: `<pkg>/ARCHITECTURE.md`. Muốn đổi một thứ cụ
thể: `CODEMAP.md`.

## Bức tranh lớn

```
                       ┌──────────────── console/ (127.0.0.1:8200) ────────────────┐
                       │  đọc bus SQLite chỉ-đọc của hai công ty; duyệt gate qua   │
                       │  đúng HumanGate; giao việc qua đúng bus + schema           │
                       └────────────┬──────────────────────────┬────────────────────┘
                                    │                          │
   ┌────────────────────────────────▼─────┐   ┌────────────────▼──────────────────────┐
   │ software-company/  (package company) │   │ Studio-creators/  (package studio)     │
   │ 6 agent · 45 skill · 19 topic        │   │ 14 agent · 24 skill · 19 topic         │
   │ 3 human gate + escalation            │   │ 4 human gate                           │
   │ code thật trên git worktree của khách│   │ render thật: TTS + ảnh + ffmpeg        │
   └────────────────┬─────────────────────┘   └────────────────┬───────────────────────┘
                    │  llm.yaml: backends + routing theo tier    │
                    └──────────────────┬─────────────────────────┘
                                       ▼
        claude-code CLI · codex CLI · gateway/ (127.0.0.1:1123, xoay tài khoản Google) · model local · API
```

Bốn package là bốn thành viên của một **uv workspace** — một `.venv`, một `uv.lock`. Không có `[project.scripts]`:
mọi entry point là `python -m <package>.<module>`. Repo khách nằm **ngoài** repo này (`--repo <đường dẫn>`).

## Kiến trúc chung của một "công ty"

```
topic (JSON Schema, có key) ──► registry: agent nào nhận topic nào
        │                              │
        ▼                              ▼
   sqlite_bus ◄──── orchestrator ──► runner (vòng lặp tool, guard, cắt ngữ cảnh) ──► routing → llm (adapter từng gói)
        │                 │
        │                 ├── human gate: chờ người duyệt (gate_cli / console)
        │                 └── supervisor: watchdog, ngân sách token, bài học
        ▼
   blackboard (artifact store, namespace theo owner) + audit-log (token thật, chi phí USD)
```

Năm nguyên tắc, mỗi cái có chỗ cắm trong code:

| Nguyên tắc | Nghĩa là | Ở đâu |
|---|---|---|
| **Model quyết định – code hành động** | tính toán, kiểm định, render, deploy, đăng… là code xác định; model chỉ trả JSON | `tools.py`, `workspace.py`, `smoke.py` (company); `renderer.py`, `platform.py` (studio) |
| **Prompt là code** | agent/skill có `version`, golden test, eval ghi/phát lại chạy trong CI không gọi model | `agents/*.md` front matter, `tests/golden/`, `evals/recordings/` |
| **Guardrail có hạn mức** | ngân sách token, retry, timeout đều có ngưỡng; hết ngưỡng → escalate, không đi tiếp | `supervisor.py`, `guard.py`, `context.py` |
| **Self-hosted, resume được** | bus SQLite; dừng và chạy tiếp ở bất kỳ điểm nào; state dựng lại từ log | `sqlite_bus.py`, `_rehydrate` trong orchestrator |
| **Trung lập provider** | đổi model bằng `llm.yaml`/env, không đổi code hay prompt | `llm.py`, `routing.py`, `docs/DIEU-PHOI-MODEL.md` |

## Ranh giới tin cậy (quan trọng nhất để không tự lừa mình)

Mọi trường mang nghĩa "đã làm được" phải do **code** điền, không phải model:

- PR: `local_checks.verified_by=workspace` — lint/test chạy thật trong worktree (ADR-0010, ADR-0013).
- Release: `release-events.smoke.verified_by=orchestrator` — sản phẩm được khởi động thật, gọi một request thật
  (ADR-0029).
- Identity của event (`env`, `release_id`, `ticket_id`) lấy từ ROUTE, model lệch thì `*_overridden` (#72, #75).
- Studio: `platform_ref`/`url` do adapter YouTube điền từ API; số liệu do `sync-*` nạp; agent chỉ diễn giải.

Còn lại là lời khai — hữu ích, nhưng chỉ ký gate trên bằng chứng.

## Human gate

| Công ty | Gate | Gác cái gì |
|---|---|---|
| software-company | `spec` → `release` → `acceptance` (+ `escalation`) | PRD; production; khách ký UAT (kế hoạch ticket do `_check_plan` chặn bằng code, không còn gate `plan` từ ADR-0037) |
| Studio-creators | `plan` → `publish` → `replies` (+ `escalation`) | kế hoạch biên tập; đăng video; trả lời bình luận |

Gate là thật: hạn 24h, nhắc 12h, quá hạn escalate, four-eyes. Mỗi gate của software-company có trợ lý kiểm duyệt
chỉ đọc `sc-gate-<kind>` và hồ sơ bằng chứng `gate_brief`.

## CI (`.github/workflows/ci.yml`)

`static` · `unit` · `eval-replay` · `audit` (pip-audit + gitleaks cả lịch sử) · `studio-static` · `studio-unit` ·
`studio-eval-replay` · `golden-check` (golden + subagents dẫn xuất khớp nguồn) · `gateway-*` · `console-*` ·
`asset-scan` (ADR-0022) · `protection-guard` (ruleset file ↔ thật) · **`quality`** gom tất cả — required check của
`main`, tên bất biến. `pr-policy.yml`: job `metadata` kiểm tiêu đề PR.

## Lịch sử repo (đọc `git log` cho đúng)

Repo này bắt đầu là fork của `humanlayer/12-factor-agents` (khoảng 200 commit "Update factor-…", "wip on wtg"…), rồi
chứa dự án MEP-Agents/CAD (08/2026, có hai lần revert chéo). **Đầu thực của X-Agents là `2438d2f` (2026-09-02, "Add
software-company AI agent framework")**; `d4abda1` cùng ngày gỡ MEP-Agents. Muốn xem lịch sử có nghĩa:
`git log 2438d2f..main`. Không rewrite lịch sử cũ — chỉ cần biết mốc.

## Tài liệu nguồn

| Câu hỏi | Đọc |
|---|---|
| Cài và vận hành từng bước | `docs/HUONG-DAN-VAN-HANH.md` |
| Model nào cho agent nào, xoay quota ra sao | `docs/DIEU-PHOI-MODEL.md` |
| Dừng khẩn, lịch trực, thứ chưa có | `docs/TRUC-VA-DUNG-KHAN.md` |
| Git: nhánh, PR, CI, worktree | `docs/QUY-TRINH-GIT.md` |
| Sửa agent/skill phải chạy lại gì | `CONTRIBUTING.md` |
| Bảo mật: bí mật, phòng thủ, báo lỗi | `SECURITY.md` |
| Vì sao quyết định thế này | `software-company/docs/adr/` (0001–0038), `Studio-creators/docs/adr/` (0001–0009), `console/docs/adr/` |
