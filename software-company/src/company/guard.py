"""Shim có RÀNG BUỘC: `company.guard` = `xagents_core.guard` đã gắn sẵn `CORE` của công ty này (K3.4).

Không phải `import *` thuần như `routing.py`: `guard_payload` cần biết topic nào là ngoài, trường nào không tin
cậy — đó là nghĩa của từng công ty, nằm ở `CoreConfig` (xem `core.py`). Nên ở đây mỗi hàm được `partial` với
`core=CORE` và bảng mẫu đã biên dịch một lần, để 4 nơi gọi (`runner`, `web`, `supervisor`, `mcp_bridge`) giữ
nguyên chữ ký cũ `scan(text)` / `guard_payload(topic, actor, payload)`.

Bảng mẫu chung của core ĐÃ LÀ bảng của company; `CORE.extra_injection_patterns` để trống có chủ ý (lý do ở
`core.py`). Xoá shim ở chân trời 3, xem `docs/DAC-TA-KICH-BAN-B.md` K3.a.
"""
from __future__ import annotations

import functools

from xagents_core.guard import LABEL as LABEL
from xagents_core.guard import PATTERNS as PATTERNS
from xagents_core.guard import ScanResult as ScanResult
from xagents_core.guard import compile_patterns
from xagents_core.guard import guard_payload as _guard_payload
from xagents_core.guard import is_external as _is_external
from xagents_core.guard import normalize as normalize
from xagents_core.guard import sanitize as _sanitize
from xagents_core.guard import sanitize_text as _sanitize_text
from xagents_core.guard import sanitize_tool_output as _sanitize_tool_output
from xagents_core.guard import scan as _scan
from xagents_core.guard import scan_obj as _scan_obj

from .core import CORE

# Bảng mẫu ĐÃ BIÊN DỊCH của công ty này (chung + riêng). Công khai vì `assetscan.py` quét file prompt trong repo
# bằng đúng bảng ấy — "một nguồn sự thật duy nhất cho cả hai lớp" (xem docstring `assetscan.py`). Trước K3.4 nó
# đọc `guard._COMPILED`, một tên riêng tư; đặt tên công khai để chỗ dùng không phải với tay vào ruột module.
COMPILED = compile_patterns(CORE.extra_injection_patterns)
_PATTERNS = COMPILED

scan = functools.partial(_scan, patterns=_PATTERNS)
scan_obj = functools.partial(_scan_obj, patterns=_PATTERNS)
sanitize = functools.partial(_sanitize, patterns=_PATTERNS)
sanitize_text = functools.partial(_sanitize_text, patterns=_PATTERNS)
sanitize_tool_output = functools.partial(_sanitize_tool_output, patterns=_PATTERNS)
guard_payload = functools.partial(_guard_payload, core=CORE, patterns=_PATTERNS)
is_external = functools.partial(_is_external, external_topics=CORE.external_topics)

__all__ = ["COMPILED", "LABEL", "PATTERNS", "ScanResult", "guard_payload", "is_external", "normalize", "sanitize",
           "sanitize_text", "sanitize_tool_output", "scan", "scan_obj"]
