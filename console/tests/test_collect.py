"""collect(): hợp đồng API.md trên DB thật (event publish qua bus của hai công ty)."""
from __future__ import annotations

import json
import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from company.gates import HumanGate as CompanyHumanGate
from studio.events import AuditLog as StudioAudit
from studio.events import Envelope as StudioEnvelope
from studio.sqlite_bus import SQLiteBus as StudioSQLiteBus

import console.collect as collect_mod
from conftest import gate_decide
from console.collect import COMPANY, STUDIO, collect

DEAD_GATEWAY = "http://127.0.0.1:9"  # cổng 9 (discard) không có ai nghe → luôn từ chối ngay


def state(company_db: Path | None, studio_db: Path | None) -> dict:
    return collect(company_db, studio_db, gateway_url=DEAD_GATEWAY)


def test_hai_xuong_deu_co_du_lieu(company_db: Path, studio_db: Path) -> None:
    s = state(company_db, studio_db)
    assert s["sources"][COMPANY]["ok"] and s["sources"][STUDIO]["ok"]
    assert s["sources"][COMPANY]["events"] == 8 and s["sources"][STUDIO]["events"] == 5
    assert s["tiles"]["events"] == 13
    assert [t["id"] for t in s["tickets"]] == ["TCK-112"]
    assert s["tickets"][0]["bud"] == 120_000 and s["tickets"][0]["used"] == 8_420
    assert s["prs"] == [{"id": "TCK-112", "br": "ticket/TCK-112", "s": "thêm login",
                         "lint": "pass", "tests": "pass", "v": "workspace"}]
    assert s["reviews"][0]["v"] == "block" and "thiếu authz" in s["reviews"][0]["f"]
    assert [v["id"] for v in s["videos"]] == ["vid-042"]
    assert s["perf"] == [{"id": "vid-042", "imp": 41_200, "views": 7_840, "ctr": 0.19, "avd": 284}]
    assert s["retention"]["video_id"] == "vid-042" and s["retention"]["points"][0] == [0.0, 100.0]
    assert dict(s["agents"])["backend"] == 0.21
    assert {g["xuong"] for g in s["gates"]} == {COMPANY, STUDIO}
    assert [r["ac"] for r in s["log"]]  # audit `produced:*`, mới nhất trước
    assert len(s["cost_days"]["days"]) == len(s["cost_days"]["series"]) == 14
    assert s["cost_days"]["series"][-1][0] == 0.21  # backend = tier strong, hôm nay


def test_moi_khoa_luon_co_mat_va_khong_nem_khi_thieu_db(tmp_path: Path, studio_db: Path) -> None:
    s = state(tmp_path / "khong-co.sqlite", studio_db)
    assert s["sources"][COMPANY] == {"ok": False, "db": None, "events": 0, "error": "chưa có file DB"}
    assert s["sources"][STUDIO]["ok"]
    assert s["tickets"] == [] and s["prs"] == [] and s["reviews"] == []
    assert [g["xuong"] for g in s["gates"]] == [STUDIO, STUDIO]  # phần của xưởng hỏng rỗng, xưởng kia vẫn đủ
    assert s["videos"] and s["tiles"]["events"] == 5
    for key in ("generated_at", "sources", "tiles", "gates", "tickets", "prs", "reviews", "videos", "perf",
                "retention", "cost_days", "agents", "backends", "supervisor", "log"):
        assert key in s


def test_db_hong_bao_loi_chu_khong_nem(tmp_path: Path, studio_db: Path) -> None:
    bad = tmp_path / "hong.sqlite"; bad.write_bytes(b"day khong phai sqlite")
    s = state(bad, studio_db)
    assert s["sources"][COMPANY]["ok"] is False
    assert "không đọc được DB" in s["sources"][COMPANY]["error"]
    assert s["tickets"] == []


def test_khong_co_db_nao(tmp_path: Path) -> None:
    s = state(None, None)
    assert s["sources"][COMPANY]["error"] == "chưa cấu hình đường dẫn DB"
    assert s["tiles"]["events"] == 0 and s["gates"] == [] and s["retention"] == {"video_id": None, "points": []}


def test_tuoi_gate_va_nguong_sev_theo_hang_so_cua_cong_ty(company_db: Path, studio_db: Path) -> None:
    g = CompanyHumanGate()
    over_h = g.timeout.total_seconds() / 3600
    warn_h = g.remind_at.total_seconds() / 3600
    by_id = {x["id"]: x for x in state(company_db, studio_db)["gates"]}
    assert by_id["PLAN-1"]["hours"] == 30 and by_id["PLAN-1"]["sev"] == "over"
    assert by_id["PUB-vid-042"]["hours"] == 13 and by_id["PUB-vid-042"]["sev"] == "warn"
    assert by_id["PLAN-ch1"]["hours"] == 2 and by_id["PLAN-ch1"]["sev"] == "calm"
    assert by_id["PLAN-1"]["hours"] >= over_h > by_id["PUB-vid-042"]["hours"] >= warn_h > by_id["PLAN-ch1"]["hours"]
    assert math.floor(over_h) == 24 and math.floor(warn_h) == 12  # khớp GATE_TIMEOUT/REMIND của repo


def test_gate_da_quyet_khong_con_trong_danh_sach(company_db: Path, studio_db: Path) -> None:
    s = state(company_db, studio_db)
    assert "SPEC-1" not in {g["id"] for g in s["gates"]}          # đã có gate.decide trong log
    assert {"PLAN-1", "PUB-vid-042", "PLAN-ch1"} == {g["id"] for g in s["gates"]}
    bus = StudioSQLiteBus(studio_db)
    gate_decide(bus, StudioEnvelope, StudioAudit, subject_id="PLAN-ch1", decision="approve", by="human:owner")
    bus.close()
    assert "PLAN-ch1" not in {g["id"] for g in state(company_db, studio_db)["gates"]}


def test_gate_mang_du_kien_va_checklist(company_db: Path, studio_db: Path) -> None:
    pub = next(g for g in state(company_db, studio_db)["gates"] if g["id"] == "PUB-vid-042")
    assert pub["kind"] == "publish" and pub["by"] == "publisher" and pub["trigger"] == "human:owner"
    assert pub["title"] == "Ống kính 50mm"
    assert ["video_id", "vid-042"] in pub["facts"]
    assert [item for item, _ in pub["cl"]] == ["review:fact:pass", "thumbnail"]


@pytest.fixture()
def khong_co_llm_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    """Máy chạy test có thể có sẵn `llm.yaml` của một trong hai công ty; khi đó collect() lấy backend từ đó và
    không bao giờ hỏi gateway. Ép nhánh gateway để test đúng thứ nó định test."""
    monkeypatch.setattr(collect_mod, "_routing_status", lambda: None)


def test_gateway_chet_khong_lam_hong_trang(company_db: Path, studio_db: Path, khong_co_llm_yaml: None) -> None:
    start = datetime.now(UTC)
    s = collect(company_db, studio_db, gateway_url=DEAD_GATEWAY)
    assert s["backends"] == []
    assert s["sources"]["gateway"]["ok"] is False
    assert "gateway" in s["sources"]["gateway"]["error"]
    assert (datetime.now(UTC) - start).total_seconds() < 5  # timeout ngắn, không treo trang
    assert s["tickets"] and s["videos"]  # phần còn lại vẫn đầy đủ


def test_doc_khong_ghi_vao_db(company_db: Path, studio_db: Path) -> None:
    before = (company_db.read_bytes(), studio_db.read_bytes())
    state(company_db, studio_db)
    assert (company_db.read_bytes(), studio_db.read_bytes()) == before


@pytest.mark.parametrize("token", [None])
def test_token_gateway_khong_bat_buoc(company_db: Path, studio_db: Path, token: Path | None, khong_co_llm_yaml: None) -> None:
    s = collect(company_db, studio_db, gateway_token_file=token, gateway_url=DEAD_GATEWAY)
    assert s["backends"] == []


# ---------- các nhánh nhỏ khó chạm tới qua collect() nguyên khối: test trực tiếp hàm/lớp nội bộ ----------


def test_envelope_hong_bao_loi_ro_thay_vi_nem_nua_voi(tmp_path: Path) -> None:
    """Một hàng trong `events` mà body không parse được thành envelope model -> _SourceError rõ ràng."""
    db = tmp_path / "hong-envelope.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE events (seq INTEGER PRIMARY KEY, body TEXT)")
    con.execute("INSERT INTO events (body) VALUES (?)", ("khong-phai-json-envelope-hop-le",))
    con.commit()
    con.close()
    s = collect(db, None, gateway_url=DEAD_GATEWAY)
    assert s["sources"][COMPANY]["ok"] is False
    assert "log hỏng" in s["sources"][COMPANY]["error"]


def test_evidence_don_bien_dang_loi() -> None:
    assert collect_mod._evidence({"evidence": "khong-phai-json"}) == {}
    assert collect_mod._evidence({"evidence": json.dumps([1, 2])}) == {}
    assert collect_mod._evidence({"evidence": None}) == {}
    assert collect_mod._evidence({"evidence": json.dumps({"event_id": "e1"})}) == {"event_id": "e1"}


def test_view_read_replay_khong_override_nem_notimplemented() -> None:
    with pytest.raises(NotImplementedError):
        collect_mod._View("x", None)

    class _ChiCoRead(collect_mod._View):
        def _read(self):
            return []

    with pytest.raises(NotImplementedError):
        _ChiCoRead("x", None)


def test_view_mac_dinh_gate_title_facts_review_note_tiers() -> None:
    """`_View` cơ sở (không override) dùng cho các test kiểm nhánh mặc định không lớp con nào chạm tới."""
    v = object.__new__(collect_mod._View)
    v.name = "x"
    v.envelopes = []
    assert v.tiers() == {}
    assert v.review_note("S1", "src") == ""

    r = SimpleNamespace(kind="plan", subject_id="S1", created_by="u")
    assert v.gate_title(r) == "plan · S1"
    assert v.gate_facts(r) == [["kind", "plan"], ["subject_id", "S1"], ["created_by", "u"]]


def test_review_note_noi_finding_khi_khong_co_root_cause() -> None:
    v = object.__new__(collect_mod._View)
    v.envelopes = [
        SimpleNamespace(topic="review-results",
                        payload={"ticket_id": "T1", "source": "revr", "verdict": "block",
                                 "findings": [{"text": "a"}, {"text": "b"}]}),
    ]
    assert v._review_note("ticket_id", "T1", "revr") == "block · a; b"
    # không khớp nguồn/subject -> rỗng
    assert v._review_note("ticket_id", "T1", "khac") == ""


def test_company_tiers_loi_load_agents_tra_rong(company_db: Path, studio_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collect_mod, "load_company_agents", lambda **k: (_ for _ in ()).throw(RuntimeError("hong")))
    s = collect(company_db, studio_db, gateway_url=DEAD_GATEWAY)
    # tiers() rỗng -> cost_days vẫn chạy được (dùng tier mặc định "standard"), không nổ.
    assert len(s["cost_days"]["series"]) == 14


def test_studio_tiers_loi_load_agents_tra_rong(company_db: Path, studio_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collect_mod, "load_studio_agents", lambda **k: (_ for _ in ()).throw(RuntimeError("hong")))
    s = collect(company_db, studio_db, gateway_url=DEAD_GATEWAY)
    assert len(s["cost_days"]["series"]) == 14


def test_retention_rong_khi_khong_co_snapshot_nao_co_curve(tmp_path: Path) -> None:
    from studio.events import Envelope as SEnv
    from studio.events import PerformanceSnapshot
    from studio.sqlite_bus import SQLiteBus as SBus

    db = tmp_path / "studio-no-curve.sqlite"
    bus = SBus(db)
    snap = PerformanceSnapshot(video_id="vid-1", channel_id="ch1", views=1, impressions=1, ctr=0.1,
                               avg_view_duration_s=1.0, retention_curve=[])
    bus.publish(SEnv(topic="performance-snapshots", key="vid-1", actor="human",
                     payload=json.loads(snap.model_dump_json())))
    bus.close()
    s = collect(None, db, gateway_url=DEAD_GATEWAY)
    assert s["retention"] == {"video_id": None, "points": []}


def test_routing_status_config_loi_bo_qua_va_thu_gateway(company_db: Path, studio_db: Path,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    """`llm.yaml` có tồn tại (giả) nhưng load_config ném lỗi -> _routing_status() bỏ qua, coi như không có, đi hỏi gateway."""
    import console.collect as cmod

    monkeypatch.setattr(cmod.company_llm, "CONFIG_FILE", "gia-lap.yaml")
    monkeypatch.setattr(Path, "exists", lambda self: True)
    monkeypatch.setattr(cmod.company_llm, "load_config", lambda p: (_ for _ in ()).throw(RuntimeError("hong config")))
    monkeypatch.setattr(cmod.studio_llm, "CONFIG_FILE", None)
    s = collect(company_db, studio_db, gateway_url=DEAD_GATEWAY)
    assert s["backends"] == []
    assert s["sources"]["gateway"]["ok"] is False


def test_routing_status_tu_llm_yaml_that_khong_hoi_gateway(tmp_path: Path, company_db: Path, studio_db: Path,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    """`llm.yaml` có `backends:` -> backends lấy từ routing.status() thật, gateway KHÔNG được hỏi (sources.gateway ok, error None).

    Trước đây nhánh này chỉ được phủ nhờ máy dev tình cờ có sẵn `software-company/llm.yaml` (bị gitignore) — trên CI
    không có file nên collect.py 395-408 và 527 chưa bao giờ chạy ở đó. Test tự tạo file để không phụ thuộc máy."""
    import console.collect as cmod

    llm_yaml = tmp_path / "llm.yaml"
    llm_yaml.write_text(
        "backends:\n"
        "  - name: antigravity\n"
        "    provider: openai\n"
        "    base_url: http://127.0.0.1:1123/v1\n"
        "    api_key: gateway-local\n"
        "    models: {strong: claude-sonnet-4-6, standard: gemini-3.7-flash, light: gemini-3.7-flash-low}\n"
        "  - name: local\n"
        "    provider: openai\n"
        "    base_url: http://localhost:11434/v1\n"
        "    models: {strong: qwen3:32b, standard: qwen3:8b}\n"
        "routing:\n"
        "  cooldown_s: 120\n"
        "  transient_cooldown_s: 5\n"
        "  prefer: {light: antigravity, strong: local}\n",
        encoding="utf-8",
    )
    # load_config ưu tiên biến môi trường: có COMPANY_LLM_PROVIDER thì backends bị xoá, COMPANY_LLM_BACKENDS thì bị lọc.
    monkeypatch.delenv("COMPANY_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("COMPANY_LLM_BACKENDS", raising=False)
    monkeypatch.setattr(cmod.company_llm, "CONFIG_FILE", llm_yaml)
    monkeypatch.setattr(cmod.studio_llm, "CONFIG_FILE", None)

    s = collect(company_db, studio_db, gateway_url=DEAD_GATEWAY)

    assert [b["n"] for b in s["backends"]] == ["antigravity", "local"]
    assert all(b["ok"] and b["st"] == "Sẵn sàng" and b["tools"] == "có" for b in s["backends"])
    assert "strong" in s["backends"][0]["tiers"] and "light" in s["backends"][0]["tiers"]
    assert s["sources"]["gateway"] == {"ok": True, "url": DEAD_GATEWAY, "error": None}  # không hỏi gateway (đã chết)


def test_gateway_status_doc_token_that_bai_van_hoi_duoc(tmp_path: Path, company_db: Path, studio_db: Path,
                                                         khong_co_llm_yaml: None) -> None:
    """token_file trỏ tới đường dẫn không đọc được (thư mục) -> OSError bị nuốt, request vẫn không kèm token."""
    bad_token = tmp_path  # là thư mục, đọc như file sẽ ném OSError
    s = collect(company_db, studio_db, gateway_token_file=bad_token, gateway_url=DEAD_GATEWAY)
    assert s["backends"] == []
    assert s["sources"]["gateway"]["ok"] is False


def test_gateway_status_thanh_cong_tra_danh_sach_account(tmp_path: Path, company_db: Path, studio_db: Path,
                                                          khong_co_llm_yaml: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`GET /auth/status` thành công, kèm token file hợp lệ -> parse ra danh sách account đúng hình dạng."""
    import io
    import urllib.request

    token_file = tmp_path / "tok"
    token_file.write_text("abc123", encoding="utf-8")

    payload = json.dumps({"accounts": [
        {"email": "a@x.com", "cooldown_remaining": 0, "is_expired": False, "last_failure_status": 0, "source": "s1"},
        {"email": "b@x.com", "cooldown_remaining": 30, "is_expired": False, "last_failure_status": 429, "source": "s2"},
        {"email": "c@x.com", "cooldown_remaining": 0, "is_expired": True, "source": "s3"},
    ]}).encode("utf-8")

    class FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    captured_headers: dict[str, str] = {}

    def fake_urlopen(req, timeout=None):
        captured_headers.update(req.headers)
        return FakeResp(payload)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    s = collect(company_db, studio_db, gateway_token_file=token_file, gateway_url="http://gia-lap")
    assert s["sources"]["gateway"]["ok"] is True
    names = {b["n"] for b in s["backends"]}
    assert names == {"a@x.com", "b@x.com", "c@x.com"}
    by_name = {b["n"]: b for b in s["backends"]}
    assert by_name["a@x.com"]["ok"] is True and by_name["a@x.com"]["st"] == "Sẵn sàng"
    assert by_name["b@x.com"]["ok"] is False and "Nghỉ 30s" in by_name["b@x.com"]["st"]
    assert by_name["c@x.com"]["ok"] is False and by_name["c@x.com"]["st"] == "Hết hạn token"
    assert "Authorization" in captured_headers
