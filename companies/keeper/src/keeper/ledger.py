"""Sổ nợ bảo trì có NGÀY ĐÁO HẠN (BT4, `DAC-TA-KEEPER.md` §6).

**Đây là cơ chế MỚI, không phải "dùng lại `debt_due` của company".** Đặc tả §6 (bản gốc) nói sai hai lần và đã
được đo lại:

1. Sai địa chỉ: `debt_due` không ở `software-company/src/company/orch/` mà ở LÕI —
   `xagents-core/src/xagents_core/supervisor.py:82` khai `self.debt_due`, `orch/gates_flow.py:88` chỉ TIÊU THỤ nó.
2. Sai bản chất: `supervisor.py:102-123` (`_count_debt`) đếm **chuỗi review liên tiếp** mà một nguồn không
   nhắc lại một mã nợ (`rec["streak"][src]`), và bắn khi chuỗi chạm bội số ngưỡng (`rec["fired"]`). Nó **không
   đọc đồng hồ ở đâu cả** — quá hạn ở lõi là quá hạn theo SỐ LẦN, không theo NGÀY.

`DebtEntry(subject, reason, due_at, tier)` mà `keeper` cần là quá hạn theo LỊCH. Hai ngữ nghĩa khác nhau nên
tên cũng phải khác: ở đây là `due_at` / `is_overdue` / `Ledger.overdue`, không có định danh nào tên `debt_due`
— để không ai đọc lướt rồi tưởng hai thứ là một và đi sửa cái này bằng luật của cái kia.

`now` là THAM SỐ BẮT BUỘC của `overdue()`/`is_overdue()`: không hàm nào ở đây gọi `datetime.now()` trong thân
mà không cho tiêm, nên test đo quanh đúng mốc `due_at` không cần `sleep`.
"""
from __future__ import annotations

from datetime import UTC, datetime

from .events import DebtEntry


def parse_due(raw: str) -> datetime:
    """ISO-8601 → `datetime` LUÔN có tzinfo. Chuỗi naive (không mang offset) được coi là UTC.

    Naive-vs-aware là bẫy thật: so một `datetime` naive với một aware ném `TypeError` giữa lúc chạy, và
    "im lặng coi giờ máy" thì cùng một sổ nợ quá hạn ở Hà Nội mà chưa quá hạn ở London. Chuẩn hoá về UTC ngay
    tại cửa vào là chỗ duy nhất phải nhớ quy ước này."""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"due_at không phải ISO-8601: {raw!r}") from exc
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _as_aware(now: datetime) -> datetime:
    return now.replace(tzinfo=UTC) if now.tzinfo is None else now


def is_overdue(entry: DebtEntry, now: datetime) -> bool:
    """`due_at <= now`. ĐÚNG MỐC tính là quá hạn: `due_at` đọc là "phải xong TRƯỚC thời điểm này", nên tới
    thời điểm đó mà chưa xong thì đã trễ."""
    return parse_due(entry.due_at) <= _as_aware(now)


class Ledger:
    """Sổ nợ trong bộ nhớ của một chu kỳ triage. Không tự bền hoá: bản bền là các event `debt-ledger` trên
    bus (`events.py`), sổ này chỉ là khung nhìn đã gom để `keeper-supervisor` hỏi "cái gì quá hạn"."""

    def __init__(self, entries: list[DebtEntry] | None = None) -> None:
        self.entries: list[DebtEntry] = list(entries or [])

    def add(self, entry: DebtEntry) -> None:
        self.entries.append(entry)

    def overdue(self, now: datetime) -> list[DebtEntry]:
        """Mục đã quá hạn, sắp theo `(due_at, subject)` — quá hạn lâu nhất lên đầu để escalate theo đúng thứ
        tự đó. `subject` là mốc phụ để thứ tự tất định khi hai mục cùng hạn."""
        return sorted(
            (e for e in self.entries if is_overdue(e, now)),
            key=lambda e: (parse_due(e.due_at), e.subject),
        )
