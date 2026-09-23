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


def _machine_ok(d: Mapping[str, Any] | None, by: str) -> bool:
    return d is not None and d.get("ok") is True and d.get("verified_by") == by and not d.get("skipped")


def _release_gaps(ev: QualityEvidence, bar: QualityBar) -> list[str]:
    gaps: list[str] = []
    if not ev.pr_checks:
        gaps.append("R1: release không có ticket/PR nào để chứng lint+test")
    for tid, lc in ev.pr_checks:
        if lc is None or lc.get("unverified") or lc.get("verified_by") != MACHINE_PR \
                or lc.get("lint") is not True or lc.get("tests") is not True:
            gaps.append(f"R1: PR của {tid} không có lint+test xanh do workspace chứng")
    run = ev.run or {}
    ran_at_sha = _machine_ok(ev.run, MACHINE_RUN) and ev.staged_sha is not None and run.get("sha") == ev.staged_sha
    deployed = bool(run.get("deploy_declared")) and _machine_ok(ev.staging_deploy, MACHINE_RUN)
    if not (ran_at_sha or deployed):
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
        prod = ev.production_deploy or {}
        if not (_machine_ok(ev.production_deploy, MACHINE_RUN) and ev.staged_sha is not None
                and prod.get("sha") == ev.staged_sha):
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
