"""Công ty GIẢ dùng chung cho mọi ca của core: hai topic, một `Envelope` con, một `CoreConfig` trong tmp_path.

Core không được biết tên topic của company hay của studio, nên test của core cũng không được mượn chúng
(bài học K3.3c2). Từ K3.5c có hai module dùng chung bộ này (`test_bus.py`, `test_sqlite_bus.py`), nên nó ở
`conftest.py` thay vì ở một test module rồi module kia nhập chéo.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel

from xagents_core.config import CoreConfig, TopicACL
from xagents_core.events import Envelope


class FakeEnvelope(Envelope):
    topic: Literal["ban-tin", "audit-log", "shared-context", "noi-bo"]


class BanTin(BaseModel):
    tieu_de: str


def _schema(topic: str, payload: dict) -> dict:
    return {"type": "object", "additionalProperties": False,
            "required": ["event_id", "topic", "key", "actor", "ts", "payload"],
            "properties": {"event_id": {"type": "string"}, "topic": {"const": topic}, "key": {"type": "string"},
                           "actor": {"type": "string"}, "ts": {"type": "string"},
                           "schema_version": {"type": "integer", "minimum": 1},
                           "correlation_id": {"type": "string"},
                           "causation_id": {"type": ["string", "null"]},
                           "payload": payload}}


@pytest.fixture
def cfg(tmp_path):
    d = tmp_path / "topics" / "schemas"; d.mkdir(parents=True)
    (d / "ban-tin.json").write_text(json.dumps(_schema("ban-tin", {
        "type": "object", "required": ["tieu_de"], "additionalProperties": False,
        "properties": {"tieu_de": {"type": "string"}, "ghi_chu": {"type": ["string", "null"]}}})), encoding="utf-8")
    (d / "audit-log.json").write_text(json.dumps(_schema("audit-log", {
        "type": "object", "required": ["actor", "action"],
        "properties": {"actor": {"type": "string"}, "action": {"type": "string"}, "evidence": {"type": "string"}}})),
        encoding="utf-8")
    (d / "shared-context.json").write_text(json.dumps(_schema("shared-context", {
        "type": "object", "required": ["namespace"], "properties": {"namespace": {"type": "string"}}})), encoding="utf-8")
    (d / "noi-bo.json").write_text(json.dumps(_schema("noi-bo", {"type": "object"})), encoding="utf-8")
    return CoreConfig(prefix="FAKE", root=tmp_path, db_name="fake.sqlite",
                      topic_acl=TopicACL(producers={"ban-tin": frozenset({"bien-tap"}), "noi-bo": frozenset({"bien-tap"})},
                                         human_topics=frozenset({"ban-tin"}),
                                         open_topics=frozenset({"audit-log", "shared-context"})),
                      payload_models={"ban-tin": BanTin},
                      namespace_owners={"giong": {"bien-tap"}})


def _tin(actor="bien-tap", **kw):
    return FakeEnvelope(**{"topic": "ban-tin", "key": "B1", "actor": actor, "payload": {"tieu_de": "t"}, **kw})


@pytest.fixture(autouse=True)
def home_rieng(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """MỌI ca chạy với `$HOME` riêng — bộ test không bao giờ đọc cấu hình thật của người đang chạy nó.

    Từ ADR-0016, `load_config()` đọc tầng máy ở `~/.config/xagents/llm.yaml` **dù có truyền `path` hay không**.
    Nên bất kỳ ca nào chạm `load_config`/`explain_config` mà không tự đặt `XAGENTS_LLM_CONFIG` đều lệ thuộc vào
    việc máy chạy test có file ấy hay không. Đo 2026-09-15 ngay sau khi tạo file theo đúng ADR: 3 ca đỏ, trong
    đó `test_khong_co_file_thi_van_ra_cau_hinh_mac_dinh` có từ TRƯỚC ADR-0016 — tức bản vá cũ làm hỏng phép thử
    cũ mà CI không thấy.

    Vì sao đặt ở `conftest.py` chứ không vá từng ca: xanh trên CI (máy sạch) và đỏ trên máy người phát triển đã
    làm theo ADR — cổng phạt đúng người làm đúng, ở chỗ khó đoán nhất. Vá từng ca thì ca thứ tư chỉ là chuyện
    thời gian.

    Ca nào cần một tầng máy THẬT vẫn tự trỏ `XAGENTS_LLM_CONFIG` vào `tmp_path`; fixture này không đụng tới.
    """
    # Tao MOT lan roi tra ve chinh no: `mktemp` goi moi lan mot thu muc khac, nen `Path.home()` trong test
    # va `Path.home()` ben trong `may_config_file` se ra hai duong dan khac nhau — dung cai bay minh vua chan.
    nha = tmp_path_factory.mktemp("home")
    monkeypatch.setattr(Path, "home", lambda: nha)
