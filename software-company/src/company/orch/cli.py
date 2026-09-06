"""CLI: `python -m company.orchestrator <lệnh>` (tách khỏi orchestrator.py, ADR-0034).

`main` chỉ parse argv, dựng `Orchestrator`/`SQLiteBus`, và gọi đúng phương thức — mọi hành vi nghiệp vụ nằm ở
`Orchestrator` hoặc các module `orch/` khác. `Orchestrator`/`ReloadRequested`/`_evidence` import LƯỜI bên trong
`main()`: `orchestrator.py` import `main` từ đây ở mức module, nên import ngược lúc nạp module sẽ vòng tròn — lúc
`main()` thật sự CHẠY thì `company.orchestrator` đã nạp xong.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from ..bus import is_human
from ..events import Envelope
from ..runner import artifact_store
from ..workspace import WorkspaceError

if TYPE_CHECKING:
    from ..orchestrator import StepResult

COMPANY_ROOT = Path(__file__).resolve().parents[3]  # thư mục software-company (như registry.ROOT)
SOURCE_GLOBS = ("src/company/**/*.py", "agents/**/*.md", "skills/**/*.md", "gates/*.md", "llm.yaml")


def source_fingerprint(root: Path | None = None) -> tuple[int, str]:
    """(số file, mô tả file mới nhất) của mọi thứ orchestrator nạp lúc khởi động. So sánh hai lần gọi là biết mã đổi;
    không cần git (worktree có thể đang ở nhánh bất kỳ)."""
    base = root or COMPANY_ROOT
    latest, n, name = 0.0, 0, ""
    for pat in SOURCE_GLOBS:
        for f in base.glob(pat):
            try: m = f.stat().st_mtime
            except OSError: continue
            n += 1
            if m > latest: latest, name = m, f.relative_to(base).as_posix()
    return n, f"{name}@{int(latest)}"


def _fmt(r: StepResult) -> str:
    tail = f"  hoãn: {r.deferred}" if r.deferred else "  " + "; ".join(r.actions)
    return f"{r.topic:<22} {r.key:<14}{tail}"


def main(argv: list[str] | None = None) -> int:
    """python -m company.orchestrator run [--db] [--max-steps N] [--watch GIÂY] [--workers N] [--web]
       python -m company.orchestrator publish <topic> <file.json> --actor human:po [--key K]
       python -m company.orchestrator decide-change <change_id> accepted|rejected|deferred --by human:po
       python -m company.orchestrator comment <ticket> --by human:x --text "..."   # hint giữa vòng, không tính retry
       python -m company.orchestrator takeover <ticket> --by human:x [--message]   # người sửa tay trong worktree rồi giao lại
       python -m company.orchestrator status | report | metrics [--prometheus] | show <namespace> [--db]
       python -m company.orchestrator trace <TICKET|REL-xxx|PROJECT> [--json]   # dòng thời gian intake → deploy"""
    from ..orchestrator import Orchestrator, ReloadRequested, _evidence
    ap = argparse.ArgumentParser(description="Orchestrator: vòng lặp tự động topic → agent → topic")
    ap.add_argument("--db", type=Path, default=Path("company.sqlite"))
    ap.add_argument("--repo", type=Path, help="git repo của khách: khối kỹ thuật sửa code thật trong worktree ticket/<id>")
    ap.add_argument("--base", default="HEAD", help="nhánh/commit gốc để tạo nhánh tích hợp lần đầu (mặc định HEAD)")
    ap.add_argument("--integration", default="company/integration", help="nhánh tích hợp: ticket rẽ từ đây, merge vào đây")
    ap.add_argument("--artifacts", type=Path, help="artifact store của blackboard (mặc định <db>.artifacts/)")
    ap.add_argument("--workers", type=int, default=1, help="số event khác key chạy song song (mặc định 1)")
    ap.add_argument("--web", action="store_true", help="cho researcher tool web_search/fetch_url (mạng ra ngoài)")
    ap.add_argument("--batch-release", action="store_true",
                    help="gom mọi ticket approved của dự án vào một RC khi không còn ticket đang chạy (mặc định: mỗi ticket một RC)")
    ap.add_argument("--deliver", action="store_true",
                    help="ADR-0027: production duyệt + deploy → tag v<version> và fast-forward nhánh release trong repo khách")
    ap.add_argument("--test-author", action="store_true",
                    help="ADR-0028: test-author viết test từ đặc tả TRƯỚC khi assignee viết code; assignee không ghi "
                         "được file test. Thêm một lượt model mỗi ticket. Stack không phân vùng được vùng test thì "
                         "ticket đi đường cũ và PR mang tests_authored_by=assignee")
    ap.add_argument("--push-remote", help="remote của repo khách để push nhánh release + tag sau khi giao (mặc định: không push)")
    ap.add_argument("--release-branch", default="company/release", help="nhánh 'đang chạy production' trong repo khách")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rn = sub.add_parser("run"); rn.add_argument("--max-steps", type=int); rn.add_argument("--no-reload", action="store_true",
                                                help="không tự khởi động lại khi mã nguồn đổi (mặc định: có, chỉ ở --watch)")
    rn.add_argument("--watch", type=float,
        help="chạy liên tục, mỗi N giây nạp event mới (gate CLI, publish) rồi xử lý")
    pb = sub.add_parser("publish"); pb.add_argument("topic"); pb.add_argument("file", type=Path)
    pb.add_argument("--actor", required=True); pb.add_argument("--key")
    dc = sub.add_parser("decide-change", help="khách quyết định change request (sau khi delivery-lead ước lượng impact)")
    dc.add_argument("change_id"); dc.add_argument("decision", choices=["accepted", "rejected", "deferred"])
    dc.add_argument("--by", required=True); dc.add_argument("--reason", default="")
    cm = sub.add_parser("comment", help="người nhận xét ticket đang chạy: phát lại task với hint, không tính retry")
    cm.add_argument("ticket_id"); cm.add_argument("--by", required=True); cm.add_argument("--text", required=True)
    tk = sub.add_parser("takeover", help="người đã sửa tay trong worktree ticket: chạy lint/test, commit, publish PR dưới tên người")
    tk.add_argument("ticket_id"); tk.add_argument("--by", required=True); tk.add_argument("--message")
    rd = sub.add_parser("redeploy", help="chạy lại lượt staging cho một release-candidate đang kẹt (sau khi sửa lỗi hạ tầng)")
    rd.add_argument("release_id"); rd.add_argument("--by", required=True)
    sub.add_parser("status"); sub.add_parser("report", help="sprint report: estimate vs actual, chi phí, hành động supervisor")
    ru = sub.add_parser("rulings", help="sổ Ruling (ADR-0030): quyết định agent tự đưa ra thay vì chờ người, kèm 'sai thì mất gì'")
    ru.add_argument("--project"); ru.add_argument("--ticket")
    dg = sub.add_parser("diagnose", help="chẩn đoán: gom lỗi thô thành khuôn lặp lại, ticket quay vòng, gate chờ quyết")
    dg.add_argument("--top", type=int, default=10, help="số khuôn lỗi in ra (mặc định 10)")
    tr = sub.add_parser("trace", help="dòng thời gian một ticket/REL-xxx/dự án từ intake tới deploy: agent, tier/model, token/USD, tool, gate, chờ, retry")
    tr.add_argument("subject"); tr.add_argument("--json", action="store_true", help="in JSON thay vì bảng chữ")
    mt = sub.add_parser("metrics", help="metrics từ audit-log: gọi/token/USD/thời gian theo agent, model, ticket; gate chờ")
    mt.add_argument("--prometheus", action="store_true", help="xuất text exposition format cho Prometheus")
    sh = sub.add_parser("show", help="in toàn văn artifact mới nhất của một namespace blackboard"); sh.add_argument("namespace")
    sh.add_argument("--project", help="dự án của artifact (ADR-0018); bỏ qua nếu chỉ có một dự án dùng namespace đó")
    ns = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # Windows console cp1252
        if hasattr(stream, "reconfigure"): stream.reconfigure(encoding="utf-8")
    from ..sqlite_bus import Lease, LeaseError, SQLiteBus
    bus = SQLiteBus(ns.db)
    if ns.cmd == "publish":
        if not is_human(ns.actor):  # CLI là cửa của người; giả danh agent/orchestrator từ đây là vượt quyền producer của bus
            print(f"--actor phải là người (human:<tên>), không phải {ns.actor!r}", file=sys.stderr); return 2
        payload = json.loads(ns.file.read_text(encoding="utf-8"))
        key = ns.key or payload.get("ticket_id") or payload.get("release_id") or payload.get("change_id") or payload.get("project_id")
        if not key: print("cần --key", file=sys.stderr); return 2
        env = bus.publish(Envelope(topic=ns.topic, key=key, actor=ns.actor, payload=payload))
        print(f"published {env.topic} key={env.key} event={env.event_id}"); return 0
    if ns.cmd == "decide-change":
        cr = next(reversed(list(bus.replay(topic="change-requests", key=ns.change_id))), None)
        if cr is None: print(f"không có change-request {ns.change_id}", file=sys.stderr); return 2
        impact = next((_evidence(e.payload) for e in reversed(list(bus.replay(topic="audit-log")))
                       if e.payload.get("action") == "change.impact" and _evidence(e.payload).get("change_id") == ns.change_id), {})
        payload = {**cr.payload, "decision": ns.decision, "impact": {**cr.payload.get("impact", {}), **impact.get("impact", {}),
                                                                       "decided_by": ns.by, "reason": ns.reason}}
        env = bus.publish(Envelope(topic="change-requests", key=ns.change_id, actor=ns.by, payload=payload))
        print(f"{ns.change_id}: {ns.decision} by {ns.by} event={env.event_id}"); return 0
    if ns.cmd == "metrics":
        from ..metrics import collect, prometheus
        m = collect(bus)
        print(prometheus(m) if ns.prometheus else json.dumps(m, ensure_ascii=False, indent=2)); return 0
    if ns.cmd == "diagnose":
        from ..metrics import diagnose
        print(json.dumps(diagnose(bus, top=ns.top), ensure_ascii=False, indent=2)); return 0
    if ns.cmd == "trace":
        from ..trace import run as trace_run
        return trace_run(bus, ns.subject, ns.json)
    from ..llm import FakeClient, make_client
    # `run` và `redeploy` GỌI MODEL (redeploy chạy lại lượt staging của release-engineer) nên cần client thật;
    # status/report/show/comment/takeover là việc của người và của code, không được đòi SDK/API key.
    # Thiếu `redeploy` ở đây thì lệnh chạy bằng FakeClient và chết "FakeClient hết câu trả lời" — đo được 2026-09-06.
    orch = Orchestrator(bus, make_client() if ns.cmd in {"run", "redeploy"} else FakeClient(), repo=ns.repo, base=ns.base, integration=ns.integration, workers=ns.workers,
                        web=ns.web, batch_releases=ns.batch_release, artifacts=ns.artifacts or artifact_store(ns.db),
                        deliver=ns.deliver, push_remote=ns.push_remote, release_branch=ns.release_branch,
                        test_author=ns.test_author)
    if ns.cmd == "status":
        print(json.dumps(orch.status(), ensure_ascii=False, indent=2)); return 0
    if ns.cmd == "rulings":
        rows = orch.rulings(project_id=ns.project, ticket_id=ns.ticket)
        for ru_ in rows:
            who = ru_.get("ticket_id") or ru_.get("project_id") or "-"
            print(f"{ru_['at']}  {ru_['by']:<18} {who:<14} {ru_['decision']}")
            print(f"{'':40} vì: {ru_['why']}")
            print(f"{'':40} sai thì: {ru_['cost_if_wrong']}")
        print(f"({len(rows)} ruling)"); return 0
    if ns.cmd == "report":
        print(json.dumps(orch.supervisor.sprint_report(), ensure_ascii=False, indent=2)); return 0
    if ns.cmd == "show":
        sc = orch.blackboard.read(ns.namespace, ns.project)
        if sc is None and ns.project is None:
            # Blackboard phân vùng theo dự án: không nêu --project thì chỉ đoán được khi đúng một dự án có namespace này.
            found = [c for (pid, nsp), c in orch.blackboard._latest.items() if nsp == ns.namespace]
            if len(found) == 1: sc = found[0]
            elif len(found) > 1:
                projects = ", ".join(sorted(str(c.project_id) for c in found))
                print(f"{ns.namespace} có ở nhiều dự án ({projects}); nêu --project", file=sys.stderr); return 2
        if sc is None: print(f"chưa có namespace {ns.namespace}", file=sys.stderr); return 2
        scope = f" [{sc.project_id}]" if sc.project_id else ""
        print(f"# {ns.namespace} v{sc.version}{scope} — {sc.content_ref}\n# {sc.summary}\n")
        print(sc.content if sc.content is not None else "(chỉ có con trỏ, không có toàn văn)"); return 0
    if ns.cmd == "redeploy":
        try:
            lease = Lease(ns.db); lease.acquire()
        except LeaseError as e:
            print(str(e), file=sys.stderr); return 3
        try:
            rc = orch.redeploy(ns.release_id, ns.by)
            print(f"{rc.key}: đã chạy lại lượt staging (by={ns.by})")
        except ValueError as e:
            print(str(e), file=sys.stderr); return 2
        finally:
            lease.release()
        return 0
    if ns.cmd in {"comment", "takeover"}:
        try:
            if ns.cmd == "comment":
                t = orch.comment(ns.ticket_id, ns.by, ns.text); print(f"{t.ticket_id}: phát lại với hint (retry={t.retry})")
            else:
                env = orch.takeover(ns.ticket_id, ns.by, ns.message)
                print(f"{env.key}: PR {env.payload['pr_ref']} của {ns.by}, lint={env.payload['local_checks']['lint']} "
                      f"tests={env.payload['local_checks']['tests']} event={env.event_id}")
        except (ValueError, WorkspaceError) as e:
            print(str(e), file=sys.stderr); return 2
        return 0
    try:
        lease = Lease(ns.db); lease.acquire()
    except LeaseError as e:
        print(str(e), file=sys.stderr); return 3
    reload = False
    try:
        if ns.watch:
            try: orch.watch(interval=ns.watch, reload=not ns.no_reload)
            except KeyboardInterrupt: pass
            except ReloadRequested: reload = True
        else:
            for r in orch.tick() if ns.max_steps is None else orch.run(ns.max_steps): print(_fmt(r))
    finally:
        lease.release()  # trả lease TRƯỚC khi exec: tiến trình mới phải lấy được lease
    if reload:
        argv = [sys.executable, "-u", "-m", "company.orchestrator", *sys.argv[1:]]  # -u: stdout không bị buffer (URL/token/log)
        _reexec(argv)
    print(json.dumps(orch.status(), ensure_ascii=False))
    return 0


def _reexec(argv: list[str]) -> None:  # tách ra để test thay được; execv không trở về
    os.execv(argv[0], argv)

