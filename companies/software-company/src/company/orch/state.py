"""Trạng thái RAM của orchestrator, gom thành một dataclass (ADR-0034).

Trước đây ~24 biến trạng thái nằm rải trong `Orchestrator.__init__`, mỗi biến một dòng gán và một dòng khôi
phục ở `rehydrate.py`. Không có gì buộc hai danh sách đó khớp nhau: thêm một biến mà quên dòng rehydrate thì
trạng thái im lặng biến mất sau restart — đúng khuôn lỗi đã gặp nhiều lần (xem `TRAPS.md`).

`OrchState` làm danh sách đó thành **dữ liệu kiểm được**: mỗi trường khai báo trong `metadata["rehydrate"]`
nguồn dựng lại của nó (`"audit:<action>"`, `"topic:<tên>"`, hay `RAM_ONLY`). Test
`test_orch_state_rehydrate.py` duyệt `fields(OrchState)` nên trường mới không khai báo nguồn là CI đỏ ngay,
không phải chờ một phiên chạy thật phát hiện hộ.

`Orchestrator` giữ nguyên bề mặt cũ: `install_aliases()` gắn property `o.processed → o.state.processed` cho
từng trường, nên ~28 file test và mọi module `orch/*` gọi `o.<tên>` như trước, đọc lẫn ghi.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, fields
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..events import Envelope
    from ..integration import Integration

RAM_ONLY = "ram-only"


def _src(nguon: str) -> dict[str, str]:
    return {"rehydrate": nguon}


@dataclass
class OrchState:
    """Toàn bộ trạng thái thay đổi được của một tiến trình orchestrator."""

    # --- hàng đợi và dấu đã xử lý ---
    processed: set[str] = field(default_factory=set, metadata=_src("audit:orchestrated"))
    queue: list[Envelope] = field(default_factory=list, metadata=_src("audit:orchestrated"))
    # event_id → agent đã chạy xong: crash giữa hai route thì agent đó không chạy lại (tốn token, sinh bản trùng)
    partial: dict[str, set[str]] = field(default_factory=dict, metadata=_src("causation_id"))
    deferred: dict[str, tuple[Envelope, str]] = field(
        default_factory=dict,
        # MỘT PHẦN, có chủ ý: chỉ event nào backend hẹn giờ rõ ràng mới quay lại `deferred`. Event hoãn vì
        # `gate:`/`paused:` không ghi `defer.until` nên mất khi restart — chúng tự vào lại hàng đợi và bị hoãn
        # lại theo trạng thái gate/pause HIỆN TẠI, đúng hơn là khôi phục một lý do có thể đã cũ.
        metadata=_src("audit:defer.until (một phần: mất event chưa có audit)"))
    # event_id → mốc monotonic sớm nhất được thử lại. Backend nói rõ "thử lại sau Ns" thì phải chờ đúng
    # chừng đó; hỏi lại sớm hơn vừa vô ích vừa làm bẩn audit-log (xem `_retry_deferred`).
    defer_until: dict[str, float] = field(
        default_factory=dict,
        metadata=_src("audit:defer.until (một phần: mất event chưa có audit)"))
    # nhắc nhở / hành động chỉ làm một lần (gate.remind, review.reassign, lesson...)
    once: set[str] = field(default_factory=set, metadata=_src("audit:once"))

    # --- kế hoạch, ticket, tích hợp ---
    plans: dict[str, dict[str, Any]] = field(default_factory=dict, metadata=_src("audit:plan.proposed"))
    # ticket đã merge vào nhánh tích hợp (khi approved, không đợi RC)
    integrated: set[str] = field(default_factory=set, metadata=_src("audit:integration.merged"))
    # ticket_id → số lần xung đột merge vào nhánh tích hợp. TÁCH KHỎI `Task.retry`: `request_changes` cũ dùng
    # chung bộ đếm với lỗi nội dung (review block, agent lỗi) và `max_retries=3` — một ticket đúng logic nhưng
    # thua cuộc đua merge (ticket khác gộp trước trong lúc nó còn đang review) cháy hết retry chỉ vì THỨ TỰ,
    # không vì làm sai gì. Đo được (2026-09-05): QLKH-011 hết 3 lần (2 lỗi CLI/review thật + 1 xung đột merge)
    # rồi `blocked` đúng lúc nội dung đã qua đủ ba reviewer. Xung đột không tính vào retry nội dung nữa; chỉ
    # chặn thật khi xung đột LẶP LẠI quá `MAX_CONFLICT_RETRIES` — dấu hiệu bế tắc cấu trúc (vd. nhiều ticket
    # cùng sửa một file interface), không phải may rủi thứ tự.
    conflict_retries: Counter[str] = field(default_factory=Counter,
                                           metadata=_src("audit:integration.conflict"))
    # spec chưa có threat model vì agent `security` lỗi
    missing_threat_model: set[str] = field(default_factory=set,
                                           metadata=_src("audit:threat_model.missing"))
    # project_id → số lần spec bị trả về spec-writer vì `kind=application` mà không có `runtime` hợp lệ (ADR-0031).
    # Về 0 khi người duyệt escalation cho chạy lại (`event.retried`).
    spec_runtime_reworks: Counter[str] = field(default_factory=Counter,
                                               metadata=_src("audit:spec.runtime_missing"))

    # --- release và bàn giao ---
    # release_id → sha ĐẦY ĐỦ của nhánh tích hợp lúc deploy staging: đúng nội dung QA đã hồi quy, và là sha được
    # giao khi production duyệt — nhánh tích hợp có thể đã đi tiếp (ticket khác merge) trong lúc chờ gate 3.
    release_sha: dict[str, str] = field(default_factory=dict, metadata=_src("audit:release.staged"))
    # release_id → {version, tag, sha, short, branch, previous}: bản đã giao (ADR-0027)
    delivered: dict[str, dict[str, Any]] = field(default_factory=dict, metadata=_src("audit:delivery.done"))
    void_releases: set[str] = field(default_factory=set, metadata=_src("audit:release.void"))

    # --- chờ người ---
    # project_id → {event_id, agent, topic, error}: dự án kẹt chờ người
    stalled: dict[str, dict[str, Any]] = field(default_factory=dict, metadata=_src("audit:project.stalled"))
    # event_id → số lần kẹt (mỗi lần một gate mới, không im lặng lần hai)
    stall_count: Counter[str] = field(default_factory=Counter, metadata=_src("audit:project.stalled"))
    # subject → {event_id, agent, topic}: event lỗi không nhánh nào nhận, chờ người
    unhandled: dict[str, dict[str, Any]] = field(default_factory=dict,
                                                 metadata=_src("audit:agent_error_unhandled"))
    # ticket_id → số quyết định escalation đã áp cho ticket đó. Đối xứng với `stall_count`: nếu không có nó,
    # ticket bị chặn LẦN HAI sinh ra đúng khoá `once` của lần một nên không mở gate nào nữa.
    escalation_decided: Counter[str] = field(default_factory=Counter, metadata=_src("audit:gate.decide"))
    # project_id → hồ sơ gate escalation nợ kiến trúc đang mở (ADR-0032)
    debt_gate: dict[str, dict[str, Any]] = field(default_factory=dict, metadata=_src("audit:debt.escalated"))
    paused: set[str] = field(default_factory=set, metadata=_src("topic:supervisor-actions"))

    # --- repo theo dự án (ADR-0025) ---
    project_repos: dict[str, Integration] = field(default_factory=dict,
                                                  metadata=_src("topic:research-requests"))
    bad_repos: set[str] = field(default_factory=set, metadata=_src("topic:research-requests"))

    # --- chỉ sống trong phiên ---
    stats: Counter[str] = field(default_factory=Counter, metadata=_src(RAM_ONLY))
    # `watch(reload=True)` bật: `run()` kiểm mã đổi GIỮA hai lô, không chỉ lúc rỗng
    reload_on_change: bool = field(default=False, metadata=_src(RAM_ONLY))


def _alias(ten: str) -> property:
    def doc(self: Any) -> Any:
        return getattr(self.state, ten)

    def ghi(self: Any, gia_tri: Any) -> None:
        setattr(self.state, ten, gia_tri)

    return property(doc, ghi, doc=f"Bí danh của `self.state.{ten}` (ADR-0034).")


def install_aliases(cls: type) -> None:
    """Gắn property `cls.<tên> → self.state.<tên>` cho từng trường của `OrchState`.

    Gọi một lần ngay sau thân class. Không có bước này thì mọi nơi gọi `o.processed` phải sửa thành
    `o.state.processed` — 28 file test và 5 module `orch/*`, đúng loại thay đổi ồn ào mà một refactor thuần
    không được phép gây ra."""
    for f in fields(OrchState):
        setattr(cls, f.name, _alias(f.name))
