"""Blackboard của `keeper` — cơ chế ở `xagents_core.blackboard`, hai dòng ở đây là lớp Envelope/SharedContext.

`keeper` hiện KHÔNG có agent nào khai `context_namespace_write` (cả 10 đều `null`), nên đường ghi blackboard
không chạy trong sản xuất. Lớp này vẫn tồn tại vì `EvalSuite.run_eval` dựng một blackboard cho mọi ca (hợp đồng
của core), và vì `shared-context` là topic mở của `CORE` — ngày một agent của `keeper` sở hữu namespace thì chỗ
ấy đã đúng sẵn, không phải nhớ dựng.

`store=None`: `keeper` chưa có artifact store nên nhánh mirror ra đĩa không chạy (như studio).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from xagents_core.blackboard import Blackboard as CoreBlackboard

from .bus import KeeperMemoryBus
from .core import CORE
from .events import Envelope, SharedContext

__all__ = ["Blackboard"]


class Blackboard(CoreBlackboard[Envelope, SharedContext]):
    envelope_cls = Envelope
    context_cls = SharedContext

    def __init__(self, bus: KeeperMemoryBus, store: Path | None = None, cfg: Any = CORE):
        super().__init__(cfg, bus, store)
