"""ADR gốc 0022 (N5): `quality:accept` được chấm lại khi candidate đổi, kể cả sau khi đã SUCCEEDED, và attempt
luôn có định danh mới khi candidate quay về một RC đã chấm. Receipt là fixture tổng hợp (xem test_quality_flow)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from xagents_core.execution import ExecutionEventKind, RunStatus, TaskStatus

from company.orch import quality_flow, quality_release
from company.quality_execution import QUALITY_TASK_ID
from test_quality_flow import RUN, FakeDriver, _journal, _sign_spec_with_profile, _signers, _start, write_trust


def _stage(tmp_path: Path, o, rid: str, tickets=("T1", "T2")) -> str:
    """Commit thêm vào nhánh tích hợp và giả lập RC `rid` đã staged ở sha mới đó."""
    wt = tmp_path / "repo" / ".worktrees" / "_integration"
    (wt / f"{rid}.py").write_text("X = 1\n", encoding="utf-8")
    for args in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", rid]):
        subprocess.run(["git", "-C", str(wt), *args], check=True, capture_output=True)
    sha = subprocess.run(["git", "-C", str(wt), "rev-parse", "HEAD"], check=True, capture_output=True,
                         text=True).stdout.strip()
    o.lead.releases.append(rid); o.lead.release_tickets[rid] = list(tickets); o.release_sha[rid] = sha
    return sha


def _kinds(tmp_path: Path) -> list[tuple[str, str]]:
    with _journal(tmp_path) as j:
        return [(e.kind.value, e.event_id.removeprefix(f"{RUN}:")) for e in j.events(RUN) if e.task_id == QUALITY_TASK_ID]


def test_sha_doi_sau_succeeded_thi_mo_lai_va_cham_lai_o_sha_moi(tmp_path):
    signers = _signers()
    driver = FakeDriver(signers)
    bus, o = _start(tmp_path, driver, trust=write_trust(tmp_path / "trust.json", signers))
    _sign_spec_with_profile(tmp_path, bus, o)
    [(_, first, _)] = driver.calls
    quality_flow.sync_quality(o)
    assert len(driver.calls) == 1, "cùng candidate đã đạt: không mở lại, không chấm lại"
    sha = _stage(tmp_path, o, "REL-009")
    quality_flow.sync_quality(o)
    assert driver.calls[-1][1] == f"REL-009@{sha}"
    with _journal(tmp_path) as j:
        state = j.resume(RUN)
        [reopened] = [e for e in j.events(RUN) if e.kind is ExecutionEventKind.TASK_REOPENED]
    assert state.status is RunStatus.SUCCEEDED and state.attempts[QUALITY_TASK_ID] == 2
    assert reopened.event_id == f"{RUN}:quality:reopen:{first}"
    assert first in reopened.payload["reason"] and f"REL-009@{sha}" in reopened.payload["reason"]
    assert quality_release.runs_for_release(o, "REL-009") == ((RUN, "succeeded", sha),)


def test_mo_lai_ma_chua_co_ket_qua_moi_thi_r6_van_thay_running(tmp_path):
    signers = _signers()
    driver = FakeDriver(signers)
    bus, o = _start(tmp_path, driver, trust=write_trust(tmp_path / "trust.json", signers))
    _sign_spec_with_profile(tmp_path, bus, o)
    o.quality_driver = None  # attempt mới chờ CLI commit
    sha = _stage(tmp_path, o, "REL-009")
    quality_flow.sync_quality(o)
    assert quality_release.runs_for_release(o, "REL-009") == ((RUN, "running", sha),)


def test_candidate_quay_ve_rc_da_cham_thi_van_mo_duoc_attempt_moi(tmp_path):
    signers = _signers()
    driver = FakeDriver(signers, drop=frozenset({"goal.traceability"}))
    bus, o = _start(tmp_path, driver, trust=write_trust(tmp_path / "trust.json", signers))
    _sign_spec_with_profile(tmp_path, bus, o)
    [(_, first, _)] = driver.calls  # hỏng ở candidate A
    _stage(tmp_path, o, "REL-009")
    quality_flow.sync_quality(o)  # hỏng ở candidate B
    assert len(driver.calls) == 2
    o.void_releases.add("REL-009")  # B bị huỷ ⇒ candidate quay về A
    driver.drop = frozenset()
    quality_flow.sync_quality(o)
    assert len(driver.calls) == 3 and driver.calls[-1][1] == f"{first}~2", "định danh mới cho candidate cũ"
    with _journal(tmp_path) as j:
        state = j.resume(RUN)
    assert state.tasks[QUALITY_TASK_ID] is TaskStatus.SUCCEEDED
    quality_flow.sync_quality(o)
    assert len(driver.calls) == 3, "đã đạt ở A (định danh ~2): không chấm lại"
    ids = [i for _, i in _kinds(tmp_path)]
    assert len(ids) == len(set(ids))


def test_succeeded_roi_quay_ve_candidate_cu_cung_mo_lai_duoc(tmp_path):
    signers = _signers()
    driver = FakeDriver(signers)
    bus, o = _start(tmp_path, driver, trust=write_trust(tmp_path / "trust.json", signers))
    _sign_spec_with_profile(tmp_path, bus, o)
    [(_, first, _)] = driver.calls
    _stage(tmp_path, o, "REL-009")
    quality_flow.sync_quality(o)
    o.void_releases.add("REL-009")
    quality_flow.sync_quality(o)
    assert [c[1] for c in driver.calls][-1] == f"{first}~2"
    assert [k for k, _ in _kinds(tmp_path)].count("task.reopened") == 2
    assert quality_release.runs_for_release(o, o.lead.releases[0])[0][1] == "succeeded"


def test_r6_doc_trang_thai_va_candidate_tu_cung_mot_snapshot(tmp_path, monkeypatch):
    """sc-security N5 #1: đọc trạng thái rồi mới đọc candidate thì một lần mở lại chen giữa ghép `succeeded` cũ với
    sha mới ⇒ R6 cho qua sha chưa ai chấm. Cặp trả về phải cùng một snapshot của journal."""
    from xagents_core.execution import ExecutionJournal
    signers = _signers()
    bus, o = _start(tmp_path, FakeDriver(signers), trust=write_trust(tmp_path / "trust.json", signers))
    _sign_spec_with_profile(tmp_path, bus, o)
    old = o.release_sha[o.lead.releases[-1]]
    o.quality_driver = None
    sha = _stage(tmp_path, o, "REL-009")
    orig, fired = ExecutionJournal.events, [False]

    def racing(self, run_id):
        out = orig(self, run_id)
        if not fired[0]:  # lần đọc đầu của runs_for_release xong thì luồng khác mở lại và start REL-009
            fired[0] = True
            quality_flow.sync_quality(o)
        return out

    monkeypatch.setattr(ExecutionJournal, "events", racing)
    [(_, status, cand)] = quality_release.runs_for_release(o, "REL-009")
    assert (status, cand) != ("succeeded", sha)
    assert (status, cand) == ("succeeded", old)


def test_cache_da_xong_bi_bo_khi_attempt_moi_dang_chay(tmp_path):
    """sc-security N5 #2: đạt ở A (cache A) → mở lại ở B → B bị huỷ khi đang chạy ⇒ candidate về A. Cache cũ không
    được làm `_sync_project` bỏ qua: A phải được mở lại để chấm."""
    signers = _signers()
    driver = FakeDriver(signers)
    bus, o = _start(tmp_path, driver, trust=write_trust(tmp_path / "trust.json", signers))
    _sign_spec_with_profile(tmp_path, bus, o)
    [(_, first, _)] = driver.calls
    o.quality_driver = None
    _stage(tmp_path, o, "REL-009")
    quality_flow.sync_quality(o)  # B đang chạy, chờ CLI
    o.void_releases.add("REL-009")
    o.quality_driver = driver
    quality_flow.sync_quality(o)  # attempt B đang RUNNING được chấm nốt (core không huỷ được attempt đang chạy)
    rid_a = first.split("@")[0]
    assert quality_release.runs_for_release(o, rid_a)[0][2] != o.release_sha[rid_a], "R6 vẫn chặn A"
    quality_flow.sync_quality(o)  # rồi A được mở lại và chấm, không bị cache cũ nuốt
    assert driver.calls[-1][1] == f"{first}~2"
    assert quality_release.runs_for_release(o, rid_a) == ((RUN, "succeeded", o.release_sha[rid_a]),)


def test_cli_commit_muon_cho_attempt_cu_bi_tu_choi_attempt_moi_van_chay(tmp_path, capsys):
    """Đường thật của N5 #3: CLI nộp kết quả cho A, sync mở lại ở B (chờ CLI), rồi nộp lại đúng tệp kết quả cũ của A."""
    import json

    from company.quality_execution import _result_document
    from company.quality_execution import main as qe_main
    signers = _signers()
    bus, o = _start(tmp_path, None, trust=write_trust(tmp_path / "trust.json", signers))
    _sign_spec_with_profile(tmp_path, bus, o)
    driver = FakeDriver(signers, o=o)
    old_result, old_receipts = driver.run(RUN, ("goal.traceability",))  # kết quả driver cho attempt A
    _stage(tmp_path, o, "REL-009")
    quality_flow.sync_quality(o)  # đã RUNNING ở A nên chưa mở lại; driver None ⇒ A vẫn chờ
    with _journal(tmp_path) as j:
        before = j.events(RUN)
    assert quality_flow.active_bindings(o, RUN).expected_attempt_id == old_result.attempt_id
    # nộp đúng attempt A ⇒ A kết thúc; sync mở lại ở B
    pf = tmp_path / "profile.json"
    files = {"--result": tmp_path / "r.json", "--receipts": tmp_path / "rc.json"}
    files["--result"].write_text(json.dumps(_result_document(old_result)), encoding="utf-8")
    files["--receipts"].write_text(json.dumps([r.model_dump(mode="json") for r in old_receipts]), encoding="utf-8")
    argv = ["commit", RUN, "--journal", str(tmp_path / "c.quality.sqlite"), "--profile", str(pf),
            "--trust", str(tmp_path / "trust.json"), "--evidence-root", str(quality_flow.evidence_root(o, RUN)),
            *[x for k, v in files.items() for x in (k, str(v))]]
    assert qe_main(argv) == 0
    quality_flow.sync_quality(o)
    b = quality_flow.active_bindings(o, RUN)
    assert b.expected_attempt_id.startswith("REL-009@")
    with _journal(tmp_path) as j:
        mid = j.events(RUN)
    assert len(mid) > len(before)
    capsys.readouterr()
    assert qe_main(argv) != 0, "cùng tệp kết quả cũ nộp lại sau khi đã mở lại attempt B"
    with _journal(tmp_path) as j:
        assert j.events(RUN) == mid, "không ghi gì"
        assert j.resume(RUN).tasks[QUALITY_TASK_ID] is TaskStatus.RUNNING


# ---------- ADR gốc 0022 phương án (a): cờ reopenable, run đăng ký trước N5 giữ hành vi cũ ----------

def test_compile_execution_danh_dau_quality_accept_reopenable_ban_legacy_giu_byte():
    from company.quality_execution import compile_execution
    from test_product_quality import make_profile
    from test_quality_execution import work_for
    profile = make_profile()
    new, legacy = compile_execution(profile, work_for(profile)), compile_execution(profile, work_for(profile),
                                                                                    reopenable=False)
    assert [t.task_id for t in new.tasks if t.reopenable] == [QUALITY_TASK_ID]
    assert not any(t.reopenable for t in legacy.tasks) and "reopenable" not in legacy.to_json()


def test_run_dang_ky_truoc_n5_khong_mo_lai_r6_van_chan_va_khong_sync_error(tmp_path, monkeypatch):
    from company.quality_execution import compile_execution
    signers = _signers()
    driver = FakeDriver(signers)
    bus, o = _start(tmp_path, driver, trust=write_trust(tmp_path / "trust.json", signers))
    with monkeypatch.context() as m:  # đăng ký như code trước N5: không có cờ reopenable
        m.setattr(quality_flow, "compile_execution", lambda p, w, **_: compile_execution(p, w, reopenable=False))
        _sign_spec_with_profile(tmp_path, bus, o)
    [(_, first, _)] = driver.calls
    with _journal(tmp_path) as j:
        assert not any(t.reopenable for t in j.load_spec(RUN).tasks), "spec cũ giữ nguyên, không migrate"
        assert j.resume(RUN).status is RunStatus.SUCCEEDED
    old = first.split("@")[1]
    sha = _stage(tmp_path, o, "REL-009")
    quality_flow.sync_quality(o)
    assert len(driver.calls) == 1, "run cũ không mở lại"
    assert not [e for e in bus.replay(topic="audit-log") if e.payload.get("action") == "quality.sync_error"]
    assert quality_release.runs_for_release(o, "REL-009") == ((RUN, "succeeded", old),)
    assert old != sha, "R6 thấy đạt ở sha cũ ⇒ gap cho REL-009"
