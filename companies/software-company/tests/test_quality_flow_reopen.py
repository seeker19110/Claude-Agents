"""ADR gốc 0022 (N5): `quality:accept` được chấm lại khi candidate đổi, kể cả sau khi đã SUCCEEDED, và attempt
luôn có định danh mới khi candidate quay về một RC đã chấm. Receipt là fixture tổng hợp (xem test_quality_flow)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from xagents_core.execution import ExecutionEventKind, RunStatus, TaskStatus

from company.orch import quality_flow
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
    assert quality_flow.runs_for_release(o, "REL-009") == ((RUN, "succeeded", sha),)


def test_mo_lai_ma_chua_co_ket_qua_moi_thi_r6_van_thay_running(tmp_path):
    signers = _signers()
    driver = FakeDriver(signers)
    bus, o = _start(tmp_path, driver, trust=write_trust(tmp_path / "trust.json", signers))
    _sign_spec_with_profile(tmp_path, bus, o)
    o.quality_driver = None  # attempt mới chờ CLI commit
    sha = _stage(tmp_path, o, "REL-009")
    quality_flow.sync_quality(o)
    assert quality_flow.runs_for_release(o, "REL-009") == ((RUN, "running", sha),)


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
    assert quality_flow.runs_for_release(o, o.lead.releases[0])[0][1] == "succeeded"
