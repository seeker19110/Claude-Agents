"""ADR-0037 PR-5e: chuỗi nghiên cứu là MỘT agent (`product`) chạy bốn pha, không phải bảy agent nối nhau.

Bất biến đo ở đây — thứ mà việc gộp bảy vai có thể làm hỏng mà không test cũ nào thấy:

1. **Đúng năm lượt, đúng thứ tự pha.** Cùng một `actor="product"` trên cả chuỗi, nên nếu guard sai thì hệ hoặc
   chạy thiếu lượt (dự án đứng im), hoặc chạy thừa/lặp (đốt token, hai bản draft cho một key) — cả hai đều
   không làm hỏng schema nào, tức là im lặng. Đếm lượt + đọc `phase` trong `audit-log` là cách duy nhất thấy.
2. **Guard theo pha đọc `_phase` do RUNNER ghi**, không phải actor và không phải lời khai của model: một
   `requirements-draft` không rõ pha (event của dự án cũ, trước PR-3) KHÔNG được kéo theo một lượt hỏi.

Chuỗi đích (§1.2): research-requests → [intake] research-findings → [research] research-findings →
[spec] requirements-draft (đã kèm `risks`) → [intake] clarification-questions → (người trả lời) →
[spec] approved-specs. Lượt `risk` riêng của bản cũ đã bị bỏ — đó là lý do con số là 5 chứ không phải 6.
"""
from __future__ import annotations

import pytest

import company.orchestrator as orch_mod
from company.bus import InMemoryBus
from company.events import Envelope
from company.llm import FakeClient
from company.orch import routes as routes_mod
from company.orchestrator import ROUTES, Orchestrator
from test_orchestrator import _agent_of, _product_phase, _pub, handler

CHUOI = ["intake", "research", "spec", "intake", "spec"]


def _phases_trong_audit(bus: InMemoryBus) -> list[str]:
    """Pha của từng lượt `product` theo sổ audit — nguồn sự thật do code ghi, không phải suy từ topic."""
    return [e.payload["phase"] for e in bus.replay(topic="audit-log")
            if e.payload["actor"] == "product" and e.payload["action"].startswith("produced:")]


def _chay_het_chuoi(bus: InMemoryBus, orch: Orchestrator) -> None:
    _pub(bus, "research-requests", "P1", "human:sales", {"project_id": "P1", "description": "app đặt lịch khám"})
    orch.run()
    _pub(bus, "clarification-answers", "P1", "human:po", {"project_id": "P1", "answers": [{"question_id": "Q1", "answer": "a"}]})
    orch.run()


def test_chuoi_research_di_dung_5_luot_theo_pha():
    bus = InMemoryBus()
    client = FakeClient(handler=handler)
    orch = Orchestrator(bus, client)
    _chay_het_chuoi(bus, orch)

    luot = [c for c in client.calls if _agent_of(c["system"]) == "product"]
    assert [_product_phase(c["system"]) for c in luot] == CHUOI, "đúng 5 lượt product, đúng thứ tự pha"
    assert _phases_trong_audit(bus) == CHUOI, "sổ audit phải ghi lại đúng thứ tự đó"
    topics = [e.topic for e in bus.replay() if e.topic not in {"audit-log", "shared-context"}]
    assert topics[:6] == ["research-requests", "research-findings", "research-findings", "requirements-draft",
                          "clarification-questions", "clarification-answers"]
    assert topics[6] == "approved-specs" and "SPEC-P1" in orch.gate.pending
    # Lượt `risk` riêng đã bỏ: đúng MỘT bản draft cho dự án, và nó phải tự mang `risks`.
    drafts = list(bus.replay(topic="requirements-draft"))
    assert len(drafts) == 1 and drafts[0].payload["risks"], "rủi ro nằm ngay trong draft, không phải một lượt sau"
    assert {e.actor for e in bus.replay(topic="requirements-draft")} == {"product"}


def test_guard_from_phase_bo_qua_draft_khong_ro_pha(monkeypatch):
    """Chiều đảo của guard `_from_phase("spec")`, đo bằng một event KHÔNG có `_phase` (bus của dự án cũ).

    Bật guard: draft ấy không kéo theo lượt hỏi nào. Tắt guard (`when=None`, đúng hình dạng bảng route trước khi
    có pha): cùng event ấy sinh `clarification-questions` — chứng minh test đo đúng dòng guard chứ không đo
    một thứ khác tình cờ đúng.
    """
    def _chay(routes) -> list[Envelope]:
        bus = InMemoryBus()
        # `orchestrator` nhập `ROUTES` theo TÊN (`from .orch.routes import ROUTES`) nên vòng lặp trong
        # `process()` đọc biến của module `orchestrator`, không phải của `orch.routes` — vá cả hai chỗ, nếu
        # không thì "tắt guard" chỉ là vá một bản sao không ai dùng và chiều đảo xanh giả.
        monkeypatch.setattr(routes_mod, "ROUTES", routes)
        monkeypatch.setattr(orch_mod, "ROUTES", routes)
        orch = Orchestrator(bus, FakeClient(handler=handler))
        bus.publish(Envelope(topic="requirements-draft", key="P1", actor="product",
                             payload={"project_id": "P1", "kind": "draft", "requirements": [], "risks": []}))
        orch.run()
        return list(bus.replay(topic="clarification-questions"))

    i = next(i for i, r in enumerate(ROUTES)
             if r.topic_in == "requirements-draft" and r.topic_out == "clarification-questions")
    assert _chay(ROUTES) == [], "draft không rõ pha thì không ai bị đánh thức"
    khong_guard = (*ROUTES[:i], routes_mod.replace(ROUTES[i], when=None), *ROUTES[i + 1:])
    assert len(_chay(khong_guard)) == 1, "tắt guard thì chính event ấy sinh câu hỏi — test đo đúng dòng đó"


@pytest.mark.parametrize("pha", CHUOI)
def test_moi_pha_cua_chuoi_deu_co_trong_front_matter(pha):
    """`check_routes` kiểm điều này lúc khởi động; giữ thêm ở đây để tên pha trong test trên không tự trôi."""
    assert pha in Orchestrator(InMemoryBus(), FakeClient()).agents["product"].phases
