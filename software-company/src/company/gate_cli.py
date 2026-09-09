"""Human gate CLI: con người duyệt spec / plan / release / escalation; mọi quyết định ghi vào `audit-log`.

Trạng thái gate không lưu riêng: dựng lại từ replay `audit-log` (action gate.request / gate.decide) trên bus bền vững.

    python -m company.gate_cli list [--db company.sqlite]
    python -m company.gate_cli request plan PLAN-1 --by delivery-lead --checklist c4,contract
    python -m company.gate_cli approve PLAN-1 --by human:pm --reason "ok"
    python -m company.gate_cli reject|request_changes|hold|rollback <id> --by <ai> --reason <lý do>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import get_args

from xagents_core.gate_cli import SYSTEM_GATE_ACTOR as SYSTEM_GATE_ACTOR
from xagents_core.gate_cli import PersistentGate as CorePersistentGate
from xagents_core.gate_cli import trusted_decision as trusted_decision

from .bus import InMemoryBus
from .events import AuditLog, Envelope
from .gates import GateKind, GateRequest, HumanGate, gate_approvers

DECISIONS: tuple[str, ...] = ("approve", "request_changes", "reject", "hold", "rollback")

# `SYSTEM_GATE_ACTOR` và `trusted_decision` ở `xagents_core.gate_cli` từ K3.7: cùng một allowlist tồn tại hai
# bản ở hai công ty đã phải vá cùng một lỗ hổng hai lần (2026-09-09). Re-export giữ nguyên chỗ nhập của mọi
# nơi gọi (`orch/scheduler.py`, console, test).


class PersistentGate(CorePersistentGate[Envelope, AuditLog], HumanGate):
    """HumanGate + ghi mọi request/decision lên bus (audit-log) và dựng lại từ replay khi mở.

    Cơ chế ở core; ở đây chỉ nói core dùng LỚP nào của company (`Envelope`, `AuditLog`, `GateRequest`) — nếu
    không, `replay()` trả về envelope core và mọi kiểm tra `topic: Topic` biến mất."""

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
        gate.request(GateRequest(kind=ns.kind, subject_id=ns.subject_id, created_by=ns.by, checklist=items))
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
