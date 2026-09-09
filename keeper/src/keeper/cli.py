"""`keeper run` — chạy khô là mặc định của việc đọc, không phải một chế độ phụ (BT5, `DAC-TA-KEEPER.md` §7).

`keeper run --dry-run` in ra kế hoạch **ticket → thao tác → file sẽ đụng** và KHÔNG chạm file nào: không mở
worktree, không chạy `make`, không ghi một byte. Ca kiểm thử băm cả cây thư mục trước/sau để chứng minh, và ca
chiều ngược chạy thật để chứng minh phép băm có phát hiện được thay đổi.

Vì sao chỉ `fix_docs` thi hành được ở CLI: `bump_dependency` cần phiên bản đích (chưa nằm trong `Ticket`), và
`regen_derived` cần `make` chạy trong worktree đã mở. Cả hai thuộc vòng lặp orchestrator (BT7). CLI nói thẳng
"bỏ qua" cho chúng thay vì im lặng bỏ sót — một dòng kế hoạch không được thi hành mà không ai thấy đúng là
khuôn lỗi "số xanh vì rỗng".
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from .events import Ticket
from .patcher import HUMAN_ONLY_SEGMENTS, fix_docs
from .worktree import SharedCheckoutRefused

Operation = str
DERIVED_HINTS = ("tests/golden", ".claude/agents", "golden")


@dataclass
class Plan:
    """Một dòng kế hoạch: ticket nào, thao tác gì, đụng file nào, và (nếu bỏ qua) vì sao."""
    ticket_id: str
    operation: Operation
    files: list[str]
    reason: str = ""


def plan_for(ticket: Ticket) -> Plan:
    """Xếp ticket vào một trong ba thao tác, hoặc `needs_human`.

    `risk_tier == "high"` và mọi thứ chạm `agents/`/`skills/` đều là `needs_human` — cùng câu cấm đã ép trong
    `patcher.check_path`, nhắc lại ở lớp kế hoạch để người đọc `--dry-run` thấy trước, chứ không phải để thay
    thế nó (chốt thật vẫn nằm ở `patcher`)."""
    subject = ticket.subject.replace("\\", "/")
    parts = subject.split("/")
    if ticket.risk_tier == "high" or any(seg in parts for seg in HUMAN_ONLY_SEGMENTS):
        return Plan(ticket.ticket_id, "needs_human", [subject],
                    reason="bảy bước CONTRIBUTING.md §3 / tier high — người quyết")
    if any(h in subject for h in DERIVED_HINTS):
        return Plan(ticket.ticket_id, "regen_derived", [subject], reason="cần `make` trong worktree (BT7)")
    if subject.endswith((".md", ".rst", ".txt")):
        return Plan(ticket.ticket_id, "fix_docs", [subject])
    return Plan(ticket.ticket_id, "bump_dependency", ["pyproject.toml"],
                reason="chưa có phiên bản đích trong Ticket (BT7)")


def _load(path: Path) -> list[Ticket]:
    return [Ticket.model_validate(x) for x in json.loads(path.read_text(encoding="utf-8"))]


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    try:
        tickets = _load(Path(args.tickets))
    except (ValidationError, ValueError, OSError) as e:
        print(f"không đọc được {args.tickets}: {e}", file=sys.stderr)
        return 2
    print(f"keeper run — {'CHẠY KHÔ (không chạm file nào)' if args.dry_run else 'THI HÀNH'} trên {root}")
    for t in tickets:
        plan = plan_for(t)
        ghi_chu = f"  [{plan.reason}]" if plan.reason else ""
        print(f"  {t.ticket_id} → {plan.operation} → {', '.join(plan.files)}{ghi_chu}")
        if args.dry_run:
            continue
        if plan.operation != "fix_docs":
            print(f"    bỏ qua: {plan.reason or plan.operation} chưa nối vào cli")
            continue
        try:
            fix_docs(root, t.ticket_id, changelog_line=f"- keeper: {t.subject} ({t.ticket_id})",
                     changelog=plan.files[0])
        except SharedCheckoutRefused as e:
            print(f"từ chối ghi: {e}", file=sys.stderr)
            return 3
        print(f"    đã ghi {plan.files[0]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="keeper", description="công ty bảo trì X-Agents")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="chạy một vòng vá theo danh sách ticket")
    run.add_argument("--tickets", required=True, help="file JSON danh sách Ticket")
    # KHÔNG có mặc định: `--root .` ngầm biến một lệnh gõ nhầm thư mục thành lệnh ghi vào checkout chung
    # (`patcher` sẽ từ chối, nhưng người gõ phải nói ra mình định ghi vào đâu — chốt và ý định là hai việc).
    run.add_argument("--root", required=True, help="worktree PHỤ của keeper để áp patch (bắt buộc)")
    run.add_argument("--dry-run", action="store_true", help="chỉ in kế hoạch, không chạm file nào")
    run.set_defaults(func=_run)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
