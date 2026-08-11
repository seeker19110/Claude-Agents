"""Nạp bản vẽ DWG (qua ODA File Converter) và gộp nội dung XREF.

Trước module này: (1) khách gửi .dwg phải tự convert sang .dxf trước khi dùng bất kỳ
tool nào, không có báo lỗi rõ ràng khi thiếu converter; (2) bản vẽ dùng XREF để ghép
nhiều file thì các tool đọc modelspace bỏ sót toàn bộ nội dung nằm trong xref, không có
cảnh báo nào — bóc khối lượng ra một con số thiếu mà tưởng là đủ."""
import math
import os
import subprocess

import ezdxf
import pytest

from src import cad_loader
from src.workspace import resolve_safe_path, set_workspace_dir


@pytest.fixture
def workspace(tmp_path):
    set_workspace_dir(str(tmp_path))
    return tmp_path


def _make_dxf(path, lines=()):
    doc = ezdxf.new()
    msp = doc.modelspace()
    for layer, start, end in lines:
        if layer not in doc.layers:
            doc.layers.add(layer)
        msp.add_line(start, end, dxfattribs={"layer": layer})
    doc.saveas(path)
    return doc


# --- ODA File Converter: phát hiện & thông báo khi thiếu ---

def test_find_oda_converter_returns_empty_when_not_configured(monkeypatch):
    monkeypatch.delenv("ODA_CONVERTER_PATH", raising=False)
    monkeypatch.setattr(cad_loader.shutil, "which", lambda name: None)
    assert cad_loader.find_oda_converter() == ""


def test_find_oda_converter_respects_env_override(monkeypatch, tmp_path):
    fake = tmp_path / "ODAFileConverter"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setenv("ODA_CONVERTER_PATH", str(fake))
    assert cad_loader.find_oda_converter() == str(fake)


def test_convert_dwg_without_converter_raises_actionable_error(monkeypatch):
    monkeypatch.delenv("ODA_CONVERTER_PATH", raising=False)
    monkeypatch.setattr(cad_loader.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError) as exc:
        cad_loader.convert_dwg_to_dxf("khong_ton_tai.dwg")
    assert "ODA File Converter" in str(exc.value)
    assert "opendesign.com" in str(exc.value)


def test_convert_dwg_calls_converter_and_returns_dxf_path(monkeypatch, tmp_path):
    """Giả lập ODA File Converter bằng một script tạo file .dxf rỗng, để kiểm tra luồng
    gọi tiến trình con và xác định đúng đường dẫn kết quả mà không cần cài converter thật."""
    dwg_path = tmp_path / "ban_ve.dwg"
    dwg_path.write_bytes(b"FAKE DWG")

    def fake_run(cmd, check, timeout, stdout, stderr):
        out_dir = cmd[2]
        ezdxf.new().saveas(os.path.join(out_dir, "ban_ve.dxf"))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(cad_loader, "find_oda_converter", lambda: "/fake/ODAFileConverter")
    monkeypatch.setattr(cad_loader.subprocess, "run", fake_run)

    result = cad_loader.convert_dwg_to_dxf(str(dwg_path), output_dir=str(tmp_path / "out"))
    assert result.endswith("ban_ve.dxf")
    assert os.path.exists(result)


def test_convert_dwg_missing_output_raises_with_context(monkeypatch, tmp_path):
    dwg_path = tmp_path / "ban_ve.dwg"
    dwg_path.write_bytes(b"FAKE DWG")

    def fake_run(cmd, check, timeout, stdout, stderr):
        return subprocess.CompletedProcess(cmd, 0)  # không tạo file .dxf nào

    monkeypatch.setattr(cad_loader, "find_oda_converter", lambda: "/fake/ODAFileConverter")
    monkeypatch.setattr(cad_loader.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError) as exc:
        cad_loader.convert_dwg_to_dxf(str(dwg_path), output_dir=str(tmp_path / "out"))
    assert "ban_ve.dxf" in str(exc.value)


def test_convert_dwg_timeout_is_reported(monkeypatch, tmp_path):
    dwg_path = tmp_path / "ban_ve.dwg"
    dwg_path.write_bytes(b"FAKE DWG")

    def fake_run(cmd, check, timeout, stdout, stderr):
        raise subprocess.TimeoutExpired(cmd, timeout)

    monkeypatch.setattr(cad_loader, "find_oda_converter", lambda: "/fake/ODAFileConverter")
    monkeypatch.setattr(cad_loader.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError) as exc:
        cad_loader.convert_dwg_to_dxf(str(dwg_path), output_dir=str(tmp_path / "out"), timeout=5)
    assert "5s" in str(exc.value)


# --- load_drawing: DXF thẳng, DWG tự chuyển, cache lần chuyển sau ---

def test_load_drawing_reads_dxf_directly(workspace):
    _make_dxf(str(workspace / "bv.dxf"), lines=[("PIPE", (0, 0), (10, 0))])
    doc, notes = cad_loader.load_drawing("bv.dxf")
    assert notes == []
    assert doc.modelspace().query("LINE")


def test_load_drawing_converts_dwg_and_notes_it(monkeypatch, workspace):
    dwg_path = workspace / "bv.dwg"
    dwg_path.write_bytes(b"FAKE DWG")

    def fake_convert(path, output_dir=None, timeout=180):
        out = os.path.join(output_dir, "bv.dxf")
        _make_dxf(out, lines=[("PIPE", (0, 0), (10, 0))])
        return out

    monkeypatch.setattr(cad_loader, "convert_dwg_to_dxf", fake_convert)
    doc, notes = cad_loader.load_drawing("bv.dwg")
    assert any("chuyển .dwg sang .dxf" in n for n in notes)
    assert doc.modelspace().query("LINE")
    assert (workspace / "bv.dxf").exists()


def test_load_drawing_reuses_previously_converted_dxf(monkeypatch, workspace):
    """Không convert lại nếu bản .dxf đã có và mới hơn file .dwg gốc — tránh gọi converter
    tốn thời gian mỗi lần agent đọc lại cùng một bản vẽ."""
    dwg_path = workspace / "bv.dwg"
    dwg_path.write_bytes(b"FAKE DWG")
    _make_dxf(str(workspace / "bv.dxf"), lines=[("PIPE", (0, 0), (5, 0))])

    calls = []
    monkeypatch.setattr(cad_loader, "convert_dwg_to_dxf", lambda *a, **k: calls.append(1))

    doc, notes = cad_loader.load_drawing("bv.dwg")
    assert calls == []
    assert any("Dùng lại bản .dxf" in n for n in notes)


# --- XREF: gộp nội dung, hoặc báo rõ khi thiếu file ---

def test_list_xrefs_finds_declared_external_reference():
    doc = ezdxf.new()
    doc.blocks.new("REF1", dxfattribs={"flags": 4, "xref_path": "other.dxf"})
    xrefs = cad_loader.list_xrefs(doc)
    assert xrefs == [("REF1", "other.dxf")]


def test_list_xrefs_ignores_normal_blocks():
    doc = ezdxf.new()
    doc.blocks.new("NORMAL_BLOCK")
    assert cad_loader.list_xrefs(doc) == []


def test_resolve_xref_segments_missing_file_is_reported_not_silently_skipped(workspace):
    """Regression: bỏ sót một xref không tìm thấy file phải được NÊU RÕ, chứ không được
    âm thầm cho ra khối lượng thiếu."""
    doc = ezdxf.new()
    doc.blocks.new("REF1", dxfattribs={"flags": 4, "xref_path": "khong_ton_tai.dxf"})
    msp = doc.modelspace()
    msp.add_blockref("REF1", (0, 0))

    segments, notes = cad_loader.resolve_xref_segments(
        doc, str(workspace), lambda space: []
    )
    assert segments == []
    assert any("KHÔNG tìm thấy file XREF" in n for n in notes)
    assert any("khong_ton_tai.dxf" in n for n in notes)


def test_resolve_xref_segments_merges_content_from_referenced_file(workspace):
    xref_path = workspace / "phu.dxf"
    _make_dxf(str(xref_path), lines=[("PIPE", (0, 0), (100, 0))])

    doc = ezdxf.new()
    doc.blocks.new("REF1", dxfattribs={"flags": 4, "xref_path": "phu.dxf"})
    msp = doc.modelspace()
    msp.add_blockref("REF1", (500, 500))

    def collect(space):
        result = []
        for entity in space:
            if entity.dxftype() == "LINE":
                s, e = entity.dxf.start, entity.dxf.end
                result.append({"layer": entity.dxf.layer, "start": (s.x, s.y, 0), "end": (e.x, e.y, 0),
                              "length": math.hypot(e.x - s.x, e.y - s.y), "is_arc": False})
        return result

    segments, notes = cad_loader.resolve_xref_segments(doc, str(workspace), collect)
    assert len(segments) == 1
    # Điểm được quy về hệ tọa độ chính: gốc xref (0,0) -> điểm chèn (500,500).
    assert segments[0]["start"] == pytest.approx((500, 500, 0))
    assert segments[0]["end"] == pytest.approx((600, 500, 0))
    assert any("Đã gộp nội dung XREF" in n for n in notes)


def test_resolve_xref_segments_applies_scale_and_rotation(workspace):
    xref_path = workspace / "phu.dxf"
    _make_dxf(str(xref_path), lines=[("PIPE", (0, 0), (100, 0))])

    doc = ezdxf.new()
    doc.blocks.new("REF1", dxfattribs={"flags": 4, "xref_path": "phu.dxf"})
    msp = doc.modelspace()
    # Chèn xref với scale x2 — đoạn 100 đơn vị trong xref phải thành 200 trong bản vẽ chính.
    msp.add_blockref("REF1", (0, 0), dxfattribs={"xscale": 2.0, "yscale": 2.0})

    def collect(space):
        result = []
        for entity in space:
            if entity.dxftype() == "LINE":
                s, e = entity.dxf.start, entity.dxf.end
                result.append({"layer": entity.dxf.layer, "start": (s.x, s.y, 0), "end": (e.x, e.y, 0),
                              "length": math.hypot(e.x - s.x, e.y - s.y), "is_arc": False})
        return result

    segments, _ = cad_loader.resolve_xref_segments(doc, str(workspace), collect)
    assert segments[0]["length"] == pytest.approx(200.0)
    assert segments[0]["end"] == pytest.approx((200, 0, 0))


def test_resolve_xref_segments_returns_nothing_when_no_xref_declared(workspace):
    doc = ezdxf.new()
    segments, notes = cad_loader.resolve_xref_segments(doc, str(workspace), lambda space: [])
    assert segments == []
    assert notes == []


# --- Tool `convert_dwg_to_dxf` (đăng ký trong src/tools.py) ---

def test_convert_dwg_to_dxf_tool_rejects_non_dwg_input(workspace):
    from src.tools import convert_dwg_to_dxf as convert_tool
    _make_dxf(str(workspace / "bv.dxf"), lines=[("PIPE", (0, 0), (10, 0))])
    result = convert_tool.invoke({"file_path": "bv.dxf"})
    assert "không phải file .dwg" in result


def test_convert_dwg_to_dxf_tool_reports_missing_converter(monkeypatch, workspace):
    from src.tools import convert_dwg_to_dxf as convert_tool
    monkeypatch.delenv("ODA_CONVERTER_PATH", raising=False)
    monkeypatch.setattr(cad_loader.shutil, "which", lambda name: None)
    (workspace / "bv.dwg").write_bytes(b"FAKE")
    result = convert_tool.invoke({"file_path": "bv.dwg"})
    assert "ODA File Converter" in result


def test_convert_dwg_to_dxf_tool_succeeds_when_converter_available(monkeypatch, workspace):
    from src.tools import convert_dwg_to_dxf as convert_tool
    (workspace / "bv.dwg").write_bytes(b"FAKE")

    def fake_convert(path, output_dir=None, timeout=180):
        out = os.path.join(output_dir, "bv.dxf")
        _make_dxf(out, lines=[("PIPE", (0, 0), (5, 0))])
        return out

    monkeypatch.setattr(cad_loader, "convert_dwg_to_dxf", fake_convert)
    result = convert_tool.invoke({"file_path": "bv.dwg"})
    assert "chuyển .dwg sang .dxf" in result
    assert (workspace / "bv.dxf").exists()
