"""BT7 — vòng lặp `watch → triage → patch → verify → gate? → release`.

Mọi ca dựng bus SQLite trong `tmp_path` và dùng `FakeGitHub` (không chạm mạng, không gọi `gh`). Không ca nào
rẽ theo `os.name` hay biến môi trường.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from keeper.events import RunOutcome, Signal
from keeper.evidence import TRUSTED_VERIFIER, EvidenceError, TwoWayEvidence
from keeper.fakes import FakeGitHub
from keeper.gates import request_gate
from keeper.orchestrator import HUMAN_ONLY, KeeperOrchestrator

NOW = datetime(2026, 9, 9, tzinfo=UTC)


class _GH(FakeGitHub):
    """Ngân sách RỘNG: không PR nào đang mở, không PR nào đã gộp trong tuần."""

    def __init__(self, open_prs: int = 0) -> None:
        super().__init__()
        self._open = open_prs

    def open_prs(self):
        return super().open_prs()[: self._open]

    def merged_prs(self, since: str):
        super().merged_prs(since)
        return []


def _orc(tmp_path: Path, gh: _GH | None = None) -> KeeperOrchestrator:
    return KeeperOrchestrator(tmp_path / "keeper.sqlite", tmp_path / "repo", gh or _GH())


def _signal(**kw) -> Signal:
    base = {"subject": "requests", "kind": "dependency", "detail": "bump", "semver_jump": "major"}
    base.update(kw)
    return Signal.model_validate(base)


def _evidence(ok: bool = True) -> TwoWayEvidence:
    cmd = "uv run pytest -q"
    return TwoWayEvidence(
        cmd=cmd,
        before=RunOutcome(cmd=cmd, exit_code=1 if ok else 0),
        after=RunOutcome(cmd=cmd, exit_code=0),
        verified_by=TRUSTED_VERIFIER,
    )


def _verify(o: KeeperOrchestrator, ticket_id: str) -> None:
    o.record_verification(ticket_id, {"ticket_id": ticket_id}, _evidence())


# ---------- triage ----------

def test_signal_thanh_ticket_mot_lan_du_phat_lai(tmp_path: Path):
    o = _orc(tmp_path)
    o.submit_signal(_signal())
    o.submit_signal(_signal())
    assert [t.risk_tier for t in o.tick(now=NOW).tickets] == ["high"]
    assert o.tick(now=NOW).tickets == []


def test_signal_cham_agents_thanh_ticket_high_cho_nguoi(tmp_path: Path):
    o = _orc(tmp_path)
    o.submit_signal(_signal(subject="software-company/agents/builder.md", kind="drift", semver_jump=None))
    (t,) = o.tick(now=NOW).tickets
    assert t.risk_tier == "high" and t.requires_gate and HUMAN_ONLY in o.pr_blockers(t)


# ---------- cổng gate: tier high phải có gate approved ----------

def test_tier_high_chua_co_gate_approved_thi_khong_mo_pr(tmp_path: Path):
    o = _orc(tmp_path)
    o.submit_signal(_signal())
    (t,) = o.tick(now=NOW).tickets
    _verify(o, t.ticket_id)
    assert "gate" in o.pr_blockers(t)
    assert o.open_pr(t) is None and o.notes == {}
    assert t.ticket_id in o.gate.pending, "gate phải được XIN, không im lặng bỏ ticket"


def test_tier_high_da_approve_thi_mo_pr(tmp_path: Path):
    o = _orc(tmp_path)
    o.submit_signal(_signal())
    (t,) = o.tick(now=NOW).tickets
    _verify(o, t.ticket_id)
    o.tick(now=NOW)  # xin gate
    o.gate.decide(t.ticket_id, "approve", by="human:pm", reason="đã soi bằng chứng hai chiều")
    assert o.pr_blockers(t) == []
    note = o.open_pr(t)
    assert note is not None and note.ticket_id == t.ticket_id and o.notes[t.ticket_id] == note


def test_tier_thap_khong_can_gate(tmp_path: Path):
    o = _orc(tmp_path)
    o.submit_signal(_signal(semver_jump=None))
    (t,) = o.tick(now=NOW).tickets
    assert t.risk_tier == "medium" and not t.requires_gate
    _verify(o, t.ticket_id)
    assert o.pr_blockers(t) == [] and o.open_pr(t) is not None


# ---------- cổng bằng chứng hai chiều (I2) ----------

def test_thieu_bang_chung_thi_ticket_khong_roi_pha_quality(tmp_path: Path):
    o = _orc(tmp_path)
    o.submit_signal(_signal(semver_jump=None))
    (t,) = o.tick(now=NOW).tickets
    assert "evidence" in o.pr_blockers(t) and o.open_pr(t) is None


def test_bang_chung_hong_bi_tu_choi_va_ticket_van_ket(tmp_path: Path):
    """`before.exit_code == 0` = tắt bản sửa mà CI vẫn xanh ⇒ báo cáo vô hiệu (I2)."""
    o = _orc(tmp_path)
    o.submit_signal(_signal(semver_jump=None))
    (t,) = o.tick(now=NOW).tickets
    with pytest.raises(EvidenceError):
        o.record_verification(t.ticket_id, {"ticket_id": t.ticket_id}, _evidence(ok=False))
    assert "evidence" in o.pr_blockers(t) and o.open_pr(t) is None


# ---------- cổng ngân sách (I3) ----------

def test_ngan_sach_het_cho_thi_khong_mo_pr_du_moi_thu_khac_san_sang(tmp_path: Path):
    o = _orc(tmp_path, _GH(open_prs=1))
    o.submit_signal(_signal(semver_jump=None))
    (t,) = o.tick(now=NOW).tickets
    _verify(o, t.ticket_id)
    assert o.pr_blockers(t) == ["budget"] and o.open_pr(t) is None


# ---------- đường cấm: agents/skills không tự làm ----------

def test_ticket_cham_agents_khong_bao_gio_mo_pr_du_gate_da_approve(tmp_path: Path):
    o = _orc(tmp_path)
    o.submit_signal(_signal(subject="keeper/skills/va-loi.md", kind="drift", semver_jump=None))
    (t,) = o.tick(now=NOW).tickets
    _verify(o, t.ticket_id)
    o.tick(now=NOW)
    o.gate.decide(t.ticket_id, "approve", by="human:pm", reason="người sẽ tự làm bảy bước")
    assert o.pr_blockers(t) == [HUMAN_ONLY] and o.open_pr(t) is None


# ---------- resume ----------

def test_resume_tu_cung_file_sqlite_giu_nguyen_trang_thai(tmp_path: Path):
    o1 = _orc(tmp_path)
    o1.submit_signal(_signal(semver_jump=None))
    (t,) = o1.tick(now=NOW).tickets
    _verify(o1, t.ticket_id)
    o1.open_pr(t)

    o2 = _orc(tmp_path)
    assert set(o2.tickets) == set(o1.tickets)
    assert o2.verified == o1.verified
    assert set(o2.notes) == set(o1.notes)
    assert o2.triage.seen == o1.triage.seen
    assert o2.tick(now=NOW).tickets == [], "signal cũ không được thành ticket lần hai sau restart"


def test_resume_giu_gate_dang_cho(tmp_path: Path):
    o1 = _orc(tmp_path)
    o1.submit_signal(_signal())
    (t,) = o1.tick(now=NOW).tickets
    o1.tick(now=NOW)
    assert t.ticket_id in o1.gate.pending
    o2 = _orc(tmp_path)
    assert t.ticket_id in o2.gate.pending


# ---------- vòng tick / watch ----------

def test_tick_mo_pr_khi_moi_cong_da_qua(tmp_path: Path):
    o = _orc(tmp_path)
    o.submit_signal(_signal(semver_jump=None))
    (t,) = o.tick(now=NOW).tickets
    _verify(o, t.ticket_id)
    res = o.tick(now=NOW)
    assert res.notes and res.notes[0].ticket_id == t.ticket_id
    assert o.tick(now=NOW).notes == [], "một ticket chỉ mở PR một lần"


def test_watch_chay_du_so_nhip(tmp_path: Path):
    o = _orc(tmp_path)
    o.submit_signal(_signal(semver_jump=None))
    o.watch(interval=0.0, max_ticks=2)
    assert o.tickets and o.ticks == 2


def test_mot_nhip_loi_khong_giet_vong_watch(tmp_path: Path, monkeypatch):
    o = _orc(tmp_path)
    goi: list[int] = []

    def _no(now=None):
        goi.append(1)
        raise RuntimeError("bus hỏng")

    monkeypatch.setattr(o, "tick", _no)
    o.watch(interval=0.0, max_ticks=2)
    assert len(goi) == 2
    actions = [a.payload["action"] for a in o.bus.replay(topic="audit-log")]
    assert "tick_error" in actions


def test_request_gate_chi_xin_mot_lan(tmp_path: Path):
    o = _orc(tmp_path)
    o.submit_signal(_signal())
    (t,) = o.tick(now=NOW).tickets
    o.tick(now=NOW)
    seq = o.gate.pending[t.ticket_id].seq
    o.tick(now=NOW)
    assert o.gate.pending[t.ticket_id].seq == seq


def test_gate_da_xin_boi_nguoi_thi_orchestrator_khong_xin_lai(tmp_path: Path):
    o = _orc(tmp_path)
    o.submit_signal(_signal())
    (t,) = o.tick(now=NOW).tickets
    request_gate(o.gate, "patch", t.ticket_id, created_by="human:seeker")
    o.tick(now=NOW)
    assert o.gate.pending[t.ticket_id].created_by == "human:seeker"


# ---------- nối vào CLI ----------

def test_cli_watch_dung_orchestrator_va_khong_cham_gh(tmp_path: Path, monkeypatch, capsys):
    """`keeper watch` phải dựng `GitHubReader` (chỉ đọc) và gọi `watch()`. Ca này thay cả hai bằng bản giả:
    không tiến trình `gh` nào được sinh ra, và không ca nào phụ thuộc `gh auth` của máy."""
    from keeper import cli as cli_mod

    goi: dict[str, object] = {}

    class _Reader:
        def __init__(self, repo):
            goi["repo"] = repo

    class _Orc:
        def __init__(self, db, repo, gh):
            goi["db"], goi["gh"] = db, gh

        def watch(self, interval, max_ticks):
            goi["watch"] = (interval, max_ticks)

    monkeypatch.setattr("keeper.github.GitHubReader", _Reader)
    monkeypatch.setattr("keeper.orchestrator.KeeperOrchestrator", _Orc)
    rc = cli_mod.main(["watch", "--db", str(tmp_path / "k.sqlite"), "--repo", str(tmp_path),
                       "--interval", "0", "--max-ticks", "1"])
    assert rc == 0 and goi["watch"] == (0.0, 1) and isinstance(goi["gh"], _Reader)
