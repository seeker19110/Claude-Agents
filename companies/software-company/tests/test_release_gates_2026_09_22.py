"""Hai lỗi cơ chế ở đường release tìm ra khi audit 2026-09-22 (xem `docs/sessions/2026-09-22.md`).

1. `_superseded_release` chỉ nhận "có bản giao SAU nó" — RC TRÙNG nằm CUỐI danh sách (không RC nào sau) mà nội
   dung đã tới khách trong bản giao TRƯỚC nó thì bị coi là chưa giao: từ chối escalation → `rework_release_tickets`
   đá ticket đã xong về `changes_requested`. `TRAPS.md` ghi "chưa vá" từ 2026-09-10 (QLKH).
2. Khoá `uat:{rid}` không mang thế hệ (miễn trong `KHOA_MIEN` với lý do "production deploy một lần mỗi RC") —
   nhưng `redeploy`/`_rerun_release` cho cùng `rid` chạy lại production sau khi khách TỪ CHỐI nghiệm thu, và lần
   `deployed` thứ hai không mở lại gate acceptance: giao hai lần, không chữ ký, không audit. Khuôn 3 `TRAPS.md`.
"""

from __future__ import annotations

from company.bus import InMemoryBus
from company.events import Task
from company.llm import FakeClient
from company.orchestrator import Orchestrator, StepResult
from test_orchestrator import handler


def _mk():
    bus = InMemoryBus()
    return bus, Orchestrator(bus, FakeClient(handler=handler))


def test_tu_choi_escalation_rc_trung_cuoi_danh_sach_khong_da_ticket_da_giao_ve_rework():
    """REL-1 đã giao (T1 tới khách). REL-2 là RC trùng sinh sau (cùng T1), kẹt `pending_human` → escalation →
    người từ chối ("trùng, đóng"). REL-2 là RC CUỐI: không có RC nào "sau" nó đã giao, nên bản cũ rơi vào
    `rework_release_tickets` và T1 (đã merged) bị đá về `changes_requested` lần nữa."""
    _bus, orch = _mk()
    orch.lead.release_tickets["REL-1"] = ["T1"]
    orch.lead.release_tickets["REL-2"] = ["T1"]
    orch.lead.releases.extend(["REL-1", "REL-2"])
    orch.lead.state["T1"] = "merged"
    orch.delivered["REL-1"] = {"tag": "v0.15.1"}
    assert orch._superseded_release("REL-2") is True, "nội dung REL-2 đã tới khách trong REL-1 → là RC trùng"
    res = StepResult("e1", "audit-log", "REL-2")
    orch._on_escalation_decided("REL-2", "reject", "human:lead", "RC trùng, đóng sổ", res)
    assert orch.lead.state["T1"] == "merged", "ticket đã giao không được đá về rework"
    assert "void:REL-2" in res.actions and "release_reworked:REL-2" not in res.actions


def test_rc_chua_giao_o_dau_thi_tu_choi_van_rework_nhu_cu():
    """Đối chứng: RC duy nhất, ticket merged (sau staging) nhưng CHƯA có bản giao nào chứa nó → từ chối là lỗi code
    thật → rework như cũ. Sửa lỗi 1 không được nuốt luôn ca hợp lệ này."""
    _bus, orch = _mk()
    orch.lead.release_tickets["REL-1"] = ["T1"]
    orch.lead.releases.append("REL-1")
    orch.lead.tickets["T1"] = Task(ticket_id="T1", project_id="P1", requirement_id="R1", assignee="builder",
                                   title="login", acceptance=["ok"], estimate_tokens=1000, budget_tokens=2000)
    orch.lead.state["T1"] = "merged"
    assert orch._superseded_release("REL-1") is False
    res = StepResult("e1", "audit-log", "REL-1")
    orch._on_escalation_decided("REL-1", "reject", "human:lead", "lỗi code thật, sửa lại", res)
    # `rework_release_tickets` đặt `changes_requested` rồi `_retry` giao lại ngay → `dispatched`; điều cần
    # kiểm là ticket KHÔNG còn `merged` và hành động là rework, không phải void.
    assert orch.lead.state["T1"] == "dispatched" and "release_reworked:REL-1" in res.actions
    assert "void:REL-1" not in res.actions


def test_gate_nghiem_thu_mo_lai_khi_deploy_lai_sau_khi_khach_tu_choi():
    """Lần `deployed` production thứ nhất mở UAT-REL-1; khách từ chối; ops `redeploy` → lần `deployed` thứ hai là
    một release-event MỚI (event_id khác) → phải mở lại gate để khách ký lại. Khoá `uat:{rid}` cũ nuốt lần hai."""
    _bus, orch = _mk()
    res1 = StepResult("ev1", "release-events", "REL-1")
    orch._open_acceptance_gate("REL-1", res1, "ev1")
    assert "UAT-REL-1" in orch.gate.pending and "gate:acceptance:UAT-REL-1" in res1.actions
    orch.gate.decide("UAT-REL-1", "reject", by="human:khach", reason="màn đăng nhập lỗi, không nhận")
    assert "UAT-REL-1" not in orch.gate.pending
    res2 = StepResult("ev2", "release-events", "REL-1")
    orch._open_acceptance_gate("REL-1", res2, "ev2")
    assert "UAT-REL-1" in orch.gate.pending, "deploy lại sau khi bị từ chối mà không hỏi khách ký lại = giao chui"
    assert "gate:acceptance:UAT-REL-1" in res2.actions


def test_cung_mot_release_event_khong_mo_gate_nghiem_thu_hai_lan():
    """Đối chứng khuôn 3: cùng event (replay/retry transient) thì KHÔNG mở lại — thế hệ là event_id, không phải
    'mỗi lần gọi'."""
    _bus, orch = _mk()
    res = StepResult("ev1", "release-events", "REL-1")
    orch._open_acceptance_gate("REL-1", res, "ev1")
    orch.gate.decide("UAT-REL-1", "reject", by="human:khach", reason="không nhận, lỗi đăng nhập")
    orch._open_acceptance_gate("REL-1", res, "ev1")
    assert "UAT-REL-1" not in orch.gate.pending
