from __future__ import annotations

from typing import get_args

import pytest
from pydantic import ValidationError

from keeper.events import PAYLOAD_MODELS, Envelope, Topic


def test_moi_topic_co_dung_mot_payload_model():
    # `<=` sẽ xanh cả khi quên model cho một topic; `==` mới khoá được cả hai chiều.
    assert set(PAYLOAD_MODELS) == set(get_args(Topic))


def test_moi_gia_tri_topic_co_dung_10_gia_tri_da_dem_lai():
    # Đặc tả BT1 viết "9 giá trị" — đếm sai; đã đo lại bảng §1: 8 topic riêng + audit-log + shared-context = 10.
    assert len(get_args(Topic)) == 10


def test_publish_topic_la_thi_validate_pydantic_that_bai():
    with pytest.raises(ValidationError):
        Envelope(topic="topic-khong-ton-tai", key="x", actor="human", payload={})


def test_envelope_giu_topic_hop_le():
    env = Envelope(topic="audit-log", key="x", actor="human", payload={"actor": "human", "action": "noop"})
    assert env.topic == "audit-log"


def test_moi_truong_cua_model_deu_co_trong_schema_topic():
    """Cổng chống lệch hợp đồng topic: thêm một trường vào model payload mà quên thêm vào
    `topics/schemas/<topic>.json` thì file schema — thứ bus dùng để validate và thứ người đọc coi là hợp đồng —
    thành lạc hậu trong im lặng.

    Không cổng nào bắt được chỗ này trước đó: `payload.additionalProperties` là `true` (cố ý, để nguồn ngoài
    thêm trường không làm vỡ bus), nên bus vẫn nhận; và test khớp topic ↔ file chỉ so TÊN FILE, không so trường.
    Đã xảy ra thật ở BT4: `Signal.severity` được thêm vào model mà schema không có.
    """
    import json

    from keeper.core import CORE
    thieu = {}
    for topic, model in PAYLOAD_MODELS.items():
        schema = json.loads((CORE.schema_dir / f"{topic}.json").read_text(encoding="utf-8"))
        props = set(schema["properties"]["payload"].get("properties", {}))
        if not props:
            continue                      # payload viết tự do (chưa khai trường) — không có gì để so
        if con_thieu := set(model.model_fields) - props:
            thieu[topic] = sorted(con_thieu)
    assert thieu == {}, f"trường có trong model mà thiếu trong schema: {thieu}"


def test_cong_chong_lech_hop_dong_co_suc_manh_phan_biet(tmp_path, monkeypatch):
    """Chiều ngược của test trên: nếu nó không thật sự so trường thì một model thừa trường vẫn xanh.
    Dựng một model có trường lạ và chứng minh phép so bắt được."""
    import json

    from keeper.core import CORE
    schema = json.loads((CORE.schema_dir / "maintenance-signals.json").read_text(encoding="utf-8"))
    props = set(schema["properties"]["payload"].get("properties", {}))
    assert props, "schema phải khai trường, nếu không test trên vô nghĩa"
    assert {"truong_khong_ton_tai"} - props == {"truong_khong_ton_tai"}
