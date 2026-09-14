# Luật cho agent Gemini / Antigravity trong repo này

**Nguồn sự thật duy nhất là [`AGENTS.md`](AGENTS.md) ở gốc repo. Đọc nó TRƯỚC KHI chạm vào bất kỳ file nào.**

File này cố ý KHÔNG chép lại luật: hai bản luật thì sẽ lệch nhau, và lúc lệch thì agent chọn bản tiện hơn.
Ở đây chỉ có thứ agent không phải Claude Code cần biết thêm.

## Ba thứ Claude Code có mà bạn không có

1. **Hook không chạy cho bạn.** `.claude/hooks/` chỉ Claude Code nạp. Bốn phép kiểm dưới đây bạn phải **tự
   làm bằng tay**, coi như luật cứng:
   - trước `git commit`: không đứng trên `main`; staged không có `llm.yaml`/`media.yaml`/`*.sqlite*`/
     `company.artifacts/`; diff không hạ `fail_under`; `scripts/dev-task.sh gate <gói>` xanh.
   - không `git push` vào `main`, không `git reset --hard`, không `merge|rebase --abort` để né xung đột.
2. **Lệnh cổng**: đừng đoán lệnh của từng package — gọi `scripts/dev-task.sh gate [gói]`
   (`gói`: `company|gateway|console|core|keeper|all`). Nó chạy đúng lệnh CI, kể cả `-n auto --cov` riêng của
   software-company.
3. **Subagent `sc-*`** (`.claude/agents/`) là bản dẫn xuất sinh bằng `make subagents` — không sửa tay
   (`AGENTS.md` luật cấm 5).

## Đọc theo thứ tự

1. `AGENTS.md` — luật cấm, luật bắt buộc, đi đâu để biết thêm.
2. `TRAPS.md` — bẫy đã mắc; đọc trước khi chẩn đoán bug lạ.
3. `ARCHITECTURE.md` + `CODEMAP.md` — hệ là gì, muốn đổi X thì sửa ở đâu.
4. `docs/sessions/` — phiên trước để lại việc dở gì.
