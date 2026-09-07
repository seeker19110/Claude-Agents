"""Khung bảng tool có ranh giới tin cậy — lõi chung hai công ty (ADR-0010 company / ADR-0007 studio, K3.2).

Đầu ra của model là dữ liệu không tin cậy, nên tool KHÔNG bao giờ nhận lệnh tự do: chỉ có một bảng tool tên cố
định, mỗi tool tự kiểm tham số, lỗi trả về cho model dưới dạng **chuỗi** (model đọc rồi tự sửa) — `ToolError` chỉ
ném khi tool không tồn tại.

Module này chỉ có phần KHUNG. Các bảng tool thật ở lại nơi chúng thuộc về, vì chúng là ranh giới bảo mật của hai
miền khác nhau: `company.tools.WorkspaceTools` (đường dẫn khoá trong worktree, allowlist lệnh) và
`studio.tools.WebTools` (web chỉ đọc, chặn IP nội bộ, chống DNS rebinding). `tools_prompt` cũng ở lại: chữ ký hai
bên đã lệch (company nhận thêm `can_write`), gộp lại là thêm một tham số mà một bên không bao giờ dùng.

`max_output` là chỗ **duy nhất** hai bên từng khác nhau trong khung này, nên nó là tham số chứ không phải hằng:
company cắt 6.000 ký tự mỗi lần gọi để một `pytest -q` dài không nuốt hết cửa sổ ngữ cảnh; studio để `None` vì
`web_fetch` đã tự cắt ở `MAX_CHARS` (20.000) sau khi bóc HTML — cắt lần hai ở tầng bảng chỉ làm mất phần cuối
trang mà không ai yêu cầu. Mặc định lấy theo company (bên có 4 nơi khởi tạo, ADR gốc 0001: company là gốc), nên
bên nào muốn khác phải nói ra.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

__all__ = ["MAX_OUTPUT", "ToolBox", "ToolCall", "ToolError", "ToolSpec"]

MAX_OUTPUT = 6_000  # ký tự trả về cho model mỗi lần gọi tool


class ToolError(Exception): ...


@dataclass(frozen=True)
class ToolSpec:
    """Mô tả tool trung lập provider; adapter đổi sang định dạng của Anthropic/OpenAI."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema của tham số


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass
class ToolBox:
    """Bảng tool: tên → (spec, hàm). Không có tool = không có hành động; model chỉ chọn trong bảng."""
    _tools: dict[str, tuple[ToolSpec, Callable[..., str]]] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)  # vết gọi để audit
    root: str | None = None  # thư mục gốc của bảng tool; provider tự chạy tool (claude-code cli_tools) cần biết cwd
    # TÊN sandbox mà lệnh của bảng này chạy trong đó (`subprocess` | `container:<image>`), `None` khi bảng không có
    # lệnh nào chạy được (`allow_run=False`). Đặt ở BẢNG chứ không ở từng vết gọi: `read_file`/`search` không chạy
    # lệnh gì, lặp chuỗi sandbox vào vết gọi của chúng làm người đọc audit tưởng chúng cũng đi qua sandbox.
    sandbox: str | None = None
    max_output: int | None = MAX_OUTPUT  # `None` = không cắt ở tầng bảng (xem docstring module)

    def add(self, spec: ToolSpec, fn: Callable[..., str]) -> None:
        self._tools[spec.name] = (spec, fn)

    def specs(self) -> list[ToolSpec]:
        return [s for s, _ in self._tools.values()]

    def call(self, tc: ToolCall) -> str:
        if tc.name not in self._tools:
            raise ToolError(f"tool không tồn tại: {tc.name}")
        spec, fn = self._tools[tc.name]
        args = tc.args if isinstance(tc.args, dict) else {}
        allowed = set(spec.parameters.get("properties", {}))
        extra = set(args) - allowed
        missing = set(spec.parameters.get("required", [])) - set(args)
        if extra or missing:
            out = f"lỗi tham số: thừa {sorted(extra)} thiếu {sorted(missing)}"
        else:
            try:
                out = fn(**args)
            except ToolError as e:
                out = f"lỗi: {e}"
            except (TypeError, ValueError) as e:
                out = f"lỗi tham số: {e}"
        out = str(out)
        if self.max_output is not None and len(out) > self.max_output:
            out = out[:self.max_output] + f"\n… (cắt, còn {len(out) - self.max_output} ký tự)"
        self.calls.append({"name": tc.name, "args": args, "ok": not out.startswith("lỗi"), "chars": len(out)})
        return out

    def summary(self) -> dict[str, int]:
        c: dict[str, int] = {}
        for x in self.calls: c[x["name"]] = c.get(x["name"], 0) + 1
        return c

    def urls(self) -> list[str]:
        """URL đã fetch THÀNH CÔNG, theo thứ tự gọi: studio đưa vào evidence của `fact-checker` để người duyệt
        gate biết kết luận dựa trên trang nào."""
        return [str(x["args"].get("url")) for x in self.calls
                if x["name"] == "web_fetch" and x["ok"] and x["args"].get("url")]
