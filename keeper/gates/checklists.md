# Human gate `keeper` — checklist

Nguyên tắc: separation of duties, four-eyes (`decided_by != created_by`), timeout 24h (supervisor nhắc 12h),
quá hạn KHÔNG tự đi tiếp. `GateKind` hiện có đúng ba giá trị: `patch`, `release`, `escalation`
(`keeper/src/keeper/gates.py`). Bản mã của checklist dưới đây là `gates.CHECKLIST`; sửa văn xuôi ở đây thì
sửa cả hai chỗ, chúng phải khớp năm câu.

Mỗi gate tách làm hai phần, giống khuôn `software-company/gates/checklists.md`:
- **Code gửi kèm** — đúng các khoá `GateRequest(...).checklist` mà `keeper.gates.request_gate` sinh ra
  (`gates.CHECKLIST`, năm mục cố định — `keeper` không phân biệt bộ khoá theo `kind` như company làm).
- **Người tự kiểm thêm** — không có trong payload; người duyệt tự đọc và trả lời.

## Gate `patch` (kind `patch`, subject `<ticket_id>`)
Mở khi: `triager` xếp ticket `risk_tier=high`, hoặc `keeper-supervisor` xin thay orchestrator trước khi
`patcher`/`refactorer` được phép mở PR (`pr_blockers()` cổng `gate`).

Code gửi kèm:
- [ ] `risk_tier đúng bậc và lý do xếp bậc kiểm được` — `Ticket.risk_tier` cùng lý do từ `triager`
- [ ] `bằng chứng đo hai chiều: tắt bản sửa CI ĐỎ, bật lại XANH` — `VerificationReport` của `regression-guard`
- [ ] `báo cáo rà họ lỗi có cả chỗ an toàn kèm lý do` — phần "rà cả họ lỗi" trong `PatchProposal`/`VerificationReport`
- [ ] `ngân sách còn chỗ: không PR bảo trì nào đang mở` — `can_open_pr()` (cổng `budget`)
- [ ] `không chạm đường cấm (.git/, .github/, llm.yaml, *.sqlite*, agents/, skills/)` — `security-findings` +
      `HUMAN_ONLY_SEGMENTS` (cổng `human-only`)

Người tự kiểm thêm:
- [ ] Patch có đúng phạm vi ticket, không "sửa cạnh bên"
- [ ] `SecurityFinding` (nếu có) đã được đọc, không chỉ đếm số lượng
- [ ] Nợ liên quan trong `debt-ledger` (nếu có) đã cập nhật hạn hoặc đã xoá đúng

Kết quả: approve / request_changes / reject / hold / rollback (`decide()` — mọi giá trị đều ĐÓNG gate, xem
lưu ý dưới)

## Gate `release` (kind `release`, subject `<release_id>`)
Mở khi: `release-clerk` đã soạn `ReleaseNote`, có `VerificationReport.ok=true` và không `SecurityFinding` chặn.

Code gửi kèm:
- [ ] `risk_tier đúng bậc và lý do xếp bậc kiểm được` — bậc của ticket/patch được gộp vào release
- [ ] `bằng chứng đo hai chiều: tắt bản sửa CI ĐỎ, bật lại XANH` — `VerificationReport` của toàn bộ patch trong release
- [ ] `báo cáo rà họ lỗi có cả chỗ an toàn kèm lý do` — tổng hợp từ mọi `PatchProposal` trong release
- [ ] `ngân sách còn chỗ: không PR bảo trì nào đang mở` — `can_open_pr()`
- [ ] `không chạm đường cấm (.git/, .github/, llm.yaml, *.sqlite*, agents/, skills/)` — tổng hợp `security-findings`

Người tự kiểm thêm:
- [ ] Dòng CHANGELOG đúng nội dung, xếp mới nhất trên cùng theo thời điểm merge
- [ ] Mục `docs/sessions/<ngày>.md` phản ánh đúng việc đã làm, không phải lời khai

Kết quả: approve / request_changes / reject / hold / rollback

## Gate `escalation` (kind `escalation`, subject `<ticket_id>` hoặc `<debt_id>`)
Mở khi: ticket bảo trì kẹt (retry hết, vòng lặp cùng lỗi ≥ 2 lần) hoặc nợ trong `debt-ledger` quá hạn
(`ledger.overdue`). Xin bởi `keeper-supervisor`; người (`human:*`) luôn xin được dù không có tên trong
`REQUEST_ACTORS`.

Code gửi kèm:
- [ ] `risk_tier đúng bậc và lý do xếp bậc kiểm được` — bậc của ticket/nợ đang kẹt
- [ ] `bằng chứng đo hai chiều: tắt bản sửa CI ĐỎ, bật lại XANH` — nếu có patch dở dang, bằng chứng hiện có
- [ ] `báo cáo rà họ lỗi có cả chỗ an toàn kèm lý do` — nếu escalation do lỗi lặp
- [ ] `ngân sách còn chỗ: không PR bảo trì nào đang mở` — `can_open_pr()`
- [ ] `không chạm đường cấm (.git/, .github/, llm.yaml, *.sqlite*, agents/, skills/)` — nếu escalation liên quan sửa đổi

Người tự kiểm thêm:
- [ ] Lý do kẹt là thật (đọc `audit-log`), không phải một lần lỗi thoáng qua
- [ ] Quyết định (resume/rollback/đóng ticket) không tự động "mở lại" gì — `decide()` chỉ đóng gate; muốn làm
      lại ticket thì orchestrator phải tự phát `supervisor-actions{action:"resume"}` sau khi gate đóng

Kết quả: approve / request_changes / reject / hold / rollback

---

**Lưu ý về `decide()`** (đã đo lại ở BT7, xem `keeper/gates.py` module docstring): `decide()` luôn ĐÓNG gate —
bỏ `subject_id` khỏi `pending`, đẩy bản ghi vào `history`, đúng một lần, bất kể `decision` là gì. Không có giá
trị `decision` nào "mở lại" ticket; nếu ticket cần làm lại, orchestrator tự phát `supervisor-actions{action:
"resume"}` sau khi gate đã đóng. Người duyệt không cần và không nên trông vào việc `approve` sẽ tự khởi động
lại gì đó — action đó là code, không phải một tác dụng phụ của gate.
