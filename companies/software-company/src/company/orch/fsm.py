"""Bảng chuyển giao dùng chung cho `ticket_fsm.py`/`release_fsm.py` (ADR-0034, PR K1.7 phần 2).

`process()` (`orchestrator.py`) trước đây là một chuỗi `if env.topic == ...` dài, mỗi nhánh gọi thẳng một
hàm — không có gì để đọc thứ tự ngoài đọc code. `Transition`/`step()` biến mỗi nhánh thành MỘT DÒNG DỮ LIỆU
(chủ đề event, điều kiện thêm, hàm xử lý) và `process()` chỉ còn tra bảng rồi gọi `_call` qua `ROUTES` —
đúng tinh thần ADR-0034 "driver, không nhân đôi": nguồn sự thật trạng thái ticket vẫn là `lead.state`
(`delivery.py`), bảng ở đây chỉ QUYẾT ĐỊNH gọi hàm nào cho event nào, không tự ý đổi state.

`action(o, env, res) -> bool` trả `True` nếu `process()` phải DỪNG NGAY và trả `res` (khớp `return` trong
code cũ), `False` nếu xử lý xong hàng này thì đi tiếp xuống các hàng/khối sau (khớp không có `return`).

`phase` phân biệt hàng chạy TRƯỚC hay SAU vòng lặp `ROUTES` trong `process()` — thứ tự đó có ý nghĩa (ví dụ
`_integrate_approved` phải chạy trước khi `ROUTES` giao việc cho ticket phụ thuộc), nên giữ nguyên bằng
trường dữ liệu thay vì phụ thuộc vị trí dòng trong hai lệnh gọi `step()` riêng của `process()`.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..events import Envelope

if TYPE_CHECKING:
    from ..orchestrator import Orchestrator, StepResult


@dataclass(frozen=True)
class Transition:
    name: str  # nhãn mô tả, hiện trong test/lỗi — không phải trạng thái ticket (process() định tuyến theo topic)
    topics: frozenset[str]
    action: Callable[[Any, Envelope, Any], bool]
    guard: Callable[[Envelope, Any], bool] | None = None
    phase: str = "pre"  # "pre" (trước vòng ROUTES trong process()) hoặc "post" (sau)


def step(table: Iterable[Transition], o: Orchestrator, env: Envelope, res: StepResult, phase: str = "pre") -> bool:
    """Tra `table` theo đúng thứ tự khai báo; hàng đầu tiên khớp topic (+ guard nếu có) thì chạy action.
    Trả `True` nếu action báo dừng (process() phải `return res` ngay), `False` nếu không hàng nào khớp hoặc
    hàng khớp không yêu cầu dừng — process() đi tiếp."""
    for t in table:
        if t.phase != phase or env.topic not in t.topics: continue
        if t.guard is not None and not t.guard(env, o): continue
        if t.action(o, env, res): return True
    return False
