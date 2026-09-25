"""N2 (`docs/thi-hanh/pe2.md` §C, ADR gốc 0021 §f + quyết định 3/5): gap R6 — release có ticket thuộc dự án mang
ProjectProfile không được tự duyệt khi `quality:accept` chưa `succeeded` ở ĐÚNG sha đã staged. Sàn chỉ thêm gap."""
from __future__ import annotations

from company.events import Task
from company.orch import quality_release
from company.quality_floor import QualityBar, collect_evidence, floor_gaps
from test_orchestrator import T1
from test_quality_collect import _full
from test_quality_floor import SHA, _release_ev
from test_quality_flow import (
    RUN,
    FakeDriver,
    _pin,
    _sign_spec_with_profile,
    _signers,
    _start,
    _unit,
    write_trust,
)

OTHER = "b" * 40


def _r6(gaps: list[str]) -> list[str]:
    return [g for g in gaps if g.startswith("R6:")]


# ---------- hàm thuần: floor_gaps ----------

def test_r6_run_failed_thi_co_khoang_trong():
    gaps = floor_gaps(_release_ev(product_quality=((RUN, "failed", SHA),)), QualityBar())
    assert gaps == [f"R6: nghiệm thu quality contract chưa đạt ở sha đã staged ({RUN}: quality:accept='failed')"]


def test_r6_succeeded_nhung_khac_sha_staged_thi_co_khoang_trong():
    gaps = floor_gaps(_release_ev(product_quality=((RUN, "succeeded", OTHER),)), QualityBar())
    assert _r6(gaps) == [f"R6: nghiệm thu quality contract chưa đạt ở sha đã staged ({RUN}: đạt ở {OTHER!r}, "
                         f"sha đã staged là {SHA!r})"]


def test_r6_succeeded_ma_khong_co_sha_staged_thi_khong_khop():
    gaps = floor_gaps(_release_ev(staged_sha=None, product_quality=((RUN, "succeeded", None),)), QualityBar())
    assert len(_r6(gaps)) == 1


def test_r6_succeeded_dung_sha_staged_thi_khong_co_khoang_trong():
    assert floor_gaps(_release_ev(product_quality=((RUN, "succeeded", SHA),)), QualityBar()) == []


def test_r6_ticket_cua_du_an_co_profile_nam_ngoai_moi_run():
    gaps = floor_gaps(_release_ev(product_quality=((RUN, "succeeded", SHA),), quality_unrun=("T9",)), QualityBar())
    assert gaps == ["R6: nghiệm thu quality contract chưa đạt ở sha đã staged "
                    "(T9: ticket của dự án có profile không thuộc run nào)"]


def test_r6_loi_doc_journal_thi_hong_thi_dong():
    gaps = floor_gaps(_release_ev(quality_error="OSError: hỏng"), QualityBar())
    assert gaps == ["R6: nghiệm thu quality contract chưa đạt ở sha đã staged (journal: OSError: hỏng)"]


def test_r6_ap_ca_cho_nghiem_thu_vi_nghiem_thu_doi_san_release():
    ev = _release_ev(kind="acceptance", release_approved=True, product_quality=((RUN, "failed", SHA),),
                     production_deploy={"ok": True, "verified_by": "orchestrator", "sha": SHA})
    assert len(_r6(floor_gaps(ev, QualityBar()))) == 1


# ---------- collect_evidence: nguồn journal ----------

def _collect(bus, **kw):
    return collect_evidence(bus, "release", "REL-1", tickets=["T1"], needs_security=False, waived=[], history=[], **kw)


def test_collect_khong_nguon_quality_thi_ket_qua_y_he_truoc():
    from company.bus import InMemoryBus
    bus = InMemoryBus(enforce_owners=False); _full(bus)
    ev = _collect(bus)
    assert (ev.product_quality, ev.quality_unrun, ev.quality_error) == ((), (), None)
    assert floor_gaps(ev, QualityBar()) == []


def test_collect_chep_run_va_ticket_ngoai_run_tu_nguon():
    from company.bus import InMemoryBus
    bus = InMemoryBus(enforce_owners=False); _full(bus)
    ev = _collect(bus, quality=lambda: (((RUN, "failed", "f" * 40),), ("T1",)))
    assert ev.product_quality == ((RUN, "failed", "f" * 40),) and ev.quality_unrun == ("T1",)
    assert len(_r6(floor_gaps(ev, QualityBar()))) == 2


def test_collect_nguon_quality_nem_loi_thi_r6():
    from company.bus import InMemoryBus
    bus = InMemoryBus(enforce_owners=False); _full(bus)

    def boom():
        raise OSError("đĩa hỏng")

    ev = _collect(bus, quality=boom)
    assert ev.quality_error == "OSError: đĩa hỏng"
    assert _r6(floor_gaps(ev, QualityBar())) == [
        "R6: nghiệm thu quality contract chưa đạt ở sha đã staged (journal: OSError: đĩa hỏng)"]


# ---------- orchestrator: release_quality + DeliveryLead._quality_evidence ----------

def test_du_an_khong_profile_khong_mo_journal_va_san_y_he_truoc(tmp_path):
    bus, o = _unit(tmp_path)
    o.lead.tickets["T1"] = Task.model_validate(T1); o.lead.release_tickets["REL-1"] = ["T1"]
    assert quality_release.release_quality(o, "REL-1") == ((), ())
    ev, bar = o.lead._quality_evidence("release", "REL-1")
    before = collect_evidence(bus, "release", "REL-1", tickets=["T1"], needs_security=False, waived=[],
                              history=o.gate.history)
    assert ev == before and floor_gaps(ev, bar or QualityBar()) == floor_gaps(before, QualityBar())
    assert not (tmp_path / "c.quality.sqlite").exists(), "không profile ⇒ không tạo file journal"


def test_du_an_khong_profile_khong_mo_journal_ca_khi_du_an_khac_co_profile(tmp_path):
    _bus, o = _unit(tmp_path)
    _pin(o, tmp_path / "c.sqlite", pid="P2")
    o.lead.tickets["T1"] = Task.model_validate(T1); o.lead.release_tickets["REL-1"] = ["T1"]
    assert quality_release.release_quality(o, "REL-1") == ((), ())
    assert not (tmp_path / "c.quality.sqlite").exists()


def test_du_an_co_profile_chua_co_journal_thi_ticket_ngoai_run(tmp_path):
    _bus, o = _unit(tmp_path)
    _pin(o, tmp_path / "c.sqlite")
    o.lead.tickets["T1"] = Task.model_validate(T1); o.lead.release_tickets["REL-1"] = ["T1", "T-la"]
    assert quality_release.release_quality(o, "REL-1") == ((), ("T1",))
    assert not (tmp_path / "c.quality.sqlite").exists(), "chỉ đọc: không tạo journal"
    ev, _bar = o.lead._quality_evidence("release", "REL-1")
    assert ev.quality_unrun == ("T1",)


def test_journal_hong_thi_r6_qua_delivery_lead(tmp_path):
    _bus, o = _unit(tmp_path)
    _pin(o, tmp_path / "c.sqlite")
    (tmp_path / "c.quality.sqlite").write_bytes(b"khong phai sqlite" * 100)
    o.lead.tickets["T1"] = Task.model_validate(T1); o.lead.release_tickets["REL-1"] = ["T1"]
    ev, bar = o.lead._quality_evidence("release", "REL-1")
    assert ev.quality_error is not None
    assert _r6(floor_gaps(ev, bar or QualityBar()))


def test_e2e_quality_succeeded_dung_sha_thi_khong_r6(tmp_path):
    signers = _signers()
    bus, o = _start(tmp_path, FakeDriver(signers), trust=write_trust(tmp_path / "trust.json", signers))
    _sign_spec_with_profile(tmp_path, bus, o)
    rid = o.lead.releases[-1]
    ev, bar = o.lead._quality_evidence("release", rid)
    assert ev.product_quality == ((RUN, "succeeded", o.release_sha[rid]),) and ev.quality_unrun == ()
    assert not _r6(floor_gaps(ev, bar or QualityBar()))


def test_e2e_quality_failed_thi_r6(tmp_path):
    signers = _signers()
    driver = FakeDriver(signers, drop=frozenset({"goal.traceability"}))
    bus, o = _start(tmp_path, driver, trust=write_trust(tmp_path / "trust.json", signers))
    _sign_spec_with_profile(tmp_path, bus, o)
    rid = o.lead.releases[-1]
    ev, bar = o.lead._quality_evidence("release", rid)
    assert _r6(floor_gaps(ev, bar or QualityBar())) == [
        f"R6: nghiệm thu quality contract chưa đạt ở sha đã staged ({RUN}: quality:accept='failed')"]
