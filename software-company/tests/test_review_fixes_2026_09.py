"""Rà soát 2026-09-04: rò rỉ blackboard giữa dự án khi event không mang project_id, merge tích hợp phải chạy một mình."""
from __future__ import annotations

import threading
import time

from company.bus import InMemoryBus
from company.llm import FakeClient
from company.orchestrator import Orchestrator
from company.workspace import Integration, MergeResult
from test_orchestrator import _agent_of, _drive_to_plan, _inp, handler
from test_tools_and_agentic import _init_repo, _repo_tool_handler


def test_threat_model_ghi_o_luot_review_pr_nam_trong_du_an_cua_ticket():
    """pull-requests không mang project_id: trước đây write_context/publish nhận env gốc nên threat-model của
    security-engineer rơi vào ô toàn cục (hiện ở mọi dự án) và audit produced:* không có project_id."""
    def h(system, user):
        a, p = _agent_of(system), _inp(user)
        if a == "security-engineer" and "ticket_id" in p and "artifacts" not in p:
            return {"payload": {"ticket_id": p["ticket_id"], "source": "security", "verdict": "pass"},
                    "context_writes": [{"namespace": "threat-model", "content_ref": "docs/tm.md", "summary": "PR", "content": "# TM từ PR"}]}
        return handler(system, user)
    bus = InMemoryBus(); orch = Orchestrator(bus, FakeClient(handler=h))
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    assert orch.lead.state["T2"] in {"approved", "merged", "in_review"}, orch.lead.state
    assert orch.blackboard.content("threat-model", "P1") == "# TM từ PR", "ghi vào đúng phân vùng dự án"
    assert orch.blackboard.read("threat-model", None) is None, "không rơi vào ô toàn cục"
    assert not any(e.payload.get("project_id") is None for e in bus.replay(topic="audit-log")
                   if e.payload.get("action") == "produced:review-results"), "audit lượt review mang project_id"
    assert orch.supervisor.project_cost.get("P1", 0) >= 0  # cộng dồn theo dự án không còn bỏ sót lượt review


def test_merge_tich_hop_khong_chay_dong_thoi(tmp_path, monkeypatch):
    """Hai thread cùng thấy một ticket approved chưa merge: chỉ một merge, merge kia thấy `integrated` và bỏ qua."""
    repo = _init_repo(tmp_path / "repo")
    bus = InMemoryBus(); client = FakeClient(handler=handler, tool_handler=_repo_tool_handler)
    orch = Orchestrator(bus, client, repo=repo, base="main")
    _drive_to_plan(bus, orch); orch.gate.decide("PLAN-P1-1", "approve", by="human:pm")
    # chạy tới lúc T1 approved nhưng chưa merge: chặn _integrate_approved trong run()
    monkeypatch.setattr(orch, "_integrate_approved", lambda res: None)
    for _ in range(50):
        if orch.lead.state.get("T1") == "approved": break
        orch.run(max_steps=1)
    assert orch.lead.state["T1"] == "approved" and "T1" not in orch.integrated
    monkeypatch.undo()
    real_merge = Integration.merge; active, peak, calls = [0], [0], [0]
    gate = threading.Barrier(2, timeout=5)
    def slow_merge(self, branch, message):
        calls[0] += 1; active[0] += 1; peak[0] = max(peak[0], active[0])
        try:
            time.sleep(0.05)
            return real_merge(self, branch, message)
        finally: active[0] -= 1
    monkeypatch.setattr(Integration, "merge", slow_merge)
    from company.orchestrator import StepResult
    def worker():
        gate.wait(); orch._integrate_approved(StepResult("x", "tasks", "T1"))
    ts = [threading.Thread(target=worker) for _ in range(2)]
    for t in ts: t.start()
    for t in ts: t.join()
    assert calls[0] == 1 and peak[0] == 1, (calls, peak)
    assert "T1" in orch.integrated
    assert isinstance(real_merge(orch.integration, "company/integration", "noop"), MergeResult)
