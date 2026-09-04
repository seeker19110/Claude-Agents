"""Bộ sinh subagent kiểm duyệt: dẫn xuất MỘT CHIỀU từ agents/, chỉ đọc, không tự quyết định.

Đặc tả: docs/dac-ta-tro-ly-kiem-duyet.md §4 và §8.1 (phần thuộc PR 1 — 20 file `sc-<id>.md`;
`sc-gate-<kind>.md` và parser checklists.md thuộc PR 2).
"""
from __future__ import annotations

import re

import pytest
import yaml

from company.registry import load_agents
from company.subagents import PREFIX, TOOLS, build, diffs, render_all, sections
from company.subagents import main as sub_main


def _fm_body(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    assert m, "file sinh phải có front matter"
    return yaml.safe_load(m.group(1)), m.group(2)


def test_moi_agent_co_subagent():
    """Thiếu một agent nghĩa là gate của khối đó không có ai chuẩn bị bằng chứng."""
    got = {p.stem for p in render_all()}
    assert got == {f"{PREFIX}{a}" for a in load_agents()}
    assert len(got) == 20


def test_build_idempotent(tmp_path):
    """Build hai lần ra cùng nội dung — nếu không thì `check` sẽ đỏ ngẫu nhiên trong CI."""
    build(out=tmp_path)
    first = {p.name: p.read_text(encoding="utf-8") for p in tmp_path.glob("*.md")}
    build(out=tmp_path)
    second = {p.name: p.read_text(encoding="utf-8") for p in tmp_path.glob("*.md")}
    assert first == second and len(first) == 20


def test_check_do_khi_sua_tay(tmp_path):
    """Sửa bản dẫn xuất bằng tay = người duyệt đang chấm theo tiêu chuẩn khác tiêu chuẩn công ty dùng thật."""
    build(out=tmp_path)
    assert sub_main(["check", "--out", str(tmp_path)]) == 0
    victim = tmp_path / f"{PREFIX}qa-debugger.md"
    victim.write_text(victim.read_text(encoding="utf-8").replace("Ranh giới", "Ranh gioi", 1), encoding="utf-8")
    assert sub_main(["check", "--out", str(tmp_path)]) == 1
    d = "\n".join(diffs(tmp_path))
    assert "sc-qa-debugger.md" in d and "Ranh gioi" in d, "diff phải nêu đúng file và đúng chỗ lệch"


def test_tools_khong_co_bash():
    """I1: subagent không được chạm company.sqlite, CLI của công ty, hay worktree."""
    for text in render_all().values():
        fm, _ = _fm_body(text)
        tools = {t.strip() for t in str(fm["tools"]).split(",")}
        assert tools <= set(TOOLS), tools
        assert "Bash" not in tools and "Write" not in tools and "Edit" not in tools


def test_khong_tu_quyet_dinh():
    """I6: trợ lý chuẩn bị bằng chứng, không khuyến nghị và không có đường đóng gate.

    Đặc tả §8.1 viết "thân bài không chứa `approve`, `nên duyệt`, `gate_cli`". Kiểm chuỗi thô `approve` thì
    ĐỎ OAN: `approved-specs` là tên topic và `approved` là trạng thái ticket, cả hai nằm trong phần prompt gốc
    mà §4.3 bắt chép NGUYÊN VĂN. Nên ở đây kiểm đúng ý định của bất biến — cụm mang nghĩa khuyến nghị, và tên
    lệnh đóng gate — chứ không kiểm từ vựng nghiệp vụ.
    """
    cam = ("gate_cli", "nên duyệt", "khuyến nghị duyệt", "an toàn để merge", "tôi đồng ý",
           "approve <", "gate_cli approve")
    for path, text in render_all().items():
        _, body = _fm_body(text)
        low = body.lower()
        for tu in cam:
            assert tu.lower() not in low, f"{path.name} chứa {tu!r}"
        assert "không quyết định" in text and "hồ sơ kiểm, không phải khuyến nghị" in body


def test_than_bai_co_du_bon_khoi():
    """Thiếu khối nào cũng làm trợ lý mất một chân: ranh giới, tiêu chuẩn để chấm, checklist, khuôn báo cáo."""
    for path, text in render_all().items():
        _, body = _fm_body(text)
        aid = path.stem[len(PREFIX):]
        assert "SINH TỰ ĐỘNG" in body and "agents/" in body
        assert "## Ranh giới" in body
        assert f"## Tiêu chuẩn của {aid}" in body
        assert "## Đầu ra" in body and "[unknown]" in body


def test_chep_nguyen_van_tieu_chuan_nguon():
    """Tiêu chuẩn phải là bản sao nguyên văn: diễn giải lại là chấm theo tiêu chuẩn đã bị bóp méo."""
    specs = load_agents()
    for path, text in render_all().items():
        spec = specs[path.stem[len(PREFIX):]]
        src = sections(spec.prompt)
        for name in ("Bạn PHẢI", "Bạn KHÔNG ĐƯỢC"):
            if body := src.get(name, "").strip():
                assert body in text, f"{path.name}: mục {name!r} không được chép nguyên văn"


def test_khong_vuot_tran_prompt():
    """ADR-0020: file sinh không được vượt trần prompt của agent gốc."""
    specs = load_agents()
    for path, text in render_all().items():
        cap = specs[path.stem[len(PREFIX):]].max_input_chars or 50_000
        assert len(text) <= cap, f"{path.name}: {len(text)} > {cap}"


def test_ban_dan_xuat_tren_dia_khop_nguon():
    """Chống trôi: `.claude/agents/` được commit, nên nó phải luôn khớp nguồn (CI gọi cùng chỗ với golden)."""
    assert diffs() == [], "chạy `make subagents` rồi commit lại .claude/agents/"


def test_only_va_agent_la():
    """`--only` nhận cả `sc-x` lẫn `x`; agent không tồn tại thì gãy to, không sinh im lặng."""
    assert set(render_all("sc-qa-debugger")) == set(render_all("qa-debugger"))
    assert len(render_all("qa-debugger")) == 1
    with pytest.raises(SystemExit):
        render_all("khong-ton-tai")
