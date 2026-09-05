"""Bộ sinh subagent kiểm duyệt: dẫn xuất MỘT CHIỀU từ agents/ và gates/checklists.md, chỉ đọc, không tự quyết định.

Đặc tả: docs/dac-ta-tro-ly-kiem-duyet.md §4 và §8.1 — 20 file `sc-<id>.md` (PR 1) + 5 file `sc-gate-<kind>.md`
và parser checklists.md (PR 2).
"""
from __future__ import annotations

import re
from typing import get_args

import pytest
import yaml

from company import gate_checklists as GC
from company.gates import GateKind
from company.registry import load_agents
from company.subagents import GATE_PREFIX, PREFIX, TOOLS, build, diffs, render_all, sections
from company.subagents import main as sub_main

N_AGENTS, N_GATES = 20, 5


def _agent_files() -> dict:
    """Chỉ file dẫn xuất từ agents/ (bỏ sc-gate-*)."""
    return {p: t for p, t in render_all().items() if not p.stem.startswith(GATE_PREFIX)}


def _gate_files() -> dict:
    return {p: t for p, t in render_all().items() if p.stem.startswith(GATE_PREFIX)}


def _fm_body(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    assert m, "file sinh phải có front matter"
    return yaml.safe_load(m.group(1)), m.group(2)


def test_moi_agent_co_subagent():
    """Thiếu một agent nghĩa là gate của khối đó không có ai chuẩn bị bằng chứng."""
    got = {p.stem for p in _agent_files()}
    assert got == {f"{PREFIX}{a}" for a in load_agents()}
    assert len(got) == N_AGENTS and len(render_all()) == N_AGENTS + N_GATES


def test_build_idempotent(tmp_path):
    """Build hai lần ra cùng nội dung — nếu không thì `check` sẽ đỏ ngẫu nhiên trong CI."""
    build(out=tmp_path)
    first = {p.name: p.read_text(encoding="utf-8") for p in tmp_path.glob("*.md")}
    build(out=tmp_path)
    second = {p.name: p.read_text(encoding="utf-8") for p in tmp_path.glob("*.md")}
    assert first == second and len(first) == N_AGENTS + N_GATES


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
    for path, text in _agent_files().items():
        _, body = _fm_body(text)
        aid = path.stem[len(PREFIX):]
        assert "SINH TỰ ĐỘNG" in body and "agents/" in body
        assert "## Ranh giới" in body
        assert f"## Tiêu chuẩn của {aid}" in body
        assert "## Đầu ra" in body and "[unknown]" in body


def test_chep_nguyen_van_tieu_chuan_nguon():
    """Tiêu chuẩn phải là bản sao nguyên văn: diễn giải lại là chấm theo tiêu chuẩn đã bị bóp méo."""
    specs = load_agents()
    for path, text in _agent_files().items():
        spec = specs[path.stem[len(PREFIX):]]
        src = sections(spec.prompt)
        for name in ("Bạn PHẢI", "Bạn KHÔNG ĐƯỢC"):
            if body := src.get(name, "").strip():
                assert body in text, f"{path.name}: mục {name!r} không được chép nguyên văn"


def test_khong_vuot_tran_prompt():
    """ADR-0020: file sinh không được vượt trần prompt của agent gốc."""
    specs = load_agents()
    for path, text in _agent_files().items():
        cap = specs[path.stem[len(PREFIX):]].max_input_chars or 50_000
        assert len(text) <= cap, f"{path.name}: {len(text)} > {cap}"
    for path, text in _gate_files().items():
        assert len(text) <= 50_000, f"{path.name}: {len(text)} > 50000"


def test_ban_dan_xuat_tren_dia_khop_nguon():
    """Chống trôi: `.claude/agents/` được commit, nên nó phải luôn khớp nguồn (CI gọi cùng chỗ với golden)."""
    assert diffs() == [], "chạy `make subagents` rồi commit lại .claude/agents/"


def test_only_va_agent_la():
    """`--only` nhận cả `sc-x` lẫn `x` lẫn `sc-gate-<kind>`; tên không tồn tại thì gãy to, không sinh im lặng."""
    assert set(render_all("sc-qa-debugger")) == set(render_all("qa-debugger"))
    assert len(render_all("qa-debugger")) == 1
    assert [p.stem for p in render_all("sc-gate-plan")] == ["sc-gate-plan"]
    with pytest.raises(SystemExit):
        render_all("khong-ton-tai")
    with pytest.raises(SystemExit):
        render_all("sc-gate-khong-co")


# ---------- PR 2: sc-gate-<kind>.md và parser gates/checklists.md ----------

def test_gate_kind_du():
    """Có đủ một trợ lý cho mỗi GateKind — gate nào không có trợ lý thì nửa "người tự kiểm" của nó lại về tay."""
    assert {p.stem for p in _gate_files()} == {f"{GATE_PREFIX}{k}" for k in get_args(GateKind)}
    assert set(GC.parse()) == set(get_args(GateKind))


def test_parser_khop_gatekind():
    """Mọi mục "Người tự kiểm thêm" và mọi khoá "Code gửi kèm" của mỗi gate phải xuất hiện đủ trong file sinh,
    kèm id ổn định và ít nhất một nguồn bằng chứng (§4.4, §5)."""
    gates = GC.parse(); files = {p.stem: t for p, t in _gate_files().items()}
    for kind, g in gates.items():
        text = files[f"{GATE_PREFIX}{kind}"]
        fm, body = _fm_body(text)
        assert fm["name"] == f"sc-gate-{kind}" and fm["model"] == ("opus" if kind in {"release", "acceptance"} else "sonnet")
        assert "## Nửa của code" in body and "## Nửa của người" in body and "## Trợ lý chuyên môn" in body
        for c in g.code:
            assert f"- `{c.key}` — {c.text}" in body, f"{kind}: thiếu khoá code {c.key}"
        for it in g.self_checks:
            assert f"**{it.text}** (`{it.id}`)" in body, f"{kind}: thiếu mục tự kiểm {it.text!r}"
            assert it.sources and all(f"nguồn: {src}" in body for src in it.sources)
        for x in GC.EXPERTS[kind]:
            assert f"- {x}" in body
    assert "## Riêng gate bất thường" in files["sc-gate-escalation"]


def test_gate_file_giu_bat_bien_i1_i6():
    """sc-gate-* chịu cùng bất biến với sc-<id>: chỉ tool đọc, không từ vựng quyết định, có khuôn báo cáo."""
    cam = ("gate_cli", "nên duyệt", "khuyến nghị duyệt", "an toàn để merge", "tôi đồng ý", "approve <")
    for path, text in _gate_files().items():
        fm, body = _fm_body(text)
        assert {t.strip() for t in str(fm["tools"]).split(",")} <= set(TOOLS)
        low = body.lower()
        for tu in cam:
            assert tu.lower() not in low, f"{path.name} chứa {tu!r}"
        assert "## Ranh giới" in body and "## Đầu ra" in body and "[unknown]" in body and "SINH TỰ ĐỘNG" in body


def _checklists() -> str:
    return GC.CHECKLISTS.read_text(encoding="utf-8")


def test_parser_gay_khi_thieu_nua_cua_code():
    with pytest.raises(ValueError, match="Code gửi kèm"):
        GC.parse(_checklists().replace("Code gửi kèm: `prd`", "Code gui kem: `prd`", 1))


def test_parser_gay_khi_thieu_nua_cua_nguoi():
    text = _checklists()
    i = text.index("## Gate 2")
    broken = text[:i] + text[i:].replace("Người tự kiểm thêm:", "Nguoi tu kiem them:", 1)
    with pytest.raises(ValueError, match="Người tự kiểm thêm"):
        GC.parse(broken)


def test_parser_gay_khi_kind_la_hoac_thieu_kind():
    with pytest.raises(ValueError, match="kind lạ"):
        GC.parse(_checklists().replace("kind `spec`", "kind `specc`", 1))
    with pytest.raises(ValueError, match="thiếu gate cho kind"):
        GC.parse(_checklists().split("## Gate 2")[0])
    with pytest.raises(ValueError, match="không nêu kind"):
        GC.parse(_checklists().replace("(kind `spec`, subject `SPEC-<project>`)", "", 1))


def test_parser_gay_khi_muc_tu_kiem_chua_co_nguon():
    """Thêm một mục tự kiểm vào checklists.md mà chưa khai nguồn bằng chứng → gãy, không sinh trợ lý mù nguồn."""
    text = _checklists().replace("- [ ] NFR có số đo", "- [ ] NFR có số đo\n- [ ] Mục mới chưa có nguồn", 1)
    with pytest.raises(ValueError, match="chưa có nguồn bằng chứng"):
        GC.parse(text)
    text = _checklists().replace("- [ ] NFR có số đo\n", "", 1)
    with pytest.raises(ValueError, match=r"không còn trong checklists\.md"):
        GC.parse(text)


def test_parser_gay_khi_dong_la_duoi_tieu_de_hoac_rong():
    text = _checklists().replace("Code gửi kèm: `prd`, `acceptance-criteria`, `ux-flow`, `risks`\n- [ ] `prd`",
                                 "Code gửi kèm: `prd`, `acceptance-criteria`, `ux-flow`, `risks`\nkhông phải mục\n- [ ] `prd`", 1)
    with pytest.raises(ValueError, match="không phải mục"):
        GC.parse(text)
    with pytest.raises(ValueError, match="không có mục `## Gate`"):
        GC.parse("# trống\n")
    two = _checklists() + "\n## Gate 9 — lặp (kind `spec`, subject `X`)\nCode gửi kèm:\n- [ ] `a` — b\n\nNgười tự kiểm thêm:\n- [ ] NFR có số đo\n"
    with pytest.raises(ValueError, match="hai lần"):
        GC.parse(two)


def test_list_in_ca_gate(capsys):
    assert sub_main(["list"]) == 0
    out = capsys.readouterr().out
    assert "sc-gate-escalation.md" in out and "sc-qa-debugger.md" in out
