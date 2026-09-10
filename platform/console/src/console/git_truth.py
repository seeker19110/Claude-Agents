"""C7 — "commit vượt integration": bao nhiêu commit của nhánh ticket CHƯA có trên nhánh tích hợp.

Đêm 05/09 nhãn `blocked` mang hai nghĩa không phân biệt được trên trang: *chưa viết xong code* và *code đã viết
xong, đã nằm trên nhánh, nhưng chưa gộp*. Hai nghĩa đó cần hai hành động ngược nhau của người trực (một bên là
gỡ cho agent chạy tiếp, một bên là gộp/mở gate release), nên phải là hai con số khác nhau.

Đo bằng ĐÚNG một lệnh::

    git -C <repo> rev-list --count company/integration..ticket/<id>

**Không dùng `git branch --contains`.** Nó trả lời câu hỏi khác ("nhánh nào chứa commit này") và cho kết quả sai ở
đúng chỗ đang cần: một nhánh ticket không có commit riêng — vừa tạo từ integration, hoặc đã bị merge rồi — vẫn
được liệt kê là "contains", nên nhánh rỗng và nhánh đã giao nhìn giống hệt nhau. `rev-list --count A..B` đếm commit
có ở B mà không có ở A: 0 nghĩa là *không còn gì chưa gộp*, n > 0 nghĩa là *n commit đang nằm ngoài*.

Chỉ đọc: không `checkout`, không `fetch`, không tạo worktree. Đường dẫn repo lấy từ chính bus (audit `project.repo`
mà orchestrator ghi khi nhận dự án), không phải từ cấu hình riêng của console — console không có nguồn sự thật nào
của riêng nó (C10).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

INTEGRATION_BRANCH = "company/integration"
TICKET_BRANCH = "ticket/{}"
GIT_TIMEOUT_S = 5.0


def _git(repo: Path, *args: str) -> str | None:
    """stdout đã strip, hoặc None nếu git không chạy được / trả mã khác 0 (ref không tồn tại là chuyện thường)."""
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                           timeout=GIT_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def ahead_count(repo: Path, ticket_id: str, integration: str = INTEGRATION_BRANCH) -> int | None:
    """Số commit của `ticket/<id>` chưa có trên nhánh tích hợp. None = không đo được (không repo, không nhánh, không git).

    None và 0 là hai câu trả lời khác nhau và trang phải hiện khác nhau: 0 là "đã gộp hết", None là "chưa biết"."""
    if not Path(repo).is_dir(): return None
    out = _git(Path(repo), "rev-list", "--count", f"{integration}..{TICKET_BRANCH.format(ticket_id)}")
    if out is None or not out.isdigit(): return None
    return int(out)
