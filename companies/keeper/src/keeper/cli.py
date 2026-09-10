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
from typing import get_args

from pydantic import ValidationError

from .drift import scan
from .events import Ticket
from .gates import GateKind
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


def _watch(args: argparse.Namespace) -> int:
    """`keeper watch` — vòng lặp `watch → triage → patch → verify → gate? → release` (BT7).

    `GitHubReader` dựng ở ĐÂY chứ không trong `KeeperOrchestrator`: adapter `gh` là thứ chạm ra ngoài máy,
    nên nó là THAM SỐ của orchestrator (test tiêm `FakeGitHub`), không phải một phụ thuộc ẩn."""
    from .github import GitHubReader
    from .orchestrator import KeeperOrchestrator

    repo = Path(args.repo).resolve()
    orc = KeeperOrchestrator(Path(args.db), repo, GitHubReader(repo))
    orc.watch(interval=args.interval, max_ticks=args.max_ticks)
    return 0


#: Mọi giá trị `decide()` nhận. Cả năm đều ĐÓNG gate (`gates.py` mục 3) — không giá trị nào "mở lại" ticket.
GATE_DECISIONS: tuple[str, ...] = ("approve", "request_changes", "reject", "hold", "rollback")


def _gate(args: argparse.Namespace) -> int:
    """`keeper gate` — đường của NGƯỜI vào sổ gate (`gates.py`), sao khuôn `company/gate_cli.py`.

    Không có nó, một ticket `risk_tier="high"` kẹt vĩnh viễn ở cổng `gate` của `pr_blockers()`: orchestrator
    chỉ XIN gate, không ai đóng được, và công ty tự khoá chính mình. Trạng thái gate không lưu riêng —
    `PersistentGate` dựng lại từ replay `audit-log` trên cùng `keeper.sqlite`, nên lệnh này là một tiến trình
    KHÁC vòng watch và quyết định tới được orchestrator qua `bus.poll()`.

    `--by` bắt buộc là NGƯỜI (`is_human`). Đây là nửa còn lại của `trusted_decision`: nó chỉ tin envelope có
    `env.actor` hình người VÀ trùng `by`, còn `PersistentGate.decide` ghi envelope dưới actor `by`. Chặn ngay
    ở đây để `--by patcher` báo lỗi thay vì ghi lên bus một bản ghi mà mọi người tiêu thụ đều lặng lẽ bỏ qua —
    "đã bấm mà không có gì xảy ra" đúng là khuôn hỏng không tự khai báo."""
    from xagents_core.bus import is_human

    from .bus import KeeperBus
    from .core import CORE
    from .gates import CHECKLIST, GateRequest, PersistentGate, gate_approvers

    gate = PersistentGate(KeeperBus(CORE, Path(args.db)), approvers=gate_approvers())
    if args.gate_cmd == "list":
        for sid, r in gate.pending.items():
            print(f"{sid}  {r.kind}  by={r.created_by or '-'}  checklist={len(r.checklist)} mục")
        if not gate.pending:
            print("(không có gate chờ)")
        return 0
    if args.gate_cmd == "request":
        try:  # vai không có quyền mở gate (ADR-0008): báo như mọi lỗi quyền khác, không traceback
            gate.request(GateRequest(kind=args.kind, subject_id=args.subject_id, created_by=args.by,
                                     checklist=list(CHECKLIST)))
        except PermissionError as e:
            print(str(e), file=sys.stderr)
            return 3
        print(f"requested {args.kind} {args.subject_id}")
        return 0
    if not is_human(args.by):
        print(f"{args.by} không phải người (`human` / `human:<tên>`) — chỉ người quyết được gate "
              f"(`trusted_decision`, xagents_core/gate_cli.py)", file=sys.stderr)
        return 3
    try:
        done = gate.decide(args.subject_id, args.gate_cmd, by=args.by, reason=args.reason)
    except KeyError:
        print(f"không có gate chờ: {args.subject_id}", file=sys.stderr)
        return 2
    except PermissionError as e:
        print(str(e), file=sys.stderr)
        return 3
    print(f"{done.subject_id}: {done.decision} by {done.decided_by}")
    return 0


def _drift(args: argparse.Namespace) -> int:
    """Phép (a)(b)(c) của `drift.scan` trên chính repo này — cổng máy cho luật cấm §5 và luật bắt buộc §10.

    Bộ dò đã có từ BT-keeper và phủ 100% test, nhưng KHÔNG workflow nào gọi nó, nên ba PR (#192, #208, #209)
    merge thiếu dòng CHANGELOG mà không cổng nào đỏ — công cụ tự soi chỉ có giá trị khi có thứ chạy nó.
    Thoát khác 0 khi còn tín hiệu, để CI dùng trực tiếp."""
    repo = Path(args.repo)
    signals = scan(
        claude_agents_dir=repo / ".claude" / "agents",
        golden_agents_dir=repo / "companies" / "software-company" / "tests" / "golden" / "agents",
        company_root=repo / "companies" / "software-company",   # ADR-0011
        repo=repo,
        changelog=repo / "CHANGELOG.md",
    )
    for s in signals:
        print(f"DRIFT {s.subject}: {s.detail}")
    if not signals:
        print("drift: sạch (bản dẫn xuất khớp nguồn, golden khớp agent, mọi PR merged có dòng CHANGELOG)")
        return 0
    print(f"\n{len(signals)} tín hiệu lệch — xem AGENTS.md luật cấm §5 và luật bắt buộc §10.")
    return 1


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
    watch = sub.add_parser("watch", help="vòng lặp orchestrator (BT7)")
    watch.add_argument("--db", required=True, help="file bus bền vững (keeper.sqlite)")
    watch.add_argument("--repo", required=True, help="repo để hỏi `gh` (chỉ đọc)")
    watch.add_argument("--interval", type=float, default=300.0, help="giây giữa hai nhịp")
    watch.add_argument("--max-ticks", type=int, default=None, help="dừng sau bấy nhiêu nhịp (mặc định: mãi)")
    watch.set_defaults(func=_watch)
    gate = sub.add_parser("gate", help="sổ human gate: list / request / duyệt (BT7)")
    gate.add_argument("--db", required=True, help="file bus bền vững (keeper.sqlite)")
    gsub = gate.add_subparsers(dest="gate_cmd", required=True)
    gsub.add_parser("list", help="gate đang chờ người")
    rq = gsub.add_parser("request", help="mở một gate")
    rq.add_argument("kind", choices=get_args(GateKind))
    rq.add_argument("subject_id")
    rq.add_argument("--by", required=True, help="actor mở gate (vai trong REQUEST_ACTORS, hoặc human:<tên>)")
    for d in GATE_DECISIONS:
        p = gsub.add_parser(d, help=f"đóng gate với quyết định {d}")
        p.add_argument("subject_id")
        p.add_argument("--by", required=True, help="NGƯỜI duyệt (`human:<tên>`)")
        p.add_argument("--reason", default="", help="lý do — người sau đọc bản ghi này, không đọc được đầu bạn")
    gate.set_defaults(func=_gate)
    drift_p = sub.add_parser("drift", help="so bản dẫn xuất/golden/CHANGELOG với nguồn (thuần cục bộ)")
    drift_p.add_argument("--repo", default=".", help="gốc repo cần soi (mặc định thư mục hiện tại)")
    drift_p.set_defaults(func=_drift)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
