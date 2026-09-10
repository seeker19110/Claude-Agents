"""decide(): đi qua HumanGate thật của software-company (four-eyes, allowlist, audit-log)."""
from __future__ import annotations

from pathlib import Path

import pytest
from company.gate_cli import PersistentGate as CompanyGate
from company.gates import APPROVERS_ENV as COMPANY_APPROVERS_ENV
from company.sqlite_bus import SQLiteBus as CompanySQLiteBus

from console.collect import COMPANY, collect
from console.decide import GateError, decide

DEAD_GATEWAY = "http://127.0.0.1:9"


def test_duyet_gate_that(company_db: Path) -> None:
    out = decide(company_db, subject_id="REL-001", xuong=COMPANY, decision="approve",
                 by="human:pm", reason="ok")
    assert out["ok"] is True and out["subject_id"] == "REL-001" and out["decision"] == "approve"
    assert out["event_id"]
    # quyết định nằm trong bus của công ty và gate không còn chờ
    bus = CompanySQLiteBus(company_db)
    try:
        gate = CompanyGate(bus)
        assert "REL-001" not in gate.pending and gate.is_approved("REL-001")
        assert any(e.event_id == out["event_id"] and e.payload["action"] == "gate.decide"
                   for e in bus.replay(topic="audit-log"))
    finally:
        bus.close()
    assert "REL-001" not in {g["id"] for g in collect(company_db, gateway_url=DEAD_GATEWAY)["gates"]}


def test_four_eyes_chan_nguoi_tao(company_db: Path) -> None:
    with pytest.raises(GateError) as e:
        decide(company_db, subject_id="REL-001", xuong=COMPANY, decision="approve",
               by="delivery-lead", reason="tự duyệt")
    assert "four-eyes" in str(e.value)
    assert "REL-001" in {g["id"] for g in collect(company_db, gateway_url=DEAD_GATEWAY)["gates"]}


def test_allowlist_nguoi_duyet_cua_cong_ty_gia_cong(company_db: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """K3.7: `COMPANY_GATE_APPROVERS` phải áp trên đường console giống hệt CLI/orchestrator — trước bản vá này
    console mở `PersistentGate(bus)` không truyền `approvers`, nên allowlist bị bỏ qua trên riêng đường này."""
    monkeypatch.setenv(COMPANY_APPROVERS_ENV, "human:cto")
    with pytest.raises(GateError) as e:
        decide(company_db, subject_id="REL-001", xuong=COMPANY, decision="approve",
               by="human:intern", reason="")
    assert "danh sách người duyệt" in str(e.value)
    out = decide(company_db, subject_id="REL-001", xuong=COMPANY, decision="approve",
                 by="human:cto", reason="ok")
    assert out["ok"] and out["event_id"]


def test_subject_khong_co_gate_cho(company_db: Path) -> None:
    with pytest.raises(GateError) as e:
        decide(company_db, subject_id="TCK-999", xuong=COMPANY, decision="approve", by="human:pm", reason="")
    assert "không có gate chờ" in str(e.value)


def test_xuong_la(company_db: Path) -> None:
    with pytest.raises(ValueError, match="xưởng lạ"):
        decide(company_db, subject_id="REL-001", xuong="phòng-marketing", decision="approve",
               by="human:pm", reason="")


def test_verb_quyet_dinh_la(company_db: Path) -> None:
    for verb in ("merge", "pending", ""):
        with pytest.raises(ValueError, match="quyết định lạ"):
            decide(company_db, subject_id="REL-001", xuong=COMPANY, decision=verb, by="human:pm", reason="")


def test_thieu_db(tmp_path: Path) -> None:
    with pytest.raises(GateError, match="chưa có file DB"):
        decide(tmp_path / "khong-co.sqlite", subject_id="REL-001", xuong=COMPANY, decision="approve",
               by="human:pm", reason="")
    with pytest.raises(GateError, match="chưa có file DB"):
        decide(None, subject_id="REL-001", xuong=COMPANY, decision="approve", by="human:pm", reason="")


def test_thieu_nguoi_duyet(company_db: Path) -> None:
    with pytest.raises(ValueError, match="người duyệt"):
        decide(company_db, subject_id="REL-001", xuong=COMPANY, decision="approve", by="  ", reason="")
    with pytest.raises(ValueError, match="subject_id"):
        decide(company_db, subject_id="", xuong=COMPANY, decision="approve", by="human:pm", reason="")
