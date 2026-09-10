"""Human gate CLI: con người duyệt spec / plan / release / escalation; mọi quyết định ghi vào `audit-log`.

Trạng thái gate không lưu riêng: dựng lại từ replay `audit-log` (action gate.request / gate.decide) trên bus bền vững.

    python -m company.gate_cli list [--db company.sqlite]
    python -m company.gate_cli request plan PLAN-1 --by delivery-lead --checklist c4,contract
    python -m company.gate_cli approve PLAN-1 --by human:pm --reason "ok"
    python -m company.gate_cli reject|request_changes|hold|rollback <id> --by <ai> --reason <lý do>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, get_args

from xagents_core.gate_cli import SYSTEM_GATE_ACTOR as SYSTEM_GATE_ACTOR
from xagents_core.gate_cli import PersistentGate as CorePersistentGate
from xagents_core.gate_cli import trusted_decision as trusted_decision

from . import gate_risk
from .bus import InMemoryBus
from .events import AuditLog, Envelope
from .gate_risk import AUTOAPPROVE_ACTOR, AUTOAPPROVE_REASON_PREFIX
from .gates import GateKind, GateRequest, HumanGate, gate_approvers, gate_autoapprove_enabled
from .roles import LEAD_ACTOR, LEGACY_GATE_ACTORS, ROLE

DECISIONS: tuple[str, ...] = ("approve", "request_changes", "reject", "hold", "rollback")

# `SYSTEM_GATE_ACTOR` và `trusted_decision` ở `xagents_core.gate_cli` từ K3.7: cùng một allowlist tồn tại hai
# bản ở hai công ty đã phải vá cùng một lỗ hổng hai lần (2026-09-09). Re-export giữ nguyên chỗ nhập của mọi
# nơi gọi (`orch/scheduler.py`, console, test).


def trusted_autoapprove(env: Envelope) -> dict[str, Any] | None:
    """Quyết định `gate.decide` do CODE tự động qua gate rủi ro thấp (ADR-0011 §4 giai đoạn 3,
    `docs/thi-hanh/adr113.md` mục D) — nhánh tin cậy RIÊNG, tách khỏi `trusted_decision` (core, không đổi:
    core không biết `AUTOAPPROVE_ACTOR`/`RISK_RULES` của company, ADR-0001 §2).

    Chỉ tin khi CẢ BỐN: actor đúng `AUTOAPPROVE_ACTOR` ("code"); `reason` mang đúng tiền tố
    `AUTOAPPROVE_REASON_PREFIX` (đánh dấu bản ghi đi qua `gate_risk.request_gate`, không phải actor giả mạo
    tên "code" tự ghi thẳng lên bus); `by` trong evidence cũng là `AUTOAPPROVE_ACTOR` (khớp actor, như
    `trusted_decision` đòi `env.actor == by` cho người); và cờ `COMPANY_GATE_AUTOAPPROVE` đang bật NGAY LÚC
    hàm này chạy — đọc lại mỗi lần `apply()`, không cache: bật/tắt cờ giữa hai lần mở tiến trình không đổi
    bản ghi CŨ trong lịch sử (nó đã `apply` rồi), nhưng bản ghi MỚI luôn theo cờ hiện tại của tiến trình đang
    replay/subscribe."""
    if env.topic != "audit-log" or env.payload.get("action") != "gate.decide": return None
    if env.actor != AUTOAPPROVE_ACTOR or not gate_autoapprove_enabled(): return None
    try: d = json.loads(env.payload.get("evidence") or "{}")
    except (ValueError, TypeError): return None
    if not isinstance(d, dict): return None
    sid = d.get("subject_id")
    if not isinstance(sid, str) or not sid: return None
    if d.get("by") != AUTOAPPROVE_ACTOR: return None
    if not isinstance(d.get("decision"), str): return None
    reason = d.get("reason")
    if not isinstance(reason, str) or not reason.startswith(AUTOAPPROVE_REASON_PREFIX): return None
    # Tên hàng phải khớp một hàng THẬT ĐANG CÓ trong `RISK_RULES` lúc replay này chạy (đọc `gate_risk.RISK_RULES`
    # qua module, không `from .gate_risk import RISK_RULES` — tên import trực tiếp đóng băng giá trị tại thời
    # điểm nhập module, không thấy bảng đổi sau đó, kể cả khi test monkeypatch bảng). Thiếu bước này, một
    # envelope `reason="auto-risk:<tên bịa>"` vẫn được tin nếu chỉ đúng tiền tố — tiền tố là hằng công khai
    # trong mã nguồn, không phải bí mật (sc-security, adr113 2026-09-10).
    rule_name = reason[len(AUTOAPPROVE_REASON_PREFIX):]
    if not any(r.name == rule_name for r in gate_risk.RISK_RULES): return None
    return d


class PersistentGate(CorePersistentGate[Envelope, AuditLog], HumanGate):
    """HumanGate + ghi mọi request/decision lên bus (audit-log) và dựng lại từ replay khi mở.

    Cơ chế ở core; ở đây chỉ nói core dùng LỚP nào của company (`Envelope`, `AuditLog`, `GateRequest`) — nếu
    không, `replay()` trả về envelope core và mọi kiểm tra `topic: Topic` biến mất."""

    #: Vai được mở gate ở công ty gia công (ADR-0008), đo từ chính các call site `gate.request`:
    #: `product` (gate `spec`, `orch/ticket_fsm.py`), `supervisor` (gate `escalation`, `orch/gates_flow.py`),
    #: `ops` (gate `acceptance` + escalation của `release_fsm`), `delivery-lead` (gate `release`, `delivery.py`).
    #: Người (`human:*`) không cần có tên ở đây — gate CLI là đường của người.
    #: `LEGACY_GATE_ACTORS`: tên trước ADR-0037 còn trong bus cũ — đo trên `company.sqlite` thật, xem `roles.py`.
    REQUEST_ACTORS = frozenset({ROLE.PRODUCT, ROLE.SUPERVISOR, ROLE.OPS, LEAD_ACTOR}) | LEGACY_GATE_ACTORS

    def _trusted(self, env: Envelope) -> dict[str, Any] | None:
        """Điểm mở duy nhất của phép kiểm tin cậy (core): thử đường cũ (người / orchestrator+UAT) trước, rồi
        thử nhánh MỚI của company (`trusted_autoapprove`) — thứ tự này cố ý, không được đảo: `AUTOAPPROVE_ACTOR`
        không phải người và không phải `"orchestrator"` nên không bao giờ khớp đường cũ, nhưng giữ thứ tự rõ
        ràng để đọc code không phải suy luận."""
        return trusted_decision(env, uat_prefix=self.UAT_PREFIX) or trusted_autoapprove(env)

    def __init__(self, bus: InMemoryBus, **kw):
        super().__init__(bus, envelope_cls=Envelope, audit_cls=AuditLog, request_cls=GateRequest, **kw)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Human gate")
    ap.add_argument("--db", type=Path, default=Path("company.sqlite"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    rq = sub.add_parser("request"); rq.add_argument("kind", choices=get_args(GateKind)); rq.add_argument("subject_id")
    rq.add_argument("--by", required=True); rq.add_argument("--checklist", default="")
    for d in DECISIONS:
        p = sub.add_parser(d); p.add_argument("subject_id"); p.add_argument("--by", required=True); p.add_argument("--reason", default="")
    ns = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")  # Windows console cp1252

    from .sqlite_bus import SQLiteBus
    bus = SQLiteBus(ns.db); gate = PersistentGate(bus, approvers=gate_approvers())
    if ns.cmd == "list":
        remind, overdue = gate.due()
        for sid, r in gate.pending.items():
            flag = " OVERDUE" if sid in overdue else (" remind" if sid in remind else "")
            print(f"{sid:<12} {r.kind:<10} by={r.created_by or '-':<16} checklist={','.join(r.checklist)}{flag}")
        if not gate.pending: print("(không có gate chờ)")
        return 0
    if ns.cmd == "request":
        items = [c.strip() for c in ns.checklist.split(",") if c.strip()]
        if not ns.subject_id.strip():
            print("subject_id không được rỗng", file=sys.stderr); return 2
        if not items:  # gate không có gì để kiểm thì việc duyệt chỉ là bấm nút
            print("cần --checklist (danh sách mục người duyệt phải kiểm, ngăn cách bằng dấu phẩy)", file=sys.stderr)
            return 2
        try:  # `--by` là vai không có quyền mở gate (ADR-0008): báo như mọi lỗi quyền khác, không traceback
            gate.request(GateRequest(kind=ns.kind, subject_id=ns.subject_id, created_by=ns.by, checklist=items))
        except PermissionError as e:
            print(str(e), file=sys.stderr); return 3
        print(f"requested {ns.kind} {ns.subject_id}"); return 0
    try:
        done = gate.decide(ns.subject_id, ns.cmd, by=ns.by, reason=ns.reason)
    except KeyError:
        print(f"không có gate chờ: {ns.subject_id}", file=sys.stderr); return 2
    except PermissionError as e:
        print(str(e), file=sys.stderr); return 3
    print(f"{done.subject_id}: {done.decision} by {done.decided_by}"); return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
