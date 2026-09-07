"""`CoreConfig` — chỗ DUY NHẤT core biết một công ty khác công ty kia ở đâu (ADR gốc 0001 §2).

Mỗi công ty dựng đúng một `CoreConfig` (`company/core.py`, `studio/core.py`) rồi truyền xuống. Thêm một điểm
khác biệt mới thì thêm một TRƯỜNG ở đây, không thêm một câu `if` trong core.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TopicACL:
    """Ai được ghi vào topic nào. Nội dung là của từng công ty; hình dạng là của core.

    `producers` liệt kê actor được phép cho từng topic. Ba tập còn lại là các miễn trừ có tên, thay cho việc
    rải điều kiện trong `bus.publish`: topic người ghi, topic mở cho mọi actor, và hai nhóm actor mà company
    dùng để nới quyền theo vai (kỹ thuật, review).
    """
    producers: Mapping[str, frozenset[str]] = field(default_factory=dict)
    human_topics: frozenset[str] = frozenset()
    open_topics: frozenset[str] = frozenset()
    engineering_actors: frozenset[str] = frozenset()
    review_producers: frozenset[str] = frozenset()


@dataclass(frozen=True)
class CoreConfig:
    """Một công ty, nhìn từ core.

    `prefix` ("COMPANY" | "STUDIO") là tiền tố của MỌI biến môi trường, của thông điệp lỗi có nhắc biến, và của
    tên tool MCP. Nó viết HOA vì biến môi trường viết hoa; chỗ nào cần chữ thường thì hạ tại chỗ dùng.

    `root` là gốc thư mục công ty — nơi có `llm.yaml`, `agents/`, `skills/`, `topics/schemas/`, `evals/`.
    Core không đoán đường dẫn nào từ `__file__` của chính nó: làm thế là core biết mình nằm ở đâu so với công
    ty, tức là lại buộc chặt vào bố cục repo.
    """
    prefix: str
    root: Path
    db_name: str
    topic_acl: TopicACL = field(default_factory=TopicACL)
    # `type[BaseModel]` để `Any`: nhập pydantic ở đây chỉ để chú kiểu sẽ buộc mọi thứ dùng CoreConfig phải có
    # pydantic trong đồ thị nhập, kể cả phần không đụng tới payload. Hợp đồng thật nằm ở nơi validate.
    payload_models: Mapping[str, Any] = field(default_factory=dict)
    namespace_owners: Mapping[str, str] = field(default_factory=dict)
    transitions: Mapping[str, frozenset[str]] = field(default_factory=dict)
    external_topics: frozenset[str] = frozenset()
    derived_topics: frozenset[str] = frozenset()

    @property
    def config_file(self) -> Path:
        """`llm.yaml` của công ty."""
        return self.root / "llm.yaml"

    @property
    def schema_dir(self) -> Path:
        """`topics/schemas/` — JSON schema của từng topic."""
        return self.root / "topics" / "schemas"

    @property
    def approvers_env(self) -> str:
        """Biến khai danh sách người được duyệt gate (four-eyes). Suy ra từ `prefix` thay vì là một trường
        riêng: hai nguồn cho một sự thật thì sớm muộn chúng lệch."""
        return self.env_name("GATE_APPROVERS")

    def env_name(self, ten: str) -> str:
        """`COMPANY_MODEL_STRONG`, `STUDIO_LLM_PROVIDER`… — một chỗ ghép tiền tố cho cả core.

        Mọi biến môi trường của core đi qua đây. Viết thẳng `f"{cfg.prefix}_..."` ở nơi dùng thì mỗi nơi tự
        chọn dấu nối, và một chỗ gõ sai sẽ im lặng đọc ra biến không tồn tại.
        """
        return f"{self.prefix}_{ten}"
