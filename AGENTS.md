# AGENTS.md — luật cho mọi agent làm việc trong repo này

Đọc file này trước khi chạm vào bất kỳ file nào. Nó ngắn vì mọi chi tiết đã có chỗ riêng; ở đây chỉ là
**điều cấm, điều bắt buộc, và đi đâu để biết thêm**. Bộ khung 9 file: `AGENTS.md` (luật) · `CLAUDE.md` (luật cho
Claude Code, nhập file này) · `TRAPS.md` (bẫy đã mắc) · `ARCHITECTURE.md` (bản đồ hệ) · `CODEMAP.md` (muốn đổi X thì
sửa ở đâu) · `CHANGELOG.md` (đã đổi gì) · `docs/TASK-PACK.md` (gói việc) · `docs/PROMPT-SHEET.md` (câu lệnh chuẩn) ·
`docs/sessions/` (nhật ký phiên). Mỗi package con có `CLAUDE.md`, `TRAPS.md`, `CODEMAP.md`, `ARCHITECTURE.md` riêng.

## Repo này là gì

X-Agents: hub các "công ty AI" đa agent. Bốn package Python trong **một uv workspace** (một `pyproject.toml`,
một `uv.lock`, một `.venv` ở gốc):

| Thư mục | Package | Là gì |
|---|---|---|
| `software-company/` | `company` | công ty gia công phần mềm: yêu cầu → PRD → ticket → code thật trên worktree → review → release → khách ký |
| `Studio-creators/` | `studio` | phòng ban video YouTube: kế hoạch → kịch bản → render → review → đăng |
| `gateway/` | `gateway` | proxy OpenAI-compatible xoay vòng tài khoản Google Antigravity |
| `console/` | `console` | trực ban hợp nhất: một trang web cục bộ nhìn cả hai công ty, duyệt gate tại chỗ |

Nguyên tắc chung (chi tiết ở `ARCHITECTURE.md`): model quyết định – code hành động; prompt là code; guardrail có
hạn mức; self-hosted, resume được; trung lập provider.

## Luật cấm

1. **Không commit thẳng `main`.** Mọi thay đổi: nhánh → PR → CI xanh → squash merge. `git push` lên `main` bị
   ruleset từ chối. Quy trình: `docs/QUY-TRINH-GIT.md`.
2. **Không dùng chung một clone với phiên khác.** Mỗi phiên agent một `git worktree` (`docs/QUY-TRINH-GIT.md` §2b).
   Thấy nhánh mình không tạo, hay `checkout` trong reflog mình không gọi → dừng, đừng commit.
3. **Không commit** `llm.yaml`, `media.yaml`, `*.sqlite*`, `company.artifacts/`, khoá/token, dữ liệu khách thật.
   Chỉ commit `*.example.yaml`. gitleaks quét cả lịch sử — lỡ commit rồi xoá vẫn đỏ (`SECURITY.md`).
4. **Không gọi provider trả phí trong test.** Provider `fake` + bản ghi eval đủ chạy offline toàn bộ.
5. **Không sửa tay bản dẫn xuất**: `.claude/agents/sc-*.md` sinh từ `software-company/agents/`, `skills/`,
   `gates/checklists.md` bằng `make subagents`; `tests/golden/` sinh bằng `make golden`. Sửa nguồn rồi sinh lại.
6. **Không hạ ngưỡng coverage để PR qua cổng.** `fail_under = 100` ở cả bốn package; mất một dòng phủ là CI đỏ
   — thêm test, không hạ số.
7. **Không "sửa" code cạnh bên.** Mỗi dòng đổi phải truy được về yêu cầu. Thấy dead code thì nói, đừng xoá.
8. **Không tin lời khai.** Của model, của agent, của chính mình. "Tests pass" cần output lệnh vừa chạy; "đã
   deploy" cần bằng chứng máy sinh (`verified_by=workspace|orchestrator`). Chưa chạy thì chưa được nói.

## Luật bắt buộc

1. **Sửa `agents/` hoặc `skills/` → checklist 7 bước** ở `CONTRIBUTING.md` §3: tăng `version` → `make golden` →
   `make eval-record AGENT=<id>` (model thật) → `make assetscan` → `make assetbudget` → `make subagents` → commit cả
   golden + recordings + `.claude/agents/`. Bỏ một bước là CI đỏ có chủ đích.
2. **Thay đổi kiến trúc → ADR trước** (`<công ty>/docs/adr/`), link trong PR. Sửa lỗi nhỏ, chỉnh prompt, sửa tài
   liệu thì không cần.
3. **Chạy đúng lệnh CI trước khi push**: `uv run ruff check src tests` + `uv run mypy src/<pkg> --ignore-missing-imports`
   + `uv run pytest -q` (software-company: `-n auto --cov`). Windows thiếu 2 dòng POSIX trong coverage là bình thường.
4. **Test phải đo hai chiều**: tắt bản sửa → test đỏ; bật lại → xanh. Ghi kết quả vào commit message.
5. **Sửa một lỗi thì rà cả họ lỗi đó**: viết câu hỏi kiểm tra rút từ lỗi vừa sửa, grep mọi chỗ dùng cùng cơ chế,
   ghi lại cả chỗ an toàn và vì sao (`TRAPS.md` §1).
6. **Đo trước khi sửa**: gặp lỗi không rõ → tái hiện với đối chứng, tách từng biến. Suy từ thông điệp lỗi đã sai 6/6
   lần (`TRAPS.md` §2).
7. **Tiêu đề PR**: `^(feat|fix|refactor|docs|test|chore|style|perf|build|ci|revert)(\([a-z0-9._/-]+\))?!?: .+` —
   scope **một từ, chữ thường** (`fix(company,console)` bị chặn). Bật auto-merge squash ngay sau khi tạo; thất bại
   thì theo dõi `gh pr checks <n> --watch --interval 150` tới khi kết luận.
8. **Sau `git push`, kiểm commit đã vào PR** (`gh pr view <n> --json commits`) trước khi báo xong.
9. **Cuối phiên**: ghi `docs/sessions/<ngày>.md` (việc dở, PR mở, thứ người sau không được quên) và một dòng
   `CHANGELOG.md` cho mỗi PR đã merge.

## Chạy cái gì ở đâu

```bash
uv sync                          # một lần ở gốc
make test                        # cả bốn package; hoặc cd <pkg> && uv run pytest -q
cd software-company && uv run python -m company.orchestrator status      # PHẢI ở trong software-company/ (gốc có company.sqlite rỗng)
cd console && uv run python -m console --allow-decide                    # trực ban; bật console thì bật luôn orchestrator run --watch
```

Lệnh dừng khẩn, lịch trực, giới hạn đã biết: `docs/TRUC-VA-DUNG-KHAN.md`. Cấu hình model theo gói tài khoản:
`docs/DIEU-PHOI-MODEL.md`. Hướng dẫn vận hành từ đầu: `docs/HUONG-DAN-VAN-HANH.md`.

## Khi bối rối

Nêu giả định thành lời và đi tiếp với giả định đó, trừ khi sai thì công việc thành vô dụng — lúc đó hỏi.
Không hỏi "tiếp không?"; không tóm tắt tiến độ thay cho làm việc. Bốn thứ được phép dừng lại hỏi người:
thao tác không đảo ngược được, việc nhạy cảm bảo mật, tác động ra ngoài worktree (merge/push/publish), và kế
hoạch hỏng tới mức mọi hướng đều là đoán.
