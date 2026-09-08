@AGENTS.md

# Ghi chú riêng cho Claude Code

Luật đầy đủ nằm ở `AGENTS.md` (nhập ở dòng đầu). Dưới đây chỉ là thứ khác biệt khi agent là Claude Code.

## Sáu điều nếu chỉ đọc được sáu dòng

1. Không commit lên `main`; nhánh → PR → auto-merge squash. Scope PR một từ chữ thường.
2. Mỗi phiên một `git worktree` — có phiên khác đang mở cùng thư mục này (`git worktree list` để kiểm).
2b. Chỉ một PR mở tại một thời điểm: `gh pr list --state open` trước khi mở PR mới; PR khác đang mở thì
   chờ nó merge, rồi `git fetch` + `git rebase origin/main` trên nhánh mình trước khi `gh pr create` (`docs/QUY-TRINH-GIT.md` §2c).
3. Không commit `llm.yaml`, `*.sqlite*`, bí mật. Không hạ `fail_under = 100`.
4. Sửa `agents/`/`skills/` → 7 bước `CONTRIBUTING.md` §3, không bỏ bước.
5. "Xong" phải có output lệnh vừa chạy trong chính lượt này. Không có thì chưa xong.
6. Trước khi sửa lỗi lạ: đọc `TRAPS.md` — 80% khả năng nó đã có tên ở đó.

## Skill và trợ lý có sẵn trong repo

- `/gate-brief <subject>` — hồ sơ bằng chứng chỉ đọc cho một human gate của software-company; không ký thay người.
- `/thi-hanh <mã> [đề bài]` — thi hành một đề bài từ đặc tả tới mọi PR merge theo `docs/KHUON-THI-HANH.md`: phiên chính
  điều phối, subagent thực thi theo mức C1/C2/C3, người ra lệnh một lần. Trạng thái ở `docs/thi-hanh/<mã>.md`.
- `.claude/agents/sc-*` — 10 trợ lý kiểm duyệt chỉ đọc (một per agent + một per gate), sinh tự động; gọi khi cần
  góc nhìn chuyên môn về một PR/spec/release. Chúng **chỉ đọc**, không quyết định.
- `.claude/launch.json` — cấu hình dev server cho browser pane.

## Thao tác trên Windows

- Shell chính là PowerShell 7; Bash tool là Git Bash. `cd` trong Bash **không giữ** qua lệnh sau — dùng đường dẫn
  tuyệt đối hoặc `cd … && …` trong cùng lệnh.
- Heredoc bash chứa `'''` hoặc nhiều backtick hay vỡ: patch dài → ghi file vào scratchpad rồi `python file.py`.
- Lệnh `taskkill`/cron/wakeup có thể bị classifier chặn — không lách; hỏi người dùng đúng lệnh.
- In tiếng Việt lỗi mã hoá → `PYTHONIOENCODING=utf-8`.

## Khi vận hành công ty (không phải sửa code)

- Bật console thì bật ngay `orchestrator run --watch` — không thì việc giao nằm im.
- Duyệt gate: lý do = root_cause + decision + hint, ≥ 20 ký tự; "ok" là hint rỗng cho agent.
- Trước khi tin dashboard: hỏi *"chạy cho tôi xem"*. Số xanh có thể xanh vì rỗng.
- Sửa tay trong worktree của ticket: commit + takeover **trước**, duyệt gate **sau** (duyệt trước là bị reset).
- Muốn đổi hành vi agent: đổi tài liệu nó đọc qua đúng vai (CR → `product` pha spec ghi prd), không ghi tay blackboard.

## Bộ nhớ

Bộ nhớ dài hạn của Claude nằm ngoài repo (`~/.claude/projects/.../memory/`). Bài học đáng để repo giữ thì đưa vào
`TRAPS.md` — bộ nhớ là của một người, `TRAPS.md` là của mọi phiên.
