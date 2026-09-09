"""Khung runner chung của hai công ty (K3.6d1 của ADR gốc 0001).

**Vì sao K3.6d lại tách đôi, và vì sao bước này CHỈ có ngần này.**

Đo theo symbol (bài học K3.6c — `difflib` trên cả file chỉ dùng để xếp thứ tự module):

| symbol | difflib | | symbol | difflib |
|---|---|---|---|---|
| `RunnerError`, `payload_schema` | **1.00** | | `_complete` | 0.32 |
| `run` | 0.91 | | `output_schema` | 0.21 |
| `RunResult` | 0.86 | | `_tool_loop`(+`_turns`) | **0.12** |
| `__init__` | 0.83 | | `write_context` | 0.15 |
| `build_user_message` | 0.74 | | `AgentRunner` (cả lớp) | 0.14 |
| `context_writes_schema` | 0.69 | | | |

`output_schema` 0.21 là một cái bẫy đọc số: hai bản **giống hệt nhau về logic**, lệch chỉ vì company có
docstring còn studio không. Đọc bằng mắt mới thấy; tin con số thì đã tách nhầm.

**Ràng buộc thật của K3.6d không phải độ lệch mã, mà là BẢN GHI EVAL.** Khoá bản ghi là
`hash(system_prompt, user_message)`, và `user_message` do `build_user_message` sinh ra. Đo trực tiếp: thêm
**một dấu cách** vào chuỗi cuối của `build_user_message` studio rồi chạy `python -m studio.evals all --replay`
— mọi ca chuyển thành *"bản ghi eval lệch prompt hiện tại"*. Nghĩa là hợp nhất bất kỳ CHỮ nào trong prompt
(`build_user_message`, `context_writes_schema`, `tools_prompt`) đòi chạy lại `make eval-record` bằng **model
thật** cho cả 20 agent — bảy bước `CONTRIBUTING.md` §3, cần API key. Đó là việc của một PR khác, có người và
có key; không phải của một PR chuyển mã.

Nên bước này giữ **mọi chuỗi prompt nguyên vẹn từng byte ở từng công ty**, và chỉ đưa lên core thứ chứng minh
được là không đụng tới prompt: ba lớp kết quả, và hai hàm schema.

`context_writes_schema` **ở lại từng công ty**, dù `difflib` 0.69 trông như gộp được: company bắt buộc trường
`content` (toàn văn artifact, ADR-0012), studio thì không. Cho studio bản company là đổi hợp đồng đầu ra của
14 agent — tức là đổi prompt. `output_schema` vì thế **nhận** schema ấy làm tham số thay vì tự dựng.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["Generated", "RunResult", "RunnerError", "output_schema", "payload_schema"]


class RunnerError(Exception): ...


@dataclass
class RunResult:
    """Một lượt agent đã publish. Company thêm `cost_usd`; studio chưa tính tiền nên nó ở lớp con."""
    output: Any          # `Envelope` của công ty — core không thu hẹp, lớp con thu hẹp (tiền lệ K3.5a)
    tokens: int
    model: str


@dataclass
class Generated:
    """Đầu ra model đã qua kiểm tra schema nhưng CHƯA publish (để code xác định quyết định).

    Bảy trường ở đây là phần CẢ HAI công ty ghi. Company thêm sáu trường của mình (`output_tokens`,
    `cost_usd`, `priced`, `duration_ms`, `phase`) ở lớp con — cùng lý do `AuditLog` ở K3.5a: đưa
    `phase` (ADR-0037) lên core là bắt studio mang một trường nó không bao giờ ghi."""
    payloads: list[dict[str, Any]]
    tokens: int
    model: str
    context_writes: list[dict[str, Any]] = field(default_factory=list)
    cache_hit_ratio: float = 0.0  # phần input lấy từ prompt cache, để đo hiệu quả cache trong audit-log
    turns: int = 1                # số lượt gọi model (1 = không dùng tool)
    tool_calls: dict[str, int] = field(default_factory=dict)  # tên tool → số lần gọi


def payload_schema(schema_dir: Path, topic: str) -> dict[str, Any]:
    """Phần `payload` trong JSON Schema của một topic. Giống hệt nhau hai bên (`difflib` 1.00)."""
    p = schema_dir / f"{topic}.json"
    if not p.exists():
        raise RunnerError(f"không có schema cho topic {topic}")
    got: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))["properties"]["payload"]
    return got


def output_schema(schema: dict[str, Any] | None, namespaces: list[str], many: bool,
                  writes_schema: dict[str, Any]) -> dict[str, Any]:
    """Schema gốc gửi cho model. Agent không sở hữu namespace và chỉ trả một payload: giữ nguyên schema topic.
    Ngược lại bọc thành {"payload"|"items": ..., "context_writes": [...]} (structured output cần object ở gốc).

    `writes_schema` là tham số chứ không dựng tại chỗ: hình dạng `context_writes` là **hợp đồng đầu ra** của
    agent, tức là prompt, tức là của từng công ty (company đòi `content`, studio không) — xem docstring module."""
    if schema is None:  # context-only
        return {"type": "object", "properties": {"context_writes": writes_schema}, "required": ["context_writes"]}
    if not namespaces and not many:
        return schema
    props: dict[str, Any] = {"items": {"type": "array", "items": schema}} if many else {"payload": schema}
    if namespaces: props["context_writes"] = writes_schema
    return {"type": "object", "properties": props, "required": ["items" if many else "payload"]}
