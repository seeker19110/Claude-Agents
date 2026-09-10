"""Hạ tầng eval của `keeper` (`src/keeper/evals.py`): bộ ca, ghi/phát lại, và CHÍNH SÁCH CỔNG của `main`.

Không ca nào gọi model thật: `--record` chạy qua `FakeClient`, `--replay` đọc bản ghi trong `tmp_path`.
Bộ ca và bản ghi THẬT trong `evals/` được đo bằng một nhóm ca riêng ở cuối file — chúng là hợp đồng với CI
(`keeper.evals all --replay --strict`), nên phải đỏ ngay tại đây nếu ai xoá một ca hay quên ghi lại bản ghi.
"""
from __future__ import annotations

import json

import pytest
import yaml
from xagents_core.llm import FakeClient, LLMError

from keeper import evals as ev
from keeper.core import CORE
from keeper.evals import SUITE, RecordingClient, ReplayClient, Suite, load_thresholds, main, run_eval

TICKET = {"ticket_id": "KEEP-1", "subject": "ruff", "risk_tier": "low"}
CASE = {
    "name": "ca-mau",
    "topic_out": "maintenance-tickets",
    "input": {"topic": "maintenance-signals", "key": "SIG-1",
              "payload": {"subject": "ruff", "kind": "dependency", "detail": "bump"}},
    "expect": {"equals": {"risk_tier": "low"}},
}


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """`evals/` giả trong tmp_path — Suite đọc từ BIẾN MODULE nên đây là seam có sẵn."""
    (tmp_path / "recordings").mkdir()
    monkeypatch.setattr(ev, "EVALS_DIR", tmp_path)
    monkeypatch.setattr(ev, "RECORDINGS_DIR", tmp_path / "recordings")
    monkeypatch.setattr(ev, "DEFAULT_THRESHOLDS_PATH", tmp_path / "thresholds.yaml")
    return tmp_path


def _cases(sandbox, agent="triager", cases=(CASE,)):
    (sandbox / f"{agent}.yaml").write_text(yaml.safe_dump({"cases": list(cases)}), encoding="utf-8")


def _fake(payload=None):
    return FakeClient(handler=lambda system, user: dict(payload or TICKET))


# ---------- bốn móc của Suite ----------

def test_suite_dung_bus_blackboard_agent_cua_keeper():
    s = Suite(CORE.root)
    bus = s.new_bus()
    assert s.new_blackboard(bus).cfg is CORE
    assert "triager" in s.load_agents()


def test_run_eval_cham_theo_expect_va_dem_token(sandbox):
    _cases(sandbox)
    res = run_eval("triager", _fake())
    assert [r.passed for r in res] == [True] and res[0].tokens > 0


def test_ca_khong_dat_expect_thi_fail_kem_ly_do(sandbox):
    _cases(sandbox)
    res = run_eval("triager", _fake({**TICKET, "risk_tier": "high"}))
    assert not res[0].passed and "risk_tier" in res[0].failures[0]
    assert not res[0].errored           # chạy được, chỉ chấm sai — hai sự thật KHÁC nhau
    assert not res[0].broken_recording


def test_ca_khong_chay_duoc_thi_errored_chu_khong_no_ra_ngoai(sandbox):
    _cases(sandbox)

    class _No:
        def complete(self, **kw): raise LLMError("hết quota")

    res = run_eval("triager", _No())
    assert res[0].errored and not res[0].passed


def test_context_cua_ca_duoc_ghi_len_blackboard_truoc_khi_chay(sandbox):
    _cases(sandbox, cases=[{**CASE, "context": [
        {"actor": "keeper-supervisor", "namespace": "knowledge", "content_ref": "bai-hoc.md",
         "summary": "ưu tiên dev-dependency"}]}])
    client = _fake()
    run_eval("triager", client)
    assert "bai-hoc.md" in client.calls[0]["user"]


# ---------- ghi / phát lại ----------

def test_ghi_roi_phat_lai_khong_goi_model(sandbox):
    _cases(sandbox)
    rc = RecordingClient(_fake(), "triager")
    run_eval("triager", rc)
    p = rc.save()
    assert json.loads(p.read_text(encoding="utf-8"))["prompt_version"] == SUITE.load_agents()["triager"].version
    assert [r.passed for r in run_eval("triager", ReplayClient("triager"))] == [True]


def test_chua_co_ban_ghi_thi_ReplayClient_noi_ro_phai_lam_gi(sandbox):
    with pytest.raises(LLMError, match="make eval-record"):
        ReplayClient("triager")


def test_ban_ghi_lech_prompt_thi_ca_do_va_duoc_danh_dau_broken_recording(sandbox):
    _cases(sandbox)
    RecordingClient(_fake(), "triager").save()   # bản ghi rỗng: có file, không có khoá nào
    res = run_eval("triager", ReplayClient("triager"))
    assert res[0].broken_recording and res[0].errored


def test_stale_recordings_chi_ra_dung_ten_ca_thieu(sandbox):
    _cases(sandbox)
    RecordingClient(_fake(), "triager").save()
    assert SUITE.stale_recordings(["triager"]) == {"triager": ["ca-mau"]}


def test_outdated_versions_bat_ban_ghi_ghi_o_prompt_cu(sandbox):
    _cases(sandbox)
    rc = RecordingClient(_fake(), "triager")
    run_eval("triager", rc)
    p = rc.save()
    data = json.loads(p.read_text(encoding="utf-8")); data["prompt_version"] = 0
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert "bản ghi ở prompt v0" in SUITE.outdated_versions(["triager"])["triager"]


# ---------- ngưỡng điểm ----------

def test_load_thresholds_khong_co_file_thi_khong_ap(sandbox):
    assert load_thresholds() == {}


def test_load_thresholds_doc_duong_dan_mac_dinh_cua_keeper(sandbox):
    (sandbox / "thresholds.yaml").write_text("triager: {min_pass_ratio: 0.9, cases: 1}\n", encoding="utf-8")
    assert load_thresholds()["triager"].cases == 1


# ---------- main: chính sách cổng ----------

def _run(argv, monkeypatch, client=None):
    monkeypatch.setattr("keeper.llm.make_client", lambda: client or _fake())
    return main(argv)


def test_main_khong_co_bo_ca_thi_bo_qua_agent_do(sandbox, monkeypatch, capsys):
    assert _run(["patcher"], monkeypatch) == 0
    assert capsys.readouterr().out == ""


def test_main_model_that_thi_moi_ca_phai_dat(sandbox, monkeypatch, capsys):
    _cases(sandbox)
    assert _run(["triager"], monkeypatch) == 0
    assert _run(["triager"], monkeypatch, client=_fake({**TICKET, "risk_tier": "high"})) == 1
    assert "FAIL triager/ca-mau" in capsys.readouterr().out


def test_main_record_ghi_file_va_in_duong_dan(sandbox, monkeypatch, capsys):
    _cases(sandbox)
    assert _run(["triager", "--record"], monkeypatch) == 0
    assert "đã ghi" in capsys.readouterr().out
    assert (sandbox / "recordings" / "triager.json").exists()


def test_main_all_chay_moi_agent_co_bo_ca(sandbox, monkeypatch, capsys):
    _cases(sandbox, "triager")
    _cases(sandbox, "release-clerk", cases=[{
        "name": "ca-note", "topic_out": "release-notes",
        "input": {"topic": "verification-reports", "key": "KEEP-1", "actor": "regression-guard",
                  "payload": {"ticket_id": "KEEP-1", "before": {"cmd": "pytest", "exit_code": 1},
                              "after": {"cmd": "pytest", "exit_code": 0}, "verified_by": "workspace"}},
        "expect": {"equals": {"ticket_id": "KEEP-1"}}}])
    note = {"ticket_id": "KEEP-1", "changelog_line": "- fix(keeper): x", "session_line": "y"}
    monkeypatch.setattr("keeper.llm.make_client", lambda: FakeClient(
        handler=lambda system, user: dict(note if "release-clerk" in system else TICKET)))
    assert main(["all"]) == 0
    out = capsys.readouterr().out
    assert "triager: 1/1 pass" in out and "release-clerk: 1/1 pass" in out


def test_main_replay_thieu_ban_ghi_la_SKIP_hoac_FAIL_tuy_REQUIRED(sandbox, monkeypatch, capsys):
    _cases(sandbox)
    assert _run(["triager", "--replay"], monkeypatch) == 0            # không --strict: SKIP, không chặn
    assert "SKIP triager" in capsys.readouterr().out
    (sandbox / "recordings" / "REQUIRED.txt").write_text("triager\n", encoding="utf-8")
    assert _run(["triager", "--replay", "--strict"], monkeypatch) == 1
    assert "FAIL triager" in capsys.readouterr().out


def test_main_strict_bat_ban_ghi_ghi_o_prompt_cu(sandbox, monkeypatch, capsys):
    _cases(sandbox)
    rc = RecordingClient(_fake(), "triager"); run_eval("triager", rc); p = rc.save()
    data = json.loads(p.read_text(encoding="utf-8")); data["prompt_version"] = 0
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert _run(["triager", "--replay", "--strict"], monkeypatch) == 1
    assert "chạy `make eval-record AGENT=triager`" in capsys.readouterr().out


def test_main_replay_ca_cham_sai_khong_lam_do_neu_khong_co_nguong(sandbox, monkeypatch, capsys):
    """Cổng của `--replay` là BẢN GHI; điểm chấm gác riêng bằng thresholds.yaml — hai cổng, hai lý do."""
    _cases(sandbox)
    rc = RecordingClient(_fake({**TICKET, "risk_tier": "high"}), "triager")
    run_eval("triager", rc); rc.save()
    assert _run(["triager", "--replay", "--no-thresholds"], monkeypatch) == 0
    assert "FAIL triager/ca-mau" in capsys.readouterr().out


def test_main_nguong_diem_lam_do_khi_ban_ghi_tut_diem(sandbox, monkeypatch, capsys):
    _cases(sandbox)
    rc = RecordingClient(_fake({**TICKET, "risk_tier": "high"}), "triager")
    run_eval("triager", rc); rc.save()
    (sandbox / "thresholds.yaml").write_text("triager: {min_pass_ratio: 0.95, cases: 1}\n", encoding="utf-8")
    assert _run(["triager", "--replay"], monkeypatch) == 1
    assert "dưới ngưỡng" in capsys.readouterr().out


def test_main_nguong_truyen_tay_thang_duong_dan_mac_dinh(sandbox, monkeypatch, capsys, tmp_path):
    _cases(sandbox)
    rc = RecordingClient(_fake(), "triager"); run_eval("triager", rc); rc.save()
    th = tmp_path / "khac.yaml"
    th.write_text("triager: {min_pass_ratio: 0.95, cases: 9}\n", encoding="utf-8")   # đòi 9 ca, chỉ có 1
    assert _run(["triager", "--replay", "--thresholds", str(th)], monkeypatch) == 1
    assert "bộ ca bị thu nhỏ" in capsys.readouterr().out


# ---------- hợp đồng với CI: bộ ca và bản ghi THẬT trong evals/ ----------

REQUIRED = sorted(SUITE.required_agents())


def test_bon_agent_bat_buoc_deu_co_bo_ca_va_ban_ghi():
    assert REQUIRED == ["keeper-supervisor", "release-clerk", "security-auditor", "triager"]
    for aid in REQUIRED:
        assert len(SUITE.load_cases(aid)) >= 5, aid
        assert SUITE.recording_path(aid).exists(), aid


def test_khong_ban_ghi_nao_lech_phien_ban_prompt_hien_tai():
    assert SUITE.outdated_versions() == {}


def test_khong_ban_ghi_nao_thieu_khoa_cho_ca_hien_tai():
    assert SUITE.stale_recordings() == {}


def test_nguong_diem_phu_dung_bon_agent_bat_buoc():
    th = load_thresholds(CORE.root / "evals" / "thresholds.yaml")
    assert sorted(th) == REQUIRED
    for aid in REQUIRED:
        assert th[aid].cases == len(SUITE.load_cases(aid)), aid
