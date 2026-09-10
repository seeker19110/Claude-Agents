"""Shim: giữ tên `company.context` cho console/test/tài liệu đang import. Bản thật ở `xagents_core.context`
(ADR gốc 0001, bước K3.1). Xoá ở chân trời 3 khi console đổi import — xem `docs/DAC-TA-KICH-BAN-B.md` K3.a."""
from xagents_core.context import *  # noqa: F403
from xagents_core.context import __all__  # noqa: F401
