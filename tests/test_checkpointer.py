"""Lịch sử hội thoại phải sống sót qua restart tiến trình (SQLite), không chỉ nằm trong RAM."""
import os

from langgraph.checkpoint.memory import MemorySaver

from src.graph import GRAPH_CONFIG, build_checkpointer
from src.config import settings


def test_sqlite_checkpointer_is_used_when_configured(tmp_path):
    db = tmp_path / "checkpoints.sqlite"
    saver = build_checkpointer(str(db))
    assert type(saver).__name__ == "SqliteSaver"
    assert os.path.exists(db)


def test_parent_directory_is_created_automatically(tmp_path):
    db = tmp_path / "chua_ton_tai" / "cp.sqlite"
    build_checkpointer(str(db))
    assert db.parent.is_dir()


def test_empty_path_falls_back_to_in_memory():
    assert isinstance(build_checkpointer(""), MemorySaver)


def test_unusable_path_falls_back_instead_of_crashing(tmp_path):
    """Đĩa chỉ đọc / đường dẫn hỏng không được làm sập ứng dụng."""
    blocker = tmp_path / "la_mot_file"
    blocker.write_text("x")
    saver = build_checkpointer(str(blocker / "khong_the_tao" / "cp.sqlite"))
    assert isinstance(saver, MemorySaver)


def test_recursion_limit_is_centralised():
    """Chốt chặn cuối cùng chống vòng lặp vô tận, dùng chung cho cả app.py và main.py."""
    assert GRAPH_CONFIG["recursion_limit"] == settings.recursion_limit
    assert settings.recursion_limit > 0
