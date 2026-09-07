# Task pack — gói việc giao cho một phiên agent

Một phiên agent nhận việc như một lập trình viên mới đến ngày đầu: không biết vì sao, không biết ranh giới, không
biết "xong" nghĩa là gì. Gói việc là tờ giấy đặt lên bàn nó. **Điền đủ 7 mục, dán vào đầu phiên.** Mục nào để trống
là mục agent sẽ tự đoán — và đoán sai im lặng.

Mẫu (copy từ dòng này):

```markdown
# Task pack: <tiêu đề một dòng, dạng động từ>

## 1. Mục tiêu — vì sao làm việc này
<1–3 câu: chuyện gì đã xảy ra / đang thiếu gì. Có ngày, có ticket/PR/release nếu là sự cố.>

## 2. Kết quả mong đợi — "xong" nghĩa là gì
- [ ] <bằng chứng máy sinh: test nào xanh, lệnh nào chạy được, số nào đổi>
- [ ] <PR mở, auto-merge bật, CI xanh>
- [ ] <CHANGELOG + session log đã ghi>

## 3. Phạm vi — được chạm và KHÔNG được chạm
Được: <thư mục/file>
Không: <file cấm; ví dụ: không sửa prompt agent nếu không đi đủ 7 bước; không sửa .claude/agents/ tay>

## 4. Bối cảnh phải đọc trước (theo thứ tự)
1. `AGENTS.md`, `TRAPS.md` §<mục liên quan>
2. `<pkg>/CODEMAP.md` dòng "<muốn gì>"
3. <ADR / báo cáo / test hiện có liên quan>

## 5. Ràng buộc kỹ thuật
- <stack, ranh giới tin cậy phải giữ, schema không được phá, coverage 100>

## 6. Bẫy đã biết cho việc này
- <trích từ TRAPS.md; hoặc "chưa có — nếu mắc bẫy mới, ghi vào TRAPS.md">

## 7. Cách kiểm và cách báo
- Kiểm: <lệnh CI đúng; test hai chiều>
- Báo: <PR #, dòng CHANGELOG, session log>; việc bỏ dở → ghi rõ vì sao, không im lặng
```

## Ví dụ đã điền (việc thật, PR #90)

```markdown
# Task pack: bằng chứng máy chạy cho `deployed` ở staging

## 1. Mục tiêu
QLKH 2026-09-06: 4 gate xanh, 389 test pass, 25 release, 0 điểm vào chạy được. `status=deployed` là lời khai của
release-engineer. Đề xuất 3 + 6 của docs/reports/2026-09-06-ban-giao-khong-chay-duoc.md.

## 2. Kết quả mong đợi
- [ ] `release-events{staging}.payload.smoke` do orchestrator điền, `verified_by=orchestrator`
- [ ] có runtime mà không chạy → status `failed` + escalation; không runtime → `unverified` kèm lý do
- [ ] test đo hai chiều; ruff + mypy sạch; PR + ADR-0029

## 3. Phạm vi
Được: src/company/smoke.py (mới), orchestrator._release, topics/schemas/{approved-specs,release-events}.json,
templates/prd.md, gates/checklists.md, docs/adr/0029.
Không: prompt release-engineer (bằng chứng do code sinh, ADR-0010 — không cần eval lại).

## 4. Bối cảnh
AGENTS.md; TRAPS.md §2 "bốn gate xanh"; software-company/CODEMAP.md "smoke"; ADR-0010, 0013, 0027;
tests/test_staging_khong_doi_gate3.py (harness FakeClient).

## 5. Ràng buộc
runtime.command chạy như lệnh lint/test của khách: clean_env, timeout, kill; cùng worktree tích hợp.

## 6. Bẫy
Sửa checklists.md → make subagents (bản dẫn xuất); thêm file test/ADR → sửa số trong README (test đếm từ đĩa).

## 7. Kiểm và báo
uv run pytest -q -p no:cacheprovider; ruff; mypy. PR #90, CHANGELOG, docs/sessions/2026-09-06.md.
```

## Gói việc thường trực: tự kiểm số liệu (ADR-0003)

Mỗi chân trời một lần (hoặc ngay sau một đợt PR làm đổi số test/agent/ADR), dán gói này vào một phiên **chỉ làm
việc này**. Lý do nó tồn tại: `AGENTS.md` luật cấm 8 nói "không tin lời khai", nhưng số liệu trong `README.md`
gốc là lời khai của một phiên nào đó trong quá khứ, và lần đầu đo lại (2026-09-07) thì 5/10 dòng lệch.

```markdown
# Task pack: tự kiểm số liệu trong tài liệu gốc

## 1. Mục tiêu
Đo lại mọi con số đang nằm trong `README.md`, `ARCHITECTURE.md` và các ADR trạng thái "được chấp nhận",
trên gói đã cài (`uv sync` xong) chứ không trên ấn tượng đọc mã. Lần trước: `docs/reports/<ngày>-tu-kiem.md`.

## 2. Kết quả mong đợi
- [ ] `docs/reports/<ngày>-tu-kiem.md` với bảng **claim · đo được · chênh · lệnh** — mỗi dòng một lệnh đã chạy
- [ ] số nào lệch → sửa TÀI LIỆU trong cùng PR; không bao giờ sửa phép đo cho khớp tài liệu
- [ ] dòng nào lệch mà chưa có test CI canh → ghi vào "Việc để lại" của báo cáo (không tự thêm test — luật cấm 7)
- [ ] PR mở, CHANGELOG + session log

## 3. Phạm vi
Được: `docs/reports/`, `README.md`, `ARCHITECTURE.md`, tài liệu bị lệch.
Không: mã nguồn, test, prompt agent, `.claude/agents/` — đây là phiên đo, không phải phiên sửa.

## 4. Bối cảnh
`docs/adr/0003-doi-chieu-ruflo.md`; báo cáo tự kiểm gần nhất; `console/tests/test_readme_goc.py` và
`*/tests/test_readme*.py` (những gì CI đã canh — không cần đo tay lại, nhưng ghi "đã có test canh" vào bảng).

## 5. Ràng buộc
Số test đếm bằng `pytest --collect-only -q` (số ca thu được), không đếm `def test_`. Agent/skill/topic/template/ADR
đếm file trên đĩa. Coverage đọc `fail_under` trong `pyproject.toml`, không đọc badge.

## 6. Bẫy
Một dòng README có hai chỗ nói cùng một số (test package đã mắc: `pytest N ca` và `Test: N ca`) — sửa một chỗ là
CI đỏ. Con số lệch một chiều "nói ít hơn thật" vẫn là lệch; đừng bỏ qua vì "ít nhất không nói quá".

## 7. Kiểm và báo
`uv run pytest -q console/tests/test_readme_goc.py Studio-creators/tests/test_readme_so_lieu.py` sau khi sửa README.
Báo: PR #, dòng CHANGELOG `docs: tự kiểm <ngày>`, session log.
```

## Khi nào không cần gói việc

Sửa tài liệu một file, đổi một chuỗi, trả lời câu hỏi. Còn lại — kể cả "sửa lỗi nhỏ" — điền mục 1, 2, 3 tối thiểu;
ba mục đó là thứ hay bị bỏ qua nhất và đắt nhất khi bỏ qua.
