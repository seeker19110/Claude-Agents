"""Dòng thời gian một chủ thể — ticket, release hay dự án — từ intake tới deploy (đặc tả nâng cấp 2026-09, B7).

`metrics` cho tổng, `diagnose` cho khuôn lỗi, `gate_brief` cho một gate. Không lệnh nào trả lời câu "ticket này đã
đi qua những gì, ai làm, tốn bao nhiêu, chờ người bao lâu, quay vòng mấy lần" theo THỨ TỰ THỜI GIAN — phiên vận hành
2026-09-05/06 muốn biết là phải tự truy SQLite. Lệnh này in đúng dòng thời gian đó, mỗi mốc một dòng:

    thời điểm · (+chờ từ mốc trước) · topic hoặc audit action · agent · tier/model · token/USD · tool đã gọi ·
    gate mở/quyết (ai, lý do) · retry

Nguồn: bus (replay mọi topic) + `audit-log` (evidence JSON của `produced:*`, `tools_used`, `llm_retry`, `gate.*`),
đọc bằng cùng cách `metrics`/`diagnose` đọc (`_ev`) — không parser mới. Chỉ đọc: `python -m company.trace` mở DB bằng
`gate_brief.open_read_only`; qua `orchestrator trace` dùng bus đã mở như `diagnose`.

    python -m company.orchestrator trace <TICKET_ID|REL-xxx|PROJECT_ID> [--json]
    python -m company.trace <subject> [--db company.sqlite] [--json]

Chủ thể không có trong bus → exit 1 và nói rõ đã tìm ở đâu.

**4L-7**: cấu trúc dòng / cách đọc `audit-log` / tổng kết / cách in nay ở `xagents_core.trace` (studio dùng chung).
Ở lại đây đúng hai thứ riêng của company: chủ thể là gì + event nào thuộc về nó (`resolve`, `_belongs` — đọc theo
`ticket_id`/`release_id`/`project_id`), và dòng của topic riêng company (`tasks`, `release-events`).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from xagents_core.trace import SKIP_ACTIONS as SKIP_ACTIONS
from xagents_core.trace import TraceError as TraceError
from xagents_core.trace import _hms as _hms
from xagents_core.trace import _wait as _wait
from xagents_core.trace import build, summarize
from xagents_core.trace import render as _render
from xagents_core.trace import run as _run

from .bus import InMemoryBus
from .events import Envelope
from .metrics import _ev

ERROR_ACTIONS = frozenset({"llm_error", "invalid_output", "handler_error", "budget_exhausted", "agent_error_unhandled"})


def _plan_of(pid: str, sid: Any) -> bool:
    return isinstance(sid, str) and sid.startswith(f"PLAN-{pid}-")


def resolve(bus: InMemoryBus, subject: str) -> dict[str, Any]:
    """Chủ thể là gì (ticket/release/project) và những id nào cùng một câu chuyện với nó.

    Ticket: chính nó + dự án (intake → spec → plan) + mọi RC chứa nó. Release: chính nó + các ticket trong RC + dự án.
    Dự án: mọi ticket, mọi RC của dự án."""
    tasks: dict[str, str] = {}      # ticket → project
    rcs: dict[str, dict[str, Any]] = {}  # release → payload
    projects: set[str] = set()
    for e in bus.replay():
        pid = e.payload.get("project_id")
        if isinstance(pid, str) and pid: projects.add(pid)
        if e.topic == "tasks": tasks.setdefault(e.key, str(pid or ""))
        elif e.topic == "release-candidates": rcs.setdefault(e.key, e.payload)
    if subject in tasks:
        pid = tasks[subject]; tids = {subject}
        rids = {r for r, p in rcs.items() if subject in (p.get("tickets") or [])}
        kind = "ticket"
    elif subject in rcs:
        pid = str(rcs[subject].get("project_id") or ""); rids = {subject}
        tids = set(rcs[subject].get("tickets") or []); kind = "release"
    elif subject in projects:
        pid = subject; tids = {t for t, p in tasks.items() if p == pid}
        rids = {r for r, p in rcs.items() if p.get("project_id") == pid}; kind = "project"
    else:
        raise TraceError(f"không có chủ thể {subject!r} trong bus: không phải ticket (topic tasks: {len(tasks)}), "
                         f"release (release-candidates: {len(rcs)}) hay dự án ({', '.join(sorted(projects)) or 'chưa có'})")
    return {"kind": kind, "subject": subject, "project_id": pid, "tickets": sorted(tids), "releases": sorted(rids)}


def _belongs(e: Envelope, scope: dict[str, Any]) -> bool:
    pid = scope["project_id"]; tids = set(scope["tickets"]); rids = set(scope["releases"])
    ids = {pid, f"SPEC-{pid}", *tids, *rids, *(f"UAT-{r}" for r in rids)} - {""}
    p = e.payload; d = _ev(p) if e.topic == "audit-log" else {}
    if e.topic == "audit-log" and str(p.get("action", "")) in SKIP_ACTIONS: return False
    # Ticket của người khác trong cùng dự án là nhiễu khi trace một ticket/release: loại theo ticket_id trước.
    for src in (p, d):
        t = src.get("ticket_id")
        if isinstance(t, str) and t and t not in tids and scope["kind"] != "project": return False
    cands = [e.key, p.get("ticket_id"), p.get("release_id"), p.get("project_id"),
             d.get("subject_id"), d.get("ticket_id"), d.get("release_id"), d.get("project_id")]
    if any(c in ids for c in cands if isinstance(c, str)): return True
    return _plan_of(pid, d.get("subject_id")) or _plan_of(pid, e.key)


def _domain(row: dict[str, Any], e: Envelope) -> bool:
    """Topic riêng của company: `tasks` mang retry + hint người giao, `release-events` mang môi trường + trạng thái."""
    p = e.payload
    if e.topic == "tasks":
        row["retry"] = int(p.get("retry") or 0)
        row["note"] = str(p.get("human_hint") or p.get("hint") or p.get("title") or "")[:120] or None
        return True
    if e.topic == "release-events":
        row["note"] = f"{p.get('env')} {p.get('status')}"
        return True
    return False


def trace(bus: InMemoryBus, subject: str, agents: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dòng thời gian + tổng kết của một chủ thể. `agents`: registry để điền tier (mặc định nạp `load_agents`)."""
    if agents is None:
        from .registry import load_agents
        agents = load_agents(check_owners=False)
    scope = resolve(bus, subject)
    rows = build((e for e in bus.replay() if _belongs(e, scope)), agents, _domain, ERROR_ACTIONS)
    summary = {**summarize(rows),
               "task_retries": max((r["retry"] for r in rows if r["topic"] == "tasks"), default=0),
               "deployed": [r["note"] for r in rows if r["topic"] == "release-events" and "deployed" in str(r["note"])]}
    return {"schema_version": 1, **scope, "rows": rows, "summary": summary}


def render(t: dict[str, Any]) -> str:
    s = t["summary"]
    header = [f"# trace {t['subject']} ({t['kind']}) — dự án {t['project_id'] or '?'}; ticket {', '.join(t['tickets']) or '-'}; "
              f"release {', '.join(t['releases']) or '-'}",
              f"# {s['rows']} mốc, {s['span_s']:.0f}s; {s['tokens']} token, {s['cost_usd']:.4f} USD; gate mở {s['gates_opened']} / "
              f"quyết {s['gates_decided']} (chờ tối đa {s['gate_wait_s_max']:.0f}s); retry ticket {s['task_retries']}, "
              f"retry model {s['llm_retries']}, lỗi {s['errors']}; deployed: {', '.join(s['deployed']) or 'chưa'}"]
    return _render(header, t["rows"])


def run(bus: InMemoryBus, subject: str, as_json: bool = False, agents: dict[str, Any] | None = None) -> int:
    """Lõi chung của `orchestrator trace` và `python -m company.trace`: in ra stdout, exit 1 khi không có chủ thể."""
    return _run(lambda: trace(bus, subject, agents), as_json, render, sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="dòng thời gian một ticket/release/dự án từ intake tới deploy (chỉ đọc)")
    ap.add_argument("subject"); ap.add_argument("--db", type=Path, default=Path("company.sqlite"))
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"): stream.reconfigure(encoding="utf-8")
    from .gate_brief import BriefError, open_read_only
    try:
        bus = open_read_only(ns.db)
    except BriefError as e:
        print(str(e), file=sys.stderr); return 3
    return run(bus, ns.subject, ns.json)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
