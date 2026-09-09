"""Gate `keeper` = cơ chế chung ở `xagents_core.gates` / `xagents_core.gate_cli` + vốn từ của công ty bảo trì.

Ba điều đặc tả §9 nói SAI, đã đo lại và sửa ở đây (`docs/thi-hanh/keeper.md` §C-BT7):

1. `HumanGate` **không có** `approve()`/`reject()`. Chỉ có `decide(subject_id, decision, by, reason, *,
   enforce)` (`xagents-core/src/xagents_core/gates.py:87`). Mọi nơi trong `keeper` gọi `decide(...)`.
2. Thế hệ chống-trùng của một gate là `GateRequest.seq`, do `HumanGate.request()` gán
   (`gates.py:84`) — KHÔNG phải `created_at`. `created_at` đổi sau mỗi lần dựng lại từ replay, nên khoá `once`
   lấy nó làm thế hệ sẽ nhắc/escalate lại một gate đã nhắc rồi.
3. Cạm bẫy "`gate_cli approve` là **reopen**, không phải close" viết SAI (đo ở `gates.py:87-94` và
   `software-company/src/company/orch/gates_flow.py:110-117`): `decide()` **đóng** gate — nó bỏ `subject_id`
   khỏi `pending` và đẩy bản ghi vào `history`, đúng một lần, bất kể `decision` là gì. "Mở lại" là **nghĩa
   riêng** mà orchestrator của company gán cho một SỐ escalation: nó tự phát `supervisor-actions{action:
   "resume"}` theo LOẠI subject sau khi gate đóng. `keeper` muốn một ticket bảo trì được làm lại thì phải tự
   phát `resume` như thế; trông vào ngữ nghĩa của `approve` là trông vào thứ không tồn tại ở lớp gate.

**Tên biến môi trường KHÔNG viết cứng ở đây**: `CORE.approvers_env` ghép `KEEPER_` một chỗ duy nhất
(`xagents-core/src/xagents_core/config.py:85-88`). Lõi không được biết tên công ty nào (I6/ADR-0001 §2), và
`keeper` không được có bản sao thứ hai của cùng một tên.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from xagents_core.bus import InMemoryBus as CoreInMemoryBus
from xagents_core.gate_cli import PersistentGate as CorePersistentGate
from xagents_core.gates import GateRequest as CoreGateRequest
from xagents_core.gates import HumanGate as CoreHumanGate
from xagents_core.gates import approvers

from .core import CORE
from .events import AuditLog, Envelope

__all__ = [
    "APPROVERS_ENV", "CHECKLIST", "GATE_ACTOR", "REQUEST_ACTORS", "Decision", "GateKind", "GateRequest",
    "HumanGate", "PersistentGate", "gate_approvers", "request_gate",
]

# `patch`: một patch tier `high` xin được mở PR; `release`: dòng CHANGELOG/nhật ký trước khi PR rời tay
# `keeper`; `escalation`: ticket bảo trì kẹt hoặc nợ quá hạn (`ledger.overdue`).
GateKind = Literal["patch", "release", "escalation"]
Decision = Literal["approve", "request_changes", "reject", "hold", "rollback", "pending"]

#: Biến khai người được duyệt gate — SUY RA từ `CORE`, không phải một chuỗi thứ hai đứng cạnh.
APPROVERS_ENV = CORE.approvers_env

#: Vai mà `keeper` cho phép TẠO gate (allowlist ADR-0008, `xagents_core/gate_cli.py:REQUEST_ACTORS`), đo từ
#: chính các call site: `keeper-supervisor` (orchestrator xin gate `patch`/`escalation`), `triager` (ticket
#: tier `high` sinh ra ngay lúc triage), `release-clerk` (gate `release`). `patcher`/`refactorer`/
#: `regression-guard` KHÔNG có tên ở đây: vai viết patch không được tự mở cái cổng xét patch của mình.
#: Người (`human:*`) không cần có tên — gate CLI là đường của người.
REQUEST_ACTORS = frozenset({"keeper-supervisor", "triager", "release-clerk"})

#: Actor mặc định khi orchestrator (code) xin gate thay công ty.
GATE_ACTOR = "keeper-supervisor"

#: Checklist gate `keeper` (`DAC-TA-KEEPER.md` §9). Bản văn xuôi cho người ký nằm ở `keeper/gates/
#: checklists.md` (BT7.b); đây là bản mã, đi kèm mọi `GateRequest` để người duyệt thấy đúng năm câu hỏi.
CHECKLIST: tuple[str, ...] = (
    "risk_tier đúng bậc và lý do xếp bậc kiểm được",
    "bằng chứng đo hai chiều: tắt bản sửa CI ĐỎ, bật lại XANH",
    "báo cáo rà họ lỗi có cả chỗ an toàn kèm lý do",
    "ngân sách còn chỗ: không PR bảo trì nào đang mở",
    "không chạm đường cấm (.git/, .github/, llm.yaml, *.sqlite*, agents/, skills/)",
)


@dataclass
class GateRequest(CoreGateRequest):
    """Trường y hệt lõi; lớp riêng để `keeper` nói về gate của mình bằng tên của mình (khuôn company)."""


def gate_approvers(cfg: Any = None) -> frozenset[str]:
    """Người được duyệt gate `keeper`: biến `CORE.approvers_env` thắng, sau đó cấu hình `gate.approvers`.
    Không đặt biến → rỗng → chỉ four-eyes (hành vi mặc định của lõi)."""
    return approvers(APPROVERS_ENV, cfg)


class HumanGate(CoreHumanGate):
    """Không bao giờ tự đi tiếp. `decided_by != created_by`; `approvers` (nếu đặt) giới hạn ai được duyệt."""

    APPROVERS_SOURCE = f"danh sách người duyệt ({APPROVERS_ENV} / gate.approvers)"

    # Thu hẹp kiểu về `GateRequest` của keeper (lõi khai lớp cơ sở).
    pending: dict[str, GateRequest]  # type: ignore[assignment]
    history: list[GateRequest]  # type: ignore[assignment]


class PersistentGate(CorePersistentGate[Envelope, AuditLog], HumanGate):
    """HumanGate + ghi mọi request/decide lên `audit-log` và dựng lại từ replay khi mở."""

    #: `keeper` KHÔNG có khái niệm nghiệm thu khách hàng (nó bảo trì repo, không giao sản phẩm cho ai ký),
    #: nên nhánh "actor hệ thống đóng gate UAT bằng chữ ký khách" của `trusted_decision` bị TẮT HẲN. Để
    #: nguyên `"UAT-"` là mở sẵn một đường cho actor không-người đóng gate mà công ty này không cần tới.
    UAT_PREFIX: str | None = None

    REQUEST_ACTORS: frozenset[str] | None = REQUEST_ACTORS

    def __init__(self, bus: CoreInMemoryBus[Envelope], **kw: Any) -> None:
        super().__init__(bus, envelope_cls=Envelope, audit_cls=AuditLog, request_cls=GateRequest, **kw)


def request_gate(gate: PersistentGate, kind: GateKind, subject_id: str, *,
                 created_by: str = GATE_ACTOR, checklist: tuple[str, ...] = CHECKLIST) -> GateRequest:
    """Xin một gate `keeper`. Ném `PermissionError` nếu `created_by` không có quyền TẠO gate — chiều ghi ném
    thay vì im lặng (lý do ở `xagents_core/gate_cli.py:request`)."""
    return gate.request(GateRequest(kind=kind, subject_id=subject_id, checklist=list(checklist),
                                    created_by=created_by))  # type: ignore[return-value]
