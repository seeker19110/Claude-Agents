"""Mức nâng chất lượng theo dự án (ADR-0043 §2): người đặt lúc ký spec, tập khoá đóng, chỉ siết."""
import json

import pytest
from xagents_core.bus import PermissionDenied

from company.bus import InMemoryBus
from company.events import AuditLog, Envelope
from company.gate_cli import main
from company.quality_floor import FAIL_CLOSED_BAR, QualityBar, project_bar
from company.roles import ROLE
from company.sqlite_bus import SQLiteBus


def _open_spec(db, sid="SPEC-P1"):
    assert main(["--db", str(db), "request", "spec", sid, "--by", ROLE.PRODUCT, "--checklist", "prd"]) == 0


def _bar_env(actor, evidence):
    return Envelope(topic="audit-log", key=actor, actor=actor,
                    payload=AuditLog(actor=actor, action="quality.bar_set",
                                     evidence=json.dumps(evidence, ensure_ascii=False)).model_dump())


def test_ky_spec_kem_muc_nang_thi_du_an_doc_duoc(tmp_path):
    db = tmp_path / "c.sqlite"; _open_spec(db)
    rc = main(["--db", str(db), "approve", "SPEC-P1", "--by", "human:pm", "--reason", "đủ prd, đủ tiêu chí",
               "--quality-bar", "release=human,security_review=required"])
    assert rc == 0
    assert project_bar(SQLiteBus(db), "P1") == QualityBar(release_human=True, security_review=True)


def test_khong_dat_muc_nang_thi_chi_co_san(tmp_path):
    db = tmp_path / "c.sqlite"; _open_spec(db)
    assert main(["--db", str(db), "approve", "SPEC-P1", "--by", "human:pm", "--reason", "đủ prd, đủ tiêu chí"]) == 0
    assert project_bar(SQLiteBus(db), "P1") == QualityBar()


@pytest.mark.parametrize("bad", ["coverage=80", "release=auto", "release", "security_review=no"])
def test_khoa_la_bi_tu_choi_truoc_khi_ky(tmp_path, bad):
    db = tmp_path / "c.sqlite"; _open_spec(db)
    rc = main(["--db", str(db), "approve", "SPEC-P1", "--by", "human:pm", "--quality-bar", bad])
    assert rc == 2
    from company.gate_cli import PersistentGate
    assert "SPEC-P1" in PersistentGate(SQLiteBus(db)).pending  # không ký nửa vời: mức nâng hỏng thì spec chưa ký


def test_muc_nang_chi_di_cung_approve_spec(tmp_path):
    db = tmp_path / "c.sqlite"
    assert main(["--db", str(db), "request", "release", "REL-1", "--by", "delivery-lead", "--checklist", "tests"]) == 0
    assert main(["--db", str(db), "approve", "REL-1", "--by", "human:pm", "--quality-bar", "release=human"]) == 2
    _open_spec(db)
    assert main(["--db", str(db), "reject", "SPEC-P1", "--by", "human:pm", "--quality-bar", "release=human"]) == 2


def test_agent_khong_ghi_duoc_muc_nang():
    bus = InMemoryBus()
    with pytest.raises(PermissionDenied):
        bus.publish(_bar_env(ROLE.PRODUCT, {"project_id": "P1", "bar": {}, "by": ROLE.PRODUCT}))


def test_ban_ghi_by_khong_khop_actor_bi_bo_qua():
    bus = InMemoryBus()
    bus.publish(_bar_env("human:a", {"project_id": "P1", "bar": {"release": "human"}, "by": "human:b"}))
    assert project_bar(bus, "P1") == QualityBar()


def test_ban_ghi_cua_nguoi_ma_hong_thi_dong_ca_hai_cua():
    bus = InMemoryBus()
    bus.publish(_bar_env("human:a", {"project_id": "P1", "bar": {"coverage": "80"}, "by": "human:a"}))
    assert project_bar(bus, "P1") == FAIL_CLOSED_BAR
    bus2 = InMemoryBus()
    bus2.publish(_bar_env("human:a", {"project_id": "P1", "bar": "release=human", "by": "human:a"}))
    assert project_bar(bus2, "P1") == FAIL_CLOSED_BAR


def test_ban_ghi_moi_nhat_thang_va_chi_cho_dung_du_an():
    bus = InMemoryBus()
    bus.publish(_bar_env("human:a", {"project_id": "P1", "bar": {"release": "human"}, "by": "human:a"}))
    bus.publish(_bar_env("human:a", {"project_id": "P1", "bar": {"acceptance": "human"}, "by": "human:a"}))
    bus.publish(_bar_env("human:a", {"project_id": "P2", "bar": {"release": "human"}, "by": "human:a"}))
    assert project_bar(bus, "P1") == QualityBar(acceptance_human=True)
    assert project_bar(bus, "P3") == QualityBar()


def test_evidence_hong_json_bi_bo_qua():
    bus = InMemoryBus()
    env = Envelope(topic="audit-log", key="human:a", actor="human:a",
                   payload=AuditLog(actor="human:a", action="quality.bar_set", evidence="{không phải json").model_dump())
    bus.publish(env)
    assert project_bar(bus, "P1") == QualityBar()
