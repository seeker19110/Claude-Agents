"""ADR-0007: orchestrator tự động nối topic → agent → topic; dừng ở human gate / supervisor; khôi phục từ SQLite."""
from __future__ import annotations

import json
import time
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime, timedelta

import pytest

from company.bus import InMemoryBus
from company.events import Envelope, SupervisorAction
from company.llm import FakeClient, LLMError
from company.orchestrator import ENGINEERING, PLAN_INPUTS, ROUTES, Orchestrator, StepResult, check_routes
from company.orchestrator import main as orch_main
from company.registry import load_agents
from company.sqlite_bus import SQLiteBus

T1 = {"ticket_id": "T1", "project_id": "P1", "requirement_id": "REQ-1", "assignee": "backend", "title": "GET /orders",
      "acceptance": ["given/when/then"], "estimate_tokens": 4_000, "budget_tokens": 6_000, "retry": 0}
T2 = {**T1, "ticket_id": "T2", "requirement_id": "REQ-2", "title": "POST /payments", "depends_on": ["T1"],
      "risk_tags": ["payment"], "priority": 1}


def _agent_of(system: str) -> str:
    return system.split("\n", 1)[0].lstrip("# ").strip()


def _inp(user: str) -> dict:
    return json.loads(user.split("```json\n", 1)[1].split("\n```", 1)[0])


def handler(system: str, user: str) -> dict:
    """Mô phỏng mọi agent bằng đầu ra hợp lệ tối thiểu; xác định agent qua tiêu đề system prompt."""
    a, p = _agent_of(system), _inp(user)
    pid = p.get("project_id", "P1")
    if a == "intake": return {"project_id": pid, "kind": "intake", "data": {"goals": ["G1"]}}
    if a == "researcher": return {"project_id": pid, "kind": "researcher", "data": {"domain": {}}}
    if a == "synthesizer": return {"project_id": pid, "kind": "draft", "requirements": []}
    if a == "risk": return {"project_id": pid, "kind": "risk", "risks": [{"id": "R1", "text": "rủi ro"}]}
    if a == "clarifier": return {"project_id": pid, "round": 1, "questions": [{"id": "Q1", "text": "?", "options": ["a"], "default": "a"}]}
    if a == "spec-writer": return {"payload": {"project_id": pid, "status": "pending_human", "artifacts": {"prd": "docs/prd.md", "requirements": "docs/requirements.json"}},
                                   "context_writes": [{"namespace": "prd", "content_ref": "docs/prd.md", "summary": "PRD v1"}]}
    if a == "delivery-lead":
        if p.get("decision") == "pending":  # ước lượng impact cho change request
            return {"actor": "delivery-lead", "action": "change.impact", "project_id": pid,
                    "evidence": json.dumps({"change_id": p["change_id"], "impact": {"estimate_days": 1, "estimate_tokens": 5000}})}
        return {"items": [T1, T2], "context_writes": [{"namespace": "architecture", "content_ref": "docs/c4.md", "summary": "L1-L2"},
                                                       {"namespace": "api-contract", "content_ref": "openapi.yaml", "summary": "v1"}]}
    if a in ENGINEERING:
        return {"ticket_id": p["ticket_id"], "branch": f"ticket/{p['ticket_id']}", "pr_ref": "#1", "local_checks": {"lint": True, "tests": True}}
    if a in {"reviewer", "qa-debugger", "security-engineer"}:
        src = {"reviewer": "reviewer", "qa-debugger": "qa", "security-engineer": "security"}[a]
        tid = p.get("ticket_id") or p.get("release_id") or f"SPEC-{pid}"
        out = {"ticket_id": tid, "source": src, "verdict": "pass"}
        if a == "security-engineer" and "artifacts" in p:  # threat model từ spec: ghi blackboard
            return {"payload": out, "context_writes": [{"namespace": "threat-model", "content_ref": "docs/threat-model.md", "summary": "v1"}]}
        return out
    if a == "release-engineer":
        return {"release_id": p["release_id"], "version": "1.0.0", "env": p["target_env"], "status": "deployed"}
    if a == "account-manager":
        if "verdict" in p:  # nghiệm thu conditional → change request cho phần còn lại
            return {"items": [{"change_id": "CR-UAT-1", "project_id": pid, "requested_by": p["signed_by"], "description": "phần còn lại", "decision": "pending"}]}
        return {"change_id": "CR-1", "project_id": pid, "requested_by": p["from"], "description": p["text"], "decision": "pending"}
    if a == "support-docs":
        if "release_id" in p: return {"context_writes": [{"namespace": "docs", "content_ref": f"docs/release-{p['release_id']}.md", "summary": "release notes"}]}
        if "text" in p: return {"items": [{"incident_id": "INC-1", "severity": "SEV3", "summary": p["text"], "root_cause_class": "code"}]} if "lỗi" in p["text"] else {"items": []}
        return {"items": [{"project_id": pid, "description": f"nghiên cứu lại từ {p['incident_id']}"}]}
    raise AssertionError(f"agent không mong đợi: {a}")


def _pub(bus, topic, key, actor, payload):
    return bus.publish(Envelope(topic=topic, key=key, actor=actor, payload=payload))


def _topics(bus):
    return [e.topic for e in bus.replay() if e.topic not in {"audit-log", "shared-context", "supervisor-actions"}]


def _drive_to_plan(bus, orch):
    """research-request → ... → clarification-questions (người trả lời) → approved-specs → gate spec → plan → gate plan."""
    _pub(bus, "research-requests", "P1", "human:sales", {"project_id": "P1", "description": "app đặt lịch"})
    orch.run()
    assert _topics(bus)[-1] == "clarification-questions", "dừng chờ người trả lời"
    _pub(bus, "clarification-answers", "P1", "human:po", {"project_id": "P1", "answers": [{"question_id": "Q1", "answer": "a"}]})
    orch.run()
    assert "SPEC-P1" in orch.gate.pending and next(iter(orch.deferred.values()))[1] == "gate:SPEC-P1"
    orch.gate.decide("SPEC-P1", "approve", by="human:po")
    orch.run()
    assert not orch.deferred and "PLAN-P1-1" in orch.gate.pending and "PLAN-P1-1" in orch.plans
    assert not orch.lead.tickets, "chưa dispatch khi plan chưa duyệt"


# ---------- bảng route ----------

def test_routes_match_front_matter():
    agents = load_agents()
    assert check_routes(agents) == []
    assert {r.topic_in for r in ROUTES} | set(PLAN_INPUTS) <= {t for a in agents.values() for t in a.reads}


# ---------- vòng đời đầy đủ trong bộ nhớ ----------

def test_full_lifecycle_stops_at_gates_and_humans():
    bus = InMemoryBus(); client = FakeClient(handler=handler); orch = Orchestrator(bus, client)
    _drive_to_plan(bus, orch)
    assert _topics(bus)[:6] == ["research-requests", "research-findings", "research-findings", "requirements-draft",
                                "requirements-draft", "clarification-questions"]

    orch.gate.decide("PLAN-P1-1", "approve", by="human:pm")
    orch.run()
    st = orch.lead.state
    # T1: backend → reviewer+qa pass → approved → REL-001 staging → merged → QA staging pass → gate 3 chờ
    # T2 (phụ thuộc T1, risk_tags): tự dispatch sau T1 approved, cần thêm security → REL-002
    assert st["T1"] == "merged" and st["T2"] == "merged", st
    assert orch.lead.releases == ["REL-001", "REL-002"] and {"REL-001", "REL-002"} <= set(orch.gate.pending)
    reviews = [(e.key, e.payload["source"]) for e in bus.replay(topic="review-results")]
    assert ("T2", "security") in reviews and ("T1", "security") not in reviews
    assert all(e.payload["env"] == "staging" for e in bus.replay(topic="release-events"))

    orch.gate.decide("REL-001", "approve", by="human:release-manager")
    orch.run()
    assert st["T1"] == "released" and st["T2"] == "merged"
    prod = [e for e in bus.replay(topic="release-events") if e.payload["env"] == "production"]
    assert [e.key for e in prod] == ["REL-001"]

    # nghiệm thu là của khách: orchestrator không tự sinh; người publish → ticket closed
    _pub(bus, "acceptance-results", "REL-001", "account-manager",
         {"release_id": "REL-001", "project_id": "P1", "verdict": "accepted", "signed_by": "customer:po"})
    orch.run()
    assert st["T1"] == "closed"

    audits = [e.payload for e in bus.replay(topic="audit-log")]
    assert all(a["tokens"] == 1300 for a in audits if a["action"].startswith("produced:")), "token thật từ client"
    assert orch.stats["errors"] == 0 and not orch.queue
    tiers = {c["model_tier"] for c in client.calls}
    assert tiers == {"strong", "standard", "light"}, "model theo tier của từng agent (ADR-0019)"


# ---------- khôi phục từ bus bền vững ----------

def test_resume_from_sqlite_does_not_redo_work(tmp_path):
    db = tmp_path / "c.sqlite"
    bus1 = SQLiteBus(db); c1 = FakeClient(handler=handler); o1 = Orchestrator(bus1, c1)
    _drive_to_plan(bus1, o1)
    o1.gate.decide("PLAN-P1-1", "approve", by="human:pm")
    o1.run(max_steps=2)  # dispatch T1, backend làm PR rồi "tắt máy" (review chưa chạy)
    n_calls, n_events = len(c1.calls), len(bus1)
    assert o1.lead.state["T1"] == "in_review"
    bus1.close()

    bus2 = SQLiteBus(db); c2 = FakeClient(handler=handler); o2 = Orchestrator(bus2, c2)
    assert o2.lead.state == o1.lead.state and o2.lead.tickets.keys() == o1.lead.tickets.keys()
    assert o2.lead.waiting() == {"T2": ["T1"]} and "PLAN-P1-1" in o2.plans and o2.gate.is_approved("PLAN-P1-1")
    assert len(bus2) == n_events, "khôi phục không phát lại event"
    assert [e.event_id for e in o2.queue] == [e.event_id for e in o1.queue]
    o2.run()
    assert o2.lead.state["T1"] == "merged" and o2.lead.state["T2"] == "merged" and o2.stats["errors"] == 0
    # 8 (nghiên cứu + threat model + plan) + T1: 2 (ADR-0021: không QA ở PR) + REL-001: 2 + T2: 4 (qa + security)
    # + REL-002: 3 (security DAST) = 19
    assert n_calls + len(c2.calls) == 19


def test_poll_picks_up_gate_decision_from_other_process(tmp_path):
    from company.gate_cli import main as gate_main
    db = tmp_path / "c.sqlite"
    bus = SQLiteBus(db); orch = Orchestrator(bus, FakeClient(handler=handler))
    _drive_to_plan(bus, orch)
    assert gate_main(["--db", str(db), "approve", "PLAN-P1-1", "--by", "human:pm"]) == 0  # tiến trình khác
    assert "PLAN-P1-1" in orch.gate.pending, "chưa poll thì chưa thấy"
    orch.tick()
    assert orch.gate.is_approved("PLAN-P1-1") and orch.lead.state["T1"] == "merged"


# ---------- supervisor pause / resume ----------

def test_paused_ticket_is_deferred_until_resume():
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler))
    _drive_to_plan(bus, orch)
    orch.gate.decide("PLAN-P1-1", "approve", by="human:pm")
    _pub(bus, "supervisor-actions", "T1", "supervisor", SupervisorAction(target="T1", action="pause", reason="test").model_dump())
    orch.run()
    assert orch.lead.state["T1"] == "dispatched" and next(iter(orch.deferred.values()))[1] == "paused:T1"
    _pub(bus, "supervisor-actions", "T1", "supervisor", SupervisorAction(target="T1", action="resume", reason="ok").model_dump())
    orch.run()
    assert orch.lead.state["T1"] == "merged" and not orch.deferred


# ---------- đầu ra sai bị chặn, không retry ----------

def test_plan_rejected_when_budget_rule_violated():
    def bad(system, user):
        if _agent_of(system) == "delivery-lead": return {"items": [{**T1, "budget_tokens": 4_000}]}
        return handler(system, user)
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=bad))
    _pub(bus, "approved-specs", "P1", "spec-writer", {"project_id": "P1", "status": "pending_human", "artifacts": {"prd": "docs/prd.md", "requirements": "docs/requirements.json"}})
    orch.run(); orch.gate.decide("SPEC-P1", "approve", by="human:po"); orch.run()
    acts = [e.payload["action"] for e in bus.replay(topic="audit-log")]
    assert "plan_rejected" in acts and not orch.plans and not orch.lead.tickets
    # Kế hoạch bị từ chối là ngõ cụt: không ticket, không plan, không cơ chế tự lập lại. Phải mở gate
    # `escalation` cho người quyết — trước đây dự án đứng im ở đây mà `status` vẫn báo mọi chỉ số xanh.
    assert orch.gate.pending.get("P1") and orch.gate.pending["P1"].kind == "escalation"
    assert "plan_problems" in orch.gate.pending["P1"].checklist


def test_loi_agent_khong_nhanh_nao_nhan_thi_mo_gate_chu_khong_im_lang():
    """Reviewer lỗi trên `pull-requests`: KHÔNG thuộc RESEARCH_TOPICS (nên `_stall` bỏ qua) và route không
    phải `tools="rw"` (nên `_rework_after_error` bỏ qua). Trước đây lỗi rơi vào im lặng: event vẫn bị đánh
    dấu đã xử lý, ticket treo `in_review`, không gate nào mở, `status` báo mọi chỉ số XANH trong khi dự án
    đã chết. Đo được khi chạy thật 2026-09-04: ba reviewer cùng hỏng, 13 ticket phụ thuộc chờ vĩnh viễn."""
    def reviewer_hong(system, user):
        if _agent_of(system) in {"reviewer", "qa-debugger", "security-engineer"}:
            raise LLMError("model không trả về nội dung nào")
        return handler(system, user)

    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=reviewer_hong))
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    _pub(bus, "pull-requests", "T1", "backend",
         {"ticket_id": "T1", "project_id": "P1", "branch": "ticket/T1", "pr_ref": "#1", "summary": "s",
          "impact": {"files": ["a.py"]}, "local_checks": {"lint": True, "tests": True, "verified_by": "workspace"}})
    orch.run()
    acts = [e.payload["action"] for e in bus.replay(topic="audit-log")]
    assert "agent_error_unhandled" in acts, "lỗi không nhánh nào nhận phải để lại dấu vết"
    assert orch.gate.pending.get("T1"), "phải mở gate escalation thay vì chết lặng"


def test_cau_tra_loi_tich_luy_trong_cung_mot_vong():
    """Người trả lời bổ sung ở lượt sau (vd. sau khi security-engineer nêu câu hỏi mở) không phải gửi lại
    toàn bộ câu cũ. Trước đây `_answers_complete` chỉ đọc event HIỆN TẠI, nên lượt bổ sung luôn bị coi là
    "thiếu hết các câu trước": spec-writer không bao giờ chạy lại, câu trả lời nằm im trong bus, không audit,
    không báo ai. Đo được khi chạy thật 2026-09-04 với OQ-02/OQ-05 của dự án QLKH."""
    def hai_cau(system, user):
        if _agent_of(system) == "clarifier":
            return {"project_id": "P1", "round": 1,
                    "questions": [{"id": "Q1", "text": "?", "options": ["a"], "default": "a"},
                                  {"id": "Q2", "text": "?", "options": ["b"], "default": "b"}]}
        return handler(system, user)

    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=hai_cau))
    _pub(bus, "research-requests", "P1", "human:sales", {"project_id": "P1", "description": "app"})
    orch.run()
    q = bus.latest("clarification-questions", "P1")
    assert {x["id"] for x in q.payload["questions"]} == {"Q1", "Q2"}

    # Hai lượt trả lời RỜI NHAU trong cùng một vòng hỏi — đúng cách người dùng trả lời bổ sung.
    _pub(bus, "clarification-answers", "P1", "human:po", {"project_id": "P1", "answers": [{"question_id": "Q1", "answer": "a"}]})
    _pub(bus, "clarification-answers", "P1", "human:po", {"project_id": "P1", "answers": [{"question_id": "Q2", "answer": "b"}]})
    orch.run()
    assert bus.latest("approved-specs", "P1"), "câu trả lời phải tích luỹ trong cùng một vòng"


def test_lenh_thu_lai_song_sot_qua_restart(tmp_path):
    """`_retry_stalled` bỏ dấu `processed` rồi đẩy vào `self.queue` — cả hai đều trong RAM. Restart giữa lúc
    đó là mất trắng: event vẫn mang dấu `orchestrated` của LẦN LỖI nên hàng đợi dựng lại loại nó ra, dự án
    nằm im vĩnh viễn dù người đã bấm duyệt. Đo được khi chạy thật 2026-09-04 (duyệt gate lúc 06:51:31,
    restart lúc 06:51:45, sau đó không một dòng `orchestrated` nào nữa)."""
    lan = {"n": 0}

    def hong_lan_dau(system, user):
        if _agent_of(system) == "researcher":
            lan["n"] += 1
            if lan["n"] == 1: raise LLMError("model rớt mạng")
        return handler(system, user)

    db = tmp_path / "c.sqlite"
    bus = SQLiteBus(db); orch = Orchestrator(bus, FakeClient(handler=hong_lan_dau))
    _pub(bus, "research-requests", "P1", "human:sales", {"project_id": "P1", "description": "app"})
    orch.run()
    assert orch.stalled.get("P1"), "researcher hỏng → dự án stalled, mở gate escalation"
    orch.gate.decide("P1", "approve", by="human:lead")
    # Xử lý ĐÚNG event gate.decide: `_retry_stalled` bỏ dấu processed và đẩy event lỗi vào self.queue (trong RAM),
    # ghi `project.retried` lên bus. `max_steps=1` dừng ngay sau đó — mô phỏng tiến trình chết trước khi kịp
    # chạy lại event vừa đưa vào hàng đợi. Đây mới là tình huống thật; nếu để `gate.decide` chưa xử lý thì
    # restart vẫn nhặt được nó và test không bắt được lỗi gì.
    orch.run(max_steps=1)
    assert any(e.payload.get("action") == "project.retried" for e in bus.replay(topic="audit-log"))
    assert not bus.latest("clarification-questions", "P1"), "chưa kịp chạy lại trước khi chết"
    # Lệnh chỉ-đọc (`status`, `report`, console) cũng dựng Orchestrator → cũng chạy `_rehydrate`.
    # Đường đọc TUYỆT ĐỐI không được ghi bus, nếu không mỗi lần xem trạng thái lại thêm một dòng rác.
    truoc = len(list(SQLiteBus(db).replay()))
    Orchestrator(SQLiteBus(db), FakeClient(handler=hong_lan_dau))
    assert len(list(SQLiteBus(db).replay())) == truoc, "dựng Orchestrator (đường đọc) không được ghi bus"

    orch2 = Orchestrator(SQLiteBus(db), FakeClient(handler=hong_lan_dau))
    orch2.run()
    assert orch2.bus.latest("clarification-questions", "P1"), "sau restart phải chạy tiếp, không được nằm im"


def test_khong_chay_lai_viec_da_co_nguoi_lam_xong(tmp_path):
    """Lệnh chạy lại chỉ sống trong RAM nên có thể nằm chờ rất lâu (người duyệt gate xong, tiến trình chết,
    hết hạn mức model). Trong lúc đó dự án vẫn đi tiếp được bằng đường khác. Nổ lại một việc đã xong là đốt
    một lượt model đắt tiền để sinh bản trùng. Đo được khi chạy thật 2026-09-04: lệnh ghi lúc 07:00:48,
    spec-writer sau đó thành công ba lần, nhưng lệnh cũ vẫn nổ lúc 09:54:42 và tiêu 317 giây claude-opus-5."""
    lan = {"n": 0}

    def hong_lan_dau(system, user):
        if _agent_of(system) == "researcher":
            lan["n"] += 1
            if lan["n"] == 1: raise LLMError("model rớt mạng")
        return handler(system, user)

    db = tmp_path / "c.sqlite"
    bus = SQLiteBus(db); orch = Orchestrator(bus, FakeClient(handler=hong_lan_dau))
    _pub(bus, "research-requests", "P1", "human:sales", {"project_id": "P1", "description": "app"})
    orch.run()
    assert orch.stalled.get("P1")
    orch.gate.decide("P1", "approve", by="human:lead")
    orch.run(max_steps=1)          # ghi `project.retried`, chưa kịp chạy lại thì tiến trình chết

    # Trong lúc chờ, việc ĐÃ ĐƯỢC LÀM XONG bằng đường khác: researcher cho ra research-findings cho P1.
    _pub(bus, "research-findings", "P1", "researcher", {"project_id": "P1", "kind": "researcher", "data": {}})

    goi_truoc = lan["n"]
    orch2 = Orchestrator(SQLiteBus(db), FakeClient(handler=hong_lan_dau))
    orch2.run()
    assert lan["n"] == goi_truoc, "việc đã xong thì không được gọi lại model"


def test_trang_thai_blocked_song_sot_qua_restart(tmp_path):
    """`blocked` suy ra từ SỐ LẦN RETRY chứ không từ event nào, nên trước đây nó chỉ nằm trong RAM. Mở lại bus
    là ticket quay về `dispatched` (theo event `tasks` cuối), và người duyệt escalation bấm approve thì
    `_on_escalation_decided` thấy state không phải blocked nên KHÔNG gọi `reopen()` — không có task mới, không
    ai làm, mà `status` vẫn báo mọi chỉ số xanh.

    Đo được khi chạy thật 2026-09-04: QLKH-001 blocked lúc 11:17, orchestrator restart lúc 11:29, gate duyệt
    cùng lúc đó → `budget.extended` có ghi nhưng không có event `tasks` nào nữa; đứng im 8 phút."""
    def hong_luon(system, user):
        if _agent_of(system) in ENGINEERING: raise LLMError("agent kỹ thuật hỏng")
        return handler(system, user)

    db = tmp_path / "c.sqlite"
    bus = SQLiteBus(db); orch = Orchestrator(bus, FakeClient(handler=hong_luon))
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    assert orch.lead.state["T1"] == "blocked", "hết retry thì ticket phải blocked"

    orch2 = Orchestrator(SQLiteBus(db), FakeClient(handler=hong_luon))
    assert orch2.lead.state["T1"] == "blocked", "blocked phải sống sót qua restart, nếu không gate duyệt cũng vô ích"

    # và người duyệt escalation phải mở lại được nó
    orch2.gate.decide("T1", "approve", by="human:lead", reason="thử lại")
    orch2.run()
    tasks = [e for e in orch2.bus.replay(topic="tasks", key="T1")]
    assert len(tasks) >= 2, "duyệt escalation phải phát task mới"


def test_ticket_bi_chan_lan_hai_van_phai_mo_gate(tmp_path):
    """Ticket bị chặn LẦN HAI phải mở gate mới, không được im lặng.

    `_check_escalations` chống gate trùng bằng khoá `escalation:<tid>:<n>:<state>`. Sau khi người duyệt mở lại
    ticket, ticket chạy tiếp rồi hết retry lần nữa: supervisor không hành động gì thêm nên `n` không đổi và
    `state` vẫn là `blocked` → khoá TRÙNG lần trước, `once` nuốt, không gate nào mở. Ticket nằm im vĩnh viễn
    trong khi `gates_pending` rỗng và `status` không báo gì bất thường.

    Đo được khi chạy thật 2026-09-04: QLKH-001 blocked lúc 13:25 với khoá `escalation:QLKH-001:5:blocked` đã có
    sẵn trong `once`; không có `gate.request` nào sau 11:58, và 13 ticket phụ thuộc đứng chờ vô hạn.

    Nhánh dự-án-kẹt đã có `stall_count` đúng vì lý do này ("mỗi lần một gate mới, không im lặng lần hai");
    nhánh ticket-bị-chặn thiếu bộ đếm tương ứng."""
    def hong_luon(system, user):
        if _agent_of(system) in ENGINEERING: raise LLMError("agent kỹ thuật hỏng")
        return handler(system, user)

    bus = SQLiteBus(tmp_path / "c.sqlite"); orch = Orchestrator(bus, FakeClient(handler=hong_luon))
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    assert orch.lead.state["T1"] == "blocked" and orch.gate.pending.get("T1"), "lần chặn đầu phải mở gate"

    orch.gate.decide("T1", "approve", by="human:lead", reason="thử lại")  # duyệt → pending rỗng, retry về 0
    orch.run()

    assert orch.lead.state["T1"] == "blocked", "agent vẫn hỏng nên ticket phải chặn lại"
    assert orch.gate.pending.get("T1"), "chặn lần hai mà không mở gate = dự án đứng im không ai được hỏi"


def test_status_canh_bao_khi_khong_con_viec_nao_chay_duoc(tmp_path):
    """`status` phải trả lời được "còn việc nào chạy được không", không chỉ liệt kê trạng thái.

    Mọi trường của `status()` đều mô tả trạng thái; không trường nào nói lên bế tắc. Nên một dự án chết đọc ra
    y hệt một dự án khoẻ: `queue: 0`, `stalled: {}`, `gates_pending: {}` — ba chỉ số xanh vì RỖNG, mà rỗng ở
    đây chính là triệu chứng.

    Đo được khi chạy thật 2026-09-04: QLKH-001 blocked lúc 13:25, gate bị `once` nuốt, 13 ticket phụ thuộc chờ
    vô hạn, `status` không có gì bất thường trong 26 phút."""
    def hong_luon(system, user):
        if _agent_of(system) in ENGINEERING: raise LLMError("agent kỹ thuật hỏng")
        return handler(system, user)

    bus = SQLiteBus(tmp_path / "c.sqlite"); orch = Orchestrator(bus, FakeClient(handler=hong_luon))
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()

    # ticket blocked NHƯNG gate escalation đang mở: người đã được hỏi, không phải bế tắc
    assert orch.gate.pending, "kịch bản phải có gate mở thì mới kiểm được chiều 'im lặng đúng'"
    assert orch.status()["warnings"] == [], "đang chờ người quyết thì không được kêu"

    orch.gate.pending.clear()  # tái hiện đúng lỗi thật: ticket blocked mà không cổng nào hỏi ai
    w = orch.status()["warnings"]
    assert w and "T1" in w[0], f"không còn đường nào chạy được thì status phải nói ra, nhận được: {w}"


def test_du_an_pause_vi_ngan_sach_phai_mo_gate_va_pause_lai_duoc(tmp_path):
    """Dự án chạm trần ngân sách bị `pause` → mọi event của nó bị hoãn. Ba lỗ hổng trên cùng một đường:

    1. `_check_escalations` lọc `t in self.lead.tickets`, mà ID dự án không phải ticket → không gate nào mở,
       không ai được hỏi. Đo được: `paused=['P1']` mà `gates_pending={}`.
    2. Điều kiện mở gate chỉ đếm `escalate`/`budget_cut`, không đếm `pause` → `n=0` cho dự án bị pause.
    3. `project_paused` không bao giờ được gỡ, nên sau lần resume đầu dự án KHÔNG BAO GIỜ pause lần nữa:
       chi phí 99 → 9999 (gấp 100 lần trần) mà supervisor chỉ sinh đúng một `pause`.

    Resume = cấp thêm một `project_budget_usd` nữa (đối xứng `budget.extended` của ticket). Không thể chỉ xoá
    `project_paused`: chi phí chỉ tăng nên tỉ lệ vẫn ≥ CUT_AT và pause bật lại ngay, thành vòng vô tận."""
    bus = SQLiteBus(tmp_path / "c.sqlite"); orch = Orchestrator(bus, FakeClient(), project_budget_usd=1.0)
    orch.lead.state["T1"] = "dispatched"

    orch.supervisor.project_cost["P1"] = 99.0; orch.supervisor._check_project("P1"); orch.run()
    assert "P1" in orch.paused, "chạm trần thì dự án phải bị pause"
    assert orch.gate.pending.get("P1"), "dự án bị pause mà không gate nào mở = không ai được hỏi"

    bus.publish(Envelope(topic="supervisor-actions", key="P1", actor="human:lead",
                         payload={"target": "P1", "action": "resume", "reason": "cấp thêm ngân sách"}))
    orch.supervisor.project_cost["P1"] = 9999.0; orch.supervisor._check_project("P1")
    pauses = [a.action for a in orch.supervisor.actions if a.target == "P1" and a.action == "pause"]
    assert len(pauses) >= 2, f"tiêu vượt trần lần nữa thì phải pause lần nữa, nhận được {pauses}"


def test_gate_qua_han_phai_vao_audit_du_da_nhac_truoc_do(tmp_path):
    """`gate.remind` và `gate.overdue` từng dùng CHUNG khoá `once` là `gate:{sid}`.

    Một gate luôn đi qua `remind` (12h) trước rồi mới tới `overdue` (24h). Lần nhắc ghi khoá vào `once`, nên khi
    gate thật sự quá hạn thì `_audit` thoát sớm và `gate.overdue` KHÔNG BAO GIỜ vào audit-log. Audit-log là bản
    ghi bền duy nhất của hệ thống, `metrics` đọc "gate chờ" từ đó — một gate bể hạn đọc ra y hệt một gate mới
    chỉ được nhắc."""
    from company.gates import GateRequest

    bus = SQLiteBus(tmp_path / "c.sqlite"); orch = Orchestrator(bus, FakeClient())
    orch.gate.request(GateRequest(kind="escalation", subject_id="G1", created_by="supervisor",
                                  checklist=["root_cause", "decision:reopen|close", "hint"]))

    orch.tick(now=datetime.now(UTC) + orch.gate.remind_at + timedelta(minutes=1))
    orch.tick(now=datetime.now(UTC) + orch.gate.timeout + timedelta(minutes=1))

    actions = [e.payload["action"] for e in bus.replay(topic="audit-log")]
    assert "gate.remind" in actions, "kịch bản phải đi qua nhắc trước thì mới kiểm được va chạm khoá"
    assert "gate.overdue" in actions, "gate quá hạn phải vào audit-log, không được bị lần nhắc nuốt mất"


# Trạng thái chỉ sống trong RAM là nguồn lỗi lặp lại nhiều nhất: nó không hỏng ồn ào, nó chỉ lặng lẽ biến mất
# khi mở lại bus, rồi dự án đứng im trong khi mọi chỉ số vẫn xanh. Test dưới đây chốt bất biến chung thay vì
# chạy theo từng ca: chạy hết một vòng đời rồi so TỪNG thuộc tính giữa đối tượng đang sống và đối tượng dựng
# lại từ log. Thêm state mới mà quên đường dựng lại thì test này đỏ ngay.
#
# Mỗi mục loại trừ dưới đây là một QUYẾT ĐỊNH có lý do, không phải chỗ giấu state chưa xử lý.
_CONG_TAC_VIEN = {"bus", "gate", "lead", "supervisor", "runner", "blackboard", "agents", "handlers"}
_CAU_HINH = {"integration", "repo", "base", "integration_branch", "workers", "web", "max_turns", "max_retries",
             "batch_releases", "require_integration", "replaying", "ticket_timeout", "review_timeout",
             "project_budget_usd"}
_CO_Y_KHONG_DUNG_LAI = {
    "queue",        # dựng lại bằng công thức riêng (event chưa `orchestrated`), không phải bản sao
    # `deferred` dựng lại MỘT PHẦN, có chủ ý: chỉ event nào backend hẹn giờ rõ ràng (`defer.until` trong
    # audit-log) mới quay về `deferred` với phần thời gian còn lại — nếu không thì mở lại bus giữa lúc chờ
    # quota là đập ngay vào backend đã cạn. Event hoãn vì `gate:`/`paused:` KHÔNG ghi hẹn: chúng tự vào lại
    # hàng đợi và bị hoãn lại ngay ở lượt chạy đầu theo trạng thái gate/pause hiện tại, đúng hơn là khôi phục
    # một lý do có thể đã cũ. Nên hai bên không bằng nhau theo từng phần tử — xem `_nap_lai_hen`.
    "deferred",
    # Cùng lý do, cộng thêm: giá trị là mốc `time.monotonic()` của TỪNG TIẾN TRÌNH nên không bao giờ so được
    # trực tiếp. Cái cần bảo đảm là "còn hẹn thì không chạy ngay", và điều đó có test riêng
    # (`test_hen_cho_backend_song_sot_qua_restart`).
    "defer_until",
    "stats",        # bộ đếm của phiên, không phải trạng thái nghiệp vụ
    "partial",      # bản dựng lại lọc theo `processed`, chặt hơn bản đang sống (và đúng hơn)
    "knowledge",    # bài học nằm trên blackboard; `sprint_report` đếm từ `lessons()`
}
_BO_QUA = _CONG_TAC_VIEN | _CAU_HINH | _CO_Y_KHONG_DUNG_LAI


def _bo_dau_thoi_gian(v):
    """Bỏ `created_at` khỏi so sánh: bản đang sống đặt nó bằng đồng hồ lúc tạo, bản dựng lại lấy từ `env.ts`.
    Hai giá trị lệch nhau vài micro giây — đó KHÔNG phải mất trạng thái. Test bản đầu so cả trường này nên
    xanh trên Windows (đồng hồ thô ~15ms nên tình cờ trùng) mà đỏ trên Linux: một test đúng-sai theo nền tảng
    còn tệ hơn không có test."""
    if is_dataclass(v) and not isinstance(v, type):
        return {f.name: _bo_dau_thoi_gian(getattr(v, f.name)) for f in fields(v) if f.name != "created_at"}
    if isinstance(v, dict): return {k: _bo_dau_thoi_gian(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)): return [_bo_dau_thoi_gian(x) for x in v]
    return v


def _thuoc_tinh_lech(a, b) -> list[str]:
    lech = []
    for k in sorted(vars(a)):
        if k in _BO_QUA or k.startswith("_"):
            continue
        va, vb = getattr(a, k, None), getattr(b, k, None)
        if callable(va):
            continue
        try:
            if _bo_dau_thoi_gian(va) != _bo_dau_thoi_gian(vb):
                lech.append(f"{k}: live={va!r:.60} != rebuilt={vb!r:.60}")
        except Exception:
            pass
    return lech


def _chay_het_vong_doi(bus, o):
    _drive_to_plan(bus, o)
    o.gate.decide("PLAN-P1-1", "approve", by="human:pm"); o.run()
    o.gate.decide("REL-001", "approve", by="human:release-manager"); o.run()
    _pub(bus, "acceptance-results", "REL-001", "account-manager",
         {"release_id": "REL-001", "project_id": "P1", "verdict": "accepted", "signed_by": "customer:po"})
    o.run()


def test_moi_trang_thai_nghiep_vu_song_sot_qua_restart(tmp_path):
    """Bất biến: mở lại bus phải dựng lại ĐÚNG trạng thái đang có, không mất mục nào.

    Trong một phiên chạy thật (2026-09-04) đã gặp nhiều lỗi cùng khuôn này — lệnh thử-lại và trạng thái
    `blocked` của ticket đều chỉ sống trong RAM — mỗi lần đều làm dự án đứng im mà `status` vẫn báo xanh.
    Test này chốt bất biến chung để không phải phát hiện từng cái qua sự cố."""
    db = tmp_path / "c.sqlite"
    bus = SQLiteBus(db)
    o = Orchestrator(bus, FakeClient(handler=handler))
    _chay_het_vong_doi(bus, o)
    assert o.lead.state["T1"] == "closed", "vòng đời phải đi hết thì so sánh mới có ý nghĩa"

    o2 = Orchestrator(SQLiteBus(db), FakeClient(handler=handler))
    for ten, a, b in (("Orchestrator", o, o2), ("DeliveryLead", o.lead, o2.lead),
                      ("Supervisor", o.supervisor, o2.supervisor), ("PersistentGate", o.gate, o2.gate)):
        lech = _thuoc_tinh_lech(a, b)
        assert not lech, f"{ten} mất trạng thái khi mở lại bus: " + " | ".join(lech)


def test_state_song_sot_qua_restart_ca_khi_co_escalation(tmp_path):
    """Bản đầu của test bất biến chỉ chạy vòng đời SẠCH nên không phủ nhánh escalation — và đúng nhánh đó có
    lỗi: `Supervisor._on` mở đầu bằng `if env.actor == "supervisor": return`, nên khi replay nó nuốt luôn
    `self.actions`. Đo được khi chạy thật 2026-09-04: bus có 5 event escalate/budget_cut cho một ticket nhưng
    sau restart đếm được 0.

    Hệ quả dây chuyền: `_check_escalations` tạo gate theo `state == "blocked" or n`; ticket đang `paused` ở
    trạng thái không phải blocked với n=0 thì KHÔNG có gate nào mở — không ai gỡ được pause, dự án đứng im
    trong khi `stalled` và `gates_pending` đều rỗng.

    Bài học về chính test bất biến: nó chỉ phủ được những gì kịch bản đi qua."""
    def reviewer_hong(system, user):
        # reviewer hỏng trên `pull-requests` → `_after_error` gọi `supervisor.escalate_gate` (đường DUY NHẤT
        # sinh action "escalate"; nhánh ticket blocked gọi thẳng `gate.request`, không qua supervisor).
        if _agent_of(system) in {"reviewer", "qa-debugger", "security-engineer"}:
            raise LLMError("reviewer hỏng")
        return handler(system, user)

    db = tmp_path / "c.sqlite"
    bus = SQLiteBus(db)
    o = Orchestrator(bus, FakeClient(handler=reviewer_hong))
    _drive_to_plan(bus, o); o.gate.decide("PLAN-P1-1", "approve", by="human:pm"); o.run()
    n_live = sum(1 for a in o.supervisor.actions if a.action in {"escalate", "budget_cut"})
    assert n_live > 0, "kịch bản phải sinh ra escalation thì mới kiểm được nhánh này"

    o2 = Orchestrator(SQLiteBus(db), FakeClient(handler=reviewer_hong))
    n_rebuilt = sum(1 for a in o2.supervisor.actions if a.action in {"escalate", "budget_cut"})
    assert n_rebuilt == n_live, f"hành động supervisor phải dựng lại đủ: live={n_live} rebuilt={n_rebuilt}"

    for ten, a, b in (("Orchestrator", o, o2), ("DeliveryLead", o.lead, o2.lead),
                      ("Supervisor", o.supervisor, o2.supervisor), ("PersistentGate", o.gate, o2.gate)):
        lech = _thuoc_tinh_lech(a, b)
        assert not lech, f"{ten} mất trạng thái khi mở lại bus: " + " | ".join(lech)


def test_bao_cao_dem_bai_hoc_tu_blackboard_khong_tu_ram(tmp_path):
    """`sprint_report()['lessons']` từng đếm `self.knowledge` — danh sách RAM không dựng lại khi mở lại bus,
    nên sau restart báo cáo hiện 0 bài học dù chúng vẫn nằm nguyên trên blackboard. Người đọc sẽ tưởng vòng
    học không chạy."""
    db = tmp_path / "c.sqlite"
    bus = SQLiteBus(db)
    o = Orchestrator(bus, FakeClient(handler=handler))
    _chay_het_vong_doi(bus, o)
    truoc = o.supervisor.sprint_report()["lessons"]
    assert truoc > 0, "vòng đời đầy đủ phải rút được ít nhất một bài học"

    o2 = Orchestrator(SQLiteBus(db), FakeClient(handler=handler))
    assert o2.supervisor.sprint_report()["lessons"] == truoc, "số bài học không được tụt về 0 sau restart"


def test_ton_trong_thoi_gian_cho_backend_da_hen():
    """Backend nói rõ "thử lại sau 1515s" thì không được hỏi lại ở nhịp tick kế. Trước đây mọi tick đều thử
    lại: đo được 60 bản ghi `llm_error`/phút LIÊN TỤC lúc pool hết quota (2026-09-04). Rẻ về tài nguyên
    (tầng routing không gọi mạng khi backend đang nghỉ) nhưng làm bẩn audit-log, mà `_rehydrate` replay TOÀN
    BỘ log nên bus phình khiến mọi lần mở lại dự án chậm dần — lỗi tự nuôi chính nó."""
    from company.llm import TransientError

    goi = {"n": 0}

    def het_quota(system, user):
        if _agent_of(system) == "intake":
            goi["n"] += 1
            raise TransientError("mọi backend đều đang nghỉ, thử lại sau 1515s")
        return handler(system, user)

    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=het_quota))
    _pub(bus, "research-requests", "P1", "human:sales", {"project_id": "P1", "description": "app"})
    orch.run()
    assert goi["n"] == 1 and orch.deferred, "lần đầu gọi rồi hoãn"
    for _ in range(5):
        orch.tick()
    assert goi["n"] == 1, f"đã hẹn 1515s thì không được hỏi lại ở tick kế (đã gọi {goi['n']} lần)"

    # hết hẹn thì phải thử lại, không được treo luôn
    for k in orch.defer_until: orch.defer_until[k] = 0.0
    orch.tick()
    assert goi["n"] == 2, "hết thời gian hẹn thì phải thử lại"


def test_release_engineer_wrong_env_is_invalid_output():
    def sneaky(system, user):
        if _agent_of(system) == "release-engineer":
            return {**handler(system, user), "env": "production"}
        return handler(system, user)
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=sneaky))
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    assert not list(bus.replay(topic="release-events")), "không deploy production khi chưa qua gate"
    assert orch.lead.state["T1"] == "approved" and orch.stats["errors"] >= 1
    assert any(e.payload["action"] == "invalid_output" for e in bus.replay(topic="audit-log"))


def test_model_error_is_audited_and_loop_continues():
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient())  # hết câu trả lời → LLMError
    _pub(bus, "research-requests", "P1", "human", {"project_id": "P1", "description": "x"})
    res = orch.run()
    assert res[0].actions[0].startswith("error:intake") and orch.stats["errors"] == 1 and not orch.queue
    acts = [e.payload["action"] for e in bus.replay(topic="audit-log")]
    assert acts[0] == "llm_error" and "project.stalled" in acts and acts[-1] == "orchestrated"


# ---------- CLI ----------

def test_cli_run_watch_thoat_em_khi_ctrl_c(tmp_path, capsys, monkeypatch):
    """`run --watch`: Ctrl+C (KeyboardInterrupt) trong `orch.watch` phải thoát êm mã 0, in status cuối, không traceback."""
    import company.orchestrator as om
    db = str(tmp_path / "c.sqlite")
    monkeypatch.setenv("COMPANY_LLM_PROVIDER", "fake")

    def boom(self, interval=5.0, max_ticks=None):
        raise KeyboardInterrupt

    monkeypatch.setattr(om.Orchestrator, "watch", boom)
    rc = orch_main(["--db", db, "run", "--watch", "5"])
    assert rc == 0
    assert '"queue"' in capsys.readouterr().out

def test_cli_publish_and_status(tmp_path, capsys, monkeypatch):
    db = str(tmp_path / "c.sqlite"); f = tmp_path / "req.json"
    f.write_text(json.dumps({"project_id": "P1", "description": "app"}), encoding="utf-8")
    monkeypatch.setenv("COMPANY_LLM_PROVIDER", "fake")
    assert orch_main(["--db", db, "publish", "research-requests", str(f), "--actor", "human:sales"]) == 0
    assert "published research-requests key=P1" in capsys.readouterr().out
    assert orch_main(["--db", db, "status"]) == 0
    assert json.loads(capsys.readouterr().out)["queue"] == 1
    assert orch_main(["--db", db, "run", "--max-steps", "1"]) == 0  # FakeClient rỗng → lỗi được ghi, không crash
    out = capsys.readouterr().out
    assert "error:intake" in out and '"errors": 1' in out


def test_orchestrator_rejects_inconsistent_routes():
    agents = load_agents(); agents["intake"].reads = ["clarification-answers"]
    with pytest.raises(ValueError, match="ROUTES lệch"):
        Orchestrator(InMemoryBus(), FakeClient(), agents=agents)


# ---------- bổ sung sau audit: blackboard, threat model, lối thoát clarifier, CR, escalation, vòng học ----------

def test_agents_write_blackboard_and_threat_model_precedes_plan():
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler))
    _drive_to_plan(bus, orch)
    bb = orch.blackboard.snapshot("P1")  # blackboard phân vùng theo dự án
    assert {"prd", "threat-model", "architecture", "api-contract"} <= set(bb), "PRD, threat model, C4, contract lên blackboard trước gate plan"
    assert bb["threat-model"].content_ref == "docs/threat-model.md"
    tm = list(bus.replay(topic="review-results", key="SPEC-P1"))
    assert len(tm) == 1 and tm[0].payload["source"] == "security"
    acts = [e.payload["action"] for e in bus.replay(topic="audit-log")]
    assert "context_written" in acts and orch.gate.pending["PLAN-P1-1"].checklist[-2:] == ["architecture", "api-contract"]


def test_security_block_on_spec_stops_planning():
    def blocker(system, user):
        if _agent_of(system) == "security-engineer" and "artifacts" in _inp(user):
            return {"ticket_id": "SPEC-P1", "source": "security", "verdict": "block", "findings": [{"level": "block", "text": "PII không mã hoá"}]}
        return handler(system, user)
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=blocker))
    _pub(bus, "approved-specs", "P1", "spec-writer", {"project_id": "P1", "status": "pending_human", "artifacts": {"prd": "docs/prd.md", "requirements": "docs/requirements.json"}})
    orch.run(); orch.gate.decide("SPEC-P1", "approve", by="human:po"); orch.run()
    assert not orch.plans and not orch.gate.pending
    assert any(e.payload["action"] == "spec_blocked_by_security" for e in bus.replay(topic="audit-log"))


def test_clarifier_without_questions_goes_straight_to_spec_writer():
    def quiet(system, user):
        if _agent_of(system) == "clarifier": return {"project_id": "P1", "round": 1, "questions": []}
        return handler(system, user)
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=quiet))
    _pub(bus, "research-requests", "P1", "human", {"project_id": "P1", "description": "x"})
    orch.run()
    assert [e.actor for e in bus.replay(topic="approved-specs")] == ["spec-writer"] and "SPEC-P1" in orch.gate.pending


def test_change_request_impact_then_human_decision_then_plan(tmp_path):
    db = tmp_path / "c.sqlite"; bus = SQLiteBus(db); orch = Orchestrator(bus, FakeClient(handler=handler))
    _pub(bus, "external-feedback", "P1", "human:customer", {"project_id": "P1", "from": "chị Lan", "text": "muốn xuất Excel"})
    orch.run()
    crs = list(bus.replay(topic="change-requests"))
    assert len(crs) == 1 and crs[0].payload["decision"] == "pending"
    assert not list(bus.replay(topic="incidents")), "feedback không phải lỗi → support-docs không mở incident"
    impact = [e for e in bus.replay(topic="audit-log") if e.payload["action"] == "change.impact"]
    assert impact and impact[0].actor == "delivery-lead"
    assert orch_main(["--db", str(db), "decide-change", "CR-1", "accepted", "--by", "human:po"]) == 0
    orch.tick()
    cr = list(bus.replay(topic="change-requests"))[-1].payload
    assert cr["decision"] == "accepted" and cr["impact"]["estimate_tokens"] == 5000 and cr["impact"]["decided_by"] == "human:po"
    assert "PLAN-P1-1" in orch.gate.pending, "CR accepted không đổi requirement → delivery-lead lập kế hoạch thẳng"


def test_feedback_with_bug_opens_incident_and_requirement_incident_reopens_research():
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler))
    _pub(bus, "external-feedback", "P1", "human:customer", {"project_id": "P1", "from": "user", "text": "app lỗi khi đặt lịch"})
    orch.run()
    assert [e.payload["incident_id"] for e in bus.replay(topic="incidents")] == ["INC-1"]
    _pub(bus, "incidents", "INC-2", "support-docs", {"incident_id": "INC-2", "severity": "SEV3", "summary": "hiểu sai yêu cầu",
                                                     "project_id": "P1", "root_cause_class": "requirement"})
    orch.run()
    assert any("INC-2" in e.payload["description"] for e in bus.replay(topic="research-requests"))


def test_conditional_acceptance_opens_change_request_and_lessons_recorded():
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler))
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    orch.gate.decide("REL-001", "approve", by="human:rm"); orch.run()
    assert orch.blackboard.read("docs", "P1") is not None, "support-docs viết release notes sau production"
    _pub(bus, "acceptance-results", "REL-001", "account-manager",
         {"release_id": "REL-001", "project_id": "P1", "verdict": "conditional", "signed_by": "customer:po"})
    orch.run()
    assert [e.payload["change_id"] for e in bus.replay(topic="change-requests")] == ["CR-UAT-1"]
    assert orch.lead.state["T1"] == "released", "conditional giữ released"
    _pub(bus, "acceptance-results", "REL-001", "account-manager",
         {"release_id": "REL-001", "project_id": "P1", "verdict": "accepted", "signed_by": "customer:po"})
    orch.run()
    assert orch.lead.state["T1"] == "closed" and orch.supervisor.knowledge
    k = orch.blackboard.read("knowledge")
    assert k is not None and json.loads(k.summary)["ticket_id"] == "T1" and json.loads(k.summary)["actual_tokens"] > 0


def test_blocked_ticket_opens_escalation_gate_and_reopens_on_approve():
    def failing(system, user):
        if _agent_of(system) == "reviewer":
            return {"ticket_id": _inp(user)["ticket_id"], "source": "reviewer", "verdict": "block", "findings": [{"level": "block", "text": "sai contract"}]}
        return handler(system, user)
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=failing))
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    # cùng lỗi lặp 2 lần → supervisor escalate → ticket bị hoãn, gate escalation mở cho người
    assert "T1" in orch.paused and orch.gate.pending["T1"].kind == "escalation" and orch.deferred
    orch.gate.decide("T1", "approve", by="human:pm", reason="cứ làm tiếp"); orch.run()
    # resume → retry tiếp → hết 3 lần → blocked → gate escalation lần hai
    assert orch.lead.state["T1"] == "blocked" and orch.gate.pending["T1"].kind == "escalation"
    orch.gate.decide("T1", "approve", by="human:pm", reason="sửa theo contract v2"); orch.run()
    reopened = [e.payload for e in bus.replay(topic="tasks") if e.payload.get("hint") == "sửa theo contract v2"]
    assert reopened and reopened[0]["retry"] == 0, "mở lại với hint của người duyệt, đếm retry lại"
    assert orch.lead.state["T1"] in {"dispatched", "blocked"} and orch.gate.pending["T1"].kind == "escalation", "vẫn block → lại escalate, không lặp vô hạn"
    orch.gate.decide("T1", "reject", by="human:pm", reason="bỏ ticket"); orch.run()
    assert orch.lead.state["T1"] == "closed" and "T1" not in orch.gate.pending


def test_overdue_review_is_reassigned_once():
    calls = []
    def lazy(system, user):
        a = _agent_of(system); calls.append(a)
        if a == "qa-debugger" and "`pull-requests`" in user and calls.count("qa-debugger:pr") == 0:  # lượt QA ở PR (T2)
            calls.append("qa-debugger:pr"); raise LLMError("timeout")
        return handler(system, user)
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=lazy))
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    later = datetime.now(UTC) + timedelta(hours=3)
    assert orch.lead.state["T2"] == "in_review" and orch.lead.overdue_reviews(later) == {"T2": {"qa"}}
    orch.tick(now=later)
    acts = [e.payload["action"] for e in bus.replay(topic="audit-log")]
    assert orch.lead.state["T2"] == "merged" and acts.count("review.reassign") == 1 and acts.count("llm_error") == 1


def test_spec_bi_reject_thi_khong_lap_plan_va_bi_danh_dau_xong():
    """Gate spec bị reject: event `approved-specs` đang hoãn phải được đánh dấu xong (không lặp lại mãi), không lập plan."""
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler))
    _pub(bus, "research-requests", "P1", "human:sales", {"project_id": "P1", "description": "app đặt lịch"})
    orch.run()
    _pub(bus, "clarification-answers", "P1", "human:po", {"project_id": "P1", "answers": [{"question_id": "Q1", "answer": "a"}]})
    orch.run()
    assert "SPEC-P1" in orch.gate.pending
    orch.gate.decide("SPEC-P1", "reject", by="human:po", reason="không cần nữa")
    orch.run()
    assert not orch.deferred and not orch.plans and not orch.lead.tickets
    acts = [e.payload["action"] for e in bus.replay(topic="audit-log")]
    assert not any(a.startswith("plan_") for a in acts)


def test_tick_nhac_va_escalate_gate_qua_han():
    """`tick` phải audit `gate.remind`/`gate.overdue` và giao việc cho supervisor khi gate quá hạn — mỗi cái một lần."""
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler))
    _drive_to_plan(bus, orch)
    later = datetime.now(UTC) + timedelta(hours=25)   # > timeout mặc định 24h
    orch.tick(now=later)
    acts = [e.payload["action"] for e in bus.replay(topic="audit-log")]
    assert "gate.overdue" in acts
    assert any(a.action == "escalate" and a.target == "PLAN-P1-1" for a in orch.supervisor.actions)
    n_before = len(orch.supervisor.actions)
    orch.tick(now=later)   # lần hai: đã escalate rồi, không lặp lại
    assert len(orch.supervisor.actions) == n_before


def test_incomplete_answers_go_back_to_clarifier_then_spec_writer():
    """Người trả lời thiếu → clarifier hỏi lại đúng phần thiếu (vòng 2); trả đủ → spec-writer đi tiếp."""
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler))
    _pub(bus, "research-requests", "P1", "human:sales", {"project_id": "P1", "description": "app đặt lịch"})
    orch.run()
    assert _topics(bus)[-1] == "clarification-questions"
    _pub(bus, "clarification-answers", "P1", "human:po", {"project_id": "P1", "answers": []})
    orch.run()
    assert _topics(bus)[-1] == "clarification-questions", "chưa trả lời câu nào thì hỏi lại, chưa viết spec"
    _pub(bus, "clarification-answers", "P1", "human:po",
         {"project_id": "P1", "answers": [{"question_id": "Q1", "answer": "a"}]})
    orch.run()
    assert "approved-specs" in _topics(bus), "trả lời đủ thì spec-writer chạy"


# ---------- F1/F2/F5 (báo cáo mô phỏng donghanhcungban 2026-09-02) ----------

def test_research_agent_error_stalls_project_opens_gate_and_retries_on_approve():
    """F1: synthesizer lỗi → dự án không có bước tiếp theo. Trước đây: status trống, không gate, không ai biết."""
    bad = {"n": 0}
    def flaky(system, user):
        if _agent_of(system) == "synthesizer" and bad["n"] == 0:
            bad["n"] += 1; return {"project_id": "P1", "kind": "draft", "requirements": [{"id": "REQ-1"}]}  # sai schema
        return handler(system, user)
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=flaky))
    _pub(bus, "research-requests", "P1", "human:sales", {"project_id": "P1", "description": "web demo"})
    orch.run()
    assert "requirements-draft" not in _topics(bus) and orch.stats["errors"] == 1
    assert orch.gate.pending["P1"].kind == "escalation" and "P1" in orch.paused, "dự án kẹt phải hiện thành gate"
    assert orch.status()["stalled"] == {"P1": "synthesizer lỗi trên research-findings: " + orch.stalled["P1"]["error"][:120]}
    # khách trả lời câu hỏi chưa tồn tại: dự án đang hoãn → không sinh spec từ đầu vào trống
    _pub(bus, "clarification-answers", "P1", "human:po", {"project_id": "P1", "answers": []})
    orch.run()
    assert "approved-specs" not in _topics(bus) and orch.deferred
    # người duyệt: approve = chạy lại event đã lỗi → chuỗi đi tiếp tới câu hỏi làm rõ
    orch.gate.decide("P1", "approve", by="human:lead", reason="model trả sai schema, thử lại")
    orch.run()
    assert "P1" not in orch.stalled and "P1" not in orch.paused
    assert _topics(bus)[-1] == "clarification-questions"
    acts = [e.payload["action"] for e in bus.replay(topic="audit-log")]
    assert "project.stalled" in acts and "project.retried" in acts


def test_stalled_project_survives_restart_and_reject_closes_it(tmp_path):
    bus = SQLiteBus(tmp_path / "c.sqlite"); orch = Orchestrator(bus, FakeClient())  # mọi agent lỗi
    _pub(bus, "research-requests", "P1", "human", {"project_id": "P1", "description": "x"})
    orch.run()
    assert "P1" in orch.stalled
    orch2 = Orchestrator(SQLiteBus(tmp_path / "c.sqlite"), FakeClient())
    assert orch2.stalled["P1"]["agent"] == "intake" and orch2.gate.pending["P1"].kind == "escalation"
    orch2.gate.decide("P1", "reject", by="human:lead", reason="huỷ dự án"); orch2.run()
    assert "P1" not in orch2.stalled and not orch2.queue
    assert any(e.payload["action"] == "project.closed" for e in orch2.bus.replay(topic="audit-log"))


def test_spec_writer_refuses_without_requirements_draft():
    """F2: câu trả lời làm rõ cho dự án chưa có bản nháp → không viết PRD từ đầu vào trống, có audit."""
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler))
    _pub(bus, "clarification-answers", "P9", "human:po", {"project_id": "P9", "answers": [{"question_id": "Q1", "answer": "a"}]})
    orch.run()
    assert "approved-specs" not in _topics(bus) and orch.stats["errors"] == 0
    a = next(e.payload for e in bus.replay(topic="audit-log") if e.payload["action"] == "spec_writer.no_draft")
    assert a["project_id"] == "P9"


def test_cli_read_only_commands_do_not_need_model(tmp_path, capsys, monkeypatch):
    """F5: status/report/show là lệnh của người xem; không được crash vì thiếu SDK hay API key."""
    db = str(tmp_path / "c.sqlite")
    monkeypatch.setenv("COMPANY_LLM_PROVIDER", "anthropic"); monkeypatch.delenv("COMPANY_LLM_API_KEY", raising=False)
    import company.orchestrator as om
    monkeypatch.setattr(om, "load_agents", load_agents)
    def boom(): raise RuntimeError("cài SDK: uv sync --extra anthropic")
    import company.llm as llm_mod
    monkeypatch.setattr(llm_mod, "make_client", boom)
    assert orch_main(["--db", db, "status"]) == 0 and json.loads(capsys.readouterr().out)["queue"] == 0
    assert orch_main(["--db", db, "report"]) == 0
    assert orch_main(["--db", db, "show", "prd"]) == 2  # chưa có artifact: lỗi nghiệp vụ, không phải lỗi model
    with pytest.raises(RuntimeError, match="SDK"):
        orch_main(["--db", db, "run", "--max-steps", "1"])  # chỉ `run` mới cần model


def test_republished_spec_does_not_create_second_plan():
    """F13: approved-specs publish lặp (spec-writer chạy lại / người publish hai lần) → không sinh plan thứ hai."""
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=handler))
    _drive_to_plan(bus, orch)
    spec = bus.latest("approved-specs", "P1")
    _pub(bus, "approved-specs", "P1", "spec-writer", spec.payload); orch.run()
    assert list(orch.plans) == ["PLAN-P1-1"] and list(orch.gate.pending) == ["PLAN-P1-1"]
    a = [json.loads(e.payload["evidence"]) for e in bus.replay(topic="audit-log") if e.payload["action"] == "plan.duplicate_spec"]
    assert a and a[0]["existing"] == ["PLAN-P1-1"]
    orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    _pub(bus, "approved-specs", "P1", "spec-writer", spec.payload); orch.run()  # sau khi plan đã duyệt cũng không lập lại
    assert list(orch.plans) == ["PLAN-P1-1"] and set(orch.lead.tickets) == {"T1", "T2"}


def test_synthesizer_receives_intake_report_with_researcher_findings():
    """Tiêu chí bắt đầu của synthesizer (ADR-0006) cần CẢ báo cáo intake lẫn báo cáo 4 mục của researcher, nhưng nó
    chỉ được đánh thức bởi báo cáo researcher. Không đính kèm đề bài intake thì draft luôn rỗng — đúng theo prompt,
    và vòng nghiên cứu không bao giờ đi tiếp."""
    seen: dict = {}

    def h(system: str, user: str) -> dict:
        if _agent_of(system) == "synthesizer": seen.update(_inp(user))
        return handler(system, user)

    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=h))
    _pub(bus, "research-findings", "P1", "intake", {"project_id": "P1", "kind": "intake",
                                                    "data": {"goals": [{"id": "G-1", "text": "đặt lịch online"}]}})
    _pub(bus, "research-findings", "P1", "researcher", {"project_id": "P1", "kind": "researcher", "data": {"domain": {}}})
    orch.run()
    assert seen["intake"] == {"goals": [{"id": "G-1", "text": "đặt lịch online"}]}


def test_hen_cho_backend_song_sot_qua_restart(tmp_path):
    """Backend hẹn "thử lại sau Ns" → mốc hẹn phải BỀN, không mất khi mở lại bus.

    `defer_until` dùng `time.monotonic()` (vô nghĩa ở tiến trình khác) và cả `deferred` lẫn nó đều chỉ sống
    trong RAM, trong khi `_rehydrate` đẩy MỌI event chưa xử lý thẳng vào `self.queue`. Nên restart giữa lúc chờ
    quota là mất hẹn và đập ngay vào backend đã cạn: vô ích, bẩn audit-log, có thể bị phạt nặng hơn.

    Đo được khi chạy thật (2026-09-04 15:46:30): cả hai backend trả 429, hệ thống hoãn đúng 2010s; nhưng
    `status` từ tiến trình khác đọc ra `deferred: {}` — mốc hẹn không tồn tại ngoài RAM của tiến trình đang chạy."""
    db = tmp_path / "c.sqlite"
    bus = SQLiteBus(db)
    orch = Orchestrator(bus, FakeClient())
    env = _pub(bus, "tasks", T1["ticket_id"], "delivery-lead", T1)

    orch._defer(env, StepResult(event_id=env.event_id, topic=env.topic, key=env.key), "transient:backend", wait_s=3600)
    assert env.event_id in orch.defer_until, "tiến trình đang chạy phải giữ mốc hẹn"

    orch2 = Orchestrator(SQLiteBus(db), FakeClient())
    assert env.event_id in orch2.deferred, "mở lại bus: event còn hẹn phải nằm ở `deferred`"
    assert env.event_id not in {e.event_id for e in orch2.queue}, \
        "không được vào hàng đợi chạy ngay — đó chính là cú đập vào backend đã cạn quota"
    assert orch2.defer_until.get(env.event_id, 0) > time.monotonic(), "hẹn phải quy về mốc của tiến trình này"
    assert orch2.status()["warnings"] == [], "đang chờ hẹn hợp lệ thì không được kêu bế tắc"

    # hẹn đã qua thì thôi, để event chạy bình thường — không kẹt vĩnh viễn
    orch3 = Orchestrator(SQLiteBus(db), FakeClient())
    orch3.deferred.clear(); orch3.defer_until.clear(); orch3.queue = [env]   # dựng lại đúng tình huống cần đo
    orch3._nap_lai_hen({env.event_id: ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), "transient:backend")})
    assert env.event_id not in orch3.deferred and [e.event_id for e in orch3.queue] == [env.event_id]

    # mốc hỏng cũng phải cho chạy, không được kẹt vĩnh viễn vì một dòng log sai định dạng
    orch3.queue = [env]
    orch3._nap_lai_hen({env.event_id: ("khong-phai-ngay-thang", "transient:backend")})
    assert [e.event_id for e in orch3.queue] == [env.event_id]
