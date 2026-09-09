from __future__ import annotations

import shutil
from dataclasses import replace
from typing import get_args

import pytest
from xagents_core.bus import BusError, PermissionDenied
from xagents_core.bus import InMemoryBus as CoreInMemoryBus

from keeper.core import CORE
from keeper.events import Envelope, Topic


class _Bus(CoreInMemoryBus[Envelope]):
    envelope_cls = Envelope


def _bus(**kw) -> _Bus:
    return _Bus(CORE, **kw)


def _signal(**kw):
    base = {"subject": "requests", "kind": "dependency", "detail": "bump patch"}
    base.update(kw)
    return base


def test_moi_topic_co_schema_dung_khuon_studio():
    bus = _bus()
    assert set(get_args(Topic)) == set(bus._schemas)


def test_thieu_mot_file_schema_thi_phep_so_o_test_tren_do(tmp_path):
    """Ca chiều ngược của test trên, đo bằng mã THẬT: dựng một `CoreConfig` có `schema_dir` thiếu đúng một file,
    nạp bus từ đó, và phép so `set(get_args(Topic)) == set(bus._schemas)` phải SAI. Không mô phỏng bằng tập giả —
    tập giả thì assert thành hằng đúng và không chạm dòng mã nào."""
    schemas = tmp_path / "topics" / "schemas"
    schemas.mkdir(parents=True)
    goc = sorted(CORE.schema_dir.glob("*.json"))
    assert len(goc) == len(get_args(Topic))          # canh: nguồn phải đủ trước khi cố tình bỏ bớt
    for p in goc[1:]:                                # chép mọi file TRỪ cái đầu
        shutil.copy(p, schemas / p.name)
    thieu = replace(CORE, root=tmp_path)
    bus = _Bus(thieu)
    assert set(get_args(Topic)) != set(bus._schemas)
    assert goc[0].stem not in bus._schemas


def test_publish_signal_hop_le():
    bus = _bus()
    bus.publish(Envelope(topic="maintenance-signals", key="requests", actor="dependency-scout",
                         payload=_signal()))
    assert len(bus) == 1


def test_publish_payload_thieu_truong_bat_buoc_bi_choi():
    bus = _bus()
    with pytest.raises(BusError):
        bus.publish(Envelope(topic="maintenance-signals", key="requests", actor="dependency-scout",
                             payload={"subject": "requests"}))


def test_maintenance_tickets_chi_triager_duoc_phat():
    bus = _bus()
    with pytest.raises(PermissionDenied):
        bus.publish(Envelope(topic="maintenance-tickets", key="requests", actor="human",
                             payload={"ticket_id": "T1", "subject": "requests", "risk_tier": "low"}))
    bus.publish(Envelope(topic="maintenance-tickets", key="requests", actor="triager",
                         payload={"ticket_id": "T1", "subject": "requests", "risk_tier": "low"}))
    # 2 = một `audit-log` "publish_denied" do bus tự ghi khi từ chối lần đầu + một `maintenance-tickets` hợp lệ.
    assert len(bus) == 2


def test_maintenance_signals_nguoi_nap_tay_duoc_human_topics():
    bus = _bus()
    bus.publish(Envelope(topic="maintenance-signals", key="requests", actor="human",
                         payload=_signal()))
    assert len(bus) == 1


def test_shared_context_theo_chu_namespace():
    bus = _bus()
    ok = {"namespace": "knowledge", "key": "k", "version": 1, "content_ref": "ctx/knowledge/k.md"}
    bus.publish(Envelope(topic="shared-context", key="knowledge/k", actor="keeper-supervisor", payload=ok))
    with pytest.raises(PermissionDenied):
        bus.publish(Envelope(topic="shared-context", key="knowledge/k", actor="triager", payload=ok))


def test_audit_log_mo_cho_moi_actor():
    bus = _bus()
    bus.publish(Envelope(topic="audit-log", key="x", actor="bat-ky-ai",
                         payload={"actor": "bat-ky-ai", "action": "noop"}))
    assert len(bus) == 1
