"""ADR-0032: supervisor đếm "nợ kiến trúc treo" — cùng mã nợ (DEF-xx, SD-xx, `debt:`) nhắc ≥ N review liên tiếp →
orchestrator (code, xác định) mở gate escalation cấp DỰ ÁN với danh sách nợ, số lần, ticket nào nhắc, hint ADR.

Đo hai chiều (2026-09-06): tắt `Orchestrator._check_debt` → `test_ba_review_lien_tiep_mo_gate_dung_mot_lan` đỏ
(gate P1 không mở); bật lại → xanh."""
from __future__ import annotations

import os

from company.bus import InMemoryBus
from company.events import Envelope, ReviewResult, Task
from company.llm import FakeClient, LLMConfig, load_config, make_client
from company.orchestrator import Orchestrator
from company.sqlite_bus import SQLiteBus
from company.supervisor import DEBT_HINT, Supervisor, debt_ids
from test_orchestrator import _drive_to_plan, handler


def _review(bus, tid, text, source="security", actor="security", pid="P1", **extra):
    payload = {"ticket_id": tid, "source": source, "verdict": "pass", "project_id": pid,
               "findings": [{"level": "warn", "text": text}] if text else [], **extra}
    return bus.publish(Envelope(topic="review-results", key=tid, actor=actor, payload=payload))


# ---------- trích mã nợ ----------

def test_debt_ids_bat_ba_dang_ma_no():
    r = {"findings": [{"level": "warn", "text": "DEF-01 chưa chọn DB thật; sd-7 treo"}, {"level": "nit", "text": "debt: auth-provider"},
                      "không phải dict"], "root_cause": "vì DEF-01"}
    assert debt_ids(r) == {"DEF-01", "SD-7", "AUTH-PROVIDER"}
    assert debt_ids({"findings": [{"level": "warn", "text": "DEFAULT-01 không phải mã nợ; SDK-2 cũng không"}]}) == set()
    assert debt_ids({}) == set()


# ---------- supervisor đếm từ bus ----------

def test_supervisor_dem_lien_tiep_theo_nguon_va_reset_khi_nguon_bo_nhac():
    bus = InMemoryBus(); sup = Supervisor(bus, debt_threshold=3)
    _review(bus, "T1", "DEF-01 treo"); _review(bus, "T2", "DEF-01 treo")
    assert sup.debt_due == [], "2 lần chưa tới ngưỡng 3"
    _review(bus, "T3", "đã có ADR, không nhắc DEF nữa")  # cùng nguồn không nhắc → chuỗi về 0
    _review(bus, "T4", "DEF-01 treo")
    assert sup.debt_due == [] and sup.debt["P1"]["DEF-01"]["streak"]["security"] == 1
    _review(bus, "T5", "DEF-01 treo"); _review(bus, "T6", "vẫn DEF-01")
    assert [d["debt_id"] for d in sup.debt_due] == ["DEF-01"]
    d = sup.debt_due[0]
    assert d["times"] == 1 and d["consecutive"] == 3 and d["mentions"] == 5 and d["hint"] == DEBT_HINT
    assert d["tickets"] == ["T1", "T2", "T4", "T5", "T6"]
    # nguồn KHÁC không nhắc thì không reset chuỗi của security; review thiếu project_id nhưng ticket đã biết vẫn đếm
    bus.publish(Envelope(topic="tasks", key="T7", actor="delivery-lead",
                         payload=Task(ticket_id="T7", project_id="P1", requirement_id="R", assignee="builder", title="x",
                                      acceptance=["a"]).model_dump()))
    _review(bus, "T7", "code ok", source="reviewer", actor="qa", pid=None)
    _review(bus, "T7", "DEF-01 vẫn treo", pid=None)
    assert sup.debt["P1"]["DEF-01"]["streak"]["security"] == 4
    # review không có project_id và ticket lạ: bỏ qua, không sập
    _review(bus, "T99", "DEF-09", pid=None)
    assert "DEF-09" not in sup.debt.get("P1", {})
    tbl = sup.debt_table("P1")
    assert tbl[0]["debt_id"] == "DEF-01" and tbl[0]["escalated"] == 1 and tbl[0]["threshold"] == 3
    assert sup.debt_table("P2") == [] and sup.sprint_report()["architecture_debt"] == sup.debt_table()


def test_supervisor_no_tang_tiep_thi_chom_nguong_lan_hai():
    """Khoá once mang lần thứ mấy: nợ nhắc tới 6 lần liên tiếp là lần thứ 2, không bị lần 1 nuốt (khuôn 3)."""
    bus = InMemoryBus(); sup = Supervisor(bus, debt_threshold=3)
    for i in range(6): _review(bus, f"T{i}", "SD-2 treo")
    assert [(d["debt_id"], d["times"]) for d in sup.debt_due] == [("SD-2", 1), ("SD-2", 2)]
    r = ReviewResult(ticket_id="T9", source="qa", verdict="fail", root_cause="debt: cache-layer", project_id="P1")
    bus.publish(Envelope(topic="review-results", key="T9", actor="qa", payload=r.model_dump()))
    assert sup.debt["P1"]["CACHE-LAYER"]["sources"] == ["qa"]


# ---------- orchestrator mở gate cấp dự án ----------

def _dua_toi_ke_hoach(bus):
    o = Orchestrator(bus, FakeClient(handler=handler))
    _drive_to_plan(bus, o); o.run()
    return o


def _debt_audits(bus):
    return [e.payload["action"] for e in bus.replay(topic="audit-log") if str(e.payload["action"]).startswith("debt.")]


def test_ba_review_lien_tiep_mo_gate_dung_mot_lan(tmp_path):
    db = tmp_path / "c.sqlite"; bus = SQLiteBus(db); o = _dua_toi_ke_hoach(bus)
    for i in range(2):
        _review(bus, "T1", f"DEF-01 chưa chọn DB thật ({i})"); o.run()
    assert "P1" not in o.gate.pending, "2 lần chưa mở gate"
    _review(bus, "T2", "DEF-01 chưa chọn DB thật (2)"); o.run(); o.run()
    g = o.gate.pending["P1"]
    assert g.kind == "escalation" and g.created_by == "supervisor"
    assert g.checklist[0] == "debt:DEF-01×3 liên tiếp (security; T1,T2)"
    assert g.checklist[1:] == ["decision:adr|waive", f"hint:{DEBT_HINT}"]
    assert _debt_audits(bus) == ["debt.escalated"]
    assert "P1" not in o.paused, "nợ treo không pause dự án"
    assert o.status()["architecture_debt"][0]["escalated"] == 1

    # restart: bus mới nạp lại từ sqlite → supervisor đếm lại y hệt, `once` dựng lại → không mở trùng
    o2 = Orchestrator(SQLiteBus(db), FakeClient(handler=handler))
    o2.run()
    assert o2.supervisor.debt_due == o.supervisor.debt_due and o2.debt_gate == o.debt_gate
    assert list(o2.gate.pending) == list(o.gate.pending) and _debt_audits(o2.bus) == ["debt.escalated"]

    # người quyết: audit `debt.decided`, gate đóng, không resume/pause, không "reopen" ticket ma
    o2.gate.decide("P1", "approve", by="human:cto", reason="đã mở ticket ADR-DB, CTO ký"); res = o2.run()
    assert any(a == "debt:P1:DEF-01:approve" for r in res for a in r.actions)
    assert "P1" not in o2.gate.pending and o2.debt_gate == {} and _debt_audits(o2.bus) == ["debt.escalated", "debt.decided"]
    assert not [e for e in o2.bus.replay(topic="supervisor-actions") if e.payload.get("target") == "P1"]

    # nợ MỚI DEF-02 đủ N → mở lần nữa; DEF-01 nhắc tiếp tới 6 = lần thứ 2 → cũng mở lại, không bị lần 1 nuốt.
    # Hai mã cùng chạm ngưỡng ở một review: mỗi lần một gate (subject trùng), mã kia đợi gate trước đóng.
    for i in range(3):
        _review(o2.bus, "T2", f"DEF-02 chưa có message queue ({i}); DEF-01 vẫn treo"); o2.run()
    g2 = o2.gate.pending["P1"]
    assert g2.checklist[0] == "debt:DEF-01×6 liên tiếp (security; T1,T2)" and g2.checklist[1] == "debt:DEF-02×3 (T2)"
    assert _debt_audits(o2.bus) == ["debt.escalated", "debt.decided", "debt.escalated"]
    # restart lần nữa với gate đang mở: `debt_gate` dựng lại, không mở thêm
    o3 = Orchestrator(SQLiteBus(db), FakeClient(handler=handler)); o3.run()
    assert o3.debt_gate.keys() == {"P1"} and _debt_audits(o3.bus).count("debt.escalated") == 2
    o3.gate.decide("P1", "reject", by="human:cto", reason="chấp nhận treo tới sprint sau"); o3.run()
    assert o3.gate.pending["P1"].checklist[0] == "debt:DEF-02×3 liên tiếp (security; T2)", "mã đợi được mở ngay nhịp sau"
    o3.gate.decide("P1", "approve", by="human:cto", reason="ADR-MQ đã có người ký"); o3.run()
    assert "P1" not in o3.gate.pending and o3.debt_gate == {}
    assert _debt_audits(o3.bus) == ["debt.escalated", "debt.decided"] * 3


def test_gate_du_an_dang_ban_thi_doi_nhip_sau(tmp_path):
    """Gate escalation của dự án đang mở vì việc khác (subject trùng) → nợ đợi, KHÔNG bị `once` nuốt: gate kia đóng
    là nhịp sau mở gate nợ."""
    bus = InMemoryBus(); o = _dua_toi_ke_hoach(bus)
    from company.gates import GateRequest
    o.gate.request(GateRequest(kind="escalation", subject_id="P1", created_by="supervisor", checklist=["agent_error"]))
    for i in range(3): _review(bus, "T1", f"SD-1 ({i})")
    o.run()
    assert o.gate.pending["P1"].checklist == ["agent_error"] and _debt_audits(bus) == []
    o.gate.decide("P1", "reject", by="human:pm", reason="đóng việc kia"); o.run()
    assert o.gate.pending["P1"].checklist[0].startswith("debt:SD-1×3") and _debt_audits(bus) == ["debt.escalated"]


def test_nguong_cau_hinh_o_llm_yaml_va_env(tmp_path, monkeypatch):
    monkeypatch.delenv("COMPANY_DEBT_REVIEWS", raising=False)
    assert LLMConfig().debt_reviews == 3
    p = tmp_path / "llm.yaml"; p.write_text("provider: fake\ndebt_reviews: 2\n", encoding="utf-8")
    cfg = load_config(p); assert cfg.debt_reviews == 2
    assert make_client(cfg).debt_reviews == 2
    monkeypatch.setenv("COMPANY_DEBT_REVIEWS", "5")
    assert load_config(p).debt_reviews == 5
    bus = InMemoryBus(); c = FakeClient(handler=handler); c.debt_reviews = 2
    o = Orchestrator(bus, c); assert o.supervisor.debt_threshold == 2
    assert Orchestrator(InMemoryBus(), FakeClient(handler=handler)).supervisor.debt_threshold == 3
    assert os.environ["COMPANY_DEBT_REVIEWS"] == "5"
