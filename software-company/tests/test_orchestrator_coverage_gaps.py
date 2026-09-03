"""Phủ các nhánh lỗi/hiếm còn thiếu trong orchestrator.py (xem coverage report): _with_diff khi diff() lỗi, dự án
paused, rework race, các nhánh của _merge_ticket/_integrate, _read_only_tools rơi vào None, threat-model
transient/lỗi, _dispatch_plan lỗi khi gate plan approve, _close_acceptance_gate khi gate.decide lỗi."""
from __future__ import annotations

import json

import pytest

from company.bus import InMemoryBus
from company.events import Envelope, Task
from company.gates import GateRequest
from company.llm import FakeClient, LLMError, TransientError
from company.orchestrator import Orchestrator, Route, StepResult, _with_diff
from company.workspace import WorkspaceError
from test_orchestrator import T1, _drive_to_plan, handler


def _orch(bus=None):
    if bus is None: bus = InMemoryBus()  # InMemoryBus có __len__: bus rỗng bị coi là falsy, `bus or ...` sẽ tráo nhầm
    return Orchestrator(bus, FakeClient(handler=handler))


# ---------- _with_diff: WorkspaceError khi đọc diff ----------

def test_with_diff_bat_workspace_error(monkeypatch, tmp_path):
    orch = _orch()

    class FakeWs:
        path = tmp_path

        def diff(self):
            raise WorkspaceError("git diff: lỗi")

        def changed_files(self):
            return []

    monkeypatch.setattr(orch, "workspace", lambda tid: FakeWs())
    env = Envelope(topic="pull-requests", key="T1", actor="backend", payload={"ticket_id": "T1"})
    out = _with_diff(env, orch)
    assert "diff_error" in out and "git diff" in out["diff_error"]


# ---------- process(): dự án bị paused (project_id trong self.paused) → defer ----------

def test_process_defer_khi_project_paused():
    orch = _orch()
    orch.paused.add("P1")
    env = Envelope(topic="pull-requests", key="T1", actor="backend",
                    payload={"ticket_id": "TX", "project_id": "P1"})
    res = orch.process(env)
    assert res is not None and res.deferred == "paused:P1"


# ---------- _rework_after_error: rework() vẫn có thể raise ValueError (race giữa các worker) ----------

def test_rework_after_error_bat_value_error(monkeypatch):
    orch = _orch()
    orch.lead.tickets["T1"] = Task.model_validate(T1)
    orch.lead.state["T1"] = "dispatched"

    def boom(tid, hint):
        raise ValueError(f"{tid}: rework chỉ từ dispatched/in_progress (đang blocked)")

    monkeypatch.setattr(orch.lead, "rework", boom)
    env = Envelope(topic="tasks", key="T1", actor="backend", payload={"ticket_id": "T1"})
    route = Route("tasks", "$assignee", "pull-requests", tools="rw")
    orch._rework_after_error(env, route, RuntimeError("lỗi giả"))
    errs = [json.loads(e.payload["evidence"]) for e in orch.bus.replay(topic="audit-log") if e.payload["action"] == "handler_error"]
    assert errs and errs[0]["agent"] == "delivery-lead"


# ---------- _merge_ticket: không có worktree → skip (trả True) ----------

def test_merge_ticket_khong_co_worktree_thi_skip(tmp_path):
    orch = _orch()
    orch.integration = type("FakeIntegration", (), {"sha": lambda self: "abc", "branch": "integration",
                                                      "path": tmp_path / "no-such-dir",
                                                      "ensure": lambda self: None})()
    res = StepResult("e1", "release-candidates", "R1")
    ok = orch._merge_ticket("T-none", res, release_id="R1")
    assert ok is True
    skipped = [e.payload for e in orch.bus.replay(topic="audit-log") if e.payload["action"] == "integration.skipped"]
    assert skipped and skipped[0]["ticket_id"] == "T-none"


# ---------- _merge_ticket: merge ok nhưng sha không đổi → noop (trả True) ----------

def test_merge_ticket_noop_khi_sha_khong_doi(tmp_path, monkeypatch):
    orch = _orch()

    class FakeWs:
        path = tmp_path
        branch = "ticket/T1"

        def __init__(self):
            self.path.mkdir(exist_ok=True)

    FakeWs()

    class FakeMerge:
        ok = True
        sha = "same-sha"
        conflicts = None

    class FakeIntegration:
        branch = "integration"

        def sha(self):
            return "same-sha"

        def merge(self, branch, msg):
            return FakeMerge()

    orch.integration = FakeIntegration()
    monkeypatch.setattr(orch, "workspace", lambda tid: FakeWs())
    res = StepResult("e1", "release-candidates", "R1")
    ok = orch._merge_ticket("T1", res, release_id="R1")
    assert ok is True and "integration_noop:T1" in res.actions
    noop = [e.payload for e in orch.bus.replay(topic="audit-log") if e.payload["action"] == "integration.noop"]
    assert noop


# ---------- _merge_ticket: xung đột → ws.fresh()/lead.request_changes lỗi (ValueError/WorkspaceError) ----------

def test_merge_ticket_conflict_va_fresh_loi(tmp_path, monkeypatch):
    orch = _orch()

    class FakeWs:
        path = tmp_path
        branch = "ticket/T1"

        def fresh(self):
            raise WorkspaceError("không dọn được worktree")

    class FakeMerge:
        ok = False
        sha = None
        conflicts = ["f.py"]

    class FakeIntegration:
        branch = "integration"

        def sha(self):
            return "before-sha"

        def merge(self, branch, msg):
            return FakeMerge()

    orch.integration = FakeIntegration()
    monkeypatch.setattr(orch, "workspace", lambda tid: FakeWs())
    res = StepResult("e1", "release-candidates", "R1")
    ok = orch._merge_ticket("T1", res, release_id="R1")
    assert ok is False and "conflict:T1" in res.actions
    errs = [json.loads(e.payload["evidence"]) for e in orch.bus.replay(topic="audit-log") if e.payload["action"] == "handler_error"]
    assert errs and "không dọn được worktree" in errs[0]["error"]


# ---------- _integrate: RC huỷ vì merge thất bại ----------

def test_integrate_huy_khi_merge_that_bai(monkeypatch):
    orch = _orch()
    orch.integration = type("FI", (), {})()  # chỉ cần không phải None
    orch.lead.tickets["T1"] = Task.model_validate(T1)
    orch.lead.state["T1"] = "approved"
    monkeypatch.setattr(orch, "_merge_ticket", lambda tid, res, release_id=None: False)
    rc = Envelope(topic="release-candidates", key="R1", actor="release-engineer",
                  payload={"release_id": "R1", "tickets": ["T1"]})
    res = StepResult("e1", "release-candidates", "R1")
    ok = orch._integrate(rc, res)
    assert ok is False and "R1" in orch.void_releases
    voided = [e.payload for e in orch.bus.replay(topic="audit-log") if e.payload["action"] == "release.void"]
    assert voided and voided[-1]["ticket_id"] == "T1"


# ---------- _read_only_tools: không xác định được ticket/release → None ----------

def test_read_only_tools_tra_none_khi_khong_xac_dinh_duoc(tmp_path):
    orch = _orch()
    orch.repo = tmp_path
    orch.integration = type("FI", (), {"path": tmp_path})()
    env = Envelope(topic="release-events", key="R1", actor="release-engineer", payload={})
    assert orch._read_only_tools(env) is None


# ---------- _threat_model: TransientError không chặn plan ----------

def test_threat_model_transient_khong_chan_plan(monkeypatch):
    orch = _orch()

    def boom(*a, **k):
        raise TransientError("mạng chập chờn")

    monkeypatch.setattr(orch.runner, "generate", boom)
    env = Envelope(topic="approved-specs", key="P1", actor="spec-writer", payload={"project_id": "P1"})
    res = StepResult("e1", "approved-specs", "P1")
    ok = orch._threat_model(env, "SPEC-P1", res)
    assert ok is True and any(a.startswith("transient:security-engineer") for a in res.actions)
    assert orch.stats["transient"] >= 1


# ---------- _threat_model: RunnerError/LLMError → không chặn nhưng đánh dấu missing_threat_model ----------

def test_threat_model_loi_danh_dau_missing(monkeypatch):
    orch = _orch()

    def boom(*a, **k):
        raise LLMError("model lỗi")

    monkeypatch.setattr(orch.runner, "generate", boom)
    env = Envelope(topic="approved-specs", key="P1", actor="spec-writer", payload={"project_id": "P1"})
    res = StepResult("e1", "approved-specs", "P1")
    ok = orch._threat_model(env, "SPEC-P1", res)
    assert ok is True and "SPEC-P1" in orch.missing_threat_model
    missing = [json.loads(e.payload["evidence"]) for e in orch.bus.replay(topic="audit-log") if e.payload["action"] == "threat_model.missing"]
    assert missing and missing[0]["subject_id"] == "SPEC-P1"


# ---------- _on_gate_decide: approve plan nhưng _dispatch_plan lỗi (depends_on vòng/chưa biết) ----------

def test_on_gate_decide_loi_dispatch_plan(monkeypatch):
    bus = InMemoryBus()
    orch = _orch(bus)
    plan_id = "PLAN-P1-1"
    orch.plans[plan_id] = {"tickets": [{**T1, "ticket_id": "TX", "depends_on": ["KHONG-CO"]}]}
    orch.gate.request(GateRequest(kind="plan", subject_id=plan_id, created_by="delivery-lead", checklist=[]))
    orch.gate.decide(plan_id, "approve", by="human:pm")
    env = Envelope(topic="audit-log", key=plan_id, actor="human:pm",
                    payload={"actor": "human:pm", "action": "gate.decide",
                             "evidence": json.dumps({"subject_id": plan_id, "decision": "approve", "by": "human:pm"})})
    res = StepResult(env.event_id, env.topic, env.key)
    out = orch._on_gate_decide(env, res)
    assert any(a.startswith("error:") for a in out.actions)
    err = [json.loads(e.payload["evidence"]) for e in bus.replay(topic="audit-log") if e.payload["action"] == "plan_dispatch_error"]
    assert err and err[0]["plan_id"] == plan_id


# ---------- _close_acceptance_gate: gate.decide lỗi (KeyError/PermissionError) ----------

def test_close_acceptance_gate_bat_loi_gate_decide(monkeypatch):
    orch = _orch()
    rid = "R1"; sid = f"UAT-{rid}"
    orch.gate.request(GateRequest(kind="acceptance", subject_id=sid, created_by="account-manager", checklist=[]))

    def boom(*a, **k):
        raise PermissionError("người ký trùng account-manager")

    monkeypatch.setattr(orch.gate, "decide", boom)
    env = Envelope(topic="acceptance-results", key=rid, actor="account-manager",
                    payload={"release_id": rid, "verdict": "accepted", "signed_by": "account-manager"})
    res = StepResult("e1", "acceptance-results", rid)
    orch._close_acceptance_gate(env, res)
    errs = [json.loads(e.payload["evidence"]) for e in orch.bus.replay(topic="audit-log") if e.payload["action"] == "handler_error"]
    assert errs and "người ký trùng" in errs[0]["error"]
