"""`company.gate_brief` — hồ sơ bằng chứng cho nửa "người tự kiểm thêm" của gate (đặc tả §5, §8.2).

Bất biến kiểm ở đây: chỉ đọc (I3), kind suy từ replay chứ không tham số hoá, không có giá trị nào mang nghĩa
quyết định (I6: verdict ∈ {ok, gap, unknown}), trích tối đa 200 ký tự mỗi nguồn (§7), và schema JSON ổn định
(golden theo kind, cập nhật bằng UPDATE_GOLDEN=1).
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from company import gate_brief as GB
from company.events import Envelope
from company.llm import FakeClient, LLMError
from company.orchestrator import ENGINEERING, Orchestrator
from company.sqlite_bus import SQLiteBus
from test_orchestrator import _agent_of, _drive_to_plan, _pub, handler
from test_tools_and_agentic import _init_repo, _repo_tool_handler

GOLDEN = Path(__file__).parent / "golden" / "gate_brief"
UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"

PRD = """# PRD P1
## Yêu cầu
- REQ-1 GET /orders trả danh sách đơn
- REQ-2 POST /payments nhận email và số điện thoại khách
## NFR
- p95 < 300 ms cho GET /orders
- sẵn sàng 99.9 %
- mô tả không có số
## Ngoài phạm vi
- Không làm app mobile
"""
C4 = "# C4\nThư viện: fastapi (MIT license), dịch vụ ngoài: cổng thanh toán VNPay\n"
CONTRACT = "openapi: 3.0.0\npaths:\n  /orders:\n    get: {}\n  /payments:\n    post: {}\n"
THREAT = "# Threat model\nPhân loại dữ liệu: PII mức 2; DPIA: cần\n"


def rich_handler(system: str, user: str) -> dict:
    """`handler` của test_orchestrator + TOÀN VĂN artifact để hồ sơ có gì mà rút."""
    out = handler(system, user); a = _agent_of(system)
    if a == "spec-writer": out["context_writes"][0]["content"] = PRD
    elif a == "delivery-lead" and "items" in out:
        out["context_writes"][0]["content"] = C4; out["context_writes"][1]["content"] = CONTRACT
    elif a == "security-engineer" and "context_writes" in out: out["context_writes"][0]["content"] = THREAT
    return out


def fail_handler(system: str, user: str) -> dict:
    """Khối kỹ thuật trả đầu ra sai schema mãi → retry tới blocked → gate escalation."""
    if _agent_of(system) in ENGINEERING: return {"ticket_id": "T1", "nonsense": True}
    return rich_handler(system, user)


def stall_handler(system: str, user: str) -> dict:
    if _agent_of(system) == "intake": raise LLMError("intake nổ")
    return rich_handler(system, user)


def _scenario(tmp_path: Path, h=rich_handler, *, to: str = "acceptance", repo: Path | None = None):
    db = tmp_path / "c.sqlite"; bus = SQLiteBus(db)
    client = FakeClient(handler=h, tool_handler=_repo_tool_handler if repo else None)
    orch = Orchestrator(bus, client, repo=repo, base="main" if repo else "HEAD")
    if to == "stalled":
        _pub(bus, "research-requests", "P1", "human:sales", {"project_id": "P1", "description": "app"}); orch.run()
        return db, bus, orch
    _drive_to_plan(bus, orch)
    if to == "plan": return db, bus, orch
    orch.gate.decide("PLAN-P1-1", "approve", by="human:pm"); orch.run()
    if to in {"release", "escalation"}: return db, bus, orch
    orch.gate.decide("REL-001", "approve", by="human:release-manager"); orch.run()
    return db, bus, orch


def _rows(db: Path) -> int:
    con = sqlite3.connect(db)
    try: return con.execute("SELECT count(*) FROM events").fetchone()[0]
    finally: con.close()


def _norm(b: dict) -> dict:
    """Bỏ phần phụ thuộc thời gian/đường dẫn/event_id ngẫu nhiên để so golden theo cấu trúc và sự việc."""
    b = json.loads(json.dumps(b, ensure_ascii=False))
    for k in ("created_at", "age_hours", "due"): b.pop(k)
    def walk(x):
        if isinstance(x, dict):
            for k in list(x):
                if k == "event_ids": x[k] = len(x[k])
                elif k in {"at", "path", "diff_stat"} and x[k] is not None: x[k] = "<…>"
                else: walk(x[k])
        elif isinstance(x, list):
            for i in x: walk(i)
    walk(b); return b


def _check_golden(kind: str, b: dict) -> None:
    got = json.dumps(_norm(b), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    f = GOLDEN / f"{kind}.json"
    if UPDATE: f.write_text(got, encoding="utf-8", newline="\n"); return
    assert f.exists(), f"thiếu golden {f}: chạy UPDATE_GOLDEN=1"
    assert f.read_text(encoding="utf-8") == got, f"schema/sự việc hồ sơ {kind} đổi — cố ý thì UPDATE_GOLDEN=1"


def _verdicts(b: dict) -> dict[str, str]:
    return {it["id"]: it["verdict"] for it in b["self_check"]}


# ---------- I3: chỉ đọc ----------

def test_chi_doc(tmp_path):
    db, bus, _orch = _scenario(tmp_path)
    n_rows, n_bus = _rows(db), len(bus)
    orch2 = GB.load_state(db)
    for sid in ("REL-002", "UAT-REL-001"):
        GB.build(orch2, sid)
    assert GB.main(["--all", "--db", str(db), "--out", str(tmp_path / "out")]) == 0
    assert _rows(db) == n_rows and len(orch2.bus) == n_bus and len(bus) == n_bus, "hồ sơ không được ghi bus"
    assert bus.poll() == [], "không có event nào do tiến trình khác ghi thêm"
    assert (tmp_path / "out" / "REL-002.json").exists() and (tmp_path / "out" / "UAT-REL-001.md").exists()


def test_khong_co_db_hoac_repo_sai(tmp_path, capsys):
    with pytest.raises(GB.BriefError):
        GB.open_read_only(tmp_path / "khong.sqlite")
    assert GB.main(["X", "--db", str(tmp_path / "khong.sqlite")]) == 3
    db, _, _ = _scenario(tmp_path, to="plan")
    assert GB.main(["PLAN-P1-1", "--db", str(db), "--repo", str(tmp_path / "khong-phai-repo")]) == 3
    assert GB.main(["--db", str(db)]) == 2, "cần subject hoặc --all"


# ---------- kind suy ra từ replay ----------

def test_kind_suy_ra_tu_replay(tmp_path):
    db, _, _ = _scenario(tmp_path)
    orch = GB.load_state(db)
    assert GB.build(orch, "REL-002")["kind"] == "release"
    assert GB.build(orch, "UAT-REL-001")["kind"] == "acceptance"
    spec = GB.build(orch, "SPEC-P1", closed=True)
    assert spec["kind"] == "spec" and spec["status"] == "approve" and spec["project_id"] == "P1"
    plan = GB.build(orch, "PLAN-P1-1", closed=True)
    assert plan["kind"] == "plan" and plan["created_by"] == "delivery-lead"
    for b in (spec, plan):
        assert set(_verdicts(b).values()) <= {"ok", "gap", "unknown"}
        assert b["schema_version"] == 1 and {"self_check", "unavailable", "code_checklist", "extra"} <= set(b)


def test_subject_khong_ton_tai(tmp_path, capsys):
    db, _, _ = _scenario(tmp_path)
    assert GB.main(["KHONG-CO", "--db", str(db)]) == 2
    assert GB.main(["SPEC-P1", "--db", str(db), "--no-write"]) == 2, "gate đã đóng: cần --closed"
    assert GB.main(["KHONG-CO", "--db", str(db), "--closed"]) == 2
    assert "--closed" in capsys.readouterr().err


# ---------- spec ----------

def test_spec_rut_nfr_out_of_scope_pii_va_cau_hoi_mo(tmp_path):
    db, bus, _ = _scenario(tmp_path, to="plan")
    orch = GB.load_state(db)
    b = GB.build(orch, "SPEC-P1", closed=True); v = _verdicts(b); facts = {it["id"]: it["facts"] for it in b["self_check"]}
    assert v["spec.nfr-co-so-do"] == "ok" and "3 dòng, 2 dòng có ngưỡng" in facts["spec.nfr-co-so-do"][0]
    assert v["spec.out-of-scope"] == "ok" and "1 mục" in facts["spec.out-of-scope"][0]
    assert v["spec.pii"] == "unknown" and any("có nhắc phân loại" in f for f in facts["spec.pii"])
    assert v["spec.cau-hoi-mo"] == "ok"
    src = next(it for it in b["self_check"] if it["id"] == "spec.nfr-co-so-do")["sources"][0]
    # So bằng `Path.parts`, không phải `endswith("prd/latest.md")`: đường dẫn mirror do `pathlib` dựng nên trên
    # Windows là `prd\latest.md` — test cũ xanh trên Linux và đỏ trên Windows, đúng kiểu "test đúng-sai theo nền
    # tảng" mà repo đã gặp một lần ở `_bo_dau_thoi_gian` (tests/test_orchestrator.py).
    assert src["kind"] == "namespace" and src["ref"] == "prd"
    assert Path(src["path"]).parts[-2:] == ("prd", "latest.md")
    # thêm một vòng câu hỏi chưa ai trả lời → gap
    bus.publish(Envelope(topic="clarification-questions", key="P1", actor="clarifier",
                         payload={"project_id": "P1", "round": 2, "questions": [{"id": "Q9", "text": "?", "options": ["a"], "default": "a"}]}))
    b2 = GB.build(GB.load_state(db), "SPEC-P1", closed=True)
    assert _verdicts(b2)["spec.cau-hoi-mo"] == "gap" and any("Q9" in f for f in next(it for it in b2["self_check"] if it["id"] == "spec.cau-hoi-mo")["facts"])
    _check_golden("spec", b)


def test_spec_khong_co_toan_van_thi_unknown_va_khong_neu_duong_dan(tmp_path):
    db, _, _ = _scenario(tmp_path, handler, to="plan")  # handler gốc: blackboard chỉ có con trỏ
    b = GB.build(GB.load_state(db), "SPEC-P1", closed=True)
    v = _verdicts(b)
    assert v["spec.nfr-co-so-do"] == "unknown" and v["spec.out-of-scope"] == "unknown"
    src = next(it for it in b["self_check"] if it["id"] == "spec.nfr-co-so-do")["sources"][0]
    assert src["path"] is None and src["content_ref"] == "docs/prd.md"
    assert "chỉ có con trỏ" in GB.render_md(b)


def test_pii_cat_200_ky_tu(tmp_path):
    long_line = "Email khách hàng: " + "a" * 900 + "@x.vn"
    def h(system, user):
        out = rich_handler(system, user)
        if _agent_of(system) == "spec-writer": out["context_writes"][0]["content"] = PRD + "\n" + long_line + "\n"
        return out
    db, _, _ = _scenario(tmp_path, h, to="plan")
    b = GB.build(GB.load_state(db), "SPEC-P1", closed=True)
    for it in b["self_check"]:
        for f in it["facts"]:
            assert len(f) <= GB.EXCERPT + 40, f"fact dài quá: {len(f)}"
    assert GB.excerpt("x" * 500) == "x" * 199 + "…" and GB.excerpt("  a   b ") == "a b" and GB.excerpt(None) == ""


# ---------- plan ----------

def test_plan_uoc_luong_phu_thuoc_ngan_sach(tmp_path):
    db, _, _ = _scenario(tmp_path, to="plan")
    b = GB.build(GB.load_state(db), "PLAN-P1-1")
    v = _verdicts(b); facts = {it["id"]: it["facts"] for it in b["self_check"]}
    assert v["plan.uoc-luong-co-so"] == "unknown" and "2/2 ticket có estimate_tokens" in facts["plan.uoc-luong-co-so"][0]
    assert any("dự án đầu" in f for f in facts["plan.uoc-luong-co-so"])
    assert v["plan.phu-thuoc-ngoai"] == "unknown" and any("fastapi" in f for f in facts["plan.phu-thuoc-ngoai"])
    assert v["plan.ngan-sach-token"] == "unknown" and "tổng estimate 8000" in facts["plan.ngan-sach-token"][0]
    assert [t["ticket_id"] for t in b["extra"]["tickets"]] == ["T1", "T2"]
    _check_golden("plan", b)


def test_plan_gap_khi_budget_vuot_tran_agent_hoac_duoi_estimate(tmp_path):
    def h(system, user):
        out = rich_handler(system, user)
        if _agent_of(system) == "delivery-lead" and "items" in out:
            out["items"] = [{**out["items"][0], "budget_tokens": 10_000_000}, {**out["items"][1]}]
        return out
    db, _, _ = _scenario(tmp_path, h, to="plan")
    b = GB.build(GB.load_state(db), "PLAN-P1-1")
    it = next(x for x in b["self_check"] if x["id"] == "plan.ngan-sach-token")
    assert it["verdict"] == "gap" and any("vượt budget_tokens_per_task" in f for f in it["facts"])


def test_plan_ok_khi_co_bai_hoc_cho_moi_assignee(tmp_path):
    db, _, orch = _scenario(tmp_path)  # đã nghiệm thu? chưa — nghiệm thu là của khách
    _pub(orch.bus, "acceptance-results", "REL-001", "account-manager",
         {"release_id": "REL-001", "project_id": "P1", "verdict": "accepted", "signed_by": "customer:po"})
    orch.run()
    assert orch.supervisor.lessons(), "sau nghiệm thu có bài học estimate-vs-actual"
    b = GB.build(GB.load_state(db), "PLAN-P1-1", closed=True)
    it = next(x for x in b["self_check"] if x["id"] == "plan.uoc-luong-co-so")
    assert it["verdict"] == "ok" and any("backend×" in f for f in it["facts"])


# ---------- release ----------

def test_release_dashboard_doi_chieu_contract_voi_infra(tmp_path):
    db, _, orch = _scenario(tmp_path, to="release")
    b = GB.build(GB.load_state(db), "REL-001")
    it = next(x for x in b["self_check"] if x["id"] == "release.dashboard-alert")
    assert it["verdict"] == "unknown" and "chưa có namespace infra" in it["facts"][0]
    orch.blackboard.write("platform", "infra", "infra/dash.md", content="Dashboard + alert cho /orders, runbook ở docs/", project_id="P1")
    b = GB.build(GB.load_state(db), "REL-001")
    it = next(x for x in b["self_check"] if x["id"] == "release.dashboard-alert")
    assert it["verdict"] == "gap" and any("/payments" in f for f in it["facts"])
    orch.blackboard.write("platform", "infra", "infra/dash.md", content="Dashboard + alert cho /orders và /payments", project_id="P1")
    b = GB.build(GB.load_state(db), "REL-001")
    assert _verdicts(b)["release.dashboard-alert"] == "ok" and _verdicts(b)["release.four-eyes"] == "ok"
    assert {u["id"] for u in b["unavailable"]} == {"release.changelog-docs-notice", "release.error-budget"}
    assert b["extra"]["version"] == "0.1.1" and b["extra"]["tickets"] == ["T1"]
    assert {r["source"] for r in b["extra"]["staging_reviews"]} == {"qa"}
    _check_golden("release", b)


def test_release_voi_repo_doc_diff_nhanh_tich_hop(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    db, _, orch = _scenario(tmp_path, to="release", repo=repo)
    assert "REL-001" in orch.gate.pending
    b = GB.build(GB.load_state(db, repo=repo), "REL-001")
    it = next(x for x in b["self_check"] if x["id"] == "release.changelog-docs-notice")
    assert it["verdict"] == "gap" and "CHANGELOG: không" in it["facts"][1] and it["sources"][0]["kind"] == "worktree"
    assert {u["id"] for u in b["unavailable"]} == {"release.error-budget"}
    assert "file đổi trên company/integration" in it["facts"][0]


def test_endpoints_va_section():
    assert GB._endpoints(CONTRACT) == ["/orders", "/payments"]
    assert GB._endpoints("GET /a\nPOST /b\n/: x\n") == ["/a", "/b"]
    assert GB._section("# A\n## NFR\nx\n## Khác\ny\n", GB._NFR_HEAD) == "\nx\n"
    assert GB._section("# A\n## Khác\ny\n", GB._NFR_HEAD) is None


# ---------- acceptance ----------

def test_acceptance_moi_truong_va_truy_vet(tmp_path):
    db, bus, orch = _scenario(tmp_path)
    b = GB.build(GB.load_state(db), "UAT-REL-001")
    v = _verdicts(b)
    assert v["acceptance.moi-truong"] == "ok" and v["acceptance.truy-vet"] == "unknown"
    _check_golden("acceptance", b)
    orch.blackboard.write("account-manager", "contract", "sow.md", content="UAT chạy trên production với dữ liệu ẩn danh", project_id="P1")
    _pub(bus, "acceptance-results", "REL-001", "account-manager",
         {"release_id": "REL-001", "project_id": "P1", "verdict": "conditional", "signed_by": "customer:po",
          "findings": [{"level": "warn", "text": "thiếu trang tin", "location": None},
                       {"level": "nit", "text": "REQ-9 sai màu", "location": "REQ-9"}]})
    orch.run()
    b = GB.build(GB.load_state(db), "UAT-REL-001", closed=True)
    it = next(x for x in b["self_check"] if x["id"] == "acceptance.truy-vet")
    assert it["verdict"] == "gap" and any("1 không truy vết" in f for f in it["facts"]) and any("REQ-9" in f for f in it["facts"])
    assert any("contract: 1 dòng" in f for f in next(x for x in b["self_check"] if x["id"] == "acceptance.moi-truong")["facts"])


def test_acceptance_gap_khi_chua_len_production(tmp_path):
    db, _, orch = _scenario(tmp_path, to="release")
    # gate nghiệm thu chưa mở (chưa production): dựng thử hồ sơ giả định qua build với --closed không có → NotPending
    with pytest.raises(GB.NotPending):
        GB.build(GB.load_state(db), "UAT-REL-001")
    # ép một gate acceptance khi release mới ở staging (người mở tay) → mục môi trường là gap
    from company.gates import GateRequest
    orch.gate.request(GateRequest(kind="acceptance", subject_id="UAT-REL-001", created_by="account-manager", checklist=["uat-script"]))
    b = GB.build(GB.load_state(db), "UAT-REL-001")
    assert _verdicts(b)["acceptance.moi-truong"] == "gap"


# ---------- escalation (§5.6) ----------

def test_escalation_gom_hint_cu_va_lich_su(tmp_path):
    db, _bus, orch = _scenario(tmp_path, fail_handler, to="escalation")
    assert orch.gate.pending["T1"].kind == "escalation" and orch.lead.state["T1"] == "blocked"
    b = GB.build(GB.load_state(db), "T1")
    assert b["kind"] == "escalation" and b["project_id"] == "P1" and b["extra"]["scope"] == "ticket"
    assert b["extra"]["hints_used"] == [] and b["extra"]["ticket"]["retry"] == 2
    acts = [h["action"] for h in b["extra"]["history"]]
    assert acts.count("tasks retry=0") == 1 and "tasks retry=2" in acts and any("invalid_output" in a for a in acts)
    assert any("ticket.blocked" in a for a in acts), "lead chặn ticket: dấu vết bền phải có trong lịch sử"
    ns = next(x for x in b["self_check"] if x["id"] == "escalation.ngan-sach")
    assert ns["verdict"] == "ok" and "đầu ra" in ns["facts"][0] and b["extra"]["budget"]["state"] == "blocked"
    assert b["extra"]["diagnose"]["blocked"] == 1
    assert {u["id"] for u in b["unavailable"]} == {"escalation.worktree"}
    _check_golden("escalation", b)

    # người mở lại hai lần với CÙNG một hint → hồ sơ liệt kê cả hai và nêu hint lặp
    orch.gate.decide("T1", "approve", by="human:lead", reason="thử lại"); orch.run()
    assert orch.lead.state["T1"] == "blocked" and "T1" in orch.gate.pending
    orch.gate.decide("T1", "approve", by="human:lead", reason="thử lại"); orch.run()
    b2 = GB.build(GB.load_state(db), "T1")
    hints = b2["extra"]["hints_used"]
    assert [h["reason"] for h in hints] == ["thử lại", "thử lại"] and b2["extra"]["duplicate_hints"] == ["thử lại"]
    md = GB.render_md(b2)
    assert "hint lặp lại y hệt: thử lại" in md and "## Lịch sử thất bại" in md and "không phải khuyến nghị" in md
    assert "gate_cli" not in md.split("## Nửa của người")[1], "phần hồ sơ không nhắc lệnh ký"


def test_escalation_voi_repo_thay_worktree(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    db, _, orch = _scenario(tmp_path, fail_handler, to="escalation", repo=repo)
    assert orch.lead.state["T1"] == "blocked"
    b = GB.build(GB.load_state(db, repo=repo), "T1")
    assert b["extra"]["worktree"]["branch"] == "ticket/T1" and b["extra"]["worktree"]["path"].endswith("T1")
    assert "escalation.worktree" not in {u["id"] for u in b["unavailable"]}
    assert "## Worktree" in GB.render_md(b)


def test_escalation_cap_du_an(tmp_path):
    db, _, orch = _scenario(tmp_path, stall_handler, to="stalled")
    assert orch.gate.pending["P1"].kind == "escalation" and "P1" in orch.stalled
    b = GB.build(GB.load_state(db), "P1")
    assert b["extra"]["scope"] == "project" and b["extra"]["stalled"]["agent"] == "intake" and b["project_id"] == "P1"
    assert any("project.stalled" in h["action"] for h in b["extra"]["history"])
    ns = b["self_check"][0]
    assert ns["id"] == "escalation.ngan-sach" and ns["verdict"] == "unknown" and "chưa đặt" in ns["facts"][0]
    assert "## Dự án kẹt" in GB.render_md(b)


def test_escalation_ngan_sach_gap_khi_can(tmp_path):
    _db, _, orch = _scenario(tmp_path, fail_handler, to="escalation")
    orch.supervisor.budgets["T1"].output_used = orch.supervisor.budgets["T1"].limit + 1
    b = GB.build(orch, "T1")  # cùng orchestrator (trạng thái sửa tay) — build không phụ thuộc DB
    assert _verdicts(b)["escalation.ngan-sach"] == "gap"


# ---------- CLI ----------

def test_cli_all_json_va_out(tmp_path, capsys):
    db, _, _ = _scenario(tmp_path)
    assert GB.main(["--all", "--db", str(db), "--format", "json", "--no-write"]) == 0
    out = capsys.readouterr().out
    assert out.count('"schema_version": 1') == 2 and '"kind": "release"' in out and '"kind": "acceptance"' in out
    assert GB.main(["REL-002", "--db", str(db)]) == 0
    default = GB.artifact_store(db) / "P1" / "gate-brief"
    assert (default / "REL-002.json").exists() and (default / "REL-002.md").exists()
    assert "hồ sơ bằng chứng, không phải khuyến nghị" in capsys.readouterr().out


def test_cli_all_khong_co_gate(tmp_path, capsys):
    db2 = tmp_path / "e.sqlite"; SQLiteBus(db2).close()
    assert GB.main(["--all", "--db", str(db2)]) == 0 and "không có gate chờ" in capsys.readouterr().out
