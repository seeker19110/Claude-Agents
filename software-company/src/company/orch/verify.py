"""Smoke/regression/evidence: bằng chứng do CODE chạy, không phải lời khai của model (ADR-0029, tách khỏi
orchestrator.py theo ADR-0034). Mỗi hàm nhận `o: Orchestrator` làm tham số đầu — được gán làm method trên
`Orchestrator` (`_smoke = verify.smoke`, …) nên `self` tự bind qua descriptor của Python, gọi `o._smoke(...)`
trong test cũ không đổi.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..events import Envelope
from ..gates import GateRequest
from ..roles import ROLE
from ..smoke import parse_runtime, run_smoke, unverified
from ..workspace import Integration
from .routes import _dict_of

if TYPE_CHECKING:
    from ..orchestrator import Orchestrator


def release_evidence(o: Orchestrator, rid: str) -> dict[str, Any]:
    staging = next((e for e in reversed(list(o.bus.replay(topic="release-events", key=rid)))
                    if e.payload.get("env") == "staging"), None)
    reviews = {s: {"verdict": x.verdict, "findings": len(x.findings)} for s, x in o.lead.release_reviews.get(rid, {}).items()}
    gate = next((g for g in reversed(o.gate.history) if g.subject_id == rid and g.kind == "release"), None)
    return {"staging": ({"status": staging.payload.get("status"), "version": staging.payload.get("version"),
                         "at": staging.ts.isoformat(timespec="seconds"),
                         "smoke": staging.payload.get("smoke")} if staging is not None else None),
            "reviews": reviews, "waived": sorted(o.lead.release_waived.get(rid, set())),
            "gate_release_by": (gate.decided_by if gate is not None else None),
            "gate_release_reason": ((gate.reason or "")[:300] if gate is not None else None),
            "delivered_sha": o.release_sha.get(rid)}


def _du_an_legacy(o: Orchestrator, pid: str | None) -> bool:
    """Cờ `legacy: true` trong `research-requests.payload` — người mở dự án tự khai "dự án này có TRƯỚC ADR-0031,
    đừng đòi nó khai `runtime`". Khai một lần lúc mở dự án, không phải cờ mà agent tự bật giữa chừng: nó nằm ở
    topic của con người (`research-requests`), không nằm ở spec do model viết."""
    if pid is None: return False
    rr = o.latest("research-requests", pid)
    return rr is not None and rr.payload.get("legacy") is True


def smoke(o: Orchestrator, agent: str, rc: Envelope, rid: str, p: dict[str, Any], integ: Integration | None) -> dict[str, Any]:
    """`status=deployed` ở staging là LỜI KHAI của release-engineer (nó không có tool deploy). ADR-0029: orchestrator
    tự khởi động sản phẩm theo `runtime` của spec trong worktree tích hợp và gọi một request thật; kết quả vào
    `payload.smoke` (`verified_by=orchestrator`). Có `runtime` mà khởi động không được / không trả lời đúng →
    status thành `failed`: bốn gate xanh không được phép che một sản phẩm không chạy (đo được 2026-09-06 QLKH:
    25 release, 0 điểm vào).

    Không smoke được (thiếu `runtime`, thiếu worktree) thì tuỳ LOẠI sản phẩm (K1.5 kịch bản B):
    `library`/`docs` — hoặc dự án khai `legacy: true` — vẫn đi tiếp, bằng chứng nói rõ là chưa kiểm; còn
    `kind=application` (mặc định khi spec thiếu `kind`) thì `unverified` là **failed**, đi đúng đường của smoke
    fail. ADR-0031 đã chặn ở gate spec: spec ứng dụng thiếu `runtime` không được mở Gate 1. Đây là lớp SAU —
    dự án được duyệt trước ADR-0031, hay `integ` biến mất giữa chừng, vẫn tới được đây; và "không kiểm được"
    của một sản phẩm-phải-chạy-được không phải là một trạng thái trung lập để đi tiếp."""
    pid = o.project_for(rc)
    spec = o.latest("approved-specs", pid) if pid else None
    kind = (spec.payload.get("kind") if spec is not None else None) or "application"
    rt = parse_runtime(spec.payload if spec is not None else None)
    if rt is None or integ is None or not integ.path.exists():
        # Hai nguyên nhân, MỘT chỗ quyết: tách ra hai nhánh song song thì sớm muộn chúng xử lý khác nhau.
        smoke = unverified("spec không khai `runtime` (lệnh khởi động, cổng, đường health)" if rt is None
                           else "không có worktree tích hợp (dự án chạy không repo)")
        o._audit("release.smoke_unverified", {"release_id": rid, "reason": smoke["reason"], "spec_kind": kind},
                    project_id=pid, once=f"smoke.unverified:{rid}:{rc.event_id}")
        if kind != "application" or _du_an_legacy(o, pid):
            return {**p, "smoke": smoke}
        o._audit("release.smoke_blocked", {"release_id": rid, "claimed_status": p.get("status"),
                                              "spec_kind": kind, "reason": smoke["reason"]}, project_id=pid)
        if rid not in o.gate.pending:   # cùng đường với smoke fail bên dưới: RC failed không có route nào tiếp
            o.gate.request(GateRequest(kind="escalation", subject_id=rid, created_by=ROLE.OPS,
                                          checklist=["root_cause", "decision:redeploy|close", "hint"]))
        return {**p, "status": "failed", "smoke": smoke}
    smoke = run_smoke(integ.path, rt, sandbox=o.sandbox)
    o._audit("release.smoke", {"release_id": rid, **smoke}, actor=agent, project_id=pid)
    if smoke.get("ok"):
        return {**p, "smoke": smoke}
    o._audit("release.smoke_failed", {"release_id": rid, "claimed_status": p.get("status"),
                                         "http_status": smoke.get("http_status"), "exit_code": smoke.get("exit_code"),
                                         "error": smoke.get("error")}, project_id=pid)
    # RC `failed` ở staging không có route nào tiếp: không mở gate thì nó nằm im như `pending_human` từng nằm.
    if rid not in o.gate.pending:
        o.gate.request(GateRequest(kind="escalation", subject_id=rid, created_by=ROLE.OPS,
                                      checklist=["root_cause", "decision:redeploy|close", "hint"]))
    return {**p, "status": "failed", "smoke": smoke}


def regression_run(o: Orchestrator, env: Envelope) -> dict[str, Any]:
    """ADR-0029 mục "regression-staging": trước lượt QA hồi quy, orchestrator TỰ khởi động sản phẩm theo `runtime`
    của spec trên worktree tích hợp (đúng sha RC đã staged) và gọi một request thật. Kết quả (lệnh, mã thoát, mã
    HTTP, `verified_by=orchestrator`) là `evidence.run` — bằng chứng của máy, đưa vào input để QA dẫn và đối chiếu
    với verdict sau lượt (`_verdict_with_run`). Không có `runtime`/worktree → `unverified` kèm lý do và `spec_kind`:
    spec khai `kind=application` mà không có `runtime` thì đó là lỗi của spec, không phải "chưa kiểm".
    Bằng chứng sống trong payload `review-results` trên bus, không giữ trong RAM; khoá `once` mang event_id của
    lượt deployed nên RC redeploy (lần hợp lệ thứ hai) vẫn được ghi lại."""
    rid = str(env.payload.get("release_id") or env.key)
    pid = o.project_for(env)
    spec = o.latest("approved-specs", pid) if pid else None
    kind = (spec.payload.get("kind") if spec is not None else None) or None
    rt = parse_runtime(spec.payload if spec is not None else None)
    integ = o._integration_of_release(env)
    if rt is None:
        run = {**unverified("spec không khai `runtime` (lệnh khởi động, cổng, đường health)"), "spec_kind": kind}
    elif integ is None or not integ.path.exists():
        run = {**unverified("không có worktree tích hợp (dự án chạy không repo)"), "spec_kind": kind}
    else:
        run = {**run_smoke(integ.path, rt, sandbox=o.sandbox), "sha": o.release_sha.get(rid) or integ.sha(), "spec_kind": kind}
        o._audit("regression.run", {"release_id": rid, **run}, project_id=pid)
        return run
    o._audit("regression.run_unverified", {"release_id": rid, "reason": run["reason"], "spec_kind": kind},
                project_id=pid, once=f"regression.unverified:{rid}:{env.event_id}")
    return run


def verdict_with_run(o: Orchestrator, agent: str, env: Envelope, p: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    """Gắn `evidence.run` do orchestrator chạy vào verdict QA (ghi đè mọi `evidence.run` model tự khai) và đối chiếu:
    smoke fail → verdict `fail`; `unverified` với spec `kind=application` → `fail` (spec phải khai `runtime`);
    `unverified` với kind khác (library, hoặc chưa khai) → giữ verdict, bằng chứng nói thẳng là chưa kiểm.
    Ba kết cục, không có kết cục thứ tư — như `_smoke` với `deployed`."""
    rid = str(env.payload.get("release_id") or env.key)
    pid = o.project_for(env)
    ev = _dict_of(p.get("evidence"))
    if "run" in ev:  # model tự khai `evidence.run`: bỏ, ghi lại — bằng chứng chạy chỉ có một nguồn là orchestrator
        o._audit("regression.run_claimed_ignored", {"release_id": rid, "claimed": ev.get("run")}, actor=agent, project_id=pid)
    p = {**p, "evidence": {**ev, "run": run}}
    if run.get("ok"):
        return p
    if run.get("unverified"):
        if run.get("spec_kind") != "application":
            return p
        reason = f"spec khai kind=application nhưng không smoke được: {run.get('reason')} — RC không đi tiếp cho tới khi spec khai `runtime`"
    else:
        reason = (f"smoke do orchestrator chạy trên worktree RC không đạt: http_status={run.get('http_status')} "
                  f"exit_code={run.get('exit_code')} error={run.get('error')} — lệnh {run.get('command')}")
    o._audit("regression.run_failed", {"release_id": rid, "claimed_verdict": p.get("verdict"), "reason": reason},
                project_id=pid)
    if p.get("verdict") == "pass":
        o._audit("regression.verdict_overridden", {"release_id": rid, "claimed": "pass", "verdict": "fail", "reason": reason},
                    actor=agent, project_id=pid)
        p = {**p, "verdict": "fail", "root_cause": p.get("root_cause") or reason,
             "findings": [*(p.get("findings") or []), {"level": "block", "location": run.get("url"), "text": reason}]}
    return p
