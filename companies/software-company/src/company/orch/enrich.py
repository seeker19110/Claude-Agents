"""Enrich của bảng route: làm giàu payload trước khi giao cho agent (tách khỏi `routes.py`, ADR-0034).

Tách cùng lý do `guards.py`. Ranh giới giữ đúng một chiều: `routes.py` nhập từ đây, đây không nhập `routes.py`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..events import Envelope
from ..roles import FINDING_KIND, ROLE
from ..workspace import WorkspaceError

if TYPE_CHECKING:
    from ..orchestrator import Orchestrator


# Trường bị gỡ khỏi payload trước khi đưa cho test-author (ADR-0028: lượt MÙ). `hint` là phản hồi review vòng
# trước — nó nói về CODE, đọc nó là hết mù.
BLIND_STRIP = frozenset({"hint", "retry", "test_suite", "diff", "chan_doan"})


def _with_draft(e: Envelope, o: Orchestrator) -> dict[str, Any]:
    d = o.latest("requirements-draft", e.payload.get("project_id") or e.key)
    return {"requirements_draft": d.payload} if d else {}


def _with_intake(e: Envelope, o: Orchestrator) -> dict[str, Any]:
    """Pha `spec` cần CẢ báo cáo của pha `intake` lẫn báo cáo 4 mục của pha `research` (ADR-0006), nhưng nó chỉ được
    đánh thức bởi báo cáo của pha `research`. Không đính kèm đề bài của pha `intake` thì tiêu chí bắt đầu không bao
    giờ đủ và draft luôn rỗng."""
    key = e.payload.get("project_id") or e.key
    found = [x for x in o.bus.replay("research-findings", key) if x.payload.get("kind") == FINDING_KIND.INTAKE]
    return {FINDING_KIND.INTAKE: found[-1].payload.get("data")} if found and found[-1].payload.get("data") else {}


def _with_diff(e: Envelope, o: Orchestrator) -> dict[str, Any]:
    """Reviewer/QA/security đọc diff thật của branch ticket (khi có repo) thay vì tin `summary` của PR."""
    ws = o.workspace(e.payload.get("ticket_id") or e.key)
    if ws is None or not ws.path.exists(): return {}
    try: return {"diff": ws.diff(), "changed_files": ws.changed_files()}
    except WorkspaceError as ex: return {"diff_error": str(ex)[:300]}


def _with_chan_doan(e: Envelope, o: Orchestrator) -> dict[str, Any]:
    """qa-debugger nhận thêm LỊCH SỬ HỎNG của chính ticket này, phạm vi hẹp và chỉ-đọc.

    Agent chỉ thấy PR trước mặt nên mỗi vòng lại chẩn đoán từ đầu, không biết mình đang xem lần thứ mấy. Đo
    được ở lần chạy thật 2026-09-04: QLKH-001 quay 8 vòng với `blocked 3× / reopen 8× / review_block 13×`, và
    179/193 lỗi của cả dự án là CÙNG MỘT sự cố hết quota — không agent nào biết điều đó vì chỉ `supervisor`
    đăng ký đọc `audit-log`.

    Cố ý bơm bản LÁT CẮT THEO TICKET chứ không phải toàn cảnh: khuôn lỗi của dự án khác là nhiễu cho việc chấm
    một PR, và `max_input_chars` của qa-debugger chỉ có 50k. Vẫn chỉ-đọc: agent không được cấp thêm tool nào,
    không sửa được mã công ty — đây là bậc thấp nhất có ích, để kiểm xem nó chẩn đoán có đúng không trước khi
    tính chuyện cho nhiều quyền hơn."""
    tid = str(e.payload.get("ticket_id") or e.key)
    try:
        from ..metrics import diagnose
        d = diagnose(o.bus, top=30)
    except Exception as ex:  # chẩn đoán hỏng không được làm hỏng lượt review
        return {"chan_doan_error": str(ex)[:200]}
    vong = d["ticket_quay_vong"].get(tid)
    khuon = [k for k in d["loi_theo_khuon"] if tid in k["tickets"]][:3]
    if not vong and not khuon: return {}
    return {"chan_doan": {"lich_su_ticket": vong, "khuon_loi_cua_ticket": khuon,
                          "gate_dang_cho": d["gate"]["dang_cho"]}}


def _with_task(e: Envelope, o: Orchestrator) -> dict[str, Any]:
    """Assignee nhận lại toàn bộ ticket (acceptance, scope, hint...) kèm bộ test vừa được viết."""
    t = o.latest("tasks", str(e.payload.get("ticket_id") or e.key))
    base = dict(t.payload) if t is not None else {}
    return {**base, "test_suite": {k: e.payload.get(k) for k in ("files", "acceptance_covered", "tests_status", "commit", "notes")},
            "tests_authored_by": ROLE.QA}
