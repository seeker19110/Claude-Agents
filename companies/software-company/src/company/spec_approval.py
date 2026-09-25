"""ApprovalLookup thật cho pha Ready: ai đã duyệt spec, đọc từ bus (ADR gốc 0021 §d, bổ sung pe2-duyet).

`approval_record` là subject gate spec (`SPEC-<pid>`). Một cặp (record, hash spec) được xác minh khi CÙNG một actor
người (bus kiểm `env.actor`, không đọc `evidence.by` như chữ ký) vừa `approve` gate đó, vừa ghim một profile mà
file ghim băm lại đúng `profile_sha256` và khai đúng record + hash spec ấy. Lời khai `approved_by` trong profile
không là nguồn sự thật: `ready_gaps` so nó với principal lookup trả về. Hỏng ở bất kỳ bước nào ⇒ `None`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from xagents_core.bus import InMemoryBus
from xagents_core.gate_cli import trusted_decision

from .gate_cli import SPEC_PREFIX
from .product_quality import ProjectProfile
from .quality_execution import pinned_profile_path
from .quality_floor import PROFILE_ACTION


class BusApprovalLookup:
    """Đọc lại bus mỗi lần hỏi (Ready chỉ chấm lúc nộp kết quả, không phải đường nóng)."""

    def __init__(self, bus: InMemoryBus, db: Path):
        self.bus, self.db = bus, Path(db)

    def approved(self, record: str, artifact_sha256: str) -> str | None:
        pid = record[len(SPEC_PREFIX) :] if record.startswith(SPEC_PREFIX) else ""
        if not pid:
            return None
        # Chỉ thế hệ MỚI NHẤT của gate còn hiệu lực (sc-security F2): mọi `gate.request`/quyết định sau một lần
        # duyệt xoá lần duyệt đó, và chỉ profile CHÍNH người duyệt ghim SAU lần duyệt ấy mới thuộc về nó.
        approver: str | None = None
        pins: list[str] = []
        for env in self.bus.replay(topic="audit-log"):
            action = env.payload.get("action")
            if action == "gate.request" and _evidence(env).get("subject_id") == record:
                approver, pins = None, []
            # uat_prefix=None: chỉ tin actor người, không tin actor hệ thống lẫn máy tự duyệt.
            elif (d := trusted_decision(env, uat_prefix=None)) is not None and d["subject_id"] == record:
                approver, pins = (env.actor if d["decision"] == "approve" else None), []
            elif action == PROFILE_ACTION and approver is not None and env.actor == approver:
                ev = _evidence(env)
                if ev.get("project_id") == pid and isinstance(sha := ev.get("profile_sha256"), str):
                    pins.append(sha)
        if approver is None:
            return None
        return approver if any(self._pinned_spec(pid, sha) == (record, artifact_sha256) for sha in pins) else None

    def _pinned_spec(self, pid: str, sha: str) -> tuple[str, str] | None:
        try:
            raw = pinned_profile_path(self.db, pid, sha).read_bytes()
            if hashlib.sha256(raw).hexdigest() != sha:
                return None
            profile = ProjectProfile.model_validate_json(raw)
        except (OSError, ValueError):
            return None
        if profile.delivery is None:
            return None
        return profile.delivery.spec.approval_record, profile.delivery.spec.artifact_sha256


def _evidence(env: object) -> dict[str, object]:
    """Evidence JSON của một bản ghi audit; hỏng (kể cả lồng quá sâu, F4) ⇒ `{}`."""
    try:
        d = json.loads(getattr(env, "payload", {}).get("evidence") or "{}")
    except (ValueError, TypeError, RecursionError):
        return {}
    return d if isinstance(d, dict) else {}
