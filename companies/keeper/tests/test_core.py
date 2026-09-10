from __future__ import annotations

from pathlib import Path

import keeper.core
from keeper.core import CORE


def test_prefix_la_keeper():
    assert CORE.prefix == "KEEPER"


def test_root_la_thu_muc_keeper_chua_pyproject():
    assert CORE.root.name == "keeper"
    assert (CORE.root / "pyproject.toml").is_file()


def test_parents_1_la_src_khong_phai_root():
    # Ca chiều ngược THẬT: tính lại `parents[1]` từ chính file `core.py` (cách `CORE.root` được tính, chỉ khác
    # chỉ số) và chứng minh nó KHÔNG dùng được làm root — thiếu cả ba thứ `CoreConfig` đi tìm ở đó.
    # Đổi `parents[2]` thành `parents[1]` trong `core.py` sẽ làm `test_root_la_thu_muc_keeper_chua_pyproject` đỏ;
    # test này nói rõ VÌ SAO đỏ, để người sửa không đi tìm nhầm chỗ.
    parents_1 = Path(keeper.core.__file__).resolve().parents[1]
    assert parents_1.name == "src"
    assert parents_1 != CORE.root
    assert not (parents_1 / "pyproject.toml").is_file()
    assert not (parents_1 / "topics" / "schemas").is_dir()


def test_env_name_ghep_prefix():
    assert CORE.env_name("GATE_APPROVERS") == "KEEPER_GATE_APPROVERS"
    assert CORE.approvers_env == "KEEPER_GATE_APPROVERS"


def test_db_name():
    assert CORE.db_name == "keeper.sqlite"


def test_topic_producers_va_open_topics_khop_moi_schema():
    topics_tren_dia = {p.stem for p in CORE.schema_dir.glob("*.json")}
    from keeper.core import OPEN_TOPICS, TOPIC_PRODUCERS
    assert set(TOPIC_PRODUCERS) | OPEN_TOPICS == topics_tren_dia


def test_human_topics_dung_bang_dac_ta():
    from keeper.core import HUMAN_TOPICS
    assert HUMAN_TOPICS == frozenset({"maintenance-signals"})
