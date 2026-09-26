"""Người mở lại ticket (duyệt escalation `approve`) thì hai trần "không tính retry" của ticket về 0 cùng `retry`.

`DeliveryLead.reopen` đếm `retry` lại từ 0, nhưng `turn_continuations` (#345) và `conflict_retries` thì không: ticket
đã dùng hết ba lần làm tiếp trước khi bị chặn, sau khi người mở lại thì lần hết lượt tool ĐẦU TIÊN đã tính retry —
người cấp thêm một vòng mà ticket chỉ được nửa vòng. Ghi ở nhật ký 2026-09-26 (#345) là thứ "không được quên";
TCK-011/TCK-015 của CAMPUS-UNI đang chờ đúng lệnh mở lại này.
"""

from __future__ import annotations

from company.bus import InMemoryBus
from company.llm import FakeClient
from company.orch.routes import ACTOR, MAX_CONFLICT_RETRIES, MAX_TURN_CONTINUATIONS
from company.orchestrator import Orchestrator
from company.roles import ROLE
from company.sqlite_bus import SQLiteBus
from test_audit_gia_mao import _forged
from test_on_dinh_auto import _audits, _builder_het_luot
from test_orchestrator import _drive_to_plan, handler
from test_tools_and_agentic import _init_repo


def _chan_roi_mo_lai(bus, orch, monkeypatch):
    _builder_het_luot(orch, monkeypatch, sua_file=True)
    _drive_to_plan(bus, orch)
    orch.run()
    assert orch.lead.state["T1"] == "blocked" and orch.turn_continuations["T1"] == MAX_TURN_CONTINUATIONS
    orch.conflict_retries["T1"] = MAX_CONFLICT_RETRIES + 1
    orch.gate.decide("T1", "approve", by="human:pm", reason="làm tiếp từ WIP trong worktree")
    orch.run()


def test_mo_lai_ticket_thi_duoc_lai_du_so_lan_lam_tiep(tmp_path, monkeypatch):
    bus = InMemoryBus()
    orch = Orchestrator(bus, FakeClient(handler=handler), repo=_init_repo(tmp_path / "repo"), base="main")
    _chan_roi_mo_lai(bus, orch, monkeypatch)
    assert len(_audits(bus, "ticket.continued")) == 2 * MAX_TURN_CONTINUATIONS, (
        "sau khi người mở lại, ticket được lại đủ số lần làm tiếp như vòng đầu"
    )
    assert orch.conflict_retries["T1"] == 0, "trần xung đột merge cũng về 0 cùng retry"


def test_mo_lai_ticket_ve_0_ben_qua_restart(tmp_path, monkeypatch):
    db = tmp_path / "c.sqlite"
    bus = SQLiteBus(db)
    orch = Orchestrator(bus, FakeClient(handler=handler), repo=_init_repo(tmp_path / "repo"), base="main")
    orch._audit(
        "integration.conflict", {"release_id": "REL-1", "ticket_id": "T1", "conflicts": ["a.py"]}, ticket_id="T1"
    )
    _chan_roi_mo_lai(bus, orch, monkeypatch)
    bus.close()
    lai = Orchestrator(SQLiteBus(db), FakeClient(handler=handler), repo=tmp_path / "repo", base="main")
    assert lai.turn_continuations["T1"] == MAX_TURN_CONTINUATIONS, "chỉ đếm lần làm tiếp SAU lần mở lại"
    assert lai.conflict_retries["T1"] == 0


def test_dong_mo_lai_do_sai_nguoi_ghi_khong_xoa_bo_dem(tmp_path):
    """`audit-log` là topic mở: agent ghi `ticket.reopened` giả thì trần làm tiếp thành vô hạn."""
    db = tmp_path / "c.sqlite"
    bus = SQLiteBus(db)
    bus.publish(_forged(ACTOR, "ticket.continued", {"ticket_id": "T9", "attempt": 1}))
    bus.publish(_forged(ACTOR, "integration.conflict", {"ticket_id": "T9", "release_id": "REL-9", "conflicts": []}))
    bus.publish(_forged(ROLE.QA, "ticket.reopened", {"ticket_id": "T9"}))
    bus.close()
    lai = Orchestrator(SQLiteBus(db), FakeClient(handler=handler))
    assert lai.turn_continuations["T9"] == 1 and lai.conflict_retries["T9"] == 1
