"""Shim: giữ tên `company.routing` cho console/test đang import. Bản thật ở `xagents_core.routing` (K3.3d) — nó
LÀ bản company, nên không có điểm nâng nào ở bước này. Xoá ở chân trời 3, xem `docs/DAC-TA-KICH-BAN-B.md` K3.a."""
from xagents_core.routing import *  # noqa: F403
from xagents_core.routing import __all__  # noqa: F401
