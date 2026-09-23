"""Sàn chất lượng cho gate tự duyệt (ADR-0043 §1–2): hàm thuần `floor_gaps` + tập khoá nâng chỉ-siết."""
from dataclasses import replace

import pytest

from company.quality_floor import FAIL_CLOSED_BAR, QualityBar, QualityEvidence, floor_gaps, parse_bar

SHA = "a" * 40
_OK_CHECKS = {"lint": True, "tests": True, "verified_by": "workspace"}


def _release_ev(**kw) -> QualityEvidence:
    base = QualityEvidence(
        kind="release", release_id="REL-1", staged_sha=SHA,
        pr_checks=(("T1", _OK_CHECKS), ("T2", _OK_CHECKS)),
        run={"ok": True, "verified_by": "orchestrator", "sha": SHA}, staging_deploy=None,
        qa_verdict="pass", security_verdict=None, needs_security=False, waived=(), had_incident=False,
        release_approved=False, production_deploy=None,
    )
    return replace(base, **kw)


def _acceptance_ev(**kw) -> QualityEvidence:
    prod = {"ok": True, "verified_by": "orchestrator", "sha": SHA}
    return replace(_release_ev(), **{"kind": "acceptance", "release_approved": True, "production_deploy": prod, **kw})


# ---------- sàn release (= deploy production) ----------

def test_release_du_bang_chung_may_thi_khong_co_khoang_trong():
    assert floor_gaps(_release_ev(), QualityBar()) == []


def test_r1_pr_test_do_la_khoang_trong():
    ev = _release_ev(pr_checks=(("T1", _OK_CHECKS), ("T2", {**_OK_CHECKS, "tests": False})))
    assert any("R1" in g and "T2" in g for g in floor_gaps(ev, QualityBar()))


def test_r1_pr_khong_co_local_checks_la_thieu_bang_chung():
    ev = _release_ev(pr_checks=(("T1", None),))
    assert any("R1" in g and "T1" in g for g in floor_gaps(ev, QualityBar()))


def test_r1_pr_unverified_khong_du_du_lint_tests_true():
    ev = _release_ev(pr_checks=(("T1", {**_OK_CHECKS, "unverified": True}),))
    assert any("R1" in g for g in floor_gaps(ev, QualityBar()))


def test_r1_verified_by_khong_phai_workspace_la_loi_khai():
    ev = _release_ev(pr_checks=(("T1", {**_OK_CHECKS, "verified_by": "builder"}),))
    assert any("R1" in g for g in floor_gaps(ev, QualityBar()))


def test_r1_release_khong_co_ticket_nao_la_thieu_bang_chung():
    assert any("R1" in g for g in floor_gaps(_release_ev(pr_checks=()), QualityBar()))


@pytest.mark.parametrize("run", [
    None,
    {"ok": False, "verified_by": "orchestrator", "sha": SHA},
    {"ok": True, "verified_by": "qa", "sha": SHA},
    {"ok": True, "verified_by": "orchestrator", "sha": "b" * 40},
    {"unverified": True, "verified_by": "orchestrator", "reason": "không có runtime"},
])
def test_r2_san_pham_khong_chung_minh_chay_dung_sha(run):
    assert any("R2" in g for g in floor_gaps(_release_ev(run=run), QualityBar()))


def test_r2_deploy_staging_do_may_chung_dung_sha_thay_cho_hoi_quy():
    dep = {"ok": True, "verified_by": "orchestrator", "sha": SHA}
    assert floor_gaps(_release_ev(run=None, staging_deploy=dep), QualityBar()) == []


@pytest.mark.parametrize("dep", [None, {"ok": False, "verified_by": "orchestrator", "sha": SHA},
                                 {"ok": True, "verified_by": "orchestrator", "sha": SHA, "skipped": "docker không có"},
                                 {"ok": True, "verified_by": "ops", "sha": SHA},
                                 {"ok": True, "verified_by": "orchestrator"},
                                 {"ok": True, "verified_by": "orchestrator", "sha": "e" * 40}])
def test_r2_deploy_staging_hong_hoac_bo_qua_khong_thay_duoc(dep):
    assert any("R2" in g for g in floor_gaps(_release_ev(run=None, staging_deploy=dep), QualityBar()))


@pytest.mark.parametrize("verdict", [None, "fail", "conditional"])
def test_r3_qa_khong_pass(verdict):
    assert any("R3" in g for g in floor_gaps(_release_ev(qa_verdict=verdict), QualityBar()))


def test_r3_can_security_ma_chua_pass():
    ev = _release_ev(needs_security=True, security_verdict=None)
    assert any("R3" in g and "security" in g for g in floor_gaps(ev, QualityBar()))
    assert floor_gaps(replace(ev, security_verdict="pass"), QualityBar()) == []


def test_r3_du_an_nang_security_review_doi_security_ca_khi_khong_risk_tags():
    bar = QualityBar(security_review=True)
    assert any("security" in g for g in floor_gaps(_release_ev(), bar))
    assert floor_gaps(_release_ev(security_verdict="pass"), bar) == []


def test_r4_finding_da_duoc_mien_la_quyet_dinh_cua_nguoi():
    assert any("R4" in g for g in floor_gaps(_release_ev(waived=("qa",)), QualityBar()))


def test_r5_release_tung_co_su_co():
    assert any("R5" in g for g in floor_gaps(_release_ev(had_incident=True), QualityBar()))


def test_du_an_nang_release_human_thi_luon_cho_nguoi():
    assert floor_gaps(_release_ev(), QualityBar(release_human=True)) != []


# ---------- sàn nghiệm thu ----------

def test_nghiem_thu_du_bang_chung():
    assert floor_gaps(_acceptance_ev(), QualityBar()) == []


def test_nghiem_thu_can_gate_release_da_duyet():
    assert any("A1" in g for g in floor_gaps(_acceptance_ev(release_approved=False), QualityBar()))


@pytest.mark.parametrize("prod", [None, {"ok": False, "verified_by": "orchestrator", "sha": SHA},
                                  {"ok": True, "verified_by": "orchestrator", "sha": SHA, "skipped": "off"},
                                  {"ok": True, "verified_by": "orchestrator", "sha": "c" * 40},
                                  {"ok": True, "verified_by": "ops", "sha": SHA}])
def test_nghiem_thu_can_deploy_production_do_may_chung(prod):
    assert any("A2" in g for g in floor_gaps(_acceptance_ev(production_deploy=prod), QualityBar()))


def test_nghiem_thu_van_doi_san_release():
    assert any("R3" in g for g in floor_gaps(_acceptance_ev(qa_verdict="fail"), QualityBar()))


def test_du_an_nang_acceptance_human():
    assert floor_gaps(_acceptance_ev(), QualityBar(acceptance_human=True)) != []
    assert floor_gaps(_release_ev(), QualityBar(acceptance_human=True)) == []


def test_kind_khac_khong_bao_gio_dat_san():
    for kind in ("spec", "escalation", "la"):
        assert floor_gaps(replace(_release_ev(), kind=kind), QualityBar()) != []


# ---------- mức nâng theo dự án: tập khoá đóng, chỉ siết ----------

def test_parse_bar_rong_la_khong_nang_gi():
    assert parse_bar({}) == QualityBar()


def test_parse_bar_ba_khoa_hop_le():
    assert parse_bar({"release": "human", "acceptance": "human", "security_review": "required"}) == \
        QualityBar(release_human=True, acceptance_human=True, security_review=True)


@pytest.mark.parametrize("raw", [{"coverage": "80"}, {"release": "auto"}, {"security_review": "no"},
                                 {"acceptance": ""}, {"release": 1}])
def test_parse_bar_khoa_hoac_gia_tri_la_bi_tu_choi(raw):
    with pytest.raises(ValueError):
        parse_bar(raw)


def test_fail_closed_bar_chan_ca_release_lan_nghiem_thu():
    assert floor_gaps(_release_ev(), FAIL_CLOSED_BAR) != []
    assert floor_gaps(_acceptance_ev(), FAIL_CLOSED_BAR) != []
