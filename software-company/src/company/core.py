"""`CORE` — công ty gia công phần mềm, nhìn từ `xagents_core` (ADR gốc 0001 §2).

Một chỗ DUY NHẤT nói "công ty này tên COMPANY, gốc ở đây, bus tên `company.sqlite`". Mọi module của company cần
một trong ba thứ đó thì đọc từ đây, không tự dựng lại từ `__file__` của mình — hai nguồn cho một sự thật thì sớm
muộn chúng lệch (và lệch đường dẫn gốc là đọc nhầm `llm.yaml` của repo khác mà không có lỗi nào nổi lên).

Các trường còn lại của `CoreConfig` (`topic_acl`, `payload_models`, `namespace_owners`, `transitions`,
`external_topics`, `derived_topics`) điền ở K3.4/K3.5 khi guard và bus chuyển sang core — khai trước một bảng
rỗng ở đây là mời người sau tin vào nó.
"""
from __future__ import annotations

from pathlib import Path

from xagents_core.config import CoreConfig

CORE = CoreConfig(
    prefix="COMPANY",
    root=Path(__file__).resolve().parents[2],   # software-company/ : llm.yaml, agents/, skills/, topics/schemas/
    db_name="company.sqlite",
)
