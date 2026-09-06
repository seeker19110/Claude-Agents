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
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .bus import InMemoryBus
from .events import Envelope
from .metrics import _ev

# Audit chỉ dùng cho việc nội bộ của orchestrator, không nói gì về chủ thể: bỏ khỏi dòng thời gian.
SKIP_ACTIONS = frozenset({"once", "orchestrated"})
ERROR_ACTIONS = frozenset({"llm_error", "invalid_output", "handler_error", "budget_exhausted", "agent_error_unhandled"})


class TraceError(Exception): ...


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


def _row(e: Envelope, prev: datetime | None, agents: dict[str, Any]) -> dict[str, Any]:
    p = e.payload
    row: dict[str, Any] = {"at": e.ts.isoformat(), "wait_s": round((e.ts - prev).total_seconds(), 3) if prev else 0.0,
                           "topic": e.topic, "action": None, "actor": e.actor, "agent": None, "tier": None, "model": None,
                           "tokens": 0, "cost_usd": 0.0, "tools": None, "gate": None, "retry": None, "error": None,
                           "note": None, "event_id": e.event_id}
    spec = agents.get(e.actor)
    if spec is not None:
        row["agent"] = e.actor; row["tier"] = getattr(spec, "model_tier", None)
    if e.topic == "tasks":
        row["retry"] = int(p.get("retry") or 0)
        row["note"] = str(p.get("human_hint") or p.get("hint") or p.get("title") or "")[:120] or None
        return row
    if e.topic != "audit-log":
        note = p.get("status") or p.get("verdict") or p.get("decision") or p.get("summary")
        if e.topic == "release-events": note = f"{p.get('env')} {p.get('status')}"
        row["note"] = str(note)[:120] if note else None
        return row
    act = str(p.get("action", "")); d = _ev(p); row["action"] = act
    row["tokens"] = int(p.get("tokens") or 0); row["cost_usd"] = round(float(p.get("cost_usd") or 0.0), 6)
    if act.startswith("produced:"):
        row["model"] = d.get("model"); row["note"] = f"{d.get('duration_ms', 0)} ms, {d.get('turns', 0)} lượt"
    elif act == "tools_used":
        calls = d.get("calls") or {}
        row["tools"] = {str(k): int(v) for k, v in calls.items()} if isinstance(calls, dict) else None
    elif act == "llm_retry":
        row["retry"] = int(d.get("attempts") or 1); row["note"] = "; ".join(str(x) for x in d.get("notes") or [])[:120] or None
    elif act in {"gate.request", "gate.decide"}:
        row["gate"] = {"subject_id": d.get("subject_id"), "kind": d.get("kind"), "decision": d.get("decision"),
                       "by": d.get("by") or d.get("created_by"), "reason": str(d.get("reason") or "")[:200] or None}
    elif act in ERROR_ACTIONS:
        row["error"] = str(d.get("error") or p.get("evidence") or act)[:200]
    else:
        row["note"] = str(p.get("evidence") or "")[:120] or None
    return row


def trace(bus: InMemoryBus, subject: str, agents: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dòng thời gian + tổng kết của một chủ thể. `agents`: registry để điền tier (mặc định nạp `load_agents`)."""
    if agents is None:
        from .registry import load_agents
        agents = load_agents(check_owners=False)
    scope = resolve(bus, subject)
    rows: list[dict[str, Any]] = []; prev: datetime | None = None
    gate_kind: dict[str, Any] = {}  # `gate.decide` không ghi kind: lấy từ `gate.request` cùng subject trước đó
    for e in bus.replay():
        if not _belongs(e, scope): continue
        r = _row(e, prev, agents); prev = e.ts
        if r["gate"]:
            if r["gate"]["kind"]: gate_kind[str(r["gate"]["subject_id"])] = r["gate"]["kind"]
            else: r["gate"]["kind"] = gate_kind.get(str(r["gate"]["subject_id"]))
        rows.append(r)
    gates = [r["gate"] for r in rows if r["gate"]]
    opened = [g for g, r in ((r["gate"], r) for r in rows if r["gate"]) if r["action"] == "gate.request"]
    decided = [g for g, r in ((r["gate"], r) for r in rows if r["gate"]) if r["action"] == "gate.decide"]
    waits = [r["wait_s"] for r in rows if r["action"] == "gate.decide"]
    summary = {"rows": len(rows), "tokens": sum(r["tokens"] for r in rows), "cost_usd": round(sum(r["cost_usd"] for r in rows), 6),
               "gates_opened": len(opened), "gates_decided": len(decided), "gates": gates,
               "gate_wait_s_max": max(waits, default=0.0),
               "task_retries": max((r["retry"] for r in rows if r["topic"] == "tasks"), default=0),
               "llm_retries": sum(r["retry"] or 0 for r in rows if r["action"] == "llm_retry"),
               "errors": sum(1 for r in rows if r["error"]),
               "span_s": round((datetime.fromisoformat(rows[-1]["at"]) - datetime.fromisoformat(rows[0]["at"])).total_seconds(), 3)
               if rows else 0.0,
               "deployed": [r["note"] for r in rows if r["topic"] == "release-events" and "deployed" in str(r["note"])]}
    return {"schema_version": 1, **scope, "rows": rows, "summary": summary}


def _hms(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%m-%d %H:%M:%S")


def _wait(s: float) -> str:
    if s < 60: return f"+{s:.0f}s"
    if s < 3600: return f"+{s / 60:.0f}m"
    return f"+{s / 3600:.1f}h"


def render(t: dict[str, Any]) -> str:
    s = t["summary"]
    out = [f"# trace {t['subject']} ({t['kind']}) — dự án {t['project_id'] or '?'}; ticket {', '.join(t['tickets']) or '-'}; "
           f"release {', '.join(t['releases']) or '-'}",
           f"# {s['rows']} mốc, {s['span_s']:.0f}s; {s['tokens']} token, {s['cost_usd']:.4f} USD; gate mở {s['gates_opened']} / "
           f"quyết {s['gates_decided']} (chờ tối đa {s['gate_wait_s_max']:.0f}s); retry ticket {s['task_retries']}, "
           f"retry model {s['llm_retries']}, lỗi {s['errors']}; deployed: {', '.join(s['deployed']) or 'chưa'}", ""]
    for r in t["rows"]:
        what = f"{r['topic']}/{r['action']}" if r["action"] else r["topic"]
        who = r["agent"] or r["actor"]
        if r["model"]: who += f" [{r['tier'] or '?'}/{r['model']}]"
        elif r["tier"]: who += f" [{r['tier']}]"
        parts = [f"{_hms(r['at'])} {_wait(r['wait_s']):>7}  {what:<34} {who}"]
        if r["tokens"]: parts.append(f"{r['tokens']} tok ${r['cost_usd']:.4f}")
        if r["tools"]: parts.append("tool " + " ".join(f"{k}×{v}" for k, v in sorted(r["tools"].items())))
        if r["gate"]:
            g = r["gate"]
            parts.append(f"gate {g['kind'] or ''} {g['subject_id']} {'quyết ' + str(g['decision']) if g['decision'] else 'mở'} "
                         f"by {g['by'] or '?'}" + (f": {g['reason']}" if g["reason"] else ""))
        if r["retry"]: parts.append(f"retry={r['retry']}")
        if r["error"]: parts.append(f"LỖI {r['error']}")
        if r["note"]: parts.append(r["note"])
        out.append("  | ".join(parts))
    return "\n".join(out)


def run(bus: InMemoryBus, subject: str, as_json: bool = False, agents: dict[str, Any] | None = None) -> int:
    """Lõi chung của `orchestrator trace` và `python -m company.trace`: in ra stdout, exit 1 khi không có chủ thể."""
    try:
        t = trace(bus, subject, agents)
    except TraceError as e:
        print(str(e), file=sys.stderr); return 1
    print(json.dumps(t, ensure_ascii=False, indent=2) if as_json else render(t)); return 0


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
