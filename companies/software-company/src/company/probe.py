"""`python -m company.probe` — CLI `claude` trên máy này có chạy được chế độ tool nào?

Cầu MCP (ADR-0024) và chế độ tool CLI (ADR-0023) đều phụ thuộc thứ nằm ngoài repo: bản `claude` đã cài, tài khoản đã
đăng nhập, và việc CLI có hiểu `--mcp-config` hay không. Không có cách nào biết bằng test — test dùng CLI giả. Nên
lệnh này gọi CLI THẬT một lượt tối thiểu, với một bảng tool chỉ có một tool đếm số lần được gọi, rồi kết luận:

    mcp   — CLI gọi ngược được tool của công ty → dùng `mcp_tools: true`, hàng rào `tools.py` giữ nguyên
    cli   — CLI chạy nhưng không hiểu `--mcp-config` → chỉ còn `cli_tools: true` (hàng rào yếu hơn một bậc)
    none  — không gọi được CLI (chưa cài, chưa đăng nhập, hết hạn mức): không chế độ nào chạy được

Đọc `llm.yaml` để dò đúng những backend `claude-code` bạn đang khai (kể cả nhiều tài khoản qua `config_dir`), hoặc
`--binary`/`--config-dir` để thử một CLI cụ thể. Exit 0 nếu MỌI backend dò được đạt `mcp`; 1 nếu có cái không.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .llm import ClaudeCodeClient, LLMConfig, LLMError, load_config
from .tools import ToolBox, ToolSpec

PROBE_TOOL = "probe_ping"
PROBE_SCHEMA: dict[str, Any] = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
PROBE_PROMPT = (f"Gọi tool `{PROBE_TOOL}` đúng một lần với note=\"probe\", rồi trả về JSON {{\"ok\": true}}. "
                "Không làm gì khác.")


def probe_toolbox() -> tuple[ToolBox, list[str]]:
    """Bảng tool tối thiểu: một tool ghi lại mình đã được gọi. Không chạm file, không chạy lệnh."""
    seen: list[str] = []

    def ping(note: str) -> str:
        seen.append(str(note))
        return "đã nhận"

    tb = ToolBox()
    tb.add(ToolSpec(PROBE_TOOL, "Báo là bạn đọc được bảng tool này; gọi một lần rồi thôi.",
                    {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]}), ping)
    return tb, seen


@dataclass
class Result:
    """Kết luận cho một backend."""
    backend: str
    mode: str                 # mcp | cli | none
    binary: str = ""
    detail: str = ""
    tool_called: bool = False
    model: str = ""

    @property
    def ok(self) -> bool:
        return self.mode == "mcp"

    def line(self) -> str:
        mark = {"mcp": "OK  ", "cli": "HẠN ", "none": "LỖI "}[self.mode]
        return f"  {mark} {self.backend:<16} {self.mode:<5} {self.detail}"


def probe_backend(cfg: LLMConfig, name: str, tier: str = "light", timeout: float = 300.0,
                  runner: Any = None) -> Result:
    """Một lượt gọi thật qua cầu MCP. Tool được gọi = CLI nói chuyện được với `ToolBox` của công ty."""
    cfg.mcp_tools = True
    cfg.cli_tools = False          # muốn biết riêng cầu MCP có chạy không, không để nó lùi sang đường khác
    cfg.mcp_max_turns = 4
    cfg.retries = 0
    tb, seen = probe_toolbox()
    try:
        client = ClaudeCodeClient(cfg, timeout=timeout, **({"runner": runner} if runner else {}))
    except LLMError as e:
        return Result(name, "none", detail=str(e)[:160])
    client.bind_toolbox(tb)
    try:
        c = client.complete(system="Bạn là công cụ tự kiểm. Trả lời ngắn.", user=PROBE_PROMPT,
                            schema=PROBE_SCHEMA, model_tier=tier, tools=tb.specs(), workdir=str(Path.cwd()))
    except LLMError as e:
        msg = str(e)
        if not client.cfg.mcp_tools:   # `_complete_mcp` đã tắt cờ: CLI không biết `--mcp-config`
            return Result(name, "cli", client.binary, "CLI không hỗ trợ --mcp-config (bản quá cũ)")
        return Result(name, "none", client.binary, msg[:160])
    finally:
        client.bind_toolbox(None)
    called = bool(seen) or bool(tb.calls)
    detail = ("CLI gọi được tool của công ty" if called else
              "CLI chạy nhưng KHÔNG gọi tool (model bỏ qua, hoặc --allowedTools không khớp)")
    return Result(name, "mcp" if called else "cli", client.binary, detail, called, c.model)


def backends_to_probe(cfg: LLMConfig, only: str | None = None) -> list[tuple[str, LLMConfig]]:
    """Mọi backend `claude-code` trong cấu hình; không có `backends:` thì chính provider cấp trên nếu là claude-code."""
    out: list[tuple[str, LLMConfig]] = []
    for data in cfg.backends:
        bc = cfg.backend_config(data)
        if bc.provider == "claude-code":
            out.append((bc.name, bc))
    if not out and cfg.provider == "claude-code":
        out.append((cfg.name, cfg))
    return [(n, c) for n, c in out if only is None or n == only]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m company.probe",
                                 description="CLI `claude` trên máy này chạy được chế độ tool nào (ADR-0023/0024)")
    ap.add_argument("--config", type=Path, help="đường dẫn llm.yaml (mặc định: llm.yaml của công ty)")
    ap.add_argument("--backend", help="chỉ dò một backend theo tên")
    ap.add_argument("--binary", help="dò một CLI cụ thể thay vì đọc llm.yaml")
    ap.add_argument("--config-dir", help="CLAUDE_CONFIG_DIR riêng khi dùng --binary (tài khoản khác)")
    ap.add_argument("--model", default="", help="model cho lượt thử (mặc định: tier light của backend)")
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--json", action="store_true", help="in JSON thay vì bảng")
    a = ap.parse_args(argv)

    if a.binary:
        cfg = LLMConfig(provider="claude-code", binary=a.binary, config_dir=a.config_dir,
                        models={"light": a.model or "claude-haiku-4-5"})
        targets = [("(--binary)", cfg)]
    else:
        cfg = load_config(a.config)
        targets = backends_to_probe(cfg, a.backend)
        if a.model:
            for _, c in targets: c.models["light"] = a.model

    if not targets:
        print("Không có backend `claude-code` nào trong cấu hình (thử --binary claude).", file=sys.stderr)
        return 1

    results = [probe_backend(c, n, timeout=a.timeout) for n, c in targets]
    if a.json:
        print(json.dumps([r.__dict__ for r in results], ensure_ascii=False, indent=2))
        return 0 if all(r.ok for r in results) else 1

    print("=" * 72)
    print("  PROBE — chế độ tool khả dụng của CLI `claude`")
    print("=" * 72)
    for r in results:
        print(r.line())
        if r.binary: print(f"       binary: {r.binary}" + (f" · model trả lời: {r.model}" if r.model else ""))
    print("-" * 72)
    if all(r.ok for r in results):
        print("  Mọi backend dùng được `mcp_tools: true` — tool chạy trong sandbox tools.py, audit đầy đủ.")
        return 0
    for r in results:
        if r.mode == "cli":
            print(f"  {r.backend}: chỉ dùng được `cli_tools: true` — hàng rào yếu hơn một bậc (ADR-0023).")
        elif r.mode == "none":
            print(f"  {r.backend}: không chạy được CLI. Kiểm `claude login`, hạn mức, hoặc đường dẫn binary.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
