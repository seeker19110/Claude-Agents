"""Bus của `keeper` = bus của lõi + `Envelope` của `keeper` (khuôn `company/bus.py`, `studio/bus.py`).

Hai dòng, nhưng không bỏ được: `InMemoryBus`/`SQLiteBus` của lõi là generic theo lớp envelope, và lớp đó phải
là `keeper.events.Envelope` — nếu để envelope của lõi thì `replay()` trả về khung core, `topic` thôi không còn
là `Literal` của `keeper`, và một topic lạ chỉ đỏ lúc chạy chứ không đỏ ở lớp kiểu (cùng lý do đã ghi ở
`xagents_core/gate_cli.py` cho `PersistentGate`).
"""
from __future__ import annotations

from xagents_core.bus import InMemoryBus as CoreInMemoryBus
from xagents_core.sqlite_bus import SQLiteBus as CoreSQLiteBus

from .events import Envelope

__all__ = ["KeeperBus", "KeeperMemoryBus"]


class KeeperMemoryBus(CoreInMemoryBus[Envelope]):
    """Bus trong bộ nhớ — chỉ cho test và chạy khô; không resume được (không có checkpoint trên đĩa)."""

    envelope_cls = Envelope


class KeeperBus(CoreSQLiteBus[Envelope]):
    """Bus bền vững: mọi event append vào `keeper.sqlite`, mở lại là replay được — đây là checkpoint duy nhất
    để `KeeperOrchestrator` tiếp tục đúng chỗ sau khi tiến trình chết (`TRAPS.md`: state chỉ sống trong RAM)."""

    envelope_cls = Envelope
