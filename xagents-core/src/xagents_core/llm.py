"""Nền chung của lớp LLM hai công ty (K3.3a của ADR gốc 0001).

**Vì sao chỉ có phần nền, không phải cả `llm.py`.** Đặc tả K3.3 viết "gốc là `company/llm.py` (1.128 dòng), tham số
hoá 8 điểm rồi studio thành shim". Đo lại bằng `difflib` trên từng symbol thì giả định đó sai: hai bản đã trôi xa
nhau, chỉ 6/22 symbol cùng tên là trùng gần nguyên văn. Ba lớp nặng nhất lệch hẳn — `ClaudeCodeClient` 0.32,
`OpenAICompatClient` 0.28, `Completion` 0.23 (hai **thuật toán bóc JSON khác nhau**), `LLMConfig` 0.56. Gộp chúng
trong một PR là đổi cách studio đọc mọi đầu ra model, đổi cấu hình, và đổi bốn adapter cùng một lúc — không có
cách nào đọc diff đó mà biết chắc studio còn chạy đúng. Nên K3.3 tách theo *mức rủi ro*: file này là phần **trùng
thật và không đổi hành vi bên nào**; phần đã rẽ nhánh đi các PR sau, mỗi PR một quyết định hợp nhất nói rõ bên nào
được nâng và eval nào chứng minh.

Ba chỗ studio **được nâng** ở đây, đều tương thích ngược (ADR gốc 0001 nguyên tắc 1):

1. `LLMError.status` — studio trước không mang mã HTTP; mặc định `None` nên mọi chỗ `LLMError("…")` cũ vẫn đúng.
   Đây là điều kiện để K3.3d cho studio phân loại lỗi tạm thời theo mã thay vì đoán bằng regex.
2. `TransientError` — studio chưa từng có; chưa ai ném nó trong studio nên chưa đổi gì, nhưng nó phải tồn tại
   trước khi `studio.orchestrator` biết hoãn event thay vì dừng.
3. `reported_model` đọc thêm `canonicalModel` — bản company; studio trước bỏ sót nên model được CLI quy đổi
   (alias → model thật) bị coi là "không khớp".

`ARGV_LIMIT` là tên của company; studio gọi cùng hằng số đó là `CLI_ARGV_MAX` — shim studio giữ cả hai tên.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

__all__ = ["ARGV_LIMIT", "CLAUDE_EFFORT", "CLI_BASE_FLAGS", "CLI_SUBTYPE_ERRORS", "CODEX_EFFORT", "TIERS",
           "TRANSIENT_HTTP", "LLMError", "Refused", "TransientError", "cli_effort_args", "find_codex_binary",
           "neutral_messages", "reported_model", "strict_schema", "system_prompt_args"]

TIERS = ("strong", "standard", "light")   # light: việc cơ học/ngắn (intake, clarifier, publisher, supervisor) — model rẻ nhất
TRANSIENT_HTTP = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 529})


class LLMError(Exception):
    """`status`: mã HTTP của provider khi biết — routing phân loại theo mã (429 quota, 404 thiếu model, 401/403 xác thực)
    thay vì đoán bằng regex trên thông điệp."""
    def __init__(self, message: str = "", status: int | None = None):
        super().__init__(message); self.status = status


class Refused(LLMError):
    """Model từ chối trả lời. Không retry mù; để supervisor escalate."""


class TransientError(LLMError):
    """Lỗi vận chuyển (mạng, quá tải, rate limit): thử lại được, không phải lỗi của agent."""


def neutral_messages(user: str, messages: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return messages if messages is not None else [{"role": "user", "content": user}]


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Structured output ở nhiều provider cần `additionalProperties: false` ở mọi object; bản sao, không đổi schema gốc."""
    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            out = {k: walk(v) for k, v in node.items() if k not in {"$schema", "$id", "format"}}
            if out.get("type") == "object":
                out["additionalProperties"] = False
                out.setdefault("properties", {})
            return out
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node
    # `walk` trả `Any` vì nó đệ quy trên cây JSON; `strict` của core bắt chỗ này, mypy lỏng của
    # company thì không — schema vào là object nên ra cũng là object.
    return cast("dict[str, Any]", walk(schema))


def reported_model(model_usage: dict[str, Any], requested: str) -> str:
    """`claude -p` liệt kê trong `modelUsage` cả model phụ mà CLI tự gọi (Haiku cho việc lặt vặt) — thường đứng TRƯỚC
    model chính. Chọn khoá khớp tên model đã yêu cầu; không có thì khoá tiêu nhiều output token nhất; rỗng thì tên yêu cầu.

    HỢP NHẤT hai bản, cả hai bên đều được nâng — đây là chỗ duy nhất trong K3.3a mà không bên nào là "gốc":

    - `canonicalModel` là của studio. Company thiếu, nên khi CLI quy đổi alias sang model thật thì company không
      khớp được và rơi xuống nhánh đoán theo output token.
    - Fallback "khoá tiêu nhiều output token nhất" và `if not model_usage: return requested` là của company.
      Studio thiếu, nên studio trả chuỗi RỖNG khi không khớp — mà rỗng đi thẳng vào audit như thể CLI không báo
      model nào.
    """
    if not model_usage: return requested
    for k, v in model_usage.items():
        canonical = str(v.get("canonicalModel", "")) if isinstance(v, dict) else ""
        if k == requested or k.startswith(requested) or requested.startswith(k) or canonical.startswith(requested):
            return k
    def out(k: str) -> int:
        v = model_usage.get(k)
        return int(v.get("outputTokens", 0) or 0) if isinstance(v, dict) else 0
    return max(model_usage, key=out)


# ---------- adapter CLI (claude / codex): phần không phụ thuộc công ty ----------

ARGV_LIMIT = 30_000 if os.name == "nt" else 120_000   # Windows: CreateProcess ~32K ký tự; Linux: một đối số ≤ 128K

# `--effort` theo tier — bảng ĐÓNG, giá trị ngoài bảng phải hỏng to thay vì rơi về mặc định (bài học `none` của
# codex: cấu hình nói một đằng, CLI chạy một nẻo).
CLAUDE_EFFORT = ("low", "medium", "high", "xhigh", "max")
CODEX_EFFORT = {"none": "none", "low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh",
                "max": "xhigh", "minimal": "minimal"}

# `--no-session-persistence`: mỗi lượt `-p` mặc định ghi transcript (chứa mã của khách, kịch bản, dossier, kết quả
# web) ra ~/.claude/projects; gọi hàng trăm lượt là hàng trăm bản sao nằm ngoài kho của công ty.
CLI_BASE_FLAGS = ("--no-session-persistence",)

# `subtype` trong JSON của `claude -p` nói vì sao phiên dừng; `result` có thể vắng ở các subtype lỗi. Adapter chỉ
# nhìn `result` thì hết lượt bị báo thành "thiếu trường result" — người vận hành không biết phải tăng gì.
CLI_SUBTYPE_ERRORS = {
    "error_max_turns": "CLI hết lượt (tăng trần lượt tool hoặc chia nhỏ việc)",
    "error_max_budget_usd": "CLI chạm trần chi phí `--max-budget-usd`",
    "error_max_structured_output_retries": "CLI không ép được đầu ra đúng JSON Schema sau nhiều lần thử",
    "error_during_execution": "CLI lỗi khi đang chạy",
}


@contextmanager
def system_prompt_args(system: str) -> Iterator[list[str]]:
    """`--system-prompt-file <path>` thay vì `--system-prompt <text>`: agent nhiều skill (vd. researcher) có system
    prompt riêng đã sát hoặc vượt ARGV_LIMIT trên Windows; ghi ra file tạm thì argv chỉ còn một đường dẫn ngắn,
    không đụng trần argv nữa (nội dung vẫn không qua stdin, để không lẫn với prompt/schema của user message)."""
    fd, path = tempfile.mkstemp(prefix="claude-sp-", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f: f.write(system)
        yield ["--system-prompt-file", path]
    finally:
        Path(path).unlink(missing_ok=True)


def cli_effort_args(effort: dict[str, str], tier: str) -> list[str]:
    """`--effort <mức>` cho tier; không khai tier → không thêm cờ (CLI dùng mặc định của nó); khai sai → lỗi rõ."""
    level = effort.get(tier)
    if level is None: return []
    if level not in CLAUDE_EFFORT:
        raise LLMError(f"claude-code: effort `{level}` cho tier `{tier}` không hợp lệ; CLI chỉ nhận "
                       f"{'|'.join(CLAUDE_EFFORT)} (khai `effort:` riêng cho backend này trong llm.yaml)")
    return ["--effort", level]


def find_codex_binary(binary: str = "codex") -> str:
    """`codex` trên PATH; không có thì tìm bản đi kèm app Codex trên Windows (%LOCALAPPDATA%/OpenAI/Codex/bin/*/codex.exe)."""
    found = shutil.which(binary)
    if found: return found
    base = os.environ.get("LOCALAPPDATA")
    if base:
        cands = sorted(Path(base).glob("OpenAI/Codex/bin/*/codex.exe"), key=lambda p: p.stat().st_mtime, reverse=True)
        if cands: return str(cands[0])
    return binary
