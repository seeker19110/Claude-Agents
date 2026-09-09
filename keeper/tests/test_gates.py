"""BT7 — gate `keeper`: allowlist vai được TẠO gate (ADR-0008), four-eyes, nguồn danh sách người duyệt.

Mọi ca dựng bus trong `tmp_path`; không ca nào đọc `keeper.sqlite` của máy đang chạy.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from xagents_core.gates import GateRequest as CoreGateRequest

from keeper import gates as gates_mod
from keeper.bus import KeeperMemoryBus
from keeper.core import CORE
from keeper.gates import (
    CHECKLIST,
    GATE_ACTOR,
    GateRequest,
    PersistentGate,
    gate_approvers,
    request_gate,
)


def _gate(**kw) -> PersistentGate:
    return PersistentGate(KeeperMemoryBus(CORE), **kw)


# ---------- nguồn danh sách người duyệt: KHÔNG viết cứng tên biến ----------

def test_ten_bien_moi_truong_ghep_tu_core_chu_khong_viet_cung():
    """`CORE.approvers_env` là nơi duy nhất ghép tiền tố (`config.py:85-88`). Ca này đỏ nếu ai đó gõ thẳng
    chuỗi `"KEEPER_GATE_APPROVERS"` vào `gates.py` rồi `prefix` đổi."""
    assert gates_mod.APPROVERS_ENV == CORE.approvers_env == "KEEPER_GATE_APPROVERS"
    assert CORE.approvers_env in PersistentGate.APPROVERS_SOURCE


def test_gate_approvers_doc_bien_moi_truong(monkeypatch):
    monkeypatch.setenv(CORE.approvers_env, "human:a, human:b")
    assert gate_approvers() == frozenset({"human:a", "human:b"})
    monkeypatch.delenv(CORE.approvers_env)
    assert gate_approvers() == frozenset()


# ---------- allowlist vai được TẠO gate ----------

def test_vai_ngoai_allowlist_khong_mo_duoc_gate():
    g = _gate()
    with pytest.raises(PermissionError):
        request_gate(g, "patch", "KEEP:1", created_by="patcher")
    assert g.pending == {}


def test_vai_trong_allowlist_mo_duoc_gate():
    g = _gate()
    r = request_gate(g, "patch", "KEEP:1")
    assert r.created_by == GATE_ACTOR and "KEEP:1" in g.pending and r.checklist == list(CHECKLIST)


def test_bo_allowlist_thi_vai_la_mo_duoc_gate(monkeypatch):
    """Chiều ngược: TẮT chính bản sửa (`REQUEST_ACTORS = None` = hành vi trước ADR-0008) rồi đo lại trên cùng
    đầu vào — `patcher` mở được gate. Không có bản sửa thì hai ca trên xanh vì lý do khác."""
    monkeypatch.setattr(PersistentGate, "REQUEST_ACTORS", None)
    g = _gate()
    request_gate(g, "patch", "KEEP:1", created_by="patcher")
    assert "KEEP:1" in g.pending


def test_nguoi_luon_mo_duoc_gate_du_khong_co_ten_trong_allowlist():
    g = _gate()
    request_gate(g, "escalation", "KEEP:1", created_by="human:seeker")
    assert g.pending["KEEP:1"].created_by == "human:seeker"


# ---------- four-eyes ----------

def test_created_by_rong_bi_chan_ngay_tu_request():
    g = _gate()
    with pytest.raises(PermissionError):
        g.request(GateRequest(kind="patch", subject_id="KEEP:1", checklist=[], created_by=""))
    assert g.pending == {}


def test_tat_kiem_created_by_thi_nguoi_tao_tu_duyet_duoc_gate_cua_minh():
    """Chiều ngược của ca trên: nếu chốt `created_by` KHÔNG có (đúng hình dạng gate lọt vào `pending` với
    `created_by` rỗng), `decide()` cho chính người tạo tự duyệt — four-eyes bị vô hiệu."""
    g = _gate()
    g.pending["KEEP:1"] = GateRequest(kind="patch", subject_id="KEEP:1", checklist=[], created_by="")
    r = g.decide("KEEP:1", "approve", by=GATE_ACTOR, reason="tự duyệt")
    assert r.decision == "approve" and g.is_approved("KEEP:1")


def test_nguoi_duyet_trung_nguoi_tao_bi_tu_choi():
    g = _gate()
    request_gate(g, "patch", "KEEP:1")
    with pytest.raises(PermissionError, match="four-eyes"):
        g.decide("KEEP:1", "approve", by=GATE_ACTOR)


def test_allowlist_nguoi_duyet_chan_nguoi_ngoai_danh_sach():
    g = _gate(approvers={"human:pm"})
    request_gate(g, "patch", "KEEP:1")
    with pytest.raises(PermissionError, match=CORE.approvers_env):
        g.decide("KEEP:1", "approve", by="human:x")


# ---------- gate keeper KHÔNG có khái niệm nghiệm thu ----------

def test_khong_co_uat_prefix():
    assert PersistentGate.UAT_PREFIX is None


def test_gate_request_la_lop_cua_keeper():
    assert issubclass(GateRequest, CoreGateRequest)
    g = _gate()
    request_gate(g, "patch", "KEEP:1")
    assert isinstance(g.pending["KEEP:1"], GateRequest)


# ---------- bền qua tiến trình ----------

def test_gate_dung_lai_duoc_tu_replay(tmp_path: Path):
    from keeper.bus import KeeperBus
    db = tmp_path / "keeper.sqlite"
    g1 = PersistentGate(KeeperBus(CORE, db))
    request_gate(g1, "patch", "KEEP:1")
    g1.decide("KEEP:1", "approve", by="human:pm", reason="ok")
    g2 = PersistentGate(KeeperBus(CORE, db))
    assert g2.is_approved("KEEP:1") and g2.pending == {}
