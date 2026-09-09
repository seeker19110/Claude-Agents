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
