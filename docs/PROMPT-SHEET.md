# Prompt sheet — câu lệnh chuẩn cho các việc lặp lại

Những câu đã dùng thật và cho kết quả đúng. Copy nguyên văn, điền chỗ `<…>`. Mỗi câu ghi **vì sao viết thế** để
người sau sửa đúng chỗ khi hoàn cảnh đổi. Câu lệnh mới đáng giữ thì thêm vào đây, kèm ngày dùng lần đầu.

## A. Bắt đầu một phiên

```
Đọc AGENTS.md, TRAPS.md, và <pkg>/CODEMAP.md. Chạy `git worktree list` và `git status`; nếu thấy nhánh không phải
của phiên này thì tạo worktree riêng trước khi làm gì khác. Sau đó nhận gói việc dưới đây.
<dán task pack>
```
*Vì sao*: hai phiên chung một clone đã làm mất commit (#86). Đọc TRAPS trước vì 80% lỗi mới là khuôn cũ.

## B. Sửa lỗi lạ

```
Trước khi đề xuất sửa: tái hiện lỗi bằng lệnh chạy được, tách từng biến một, và so một con số đặc trưng với lượt
thật. Đối chiếu với bốn khuôn ở TRAPS.md §1 và nói nó thuộc khuôn nào (hoặc không). Chỉ khi bật/tắt được lỗi theo
ý muốn mới viết test đỏ rồi sửa. Sửa xong: rút một câu hỏi kiểm tra từ lỗi này, grep mọi chỗ dùng cùng cơ chế,
báo cả chỗ an toàn và vì sao.
```
*Vì sao*: chẩn đoán từ thông điệp lỗi sai 6/6 lần (2026-09-04); rà cả họ cho tỉ lệ 3/7 khoá hỏng.

## C. Agent trong công ty thất bại lặp lại

```
Agent <id> thất bại <n> lần ở cùng một thao tác "<thao tác>". Trước khi chỉnh hint hay prompt: mở
software-company/src/company/tools.py, liệt kê tool nó thực sự được cấp và allowlist của `run`, rồi trả lời
"việc này có làm được về mặt vật lý không". Nếu không: đề xuất cấp tool kèm ranh giới an toàn, không viết lại hint.
```
*Vì sao*: 4 vòng ép reviewer xoá file mà bộ tool không có `rm` (2026-09-04).

## D. Sửa prompt agent / skill

```
Sửa <agents|skills>/<file>. Đi đủ 7 bước CONTRIBUTING.md §3 theo đúng thứ tự, không bỏ bước nào; cuối cùng liệt kê
file đã commit: golden, evals/recordings/<id>.json, .claude/agents/. Nếu không có model thật để eval-record, DỪNG và
nói rõ — đừng commit prompt mà không có bản ghi.
```
*Vì sao*: CI `eval-replay --strict` đỏ khi bản ghi lệch version; bản ghi ghi giữa lúc stash prompt đã sai version.

## E. Vận hành: dự án đứng im

```
Dự án <project_id> không tiến. Đừng tin `status` xanh. Trả lời bốn câu bằng dữ liệu từ bus (chạy trong
software-company/): (1) release cuối của mỗi RC đang ở env/status nào — vẽ phễu RC → staging → qa → gate 3 →
production; (2) có gate nào đang chờ, kind gì, hậu quả duyệt là gì; (3) ticket nào `blocked` mà KHÔNG có gate;
(4) `delivery` đã giao được gì (tag, sha). Rồi mới đề xuất một hành động.
```
*Vì sao*: đêm 2026-09-05 mất hàng giờ vì `queue: 0, blocked: [], gates: {}` xanh do rỗng.

## F. Duyệt gate

```
Trước khi duyệt <subject>: chạy /gate-brief <subject>, đọc `kind` và hậu quả của việc duyệt. Lý do duyệt viết đủ
ba phần: root_cause — decision — hint cho agent (≥ 20 ký tự, không phải "ok"). Nếu là gate release: smoke của
staging phải `ok=true`; `unverified` thì hỏi "chạy cho tôi xem" trước.
```
*Vì sao*: "ok" là hint rỗng (13:05 2026-09-06); duyệt nhầm `escalation` tưởng đã giao hàng.

## G. Kết thúc phiên

```
Trước khi dừng: (1) mọi PR đã push — kiểm `gh pr view <n> --json commits` khớp; auto-merge bật; (2) thêm dòng
CHANGELOG cho PR đã merge; (3) ghi docs/sessions/<YYYY-MM-DD>.md theo mẫu: việc xong, việc dở + vì sao, PR mở,
bẫy mới (đã ghi TRAPS chưa), thứ người sau KHÔNG được quên. Không tóm tắt lại cả phiên — chỉ thứ người sau cần.
```
*Vì sao*: bàn giao cuối ca là viết ra, không nói miệng (TRUC-VA-DUNG-KHAN §2); commit rơi khỏi PR sau push (#77).

## H. Đọc một repo/skill bên ngoài để học

```
Đọc <repo>. Đối chiếu từng phần với những gì repo này ĐÃ CÓ (skills/, ADR, TRAPS). Kết luận theo ba cột: đã có và
sâu hơn / đã có nhưng nông hơn / chưa có. Với "chưa có": nó giải quyết sự cố nào ĐÃ XẢY RA ở đây? Không có sự cố
tương ứng thì xếp vào "chưa cần". Không cài gì; đề xuất là sửa tài liệu/code của mình.
```
*Vì sao*: PR #85 — 12/14 skill của superpowers là tập con; hai cái còn lại trùng đúng sự cố QLKH.
