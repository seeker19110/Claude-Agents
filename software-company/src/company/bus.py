"""Bus của company — cơ chế ở `xagents_core.bus`, dữ liệu ở `core.CORE` (K3.5b của ADR gốc 0001).

Còn lại ở đây đúng ba thứ mà core không được biết: lớp `Envelope` của company, một luật riêng
(`audit-log` mở cho mọi actor, nhưng `action="gate.decide"` chỉ người ghi), và các tên cũ được tái xuất để
mọi nơi đang `from .bus import TOPIC_PRODUCERS` không phải đổi ở PR này.
"""
from __future__ import annotations

from typing import Any

from xagents_core.bus import BusError as BusError
from xagents_core.bus import InMemoryBus as CoreInMemoryBus
from xagents_core.bus import PermissionDenied as PermissionDenied
from xagents_core.bus import is_human as is_human
from xagents_core.bus import producer_allowed as _producer_allowed

from .core import CORE
from .core import ENGINEERING_ACTORS as ENGINEERING_ACTORS
from .core import HUMAN_TOPICS as HUMAN_TOPICS
from .core import OPEN_TOPICS as OPEN_TOPICS
from .core import REVIEW_PRODUCERS as REVIEW_PRODUCERS
from .core import TOPIC_PRODUCERS as TOPIC_PRODUCERS
from .events import Envelope

SCHEMA_DIR = CORE.schema_dir


def producer_allowed(topic: str, actor: str) -> bool:
    """Chữ ký cũ (topic, actor) — bảng ACL nay đến từ `CORE`, không phải tham số."""
    return _producer_allowed(CORE.topic_acl, topic, actor)


class InMemoryBus(CoreInMemoryBus[Envelope]):
    envelope_cls = Envelope

    def __init__(self, cfg: Any = CORE, enforce_owners: bool = True):
        # Thứ tự tham số theo core (`cfg` trước): `SQLiteBus` của K3.5c kế thừa CẢ lớp này lẫn
        # `xagents_core.sqlite_bus.SQLiteBus`, và `super().__init__(cfg, ...)` của core đi qua đây theo MRO.
        super().__init__(cfg, enforce_owners=enforce_owners)

    def _extra_publish_checks(self, env: Envelope) -> None:
        if env.topic == "audit-log" and env.payload.get("action") == "gate.decide" \
                and not (is_human(env.actor) or env.actor == "orchestrator"):
            # audit-log mở cho mọi actor, nhưng quyết định gate là của người: agent không được ghi `gate.decide`
            # (orchestrator chỉ ghi khi đóng gate nghiệm thu từ chữ ký khách — gate_cli.trusted_decision kiểm tiếp)
            self._deny(env, f"agent {env.actor} không được ghi quyết định gate (gate.decide) — chỉ người (human:*)")
