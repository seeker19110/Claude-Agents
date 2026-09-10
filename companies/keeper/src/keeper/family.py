"""Sửa một lỗi thì rà cả HỌ lỗi đó (`AGENTS.md` bắt buộc §5, `TRAPS.md` §1).

Luật gốc có hai vế và vế thứ hai mới là vế bị bỏ: "grep mọi chỗ dùng cùng cơ chế, **ghi lại cả chỗ an toàn và
vì sao**". Một báo cáo chỉ có `hits` không phân biệt được hai trạng thái rất khác nhau — "đã soi 12 chỗ, 3 chỗ
phải sửa, 9 chỗ an toàn vì X" và "đã grep ra 3 chỗ rồi thôi". Nên `safe` rỗng trong khi `hits` không rỗng là
báo cáo KHÔNG HỢP LỆ, và mỗi mục `safe` phải mang LÝ DO viết ra được: một danh sách đường dẫn không kèm lý do
là lời khai (`AGENTS.md` cấm §8), không phải bằng chứng đã soi.

"Cơ chế" rút từ patch theo ba hình dạng đo được trong chính repo này (không phải ba hình dạng tưởng tượng):

* `function` — `def <tên>(`: sửa một hàm thì mọi nơi GỌI nó là họ hàng gần nhất;
* `key` — khoá chuỗi trong bảng tra (`"weekly-quota": ...`): repo dùng bảng-thay-`if` khắp nơi
  (`risk.RISK_RULES`, `budget.BUDGET_CHECKS`, `triage.DUE_DAYS`), nên một khoá là một cơ chế;
* `regex` — chuỗi trong `re.compile(r"...")`: `drift.py` có bốn mẫu, sửa sai một mẫu thì các mẫu chép từ nó
  cũng sai (đúng khuôn "1 lỗi thành 5" ở `TRAPS.md`).

`safe` KHÔNG được suy ra tự động: `scan_family()` cố ý trả `safe=[]` và để `require_family_report()` từ chối.
Một máy đoán hộ "chỗ này an toàn" là lại một lời khai, chỉ khác là do code khai. Người/agent phải điền lý do
từng chỗ rồi mới qua cửa.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

# Dòng ĐỔI của diff (`+`/`-`), không tính đầu file (`+++`/`---`) — đó là tên file, không phải nội dung.
_CHANGED_RE = re.compile(r"^[+-](?![+-])")
_DEF_RE = re.compile(r"^[+-]\s*(?:async\s+)?def\s+(?P<name>\w+)\s*\(")
_KEY_RE = re.compile(r"""["'](?P<key>[A-Za-z][A-Za-z0-9_.-]{2,})["']\s*:""")
_RE_RE = re.compile(r"""re\.compile\(\s*r?["'](?P<pat>.{3,}?)["']\s*[,)]""")

# Đuôi file được soi: mã và tài liệu của repo. Nhị phân/ảnh không có "cơ chế" để rà, và đọc chúng như văn bản
# chỉ sinh hit rác.
TEXT_SUFFIXES = frozenset({".py", ".md", ".toml", ".yaml", ".yml", ".json", ".cfg", ".ini", ".txt"})
SKIP_DIRS = frozenset({".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache",
                       ".pytest_cache", ".ruff_cache", "dist", "build", "htmlcov"})

# `mechanisms_from_patch()` rút số cơ chế từ NỘI DUNG DIFF — do người/model viết, không phải một tập cố định
# trong repo — nên số cơ chế của một patch không có trần tự nhiên. `grep_repo()` là O(mechanisms × dòng repo),
# nên một patch (cố ý hay vô tình) sửa hàng trăm hàm/khoá/regex trong một lượt biến một cú `scan_family()`
# thành quét toàn repo hàng trăm lần. Hai trần dưới đây KHÔNG đổi kết quả trong ca bình thường (một patch thật
# hiếm khi chạm quá vài chục cơ chế), chỉ chặn ca bất thường: cắt bớt CƠ CHẾ (giữ N cái gặp đầu, theo đúng thứ
# tự `mechanisms_from_patch()` đã giữ) và dừng SỚM khi đã đủ HIT — quá `MAX_FAMILY_HITS` chỗ cùng cơ chế thì
# người đọc báo cáo cũng không còn soi hết được, cắt sớm không mất thông tin hữu ích.
MAX_FAMILY_MECHANISMS = 50
MAX_FAMILY_HITS = 500


class FamilyReportInvalid(Exception):
    """Báo cáo rà họ lỗi không đủ điều kiện (`TRAPS.md` §1)."""


@dataclass(frozen=True)
class Mechanism:
    """Một "cơ chế" rút từ patch. `name` là thứ đem đi grep; `kind` chỉ để đọc báo cáo cho dễ."""
    kind: str
    name: str


class FamilySite(BaseModel):
    """Một chỗ dùng CÙNG cơ chế, chưa phán xét đúng/sai."""
    path: str
    line: int
    text: str
    mechanism: str


class SafeSite(BaseModel):
    """Một chỗ ĐÃ SOI và kết luận an toàn. `reason` là bắt buộc có nội dung — xem docstring module."""
    path: str
    mechanism: str
    reason: str
    line: int | None = None


class FamilyReport(BaseModel):
    mechanisms: list[str] = []
    hits: list[FamilySite] = []
    safe: list[SafeSite] = []


@dataclass(frozen=True)
class FamilyRule:
    name: str
    ok: Callable[[FamilyReport], bool]
    why: str


FAMILY_RULES: tuple[FamilyRule, ...] = (
    FamilyRule("safe-must-exist", lambda r: not r.hits or bool(r.safe),
               "có chỗ cùng cơ chế nhưng không ghi chỗ nào đã kiểm là an toàn (TRAPS.md §1)"),
    FamilyRule("safe-must-be-explained", lambda r: all(s.reason.strip() for s in r.safe),
               "một mục safe không kèm lý do là lời khai, không phải bằng chứng đã soi"),
)


def rules_without(*names: str) -> tuple[FamilyRule, ...]:
    known = {r.name for r in FAMILY_RULES}
    missing = sorted(set(names) - known)
    if missing:
        raise KeyError(f"không có hàng kiểm {missing} trong FAMILY_RULES")
    return tuple(r for r in FAMILY_RULES if r.name not in names)


def require_family_report(report: FamilyReport, *, rules: tuple[FamilyRule, ...] = FAMILY_RULES) -> None:
    broken = [r for r in rules if not r.ok(report)]
    if broken:
        raise FamilyReportInvalid("; ".join(f"{r.name}: {r.why}" for r in broken))


def mechanisms_from_patch(diff: str) -> list[Mechanism]:
    """Rút cơ chế từ các dòng ĐỔI của một unified diff. Giữ thứ tự gặp, bỏ trùng theo `(kind, name)`."""
    out: list[Mechanism] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, name: str) -> None:
        if (kind, name) not in seen:
            seen.add((kind, name))
            out.append(Mechanism(kind=kind, name=name))

    for line in diff.splitlines():
        if not _CHANGED_RE.match(line):
            continue
        m = _DEF_RE.match(line)
        if m:
            add("function", m.group("name"))
        for k in _KEY_RE.finditer(line):
            add("key", k.group("key"))
        for r in _RE_RE.finditer(line):
            add("regex", r.group("pat"))
    return out


def grep_repo(
    root: Path, mechanisms: Iterable[Mechanism], *, exclude: Sequence[str] = (),
) -> list[FamilySite]:
    """Grep toàn repo tìm chỗ dùng cùng cơ chế. `exclude` là các đường dẫn (tương đối, dấu `/`) của CHÍNH
    patch — chúng đã được sửa, đưa vào `hits` chỉ làm loãng báo cáo."""
    mechs = list(mechanisms)[:MAX_FAMILY_MECHANISMS]
    if not mechs:
        return []
    skip = {e.replace("\\", "/") for e in exclude}
    out: list[FamilySite] = []
    for path in sorted(root.rglob("*")):
        if len(out) >= MAX_FAMILY_HITS:
            break
        if path.suffix not in TEXT_SUFFIXES or not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel in skip or SKIP_DIRS & set(path.relative_to(root).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # file nhị phân đội lốt đuôi văn bản, hay không đọc được: bỏ qua, không làm hỏng cả lượt rà
        for lineno, line in enumerate(text.splitlines(), start=1):
            if len(out) >= MAX_FAMILY_HITS:
                break
            for mech in mechs:
                if mech.name in line:
                    out.append(FamilySite(path=rel, line=lineno, text=line.strip()[:200], mechanism=mech.name))
                    if len(out) >= MAX_FAMILY_HITS:
                        break
    return out


def scan_family(root: Path, diff: str, *, files: Sequence[str] = ()) -> FamilyReport:
    """Patch (đường dẫn + diff dạng CHUỖI THUẦN, không phụ thuộc module `patcher`) → báo cáo có `hits`,
    `safe` để RỖNG. Báo cáo trả về chưa hợp lệ theo `require_family_report()` cho tới khi người điền `safe`."""
    mechs = mechanisms_from_patch(diff)
    return FamilyReport(
        mechanisms=[m.name for m in mechs],
        hits=grep_repo(root, mechs, exclude=files),
        safe=[],
    )
