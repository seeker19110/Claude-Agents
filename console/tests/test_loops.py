"""4L-5: `collect()["loops"]` — console đọc `company.metrics.collect()["loops"]` nguyên vẹn.

ADR-0003: ô "vòng tool" KHÔNG BAO GIỜ hiện như đang tốt (`ok`/xanh) khi `empty=True`, dù các số khác — vd
`capped_ratio` mặc định về 0/None — trông "đẹp". Đây đúng bẫy "số xanh vì rỗng" (console/TRAPS.md).
"""
from __future__ import annotations

import json
from pathlib import Path

from company.events import AuditLog as CompanyAudit
from company.events import Envelope as CompanyEnvelope
from company.events import Task
from company.sqlite_bus import SQLiteBus as CompanySQLiteBus

from console.collect import collect

DEAD_GATEWAY = "http://127.0.0.1:9"


def _audit(bus, actor: str, action: str, evidence: dict, **kw: object) -> None:
    bus.publish(CompanyEnvelope(topic="audit-log", key=actor, actor=actor,
                                payload=CompanyAudit(actor=actor, action=action,
                                                     evidence=json.dumps(evidence, ensure_ascii=False), **kw).model_dump()))


def _tools_used_db(path: Path) -> Path:
    bus = CompanySQLiteBus(path)
    task = Task(ticket_id="TCK-1", project_id="P1", requirement_id="R1", assignee="builder", title="x",
               acceptance=["ok"], estimate_tokens=1_000, budget_tokens=2_000)
    bus.publish(CompanyEnvelope(topic="tasks", key="TCK-1", actor="delivery-lead", payload=task.model_dump()))
    for turns, capped in ((3, False), (5, False), (25, True), (25, True)):
        _audit(bus, "builder", "tools_used",
              {"turns": turns, "mode": "loop", "calls": {"read_file": 1}, "capped": capped, "max_turns": 25},
              ticket_id="TCK-1")
    _audit(bus, "orchestrator", "ticket.blocked", {"ticket_id": "TCK-1"})
    bus.close()
    return path


def test_loops_khong_co_tools_used_la_empty(company_db: Path) -> None:
    """`company_db` (conftest) không ghi audit `tools_used` nào — `loops` phải là `empty=True`, không phải xanh giả."""
    s = collect(company_db, None, gateway_url=DEAD_GATEWAY)
    assert s["loops"]["empty"] is True and s["loops"]["n"] == 0
    for k in ("turns_p50", "turns_p90", "turns_max", "capped_ratio", "no_progress_ratio", "retry_max_ratio"):
        assert s["loops"][k] is None, f"{k} phải là None khi empty, không phải 0 giả"


def test_loops_khong_co_db_la_empty(tmp_path: Path) -> None:
    s = collect(tmp_path / "khong-co.sqlite", None, gateway_url=DEAD_GATEWAY)
    assert s["loops"]["empty"] is True and s["loops"]["n"] == 0


def test_loops_doc_dung_tu_company_metrics(tmp_path: Path) -> None:
    db = _tools_used_db(tmp_path / "company.sqlite")
    s = collect(db, None, gateway_url=DEAD_GATEWAY)
    lp = s["loops"]
    assert lp["empty"] is False and lp["n"] == 4
    assert lp["turns_p50"] == 15 and lp["turns_max"] == 25
    assert lp["capped_ratio"] == 0.5
    assert lp["retry_max_ratio"] == 1.0  # ticket TCK-1 duy nhất có task, và bị blocked


def test_loops_co_mat_ca_khi_xuong_hong(tmp_path: Path) -> None:
    bad = tmp_path / "hong.sqlite"; bad.write_bytes(b"khong phai sqlite")
    s = collect(bad, None, gateway_url=DEAD_GATEWAY)
    assert s["loops"]["empty"] is True and "loops" in s
