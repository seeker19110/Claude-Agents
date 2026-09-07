"""ADR-0033 (B6): "định nghĩa xong" phải gồm sản phẩm chạy được, và ticket frontend phải đính ảnh chụp giao diện.

Vì sao có file này. ADR-0029 và ADR-0031 vá cơ chế và đầu vào bằng CODE, nhưng "xong" trong đầu ba agent điều phối
vẫn là *xong tài liệu*: QLKH có 14/14 ticket đạt DoD của delivery-lead mà không có một lệnh khởi động nào
(`docs/reports/2026-09-06-ban-giao-khong-chay-duoc.md`). Prompt là code (ADR-0004) nên dòng DoD được canh như code.

Đo hai chiều (chạy 2026-09-06):
* Xoá dòng DoD ở BẤT KỲ agent nào trong ba agent → `test_ba_agent_dieu_phoi_doi_san_pham_chay_duoc` ĐỎ.
* Xoá đoạn ảnh chụp ở `frontend` → `test_frontend_doi_anh_chup_va_bat_noi_ra_khi_khong_chup_duoc` ĐỎ.
* Bỏ `evidence` khỏi `topics/schemas/pull-requests.json` → `test_evidence_screenshots_co_trong_schema_va_model` ĐỎ.
* Bỏ `evidence` khỏi `PullRequest` → cùng test ĐỎ (model thiếu trường thì payload rơi lại `additionalProperties`).
"""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from company.bus import SCHEMA_DIR, BusError, InMemoryBus
from company.events import Envelope, PullRequest
from company.registry import load_agents

# Nội dung là MỘT, diễn đạt khác nhau theo văn phong từng vai (ADR-0033 mục 1). Test canh phần nội dung.
DOD_CHUNG = "khởi động bằng một lệnh ghi trong README và trả lời một request thật"
# ADR-0037 PR-5b: `release-engineer` và `account-manager` gộp vào `ops` (pha `deploy`/`account`) — mỗi pha vẫn
# giữ dòng DoD riêng dưới `## Definition of done` (một H2 chung, nhiều H3 theo pha), nên soát cả prompt của
# `ops` vẫn thấy đủ hai câu như trước, chỉ còn hai định danh thay vì ba.
DIEU_PHOI = ("delivery-lead", "ops")


@pytest.fixture(scope="module")
def agents() -> dict:
    return load_agents()


@pytest.mark.parametrize("agent_id", DIEU_PHOI)
def test_ba_agent_dieu_phoi_doi_san_pham_chay_duoc(agents, agent_id):
    """Ba vai quyết định "xong" ở ba mốc khác nhau (kế hoạch, release, nghiệm thu) phải đòi cùng một thứ —
    không thì mốc nào lỏng nhất sẽ là mốc quyết định."""
    a = agents[agent_id]
    dod = a.prompt.split("## Definition of done", 1)
    assert len(dod) == 2, f"{agent_id}: prompt phải có mục Definition of done"
    dod = dod[1].split("\n## ", 1)[0]
    assert DOD_CHUNG in dod, f"{agent_id}: DoD phải đòi sản phẩm chạy được (ADR-0033)"
    assert "ADR-0033" in dod, f"{agent_id}: DoD phải dẫn ADR-0033 để người sau tìm được lý do"


def test_ba_agent_dung_mot_cau_khong_ba_cau_khac_nghia(agents):
    """Bẫy đã thấy ở nơi khác: cùng một luật viết ba lần thành ba luật. Canh đúng chuỗi chung."""
    assert all(DOD_CHUNG in agents[i].prompt for i in DIEU_PHOI)


def test_frontend_doi_anh_chup_va_bat_noi_ra_khi_khong_chup_duoc(agents):
    """Hai nửa, nửa sau quan trọng hơn: công ty KHÔNG có tool chụp ảnh (ADR-0033 mục 3 bác playwright), nên
    prompt phải dặn agent NÓI RA khi không chụp được — `TRAPS.md` §2 "ép agent làm việc nó không có tool":
    agent thiếu năng lực thì lặng lẽ sửa việc khác, bốn vòng rework không ai biết."""
    # ADR-0037 PR-5d: `frontend` là một PHA của `builder`, DoD của nó là tiểu mục `### Stack frontend`
    dod = agents["builder"].prompt.split("## Definition of done", 1)[1].split("\n## ", 1)[0]
    dod = dod.split("### Stack frontend", 1)[1].split("\n### ", 1)[0]
    assert "evidence.screenshots[]" in dod, "frontend: ảnh chụp phải vào evidence.screenshots[] của pull-requests"
    assert "ADR-0033" in dod
    assert "skipped" in dod and "reason" in dod, "frontend: không chụp được thì phải trả mục skipped kèm lý do"
    assert "KHÔNG có tool chụp ảnh" in dod, "frontend: phải nói thẳng công ty không có tool chụp, đừng để agent đoán"


def test_evidence_screenshots_co_trong_schema_va_model():
    """`topics/schemas/*.json` là nguồn sự thật của topic (ADR-0014); model Pydantic phải khai cùng trường,
    nếu không `evidence` chỉ lọt nhờ `additionalProperties` và không ai đọc được hình dạng của nó."""
    schema = json.loads((SCHEMA_DIR / "pull-requests.json").read_text(encoding="utf-8"))
    ev = schema["properties"]["payload"]["properties"]["evidence"]
    item = ev["properties"]["screenshots"]["items"]
    assert ev["type"] == "object" and "ADR-0033" in ev["description"]
    assert item["required"] == ["screen"], "mỗi mục phải nói nó là màn hình nào, kể cả mục skipped"
    assert {"path", "screen", "state", "how", "skipped", "reason"} <= set(item["properties"])
    assert "evidence" in PullRequest.model_fields
    assert PullRequest(ticket_id="T", branch="b", pr_ref="p", local_checks={}).evidence == {}, "PR cũ vẫn hợp lệ"


def _pr(evidence: dict) -> Envelope:
    return Envelope(topic="pull-requests", key="T-1", actor="builder",
                    payload={"ticket_id": "T-1", "branch": "ticket/T-1", "pr_ref": "PR-1",
                             "local_checks": {"lint": True, "tests": True, "verified_by": "workspace"},
                             "evidence": evidence})


def test_bus_nhan_anh_chup_va_nhan_ca_muc_skipped():
    """Hai trạng thái hợp lệ, khác nghĩa: đã chụp, và không chụp được nhưng nói ra."""
    bus = InMemoryBus()
    bus.publish(_pr({"screenshots": [{"screen": "/login", "state": "error",
                                      "path": "docs/screenshots/T-1-login.png", "how": "npm run screenshots"}]}))
    bus.publish(_pr({"screenshots": [{"screen": "/login", "state": "success", "skipped": True,
                                      "reason": "spec không khai lệnh chụp trong runtime"}]}))
    assert len(list(bus.replay("pull-requests"))) == 2


def test_bus_tu_choi_muc_anh_khong_noi_la_man_hinh_nao():
    """Mục thiếu `screen` = bằng chứng không gắn được vào cái gì; JSON Schema chặn ở biên bus, không phải ở prompt."""
    with pytest.raises(BusError, match="JSON Schema"):
        InMemoryBus().publish(_pr({"screenshots": [{"path": "a.png"}]}))


def test_evidence_phai_la_object():
    with pytest.raises(ValidationError):
        PullRequest(ticket_id="T", branch="b", pr_ref="p", local_checks={}, evidence="có ảnh")
