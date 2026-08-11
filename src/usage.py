"""Đo lường token & chi phí THẬT của từng lượt gọi LLM, tách theo vai trò.

Trước đây UI ước lượng token bằng `len(text) / 4` — một con số hoàn toàn bịa, không
liên quan tới hóa đơn thật, và càng sai khi mỗi vai trò được cấu hình một
provider/model khác nhau (xem `AI_MODEL_SETUP.md`). Module này đọc `usage_metadata`
mà LangChain trả về kèm mỗi `AIMessage` (input/output token do chính nhà cung cấp
báo về) và cộng dồn theo vai trò cho từng phiên.

Số liệu được giữ trong contextvar, cùng cơ chế với `src/workspace.py`, để hai phiên
Streamlit chạy song song không cộng nhầm token của nhau.
"""
import contextvars
from dataclasses import dataclass, field

# Đơn giá USD cho 1 triệu token (input, output). Chỉ dùng để ƯỚC TÍNH chi phí hiển
# thị cho người dùng — cập nhật lại khi nhà cung cấp đổi giá. Model không có trong
# bảng sẽ chỉ đếm token, không quy ra tiền (tránh báo một con số sai).
PRICE_PER_MTOK = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-opus-5": (15.00, 75.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
    "llama-3.3-70b-versatile": (0.59, 0.79),
}


@dataclass
class RoleUsage:
    """Token cộng dồn của một vai trò (Mechanical, QS, Reviewer, ...)."""
    role: str
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cost_usd(self):
        """Chi phí ước tính, hoặc None nếu chưa biết đơn giá của model này."""
        price = PRICE_PER_MTOK.get(self.model)
        if not price:
            return None
        in_price, out_price = price
        return (self.input_tokens * in_price + self.output_tokens * out_price) / 1_000_000


@dataclass
class UsageTracker:
    by_role: dict = field(default_factory=dict)

    def add(self, role: str, model: str, input_tokens: int, output_tokens: int) -> None:
        entry = self.by_role.setdefault(role, RoleUsage(role=role))
        entry.model = model or entry.model
        entry.input_tokens += int(input_tokens or 0)
        entry.output_tokens += int(output_tokens or 0)
        entry.calls += 1

    @property
    def total_tokens(self) -> int:
        return sum(e.total_tokens for e in self.by_role.values())

    @property
    def total_cost_usd(self):
        """Tổng chi phí của các vai trò biết đơn giá; None nếu không vai trò nào biết."""
        costs = [e.cost_usd for e in self.by_role.values() if e.cost_usd is not None]
        return sum(costs) if costs else None

    def reset(self) -> None:
        self.by_role.clear()


_tracker_var: contextvars.ContextVar = contextvars.ContextVar("usage_tracker", default=None)


def get_tracker() -> UsageTracker:
    """Bộ đếm của ngữ cảnh hiện tại, tự khởi tạo ở lần dùng đầu tiên."""
    tracker = _tracker_var.get()
    if tracker is None:
        tracker = UsageTracker()
        _tracker_var.set(tracker)
    return tracker


def reset_tracker() -> UsageTracker:
    """Bắt đầu đếm lại từ đầu (gọi trước mỗi lượt hội thoại mới)."""
    tracker = UsageTracker()
    _tracker_var.set(tracker)
    return tracker


def _extract_model(message) -> str:
    meta = getattr(message, "response_metadata", None) or {}
    return meta.get("model_name") or meta.get("model") or ""


def record_usage(role: str, message) -> None:
    """Ghi nhận token của một `AIMessage` trả về từ LLM.

    Bỏ qua im lặng khi provider không báo `usage_metadata` (một số backend local như
    Ollama) — thiếu số liệu không được phép làm hỏng luồng tư vấn.
    """
    usage = getattr(message, "usage_metadata", None)
    if not usage:
        return
    try:
        get_tracker().add(
            role=role,
            model=_extract_model(message),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        )
    except Exception:  # pragma: no cover - đo lường không bao giờ được làm sập agent
        pass
