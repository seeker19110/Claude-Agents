@AGENTS.md

# Ghi chú riêng cho Claude Code

Luật đầy đủ nằm ở `AGENTS.md` (nhập ở dòng đầu). Dưới đây chỉ là thứ khác biệt khi agent là Claude Code.

## Bảy điều nếu chỉ đọc được bảy dòng

1. Không commit lên `main`; nhánh → PR → auto-merge squash. Scope PR một từ chữ thường. Việc lớn nhiều task
   liên quan: **một nhánh cho cả hạng mục** (không phải một nhánh mỗi task), PR nháp ngay sau task đầu, `gh pr
   ready` khi hạng mục xong (`docs/QUY-TRINH-GIT.md` §2d, ADR-0012) — vẫn tính là một PR mở với luật 2b dưới đây.
2. Mỗi phiên một `git worktree` — có phiên khác đang mở cùng thư mục này (`git worktree list` để kiểm). Có tool
   worktree riêng của harness (`EnterWorktree`/tương đương) thì dùng nó trước, đừng tự `git worktree add` —
   tool native lo cả đặt chỗ, tạo nhánh, dọn dẹp mà `git` tay không biết tới.
2b. Chỉ một PR mở tại một thời điểm: `gh pr list --state open` trước khi mở PR mới; PR khác đang mở thì
   chờ nó merge, rồi `git fetch` + `git rebase origin/main` trên nhánh mình trước khi `gh pr create` (`docs/QUY-TRINH-GIT.md` §2c).
   Trước khi tạo PR: cũng kiểm PR/issue đã đóng cùng vấn đề (`AGENTS.md` luật bắt buộc 11) — trùng thì nói rõ
   cái gì khác đi, đừng lặng lẽ mở PR thứ hai.
3. Không commit `llm.yaml`, `*.sqlite*`, bí mật. Không hạ `fail_under = 100`.
4. Sửa `agents/`/`skills/` → 7 bước `CONTRIBUTING.md` §3, không bỏ bước.
5. **TDD cho mọi code, không riêng bugfix**: viết test đỏ trước → code tối thiểu cho xanh → refactor. Không có
   test đỏ đi trước thì chưa được viết code sản xuất (`AGENTS.md` luật bắt buộc 4). Vá 3 lần liên tiếp vẫn lòi
   vấn đề mới chỗ khác → dừng, hỏi người, đừng vá lần 4 một mình (luật bắt buộc 6).
6. "Xong" phải có output lệnh vừa chạy trong chính lượt này. Không có thì chưa xong.
7. Trước khi sửa lỗi lạ: đọc `TRAPS.md` — 80% khả năng nó đã có tên ở đó, kể cả câu bạn đang định tự biện hộ
   (`TRAPS.md` §6).

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
