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
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Self, TypeVar, cast

import yaml

from .config import CoreConfig

__all__ = ["ARGV_LIMIT", "CLAUDE_EFFORT", "CLI_BASE_FLAGS", "CLI_SUBTYPE_ERRORS", "CODEX_EFFORT", "TIERS",
           "TRANSIENT_HTTP", "LLMConfig", "LLMError", "Refused", "TransientError", "cli_effort_args",
           "find_codex_binary", "load_config", "neutral_messages", "reported_model", "strict_schema",
           "system_prompt_args"]

C = TypeVar("C", bound="LLMConfig")

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


# ---------- cấu hình (K3.3b) ----------

@dataclass
class LLMConfig:
    """Cấu hình lớp LLM của MỘT công ty — phần hai công ty khai giống nhau.

    Đây là bước b của K3.3: `LLMConfig`/`load_config` là chỗ duy nhất trong `llm.py` mà hai bản chỉ khác nhau ở
    *tên biến môi trường* và *tập trường phụ*, chứ không khác thuật toán (khác thuật toán là bốn adapter và
    `Completion.json()` — bước c). `difflib` đo `LLMConfig` 0.56 chủ yếu vì company có 14 trường studio không có
    (CLI/MCP, giá, ngân sách, sandbox, retry): bỏ khối trường đó ra thì phần còn lại trùng gần nguyên văn, kể cả
    thứ tự dòng trong `backend_config`.

    **Vì sao kế thừa chứ không tham số hoá bằng cờ.** Trường phụ của company là *dữ liệu*, không phải hành vi:
    `retries`, `prices`, `sandbox`… phải có kiểu thật để mypy bắt được chỗ đọc sai tên. Nhét chúng vào một
    `dict[str, Any]` chung ở core là đổi 14 trường có kiểu lấy một túi `Any` — mất đúng thứ mà `strict` của core
    sinh ra để giữ. Nên core giữ khung + khoá dùng chung, mỗi công ty kế thừa và **ghi đè ba móc**
    (`apply_backend_yaml`, `apply_yaml`, `apply_env`), mỗi móc gọi `super()` trước rồi đọc thêm phần của mình.

    `PREFIX` là `ClassVar` (không phải trường) vì hai lẽ: `backend_config` sao chép `self.__dict__` nên mọi trường
    đều bị nhân bản xuống từng backend — tiền tố công ty thì không có lý do gì để khác nhau giữa hai backend của
    cùng một công ty; và một `LLMConfig()` dựng tay trong test vẫn phải báo lỗi đúng tên biến, không phải chuỗi
    rỗng vì người dựng quên truyền tiền tố.
    """
    PREFIX: ClassVar[str] = ""   # company/studio gán = CORE.prefix; core không tự biết mình phục vụ ai

    provider: str = "fake"       # công ty ghi đè mặc định của mình (company: anthropic)
    models: dict[str, str] = field(default_factory=lambda: dict.fromkeys(TIERS, ""))
    base_url: str | None = None
    api_key: str | None = None
    max_tokens: int = 16_000
    effort: dict[str, str] = field(default_factory=lambda: {"strong": "high", "standard": "medium", "light": "low"})
    extra: dict[str, Any] = field(default_factory=dict)  # tham số provider-specific, truyền thẳng vào request
    config_dir: str | None = None    # claude-code: CLAUDE_CONFIG_DIR / codex: CODEX_HOME riêng → tài khoản khác trên cùng máy
    binary: str | None = None        # đường dẫn CLI (claude / codex) khi không có trên PATH
    name: str = "default"            # tên backend, hiện trong ghi chú audit khi xoay
    backends: list[dict[str, Any]] = field(default_factory=list)   # mỗi phần tử = một backend, cùng khoá như cấp trên
    routing: dict[str, Any] = field(default_factory=dict)          # cooldown_s, transient_cooldown_s, prefer{tier: backend}
    max_input_chars: int = 120_000   # trần ký tự prompt (≈ 37k token); runner cắt payload/blackboard theo `context.py`

    def model_for(self, tier: str) -> str:
        """light → standard → strong: backend không có model rẻ thì dùng model tầm trung, không bao giờ lùi lên tier cao
        hơn yêu cầu trừ khi đó là model duy nhất."""
        m = self.models.get(tier) or self.models.get("standard") or self.models.get("strong") or ""
        if not m:
            raise LLMError(f"chưa cấu hình model cho tier `{tier}` ({self.PREFIX}_MODEL_{tier.upper()} hoặc llm.yaml)")
        return m

    def tiers_configured(self) -> frozenset[str]:
        return frozenset(t for t in TIERS if self.models.get(t))

    def apply_backend_yaml(self, data: Mapping[str, Any]) -> None:
        """Khoá đọc được ở CẢ HAI cấp: gốc `llm.yaml` và từng phần tử `backends:`. Công ty ghi đè để đọc thêm khoá
        của mình (company: `cli_*`, `mcp_*`) — thêm ở đây thì cả hai cấp cùng hiểu, không phải nhớ sửa hai chỗ."""
        self.provider = data.get("provider", self.provider)
        self.models.update({k: str(v) for k, v in (data.get("models") or {}).items()})
        self.effort.update(data.get("effort") or {})
        self.base_url = data.get("base_url", self.base_url)
        self.max_tokens = int(data.get("max_tokens", self.max_tokens))
        if "extra" in data: self.extra = dict(data.get("extra") or {})

    def apply_yaml(self, data: Mapping[str, Any]) -> None:
        """Khoá chỉ đọc được ở GỐC `llm.yaml`."""
        self.apply_backend_yaml(data)
        # Cố ý KHÔNG ở trong `apply_backend_yaml`: trần prompt là thuộc tính của cả hệ, không của một backend —
        # mỗi backend một trần khác nhau thì cùng một agent bị cắt khác nhau tuỳ tài khoản nào còn hạn mức.
        self.max_input_chars = int(data.get("max_input_chars", self.max_input_chars))
        self.backends = [dict(b) for b in (data.get("backends") or []) if isinstance(b, dict)]
        self.routing = dict(data.get("routing") or {})

    def apply_env(self, env: Mapping[str, str], core: CoreConfig) -> None:
        """Biến môi trường thắng file. Tên biến đi qua `core.env_name` — core không tự ghép tiền tố ở nơi dùng."""
        if env.get(core.env_name("LLM_PROVIDER")):   # một provider được chỉ đích danh → bỏ `backends:`
            self.provider, self.backends = env[core.env_name("LLM_PROVIDER")], []
        for t in TIERS:
            if env.get(core.env_name(f"MODEL_{t.upper()}")): self.models[t] = env[core.env_name(f"MODEL_{t.upper()}")]
        self.base_url = env.get(core.env_name("LLM_BASE_URL"), self.base_url)
        self.api_key = env.get(core.env_name("LLM_API_KEY"), self.api_key)
        if env.get(core.env_name("MAX_INPUT_CHARS")):
            self.max_input_chars = int(env[core.env_name("MAX_INPUT_CHARS")])

    def select_backends(self, env: Mapping[str, str], core: CoreConfig) -> None:
        """`<PREFIX>_LLM_BACKENDS` lọc/sắp thứ tự `backends:`. Tách khỏi `apply_env` và gọi SAU CÙNG trong
        `load_config`: nó đọc `self.backends` mà `apply_env` của công ty có thể còn ghi vào, và một lớp con quên
        gọi `super()` đúng chỗ thì bộ lọc lặng lẽ chạy trên danh sách cũ."""
        raw = env.get(core.env_name("LLM_BACKENDS"))
        if not raw: return
        wanted = [s.strip() for s in raw.split(",") if s.strip()]
        by_name = {str(b.get("name") or b.get("provider")): b for b in self.backends}
        missing = [w for w in wanted if w not in by_name]
        if missing:
            raise LLMError(f"{core.env_name('LLM_BACKENDS')} nhắc backend không có trong llm.yaml: {missing}")
        self.backends = [by_name[w] for w in wanted]
        if self.routing.get("prefer"):   # prefer trỏ backend đã bị lọc bỏ thì bỏ mục đó, không phải lỗi cấu hình
            self.routing["prefer"] = {t: n for t, n in self.routing["prefer"].items() if n in wanted}

    def backend_config(self, data: Mapping[str, Any]) -> Self:
        """Cấu hình cho một phần tử `backends:`: thừa kế mọi khoá dùng chung (retry, giá, trần ký tự) từ cấp trên,
        ghi đè provider / models / base_url / api_key / effort / extra / max_tokens theo phần tử.

        `type(self)` chứ không phải `LLMConfig`: lớp con của công ty phải sinh ra chính lớp con đó, nếu không mọi
        trường phụ (giá, ngân sách, sandbox) biến mất ngay khi cấu hình có `backends:`.
        """
        cfg = type(self)(**{k: v for k, v in self.__dict__.items() if k not in {"backends", "routing"}})
        cfg.models = dict(self.models) if data.get("inherit_models") else dict.fromkeys(TIERS, "")
        cfg.effort, cfg.extra = dict(self.effort), dict(self.extra)
        cfg.apply_backend_yaml(data)
        cfg.name = str(data.get("name") or cfg.provider)
        cfg.config_dir = str(data["config_dir"]) if data.get("config_dir") else None
        cfg.binary = str(data["binary"]) if data.get("binary") else None
        if data.get("api_key"): cfg.api_key = str(data["api_key"])
        if data.get("api_key_env"): cfg.api_key = os.environ.get(str(data["api_key_env"]), cfg.api_key)
        return cfg


def load_config(core: CoreConfig, path: Path | None = None, *, cls: type[C]) -> C:
    """`llm.yaml` của công ty rồi biến môi trường đè lên. `cls` là lớp cấu hình của công ty — bắt buộc, không có
    mặc định: một `load_config` lỡ trả `LLMConfig` trần cho company thì mất im lặng cả `prices` lẫn `sandbox`,
    và mypy không cứu được vì lớp con vẫn là `LLMConfig`."""
    cfg = cls()
    p = path or core.config_file
    if p.exists():
        cfg.apply_yaml(yaml.safe_load(p.read_text(encoding="utf-8")) or {})
    cfg.apply_env(os.environ, core)
    cfg.select_backends(os.environ, core)
    return cfg

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
