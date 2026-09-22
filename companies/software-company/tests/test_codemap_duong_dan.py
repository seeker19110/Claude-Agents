"""Cổng: mọi đường dẫn trong backtick của `CODEMAP.md`/`ARCHITECTURE.md`/`CLAUDE.md` của package phải tồn tại trên đĩa.

Audit 2026-09-22 đo được 14 đường dẫn sai trong `CODEMAP.md` sau lần dời `xagents-core/`, `console/` vào
`platform/` (#2xx): `xagents-core/src/xagents_core/*.py`, `console/src/console/truth.py`, `docs/thi-hanh/adr113.md`,
`../.claude/commands/gate-brief.md`… — file "muốn đổi X thì sửa ở đâu" trỏ vào chỗ không có, và không cổng nào
canh (`docs/TASK-PACK.md` A3 "hoá thạch sau đổi cấu trúc: grep tay"). Cổng này đổi grep tay thành máy: đường dẫn
tương đối được thử từ gốc package, gốc hub, `src/company/`, `src/` và `agents/` (bốn cách viết tắt tài liệu
đang dùng); không tồn tại ở đâu là đỏ.

Chỉ bắt token có `/` và đuôi file quen (không bắt tên hàm, glob `*`, `<placeholder>`)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1]
HUB = PKG.parents[1]
DOCS = ("CODEMAP.md", "ARCHITECTURE.md", "CLAUDE.md")
_TOKEN = re.compile(r"`([^`\n]+)`")
_PATHLIKE = re.compile(r"^[\w.\-/]+/[\w.\-]+\.(py|md|json|yaml|yml|txt|sh|js|html|toml)$")


def _duong_dan(doc: Path) -> list[str]:
    out = []
    for tok in _TOKEN.findall(doc.read_text(encoding="utf-8")):
        tok = tok.split("::", 1)[0].strip()  # `orch/routes.py::phase_for` → phần file
        if "*" in tok or "<" in tok or " " in tok:
            continue
        if _PATHLIKE.match(tok):
            out.append(tok)
    return sorted(set(out))


def _ton_tai(rel: str) -> bool:
    goc = (PKG, HUB, PKG / "src" / "company", PKG / "src", PKG / "agents")
    return any((g / rel).exists() for g in goc)


@pytest.mark.parametrize("doc", DOCS)
def test_moi_duong_dan_trong_tai_lieu_package_ton_tai(doc: str) -> None:
    paths = _duong_dan(PKG / doc)
    assert paths, f"{doc}: regex không bắt được đường dẫn nào — cổng tự mù, kiểm lại `_PATHLIKE`"
    thieu = [p for p in paths if not _ton_tai(p)]
    assert not thieu, f"{doc} trỏ tới đường dẫn không tồn tại (thử từ gốc package và gốc hub): {thieu}"


def test_regex_bat_duoc_duong_dan_sai_da_biet() -> None:
    """Kiểm chính cái mẫu trên một vi phạm đã biết trước khi tin nó (bài học 2026-09-07: test quy ước xanh vì
    mẫu không nhìn thấy vi phạm)."""
    assert _PATHLIKE.match("xagents-core/src/xagents_core/events.py")
    assert _PATHLIKE.match("../.claude/commands/gate-brief.md")
    assert not _ton_tai("xagents-core/src/xagents_core/events.py")
    assert _ton_tai("platform/xagents-core/src/xagents_core/events.py")
    assert not _PATHLIKE.match("phase_for") and not _PATHLIKE.match("tests/golden/")
