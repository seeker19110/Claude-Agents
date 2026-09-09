"""Blackboard của company — cơ chế ở `xagents_core.blackboard` (K3.6b của ADR gốc 0001).

Còn lại ở đây đúng ba thứ: hai lớp của company (`Envelope`, `SharedContext` — `SharedContext` mang `rulings`
mà core không được biết) và bảng `EXT`.

Hai hàm module `scope_of`/`context_key` **biến mất**, thành phương thức của `Blackboard`. Chúng đọc
`global_namespaces`, mà bảng ấy nay ở `CoreConfig` — giữ chúng là hàm module thì `cfg` phải lấy từ đâu đó
ngoài instance, tức hai nguồn cho một luật. Nơi duy nhất gọi chúng ngoài blackboard là một ca test, đã đổi
sang vá phương thức.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from xagents_core.blackboard import Blackboard as CoreBlackboard
from xagents_core.blackboard import Scope as Scope

from .bus import InMemoryBus
from .core import CORE
from .events import Envelope, SharedContext

EXT = {"api-contract": "yaml", "schema": "sql"}  # phần mở rộng file mirror theo namespace; còn lại markdown


class Blackboard(CoreBlackboard[Envelope, SharedContext]):
    envelope_cls = Envelope
    context_cls = SharedContext
    EXT = EXT

    def __init__(self, bus: InMemoryBus, store: Path | None = None, cfg: Any = CORE):
        super().__init__(cfg, bus, store)
