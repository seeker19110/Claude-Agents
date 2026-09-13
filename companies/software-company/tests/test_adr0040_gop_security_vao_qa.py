"""ADR-0040: `security` gộp vào `qa` thành pha thứ ba.

Hai nhóm test, cố ý tách:
- **Gộp** — cái ADR này ĐỔI: không còn agent `security`, định tuyến trỏ về `qa`.
- **Bằng chứng** — cái ADR này THỀ KHÔNG ĐỔI (§3). Ranh giới agent gộp được, ranh giới bằng chứng thì không:
  ticket rủi ro vẫn phải có một dòng review nhãn `security` từ một lượt gọi model riêng. Nhóm này là lưới an
  toàn: gộp tiếp tay vào đây là đỏ.
"""
from __future__ import annotations

from typing import get_args

from company.bus import InMemoryBus
from company.core import REVIEW_PRODUCERS
from company.delivery import DeliveryLead
from company.events import NAMESPACE_OWNERS, Task
from company.orch.routes import REVIEW_AGENT
from company.registry import load_agents
from company.roles import ROLE, SOURCE, ReviewSource

# --- Gộp ------------------------------------------------------------------

def test_khong_con_agent_security() -> None:
    agents = load_agents()
    assert "security" not in agents, "ADR-0040: `security` gộp vào `qa`"
    assert set(agents) == {"product", "builder", "qa", "ops", "supervisor"}


def test_role_security_bi_xoa() -> None:
    assert not hasattr(ROLE, "SECURITY"), "ADR-0040: `ROLE.SECURITY` không còn; id cũ vào MIGRATED"


def test_qa_co_pha_security() -> None:
    qa = load_agents()["qa"]
    assert set(qa.phases) == {"author", "review", "security"}


def test_qa_doc_duoc_topic_cua_security() -> None:
    """Pha `security` chạy trên 3 lượt: threat model (approved-specs), PR rủi ro, release-candidates."""
    qa = load_agents()["qa"]
    assert {"approved-specs", "release-candidates"} <= set(qa.reads)


def test_qa_giu_namespace_threat_model() -> None:
    assert NAMESPACE_OWNERS["threat-model"] == {ROLE.QA}


def test_qa_len_tier_strong() -> None:
    """`Phase` không có `model_tier` riêng (ADR-0040 §4) nên cả agent phải lên `strong`."""
    assert load_agents()["qa"].model_tier == "strong"


def test_dinh_tuyen_review_security_ve_qa() -> None:
    assert REVIEW_AGENT[SOURCE.SECURITY] == ROLE.QA


# --- Bằng chứng: KHÔNG được đổi (ADR-0040 §3) -----------------------------

def test_source_security_van_con() -> None:
    assert SOURCE.SECURITY == "security"
    assert "security" in get_args(ReviewSource), "gộp AGENT, không gộp NHÃN bằng chứng"


def test_risk_reviews_van_doi_nhan_security() -> None:
    assert DeliveryLead.RISK_REVIEWS == frozenset({SOURCE.SECURITY})


def test_ticket_rui_ro_van_cho_du_hai_dong_review() -> None:
    """Lượt gọi model KHÔNG giảm: ticket có risk_tags vẫn chờ cả `reviewer` lẫn `security`, dù nay cùng
    một agent `qa` phát cả hai (khác pha)."""
    lead = DeliveryLead(InMemoryBus(), None)
    lead.tickets["T1"] = Task(ticket_id="T1", project_id="P", requirement_id="R1", assignee=ROLE.BUILDER,
                              title="x", acceptance=["a"], risk_tags=["auth"])
    assert lead.required_reviews("T1") == {SOURCE.REVIEWER, SOURCE.SECURITY}


def test_qa_van_la_producer_hop_le_cua_review_results() -> None:
    assert ROLE.QA in REVIEW_PRODUCERS and SOURCE.SECURITY in REVIEW_PRODUCERS

