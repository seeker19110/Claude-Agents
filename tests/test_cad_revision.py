"""Theo dõi phiên bản bản vẽ: các tool sửa CAD ghi đè tại chỗ, phải luôn có đường lùi."""
import ezdxf
import pytest

from src.cad_revision import (
    _read_history, create_snapshot, diff_cad_revisions, list_cad_revisions,
    restore_cad_revision, snapshot_cad, summarize_drawing,
)
from src.workspace import resolve_safe_path, set_workspace_dir


@pytest.fixture
def workspace(tmp_path):
    set_workspace_dir(str(tmp_path))
    return tmp_path


def _make_dxf(path, lines=(), blocks=()):
    doc = ezdxf.new()
    msp = doc.modelspace()
    for name in {b[0] for b in blocks}:
        block = doc.blocks.new(name=name)
        block.add_circle((0, 0), radius=50)
    for layer, start, end in lines:
        if layer not in doc.layers:
            doc.layers.add(layer)
        msp.add_line(start, end, dxfattribs={"layer": layer})
    for name, point in blocks:
        msp.add_blockref(name, point)
    doc.saveas(path)


def test_snapshot_creates_a_revision(workspace):
    _make_dxf(workspace / "bv.dxf", lines=[("PIPE", (0, 0), (10, 0))])
    result = snapshot_cad.invoke({"file_path": "bv.dxf", "note": "trước khi sửa"})
    assert "Đã lưu phiên bản" in result
    assert "trước khi sửa" in result


def test_snapshot_of_missing_file_is_reported(workspace):
    assert "Không tìm thấy file" in snapshot_cad.invoke({"file_path": "khong_co.dxf"})


def test_history_lists_revisions_in_order(workspace):
    _make_dxf(workspace / "bv.dxf", lines=[("PIPE", (0, 0), (10, 0))])
    create_snapshot("bv.dxf", "lần 1")
    create_snapshot("bv.dxf", "lần 2")
    result = list_cad_revisions.invoke({"file_path": "bv.dxf"})
    assert "2 phiên bản" in result
    assert result.index("lần 1") < result.index("lần 2")


def test_history_is_empty_before_any_snapshot(workspace):
    _make_dxf(workspace / "bv.dxf", lines=[("PIPE", (0, 0), (10, 0))])
    assert "chưa có phiên bản nào" in list_cad_revisions.invoke({"file_path": "bv.dxf"})


def test_diff_reports_added_blocks_and_length_changes(workspace):
    path = workspace / "bv.dxf"
    _make_dxf(path, lines=[("PIPE", (0, 0), (10, 0))], blocks=[("SPRINKLER", (1, 1))])
    create_snapshot("bv.dxf", "gốc")

    # Sửa bản vẽ: thêm 1 sprinkler và kéo dài tuyến ống.
    _make_dxf(path, lines=[("PIPE", (0, 0), (30, 0))],
              blocks=[("SPRINKLER", (1, 1)), ("SPRINKLER", (5, 5))])

    result = diff_cad_revisions.invoke({"file_path": "bv.dxf"})
    assert "SPRINKLER: 1 -> 2 (+1)" in result
    assert "PIPE: 10.00 -> 30.00 (+20.00)" in result


def test_diff_detects_no_change(workspace):
    _make_dxf(workspace / "bv.dxf", lines=[("PIPE", (0, 0), (10, 0))])
    create_snapshot("bv.dxf")
    result = diff_cad_revisions.invoke({"file_path": "bv.dxf"})
    assert "GIỐNG NHAU" in result


def test_diff_reports_layer_additions_and_removals(workspace):
    path = workspace / "bv.dxf"
    _make_dxf(path, lines=[("PIPE_CU", (0, 0), (10, 0))])
    create_snapshot("bv.dxf")
    _make_dxf(path, lines=[("PIPE_MOI", (0, 0), (10, 0))])

    result = diff_cad_revisions.invoke({"file_path": "bv.dxf"})
    assert "PIPE_MOI" in result.split("LAYER ĐƯỢC THÊM")[1]
    assert "PIPE_CU" in result.split("LAYER BỊ XÓA")[1]


def test_diff_without_snapshot_tells_user_what_to_do(workspace):
    _make_dxf(workspace / "bv.dxf", lines=[("PIPE", (0, 0), (10, 0))])
    assert "snapshot_cad" in diff_cad_revisions.invoke({"file_path": "bv.dxf"})


def test_diff_with_unknown_revision_name(workspace):
    _make_dxf(workspace / "bv.dxf", lines=[("PIPE", (0, 0), (10, 0))])
    create_snapshot("bv.dxf")
    result = diff_cad_revisions.invoke({"file_path": "bv.dxf", "revision_a": "rev_khong_co.dxf"})
    assert "Không tìm thấy phiên bản" in result


def test_restore_brings_back_the_earlier_drawing(workspace):
    path = workspace / "bv.dxf"
    _make_dxf(path, lines=[("PIPE", (0, 0), (10, 0))])
    rev = create_snapshot("bv.dxf", "bản gốc")

    _make_dxf(path, lines=[("PIPE", (0, 0), (99, 0))])   # sửa hỏng
    assert summarize_drawing(str(path))["lengths"]["PIPE"] == 99.0

    result = restore_cad_revision.invoke({"file_path": "bv.dxf", "revision": rev})
    assert "Đã khôi phục" in result
    assert summarize_drawing(str(path))["lengths"]["PIPE"] == 10.0


def test_restore_is_itself_undoable(workspace):
    """Trước khi ghi đè, bản hiện tại cũng được lưu lại — khôi phục nhầm vẫn quay lại được."""
    path = workspace / "bv.dxf"
    _make_dxf(path, lines=[("PIPE", (0, 0), (10, 0))])
    create_snapshot("bv.dxf")
    _make_dxf(path, lines=[("PIPE", (0, 0), (50, 0))])

    result = restore_cad_revision.invoke({"file_path": "bv.dxf"})
    assert "đã được lưu thành" in result
    assert len(list_cad_revisions.invoke({"file_path": "bv.dxf"}).splitlines()) >= 3


def test_restore_without_history_is_reported(workspace):
    _make_dxf(workspace / "bv.dxf", lines=[("PIPE", (0, 0), (10, 0))])
    assert "chưa có phiên bản nào" in restore_cad_revision.invoke({"file_path": "bv.dxf"})


def test_edit_tools_snapshot_automatically_before_overwriting(workspace):
    """Regression: `edit_cad`/`optimize_cad_drawing`/`ai_block_recovery` ghi đè file tại
    chỗ — nếu không tự chụp trước thì một lần AI sửa sai là mất bản gốc."""
    from src.tools import optimize_cad_drawing

    path = workspace / "bv.dxf"
    _make_dxf(path, lines=[("PIPE", (0, 0), (10, 0)), ("RAC", (5, 5), (5, 5))])
    optimize_cad_drawing.invoke({"file_path": "bv.dxf"})

    history = list_cad_revisions.invoke({"file_path": "bv.dxf"})
    assert "optimize_cad_drawing" in history


def test_revisions_are_isolated_per_session(tmp_path):
    """Workspace riêng theo phiên => phiên này không thấy revision của phiên khác."""
    set_workspace_dir(str(tmp_path / "phien_a"))
    _make_dxf(resolve_safe_path("bv.dxf"), lines=[("PIPE", (0, 0), (10, 0))])
    create_snapshot("bv.dxf")
    assert "1 phiên bản" in list_cad_revisions.invoke({"file_path": "bv.dxf"})

    set_workspace_dir(str(tmp_path / "phien_b"))
    assert "chưa có phiên bản nào" in list_cad_revisions.invoke({"file_path": "bv.dxf"})


# --- Hạn mức lưu trữ: chỉ giữ N revision gần nhất ---

def test_only_the_configured_number_of_revisions_is_kept(workspace):
    """Mỗi revision là một bản sao .dxf đầy đủ; phiên sửa nhiều lần sẽ phình workspace
    nếu giữ hết."""
    from src.config import settings

    _make_dxf(workspace / "bv.dxf", lines=[("PIPE", (0, 0), (10, 0))])
    for i in range(8):
        create_snapshot("bv.dxf", f"lần {i}")

    assert len(_read_history("bv.dxf")) == settings.max_cad_revisions
    on_disk = [f for f in (workspace / ".revisions" / "bv.dxf").iterdir() if f.suffix == ".dxf"]
    assert len(on_disk) == settings.max_cad_revisions


def test_pruning_keeps_the_newest_revisions(workspace):
    _make_dxf(workspace / "bv.dxf", lines=[("PIPE", (0, 0), (10, 0))])
    for i in range(6):
        create_snapshot("bv.dxf", f"lần {i}")

    notes = [e["ghi_chu"] for e in _read_history("bv.dxf")]
    assert notes == ["lần 3", "lần 4", "lần 5"]


def test_history_never_lists_a_revision_whose_file_was_pruned(workspace):
    """Regression: lịch sử hiển thị phiên bản không còn khôi phục được là tệ hơn cả việc
    không có lịch sử."""
    _make_dxf(workspace / "bv.dxf", lines=[("PIPE", (0, 0), (10, 0))])
    for i in range(10):
        create_snapshot("bv.dxf", f"lần {i}")

    folder = workspace / ".revisions" / "bv.dxf"
    on_disk = {f.name for f in folder.iterdir() if f.suffix == ".dxf"}
    assert {e["revision"] for e in _read_history("bv.dxf")} <= on_disk


def test_revision_names_are_unique_even_within_the_same_millisecond(workspace):
    """Regression: hai snapshot liên tiếp (snapshot_cad rồi edit_cad) có thể rơi vào cùng
    một mili-giây; nếu tên trùng thì bản sau ghi đè bản trước mà lịch sử vẫn ghi hai dòng."""
    _make_dxf(workspace / "bv.dxf", lines=[("PIPE", (0, 0), (10, 0))])
    names = [create_snapshot("bv.dxf", f"lần {i}") for i in range(10)]
    assert len(set(names)) == len(names)


def test_pruning_can_be_disabled(workspace, monkeypatch):
    from src import cad_revision
    from src.config import settings

    monkeypatch.setattr(settings, "max_cad_revisions", 0)
    _make_dxf(workspace / "bv.dxf", lines=[("PIPE", (0, 0), (10, 0))])
    for i in range(6):
        cad_revision.create_snapshot("bv.dxf", f"lần {i}")

    assert len(cad_revision._read_history("bv.dxf")) == 6


def test_restore_still_works_on_the_oldest_kept_revision(workspace):
    """Dọn dẹp không được làm hỏng khả năng khôi phục các bản còn giữ."""
    path = workspace / "bv.dxf"
    _make_dxf(path, lines=[("PIPE", (0, 0), (7, 0))])
    for _ in range(6):
        create_snapshot("bv.dxf")
        _make_dxf(path, lines=[("PIPE", (0, 0), (99, 0))])

    oldest = _read_history("bv.dxf")[0]["revision"]
    result = restore_cad_revision.invoke({"file_path": "bv.dxf", "revision": oldest})
    assert "Đã khôi phục" in result
    assert summarize_drawing(str(path))["lengths"]["PIPE"] == 99.0


def test_snapshot_report_mentions_the_retention_limit(workspace):
    _make_dxf(workspace / "bv.dxf", lines=[("PIPE", (0, 0), (10, 0))])
    assert "phiên bản gần nhất" in snapshot_cad.invoke({"file_path": "bv.dxf"})
