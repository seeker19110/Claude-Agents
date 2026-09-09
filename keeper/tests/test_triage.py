"""BT4 — `triage.py`: `maintenance-signals` → `maintenance-tickets`, khoá chống-trùng MANG THẾ HỆ.

Ca cốt lõi (bug `once=` K1.7): cùng signal, cùng thế hệ → một ticket; sang thế hệ mới → được phép lần hai.
"""
from datetime import UTC, datetime

import pytest

from keeper.events import Signal
from keeper.triage import DUE_DAYS, TriageState, dedupe_key, triager

NOW = datetime(2026, 9, 9, tzinfo=UTC)


def _sig(subject="pydantic", **kw) -> Signal:
    kw.setdefault("kind", "dependency")
    kw.setdefault("detail", "Bump pydantic from 1.9.0 to 2.0.0")
    return Signal(subject=subject, **kw)


def test_mot_signal_thanh_mot_ticket():
    tickets = triager([_sig(semver_jump="minor")], generation=0, state=TriageState(), now=NOW)
    assert len(tickets) == 1
    t = tickets[0]
    assert t.subject == "pydantic"
    assert t.signal_subjects == ["pydantic"]
    assert t.status == "open"


def test_tier_high_dinh_kem_yeu_cau_gate():
    t = triager([_sig(semver_jump="major")], generation=0, state=TriageState(), now=NOW)[0]
    assert t.risk_tier == "high"
    assert t.requires_gate is True


def test_tier_khong_high_thi_khong_gate():
    t = triager([_sig(semver_jump="patch", is_dev=True)], generation=0, state=TriageState(), now=NOW)[0]
    assert t.risk_tier == "low"
    assert t.requires_gate is False


def test_due_at_theo_tier():
    t = triager([_sig(semver_jump="major")], generation=0, state=TriageState(), now=NOW)[0]
    assert t.due_at == "2026-09-10T00:00:00+00:00"
    assert DUE_DAYS["high"] == 1


def test_gop_trung_truoc_khi_ra_ticket():
    sigs = [_sig(semver_jump="minor"), _sig(semver_jump="minor")]
    tickets = triager(sigs, generation=0, state=TriageState(), now=NOW)
    assert len(tickets) == 1


def test_cung_the_he_xu_ly_hai_lan_chi_mot_ticket():
    state = TriageState()
    first = triager([_sig(semver_jump="minor")], generation=0, state=state, now=NOW)
    second = triager([_sig(semver_jump="minor")], generation=0, state=state, now=NOW)
    assert len(first) == 1
    assert second == []


def test_the_he_moi_duoc_phep_lan_hai():
    """Chiều ngược của ca trên: cùng signal, chỉ đổi thế hệ → ticket thứ hai được ra."""
    state = TriageState()
    first = triager([_sig(semver_jump="minor")], generation=0, state=state, now=NOW)
    second = triager([_sig(semver_jump="minor")], generation=1, state=state, now=NOW)
    assert len(first) == len(second) == 1
    assert first[0].ticket_id != second[0].ticket_id


def test_khoa_chong_trung_mang_the_he():
    s = _sig()
    assert dedupe_key(s, 0) != dedupe_key(s, 1)
    assert dedupe_key(s, 0) == dedupe_key(_sig(), 0)


def test_ticket_id_hop_le_voi_ID_PATTERN():
    t = triager([_sig(subject="xagents-core/src/xagents_core/supervisor.py", kind="drift", detail="lệch")],
                generation=3, state=TriageState(), now=NOW)[0]
    assert t.ticket_id.startswith("KEEP:3:")
    assert " " not in t.ticket_id


def test_the_he_am_bi_tu_choi():
    with pytest.raises(ValueError, match="generation"):
        triager([_sig()], generation=-1, state=TriageState(), now=NOW)


def test_nhieu_signal_ra_nhieu_ticket_giu_thu_tu():
    sigs = [_sig("a", kind="drift", detail="x"), _sig("b", kind="drift", detail="y")]
    assert [t.subject for t in triager(sigs, generation=0, state=TriageState(), now=NOW)] == ["a", "b"]
