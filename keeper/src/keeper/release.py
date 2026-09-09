"""`release-clerk`: dòng `CHANGELOG.md` + mục `docs/sessions/<ngày>.md` (BT7, `DAC-TA-KEEPER.md` §9).

## Vì sao có chỗ trống `(#PR)` thay vì chờ tới khi biết số

`AGENTS.md` §10: tài liệu đi CÙNG PR, không đi sau nó — nhưng số PR **chỉ tồn tại sau `gh pr create`**. Nên
thứ tự bắt buộc là: `record()` ghi dòng mang chỗ trống → commit → mở PR → `fill_pr_number()` thay chỗ trống
bằng `(#n)` → **commit tiếp vào CHÍNH PR đó**. Không bao giờ mở PR thứ hai để vá số: một PR "dọn dẹp" là đúng
thứ §10 cấm, và nó tiêu mất suất PR duy nhất mà bất biến I3 cho phép (`budget.can_open_pr`).

## Vì sao không có thao tác ghi nào ở file này

Mọi lần chạm đĩa đi qua `patcher` (`fix_docs` để THÊM, `apply_edits` để SỬA TẠI CHỖ). Nhờ vậy đường cấm I4
(`.git/`, `.github/`, `llm.yaml`, `*.sqlite*`), chốt worktree (`refuse_shared_checkout`) và chốt coverage áp
cho cả đường release mà không phải nhắc lại — một bản sao thứ hai của bảng chặn là một bản sẽ lệch.

`fill_pr_number` NỔ khi không tìm thấy chỗ trống. Im lặng bỏ qua thì một dòng CHANGELOG thiếu số PR vĩnh viễn
mà không ai thấy — đúng khuôn "số xanh vì rỗng".
"""
from __future__ import annotations

from pathlib import Path

from .events import PatchProposal, ReleaseNote, Ticket
from .patcher import Edit, apply_edits, fix_docs

__all__ = ["PR_PLACEHOLDER", "compose", "fill_pr_number", "record"]

#: Chỗ trống cho số PR. Cố ý mang hình dạng `(#…)` y như dòng thật để `grep '(#'` thấy nó, chứ không phải một
#: dấu hiệu vô hình kiểu chuỗi rỗng.
PR_PLACEHOLDER = "(#PR)"


def _ref(pr_number: int | None) -> str:
    return PR_PLACEHOLDER if pr_number is None else f"(#{pr_number})"


def compose(ticket: Ticket, *, pr_number: int | None = None) -> ReleaseNote:
    """Dòng CHANGELOG + mục nhật ký phiên cho một ticket bảo trì.

    Dòng CHANGELOG theo khuôn của repo (`fix|feat|chore(<scope>): <việc> (#n)`); mục nhật ký mang mã ticket
    để người đọc lần ngược về signal đã sinh ra nó."""
    ref = _ref(pr_number)
    return ReleaseNote(
        ticket_id=ticket.ticket_id,
        pr_number=pr_number,
        changelog_line=f"- fix(keeper): {ticket.subject} — bảo trì tự động, tier {ticket.risk_tier} {ref}",
        session_line=f"- `{ticket.ticket_id}` — {ticket.subject} (tier {ticket.risk_tier}) {ref}",
    )


def record(root: Path, note: ReleaseNote, *, session_date: str,
           changelog: str = "CHANGELOG.md") -> PatchProposal:
    """Ghi cả hai dòng vào worktree PHỤ của ticket. Đi qua `patcher.fix_docs`, không tự mở file."""
    return fix_docs(root, note.ticket_id, changelog_line=note.changelog_line,
                    session_line=note.session_line, session_date=session_date, changelog=changelog)


def fill_pr_number(root: Path, note: ReleaseNote, pr_number: int, *, session_date: str,
                   changelog: str = "CHANGELOG.md") -> ReleaseNote:
    """Thay `(#PR)` bằng `(#<pr_number>)` TẠI CHỖ, trong chính worktree của PR đang mở.

    Không thêm dòng nào: dòng đã nằm trong PR từ commit trước, đây chỉ là commit thứ hai vào cùng PR."""
    if note.pr_number is not None:
        raise ValueError(f"note của {note.ticket_id} đã có số PR (#{note.pr_number}) — không điền lần hai")
    moi = note.model_copy(update={
        "pr_number": pr_number,
        "changelog_line": note.changelog_line.replace(PR_PLACEHOLDER, _ref(pr_number)),
        "session_line": note.session_line.replace(PR_PLACEHOLDER, _ref(pr_number)),
    })
    edits: list[Edit] = []
    for rel in (changelog, f"docs/sessions/{session_date}.md"):
        target = root / rel
        # Nhật ký phiên có thể chưa tồn tại (note chỉ có dòng CHANGELOG); CHANGELOG thiếu chỗ trống thì rơi
        # xuống `raise` bên dưới — không có nhánh nào im lặng.
        if not target.exists():
            continue
        cu = target.read_text(encoding="utf-8")
        if PR_PLACEHOLDER not in cu:
            continue
        edits.append(Edit(rel, cu.replace(PR_PLACEHOLDER, _ref(pr_number))))
    if not edits:
        raise ValueError(
            f"không tìm thấy {PR_PLACEHOLDER} trong {changelog}/docs/sessions/{session_date}.md — "
            f"`record()` chưa chạy, hay số PR đã điền rồi?")
    apply_edits(root, edits, operation="fix_docs", ticket_id=note.ticket_id,
                summary=f"điền số PR #{pr_number}")
    return moi
