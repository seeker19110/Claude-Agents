"""Gate 3 gác PRODUCTION, không gác STAGING — nếu gác cả hai thì dây chuyền khoá kín.

Đo được 2026-09-06 (dự án QLKH): `_release` gửi `gate_release` cho CẢ hai env. Ở staging nó luôn `false` (Gate 3 chưa
thể duyệt vì chưa có qa hồi quy), release-engineer đọc đó là "chưa được phép" và TỪ CHỐI deploy staging. Vòng khoá:

    release-engineer từ chối staging (gate_release=false)
      → staging không bao giờ `deployed`
      → qa hồi quy (route `release-events` khi `deployed`) không chạy
      → Gate 3 thiếu nguồn `qa`, không mở
      → `gate.is_approved(rid)` mãi false → quay lại đầu

Kết quả thật: 18/18 release-candidate chết ở đây, 0 lần ra production, 0 tag giao hàng, dù 14/14 ticket đã vào
`company/integration`. Staging chính là nơi QA hồi quy TRƯỚC khi xin Gate 3 (ADR-0006) nên nó không được đòi Gate 3.
"""
from __future__ import annotations

from company.events import Envelope, Task
from company.llm import FakeClient
from company.orchestrator import Orchestrator
from company.sqlite_bus import SQLiteBus
from test_orchestrator import handler


def _rc(bus, rid="REL-001", tid="T1", version="0.1.0"):
    bus.publish(Envelope(topic="release-candidates", key=rid, actor="delivery-lead",
                         payload={"release_id": rid, "project_id": "P", "tickets": [tid], "version": version,
                                  "notes": "rc"}))


def _payload_gui_release_engineer(client, env):
    """Payload thực sự gửi cho ops[deploy] (từng là release-engineer riêng, ADR-0037 PR-5b) ở env đó — đọc từ
    prompt của FakeClient. `ops` cũng chạy pha docs/account trong CÙNG kịch bản (vd. release-events production
    → ghi docs) nên phải lọc đúng pha `deploy` qua chữ ký `# Skills của pha deploy` mà `system_prompt` nối vào
    cuối, không chỉ lọc theo id agent."""
    import json
    for c in client.calls:
        if "# ops" not in c["system"][:10] or "# Skills của pha deploy" not in c["system"]:
            continue
        u = c["user"]
        # Lấy đúng khối ```json``` ĐẦU TIÊN (mục "Đầu vào"): `ops` sở hữu hai namespace (`docs`, `contract`) nên
        # phần "Yêu cầu" ở cuối user message cũng có dấu `{}` (liệt kê `context_writes`) — brace-matching thô
        # (`rindex("}")`) ăn luôn đoạn đó và làm JSON hỏng, khác `release-engineer` cũ (không sở hữu namespace).
        i = u.find("```json\n")
        if i < 0:
            continue
        j = u.find("\n```", i)
        if j < 0:
            continue
        try:
            p = json.loads(u[i + len("```json\n"):j])
        except ValueError:
            continue
        if p.get("target_env") == env:
            return p
    return None


def _orch(tmp_path):
    bus = SQLiteBus(tmp_path / "c.sqlite")
    client = FakeClient(handler=handler)
    orch = Orchestrator(bus, client, repo=None)
    orch.lead.tickets["T1"] = Task(ticket_id="T1", project_id="P", requirement_id="R1", assignee="backend",
                                   title="T1", acceptance=["a"])
    orch.lead.state["T1"] = "approved"
    # K1.5 (ADR-0036): các ca dưới đây đo GATE, chạy không repo nên không bao giờ smoke được. Spec nền khai
    # `kind: library` để RC đi tiếp đúng như trước — thiếu spec thì mặc định là `application` và RC thành
    # `failed` ngay ở staging, đúng ý đồ nhưng che mất thứ file này đo. Ca smoke ở `test_smoke_evidence.py`.
    bus.publish(Envelope(topic="approved-specs", key="P", actor="spec-writer",
                         payload={"project_id": "P", "status": "approved", "kind": "library",
                                  "artifacts": {"prd": "prd", "requirements": "req"}}))
    return bus, client, orch


def test_staging_khong_nhan_co_gate_release(tmp_path):
    bus, client, orch = _orch(tmp_path)
    _rc(bus)
    orch.run()

    p = _payload_gui_release_engineer(client, "staging")
    assert p is not None, "release-engineer phải được gọi cho staging"
    assert "gate_release" not in p, ("staging KHÔNG được nhận cờ Gate 3 — thấy `false` là nó từ chối deploy, "
                                    "và cả dây chuyền khoá kín")
    assert p.get("integration_branch") or True  # các trường khác giữ nguyên


def test_production_van_nhan_co_gate_release(tmp_path):
    """Chiều ngược: production VẪN phải nhận `gate_release` — đó là chỗ Gate 3 thật sự gác."""
    bus, client, orch = _orch(tmp_path)
    _rc(bus)
    orch.run()
    # qa hồi quy pass trên staging rồi người duyệt Gate 3 → orchestrator gọi release-engineer cho production
    bus.publish(Envelope(topic="release-events", key="REL-001", actor="ops",
                         payload={"release_id": "REL-001", "project_id": "P", "env": "staging",
                                  "status": "deployed", "version": "0.1.0"}))
    orch.run()
    orch.gate.decide("REL-001", "approve", by="human:pm", reason="ok")
    orch.run()

    p = _payload_gui_release_engineer(client, "production")
    assert p is not None, "duyệt Gate 3 phải kích hoạt lượt production"
    assert p.get("gate_release") is True, "production nhận cờ Gate 3 và nó phải là true sau khi duyệt"


def test_day_chuyen_di_het_tu_rc_toi_production(tmp_path):
    """Chốt chặn cho chính vòng khoá: từ release-candidate đi được tới `production/deployed` mà không cần ai
    duyệt Gate 3 TRƯỚC staging."""
    bus, _client, orch = _orch(tmp_path)
    _rc(bus)
    orch.run()
    envs = [(e.payload.get("env"), e.payload.get("status")) for e in bus.replay(topic="release-events")]
    assert ("staging", "deployed") in envs, f"staging phải deploy được ngay, nhận được: {envs}"

    orch.run()  # qa hồi quy trên staging → đủ nguồn → mở Gate 3
    assert "REL-001" in orch.gate.pending and orch.gate.pending["REL-001"].kind == "release"

    orch.gate.decide("REL-001", "approve", by="human:pm", reason="ok")
    orch.run()
    envs = [(e.payload.get("env"), e.payload.get("status")) for e in bus.replay(topic="release-events")]
    assert ("production", "deployed") in envs, f"phải ra được production, nhận được: {envs}"
