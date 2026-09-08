"""Bus bền vững SQLite của company — cơ chế ở `xagents_core.sqlite_bus` (K3.5c của ADR gốc 0001).

Còn lại ở đây đúng hai thứ: lớp `Envelope` của company (qua `bus.InMemoryBus`, để giữ luật riêng
`gate.decide`), và tên file bus mặc định — nay đọc từ `CORE.db_name` chứ không viết cứng `"company.sqlite"`.

`SQLiteBus` kế thừa HAI lớp: cơ chế đĩa của core và bus company. MRO là
`SQLiteBus → CoreSQLiteBus → company.bus.InMemoryBus → CoreInMemoryBus`, nên `_extra_publish_checks` của
company vẫn chạy trong `_check_publish` mà core gọi.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from xagents_core.sqlite_bus import BUSY_TIMEOUT_S as BUSY_TIMEOUT_S
from xagents_core.sqlite_bus import DDL as DDL
from xagents_core.sqlite_bus import Lease as Lease
from xagents_core.sqlite_bus import LeaseError as LeaseError
from xagents_core.sqlite_bus import SQLiteBus as CoreSQLiteBus

from .bus import InMemoryBus
from .core import CORE
from .events import Envelope

_DDL = DDL  # tên cũ (có gạch dưới) mà test và script cũ nhập


class SQLiteBus(CoreSQLiteBus[Envelope], InMemoryBus):
    def __init__(self, path: str | Path | None = None, enforce_owners: bool = True, cfg: Any = CORE):
        super().__init__(cfg, path, enforce_owners=enforce_owners)
