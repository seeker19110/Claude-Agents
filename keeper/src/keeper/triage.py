"""`triager`: `maintenance-signals` → `maintenance-tickets` (BT4, `DAC-TA-KEEPER.md` §6).

## Khoá chống-trùng MANG THẾ HỆ — thế hệ nào và vì sao

Cạm bẫy §6 (bug `once="no-test-author:{tid}"`, K1.7): một khoá chống-trùng không mang thế hệ sẽ nuốt lần thứ
hai HỢP LỆ. Hai thế hệ có sẵn trong nhà đã đo:

* lõi: `GateRequest.seq` do `HumanGate.request()` gán (`xagents-core/src/xagents_core/gates.py:84`) — tăng mỗi
  lần MỘT GATE được xin lại;
* company: `Task.retry`, và `due["times"]` của `supervisor._count_debt` (`supervisor.py:118`) — tăng mỗi lần
  một mã nợ chạm lại ngưỡng.

`keeper` không dùng được thẳng cái nào: ở đây chưa có gate lúc triage (gate chỉ được XIN sau, cho tier `high`),
và chưa có `Task`. Điểm chung của cả hai là thế hệ tăng khi **vòng đời trước đã kết thúc**, không theo đồng hồ
và không theo mỗi lần quét. Nên thế hệ của `keeper` là **số vòng đời ticket đã ĐÓNG của chủ thể đó**, do
orchestrator đếm và truyền vào (`generation=`).

Chọn thế hệ như vậy vì hai chiều đều phải đúng:

* Vòng watch chạy mỗi vài phút và `dependency-scout` phát lại CÙNG một signal mỗi vòng. Nếu thế hệ là số vòng
  quét thì mỗi vòng ra một ticket mới — chống trùng thành vô nghĩa.
* Ngược lại, nếu không có thế hệ nào cả thì sau khi ticket "bump pydantic" đóng lại mà pydantic ra bản mới,
  signal thứ hai HỢP LỆ bị khoá cũ nuốt, và không ai biết vì khoá im lặng.

`generation` là tham số, không phải state trong module: đúng như `can_open_pr` không tin biến đếm trong RAM,
`triager` không tự đếm vòng đời — nó nhận con số đã đo được từ nơi giữ trạng thái thật.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .events import RiskTier, Signal, Ticket
from .risk import risk_tier
from .signals import dedupe

# Hạn xử lý theo tier (`Ticket.due_at`, tiêu thụ bởi `ledger.overdue`). Bảng, không `if`.
DUE_DAYS: dict[RiskTier, int] = {"high": 1, "medium": 7, "low": 30}


class TriageState:
    """Khoá chống-trùng đã dùng. Một instance cho một vòng đời orchestrator; sống cùng nơi giữ `generation`."""

    def __init__(self, seen: set[str] | None = None) -> None:
        self.seen: set[str] = set(seen or ())


def dedupe_key(signal: Signal, generation: int) -> str:
    """`<thế hệ>:<kind>:<subject>` — thế hệ ở ĐẦU khoá để đọc log là thấy ngay nó có thế hệ hay không."""
    return f"{generation}:{signal.kind}:{signal.subject}"


def _due_at(tier: RiskTier, now: datetime) -> str:
    reference = now.replace(tzinfo=UTC) if now.tzinfo is None else now
    return (reference + timedelta(days=DUE_DAYS[tier])).isoformat()


def triager(
    signals: list[Signal], *, generation: int, state: TriageState, now: datetime,
) -> list[Ticket]:
    """Gộp trùng (`signals.dedupe`) → xếp bậc (`risk.risk_tier`) → `Ticket` mang hạn; tier `high` đính kèm
    yêu cầu gate `keeper` (`requires_gate=True`).

    Trả về CHỈ những ticket mới của lần gọi này: signal đã ra ticket trong cùng thế hệ bị bỏ qua."""
    if generation < 0:
        raise ValueError(f"generation phải >= 0, nhận {generation}")
    out: list[Ticket] = []
    for signal in dedupe(signals):
        key = dedupe_key(signal, generation)
        if key in state.seen:
            continue
        state.seen.add(key)
        tier = risk_tier(signal)
        out.append(Ticket(
            ticket_id=f"KEEP:{key}",
            subject=signal.subject,
            risk_tier=tier,
            signal_subjects=[signal.subject],
            due_at=_due_at(tier, now),
            requires_gate=tier == "high",
        ))
    return out
