"""Sàn chất lượng cho gate tự duyệt (ADR-0043): `release` (= deploy production) và `acceptance` (`UAT-*`).

Hai nửa tách rời có chủ ý:
- `floor_gaps(evidence, bar)` — hàm THUẦN: bằng chứng + mức nâng của dự án → danh sách khoảng trống (rỗng ⇔ đạt
  sàn). Không đọc bus, không đọc env, không gọi gì — nên sàn test được bằng bảng, và đổi sàn là đổi đúng hàm này.
- `collect_*` (đọc bus) dựng `QualityEvidence` — chỉ từ bằng chứng DO MÁY SINH (`verified_by=workspace|
  orchestrator`). Verdict của QA/security là lời khai của model: dùng được theo chiều CHẶN (không `pass` → khoảng
  trống), không bao giờ theo chiều CHO QUA một mình.

Mức nâng (`QualityBar`) là tập khoá ĐÓNG, mỗi khoá chỉ thêm điều kiện — "không hạ dưới sàn" là tính chất của kiểu
dữ liệu, không phải một phép kẹp có thể quên ở chỗ gọi (ADR-0043 §2).
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from xagents_core.bus import is_human

from .roles import SOURCE

MACHINE_PR = "workspace"
MACHINE_RUN = "orchestrator"
#: `audit-log` action mang mức nâng người đặt lúc ký spec (`gate_cli approve SPEC-<pid> --quality-bar ...`).
BAR_ACTION = "quality.bar_set"


@dataclass(frozen=True)
class QualityBar:
    """Mức nâng của MỘT dự án, người đặt lúc ký spec. Mặc định: không nâng gì (chỉ sàn)."""
    release_human: bool = False
    acceptance_human: bool = False
    security_review: bool = False


#: Bản ghi mức nâng hỏng/không tin được khi replay ⇒ đóng cả hai cửa tự duyệt (hỏng thì đóng, không mở).
FAIL_CLOSED_BAR = QualityBar(release_human=True, acceptance_human=True, security_review=True)

_BAR_KEYS: dict[str, tuple[str, str]] = {
    "release": ("release_human", "human"),
    "acceptance": ("acceptance_human", "human"),
    "security_review": ("security_review", "required"),
}


def parse_bar(raw: Mapping[str, Any]) -> QualityBar:
    """`{"release": "human", ...}` → `QualityBar`. Khoá lạ hoặc giá trị khác giá trị siết duy nhất → `ValueError`."""
    fields: dict[str, bool] = {}
    for key, val in raw.items():
        if key not in _BAR_KEYS:
            raise ValueError(f"khoá mức nâng lạ: {key!r} (chỉ nhận {sorted(_BAR_KEYS)})")
        field, only = _BAR_KEYS[key]
        if val != only:
            raise ValueError(f"{key}={val!r}: khoá này chỉ nhận {only!r} (mức nâng chỉ siết, không nới)")
        fields[field] = True
    return QualityBar(**fields)


@dataclass(frozen=True)
class QualityEvidence:
    """Bằng chứng tại thời điểm mở gate. `None` ở một trường = không có bằng chứng đó (⇒ khoảng trống)."""
    kind: str
    release_id: str
    staged_sha: str | None
    pr_checks: tuple[tuple[str, Mapping[str, Any] | None], ...]
    run: Mapping[str, Any] | None
    staging_deploy: Mapping[str, Any] | None
    qa_verdict: str | None
    security_verdict: str | None
    needs_security: bool
    waived: tuple[str, ...]
    had_incident: bool
    release_approved: bool
    production_deploy: Mapping[str, Any] | None


def _machine_ok_at(d: Mapping[str, Any] | None, sha: str | None) -> bool:
    """Máy (orchestrator) chứng `ok`, không `skipped`, ở ĐÚNG sha đã staged — thiếu sha ở một trong hai phía là thiếu
    bằng chứng, không phải "khớp"."""
    return (d is not None and d.get("ok") is True and d.get("verified_by") == MACHINE_RUN and not d.get("skipped")
            and sha is not None and d.get("sha") == sha)


def _release_gaps(ev: QualityEvidence, bar: QualityBar) -> list[str]:
    gaps: list[str] = []
    if not ev.pr_checks:
        gaps.append("R1: release không có ticket/PR nào để chứng lint+test")
    for tid, lc in ev.pr_checks:
        if lc is None or lc.get("unverified") or lc.get("verified_by") != MACHINE_PR \
                or lc.get("lint") is not True or lc.get("tests") is not True:
            gaps.append(f"R1: PR của {tid} không có lint+test xanh do workspace chứng")
    deployed = bool((ev.run or {}).get("deploy_declared")) and _machine_ok_at(ev.staging_deploy, ev.staged_sha)
    if not (_machine_ok_at(ev.run, ev.staged_sha) or deployed):
        gaps.append("R2: không có bằng chứng orchestrator rằng sản phẩm chạy được ở đúng sha đã staged")
    if ev.qa_verdict != "pass":
        gaps.append(f"R3: review QA trên release là {ev.qa_verdict!r}, không phải 'pass'")
    if (ev.needs_security or bar.security_review) and ev.security_verdict != "pass":
        gaps.append(f"R3: review security trên release là {ev.security_verdict!r}, không phải 'pass'")
    if ev.waived:
        gaps.append(f"R4: finding đã được người miễn ({', '.join(ev.waived)}) — máy không thừa hưởng quyết định đó")
    if ev.had_incident:
        gaps.append("R5: release này từng có escalation/quyết định khác approve — việc của người")
    return gaps


def floor_gaps(ev: QualityEvidence, bar: QualityBar) -> list[str]:
    """Khoảng trống so với sàn (+ mức nâng). Rỗng ⇔ được tự duyệt. Mọi `kind` khác release/acceptance: không tự duyệt."""
    if ev.kind == "release":
        return (["nâng: dự án đặt release=human"] if bar.release_human else []) + _release_gaps(ev, bar)
    if ev.kind == "acceptance":
        gaps = ["nâng: dự án đặt acceptance=human"] if bar.acceptance_human else []
        if not ev.release_approved:
            gaps.append("A1: gate release của release này chưa được duyệt")
        if not _machine_ok_at(ev.production_deploy, ev.staged_sha):
            gaps.append("A2: không có deploy production do orchestrator chứng ở đúng sha đã staged")
        return gaps + _release_gaps(ev, bar)
    return [f"gate {ev.kind!r} không bao giờ tự duyệt (ADR-0043)"]


class _Replayable(Protocol):
    def replay(self, topic: str | None = None, key: str | None = None) -> Iterable[Any]: ...


def project_bar(bus: _Replayable, project_id: str) -> QualityBar:
    """Mức nâng hiện hành của dự án: bản ghi `quality.bar_set` MỚI NHẤT đáng tin (actor là người và khớp `by`).

    Bản ghi không tin được bị BỎ QUA — bỏ qua không nới được gì, vì không có bản ghi nào nghĩa là chỉ có sàn.
    Bản ghi của người mà hỏng (khoá lạ, không phải object) ⇒ `FAIL_CLOSED_BAR`: người đã định siết mà máy không
    đọc được siết gì, nên đóng cả hai cửa tự duyệt thay vì đoán."""
    bar = QualityBar()
    for env in bus.replay(topic="audit-log"):
        if env.payload.get("action") != BAR_ACTION or not is_human(env.actor):
            continue
        try:
            d = json.loads(env.payload.get("evidence") or "{}")
        except (ValueError, TypeError):
            continue
        if not isinstance(d, dict) or d.get("project_id") != project_id or d.get("by") != env.actor:
            continue
        raw = d.get("bar")
        try:
            bar = parse_bar(raw) if isinstance(raw, dict) else FAIL_CLOSED_BAR
        except ValueError:
            bar = FAIL_CLOSED_BAR
    return bar


def _json_dict(raw: Any) -> dict[str, Any]:
    try:
        d = json.loads(raw or "{}")
    except (ValueError, TypeError):
        return {}
    return d if isinstance(d, dict) else {}


def _dict(v: Any) -> dict[str, Any] | None:
    return v if isinstance(v, dict) else None


class _Gate(Protocol):
    kind: str
    subject_id: str
    decision: str


def collect_evidence(bus: _Replayable, kind: str, rid: str, *, tickets: Iterable[str], needs_security: bool,
                     waived: Iterable[str], history: Iterable[_Gate]) -> QualityEvidence:
    """Dựng `QualityEvidence` cho gate `kind` của release `rid` từ bus — bản MỚI NHẤT của mỗi nguồn.

    Nguồn nào thiếu thì trường đó là `None`/rỗng (⇒ `floor_gaps` báo khoảng trống), không bao giờ điền giá trị
    mặc định "cho có". `release.staged` chỉ tin khi actor là `orchestrator` (audit-log là topic mở: agent ghi được
    một dòng cùng tên với sha tuỳ ý). `tickets`/`needs_security`/`waived` do `DeliveryLead` giữ; `history` là
    `gate.history` — cả ba đều đã có sẵn ở nơi gọi, không đọc lại từ bus.
    # no-ky-thuat: quét tuyến tính audit-log + review-results + release-events mỗi lần mở gate release/nghiệm thu, ổn tới ~50k event audit, quay lại khi mở gate chậm quá 1s trên company.sqlite thật
    """
    staged: str | None = None
    for env in bus.replay(topic="audit-log"):
        if env.payload.get("action") == "release.staged" and env.actor == MACHINE_RUN:
            d = _json_dict(env.payload.get("evidence"))
            if d.get("release_id") == rid and isinstance(d.get("sha"), str):
                staged = d["sha"]
    pr_checks = []
    for tid in tickets:
        pr = bus.latest("pull-requests", tid)  # type: ignore[attr-defined]
        pr_checks.append((tid, _dict(pr.payload.get("local_checks")) if pr is not None else None))
    verdicts: dict[str, str] = {}; run: dict[str, Any] | None = None
    for env in bus.replay(topic="review-results", key=rid):
        src, verdict = env.payload.get("source"), env.payload.get("verdict")
        verdicts[str(src)] = str(verdict)
        if src == SOURCE.QA:
            run = _dict((_dict(env.payload.get("evidence")) or {}).get("run"))
    deploys: dict[str, dict[str, Any] | None] = {}
    for env in bus.replay(topic="release-events", key=rid):
        if env.payload.get("status") == "deployed":
            deploys[str(env.payload.get("env"))] = _dict((_dict(env.payload.get("evidence")) or {}).get("deploy"))
    subjects = {rid, f"UAT-{rid}"}
    gates = [g for g in history if g.subject_id in subjects and g.decision != "pending"]
    return QualityEvidence(
        kind=kind, release_id=rid, staged_sha=staged, pr_checks=tuple(pr_checks), run=run,
        staging_deploy=deploys.get("staging"), qa_verdict=verdicts.get(SOURCE.QA),
        security_verdict=verdicts.get(SOURCE.SECURITY),
        needs_security=needs_security, waived=tuple(waived),
        had_incident=any(g.kind == "escalation" or g.decision != "approve" for g in gates),
        release_approved=any(g.subject_id == rid and g.kind == "release" and g.decision == "approve" for g in gates),
        production_deploy=deploys.get("production"),
    )
