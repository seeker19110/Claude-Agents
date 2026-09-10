"""BT4 — `ledger.py`: sổ nợ có NGÀY đáo hạn.

Không `sleep`: `now` là tham số bắt buộc của `overdue()`. Ca quanh đúng mốc `due_at` và ca naive-vs-aware.
"""
from datetime import UTC, datetime, timedelta, timezone

import pytest

from keeper.events import DebtEntry
from keeper.ledger import Ledger, is_overdue, parse_due

DUE = "2026-09-10T00:00:00+00:00"


def _entry(subject="pydantic", due=DUE, tier="medium") -> DebtEntry:
    return DebtEntry(subject=subject, reason="chờ ADR", due_at=due, tier=tier)


def test_chua_qua_han_ngay_truoc_moc():
    assert is_overdue(_entry(), datetime(2026, 9, 9, 23, 59, 59, tzinfo=UTC)) is False


def test_dung_moc_la_qua_han():
    """Chọn `due_at <= now` (mốc tính là quá hạn): hạn là "phải xong TRƯỚC lúc đó"."""
    assert is_overdue(_entry(), datetime(2026, 9, 10, tzinfo=UTC)) is True


def test_sau_moc_la_qua_han():
    assert is_overdue(_entry(), datetime(2026, 9, 10, 0, 0, 1, tzinfo=UTC)) is True


def test_due_at_naive_coi_la_utc():
    e = _entry(due="2026-09-10T00:00:00")
    assert parse_due(e.due_at).tzinfo is UTC
    assert is_overdue(e, datetime(2026, 9, 9, 23, 59, 59, tzinfo=UTC)) is False
    assert is_overdue(e, datetime(2026, 9, 10, tzinfo=UTC)) is True


def test_now_naive_cung_coi_la_utc():
    assert is_overdue(_entry(), datetime(2026, 9, 10)) is True
    assert is_overdue(_entry(), datetime(2026, 9, 9)) is False


def test_mui_gio_khac_utc_so_dung():
    e = _entry(due="2026-09-10T07:00:00+07:00")  # = 2026-09-10T00:00:00Z
    assert is_overdue(e, datetime(2026, 9, 9, 23, 59, tzinfo=UTC)) is False
    assert is_overdue(e, datetime(2026, 9, 10, 6, 59, tzinfo=timezone(timedelta(hours=7)))) is False
    assert is_overdue(e, datetime(2026, 9, 10, 7, 0, tzinfo=timezone(timedelta(hours=7)))) is True


def test_due_at_hong_thi_no():
    with pytest.raises(ValueError, match="due_at"):
        parse_due("hôm nào đó")


def test_ledger_overdue_loc_va_sap_xep():
    led = Ledger([
        _entry("b", "2026-09-11T00:00:00+00:00"),
        _entry("a", "2026-09-09T00:00:00+00:00"),
        _entry("c", "2026-09-09T00:00:00+00:00"),
    ])
    led.add(_entry("d", "2026-09-01T00:00:00+00:00", tier="high"))
    got = led.overdue(datetime(2026, 9, 10, tzinfo=UTC))
    assert [e.subject for e in got] == ["d", "a", "c"]


def test_ledger_rong():
    assert Ledger().overdue(datetime(2026, 9, 10, tzinfo=UTC)) == []


def test_overdue_khong_goi_datetime_now():
    """`now` bắt buộc tiêm: gọi thiếu là `TypeError`, không phải im lặng lấy giờ máy."""
    with pytest.raises(TypeError):
        Ledger().overdue()  # type: ignore[call-arg]
