"""Nhận diện stack của repo khách và lệnh lint/test tương ứng (ADR-0013).

`run_checks` trước đây cứng `ruff` + `pytest`, nên PR của frontend, mobile, platform và data mang
`local_checks.lint/tests` do một lệnh không liên quan đến code của họ sinh ra: bằng chứng hình thức, không có giá trị.
Ở đây mỗi stack tự khai dấu hiệu nhận biết và argv của lint/test; argv do CODE ghép, model chỉ chọn tên lệnh,
nên ranh giới tin cậy của ADR-0010 không đổi. Không nhận ra stack nào → `local_checks` nói thẳng là không chạy được,
thay vì báo pass giả."""

from __future__ import annotations

import json
import re
import sys
import tomllib
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path


@dataclass(frozen=True)
class Stack:
    name: str
    lint: list[str] | None
    test: list[str] | None
    # Thư mục/tên file được coi là TEST của stack này (ADR-0028). Dùng để phân vùng quyền ghi giữa
    # `test-author` (chỉ test) và agent viết code (mọi thứ trừ test). Rỗng = không phân vùng được ⇒ fail closed.
    test_globs: tuple[str, ...] = ()

    def commands(self) -> dict[str, list[str]]:
        return {k: v for k, v in (("lint", self.lint), ("test", self.test)) if v}

    def is_test_path(self, rel: str) -> bool:
        """`rel` (POSIX, tương đối gốc worktree) có nằm trong vùng test của stack không.

        Khớp cả đường dẫn đầy đủ (`tests/**`) lẫn riêng tên file (`test_*.py` ở bất kỳ thư mục nào)."""
        rel = rel.replace("\\", "/").lstrip("./")
        name = rel.rsplit("/", 1)[-1]
        return any(fnmatch(rel, g) or fnmatch(name, g) for g in self.test_globs)


PY_TEST_GLOBS = ("tests/**", "test/**", "test_*.py", "*_test.py")
NODE_TEST_GLOBS = ("test/**", "tests/**", "__tests__/**", "*.test.*", "*.spec.*")

PY = Stack(
    "python",
    [sys.executable, "-m", "ruff", "check"],
    [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
    PY_TEST_GLOBS,
)
# ADR-0044: repo khách là dự án uv (`[project]` trong `pyproject.toml`) thì lint/test chạy bằng MÔI TRƯỜNG CỦA
# KHÁCH. `uv run` tự đồng bộ `.venv` của worktree trước khi chạy, nên phụ thuộc khách khai (Django, pytest-django…)
# có mặt. Dùng `sys.executable` ở đây là venv của ORCHESTRATOR: đo 2026-09-23 trên CAMPUS-UNI/TCK-001, mọi lượt
# builder đều chết ở khâu collect vì thiếu `django` — lỗi hạ tầng mà ticket phải gánh tới `ticket.blocked`.
_UV_RUN = ["uv", "run", "--", "python", "-m"]
NODE = Stack("node", ["npm", "run", "--if-present", "lint"], ["npm", "test", "--if-present"], NODE_TEST_GLOBS)
GO = Stack("go", ["go", "vet", "./..."], ["go", "test", "./..."], ("*_test.go",))
RUST = Stack("rust", ["cargo", "clippy", "--quiet"], ["cargo", "test", "--quiet"], ("tests/**",))
GRADLE = Stack("gradle", ["./gradlew", "lint"], ["./gradlew", "test"], ("src/test/**",))
MAVEN = Stack("maven", ["mvn", "-q", "checkstyle:check"], ["mvn", "-q", "test"], ("src/test/**",))
UNKNOWN = Stack("unknown", None, None)  # không có test_globs ⇒ không phân vùng ghi được (ADR-0028 §3)

# Thứ tự có ý nghĩa: file dấu hiệu đầu tiên khớp thì thắng (repo đa ngôn ngữ lấy stack của gốc repo).
MARKERS: tuple[tuple[str, Stack], ...] = (
    ("pyproject.toml", PY),
    ("setup.cfg", PY),
    ("requirements.txt", PY),
    ("package.json", NODE),
    ("go.mod", GO),
    ("Cargo.toml", RUST),
    ("build.gradle", GRADLE),
    ("build.gradle.kts", GRADLE),
    ("pom.xml", MAVEN),
)


def detect(root: Path) -> Stack:
    """Stack của một worktree theo file dấu hiệu ở gốc. Node có script lint/test hay không thì `--if-present` lo."""
    for marker, stack in MARKERS:
        if (root / marker).exists():
            if stack is NODE:
                return _node_stack(root / marker)
            if stack is PY and marker == "pyproject.toml":
                return _py_stack(root / marker)
            return stack
    return UNKNOWN


def _py_stack(pyproject: Path) -> Stack:
    """Chỉ chuyển sang `uv run` cho công cụ mà khách THẬT SỰ khai — cùng lý lẽ với `_node_stack`.

    Khai `[project]` + `pytest` ⇒ `uv run` chạy bằng venv của khách (ADR-0044). Khai `[project]` nhưng không có
    `pytest` ⇒ khách không mang bộ test riêng; `uv run` chỉ dựng một venv rỗng rồi trả `No module named pytest`,
    tức một màu đỏ do hạ tầng chứ không do code — giữ đường cũ thay vì bịa ra lỗi mới."""
    deps = _khai_bao(pyproject)
    return Stack(
        "python",
        [*_UV_RUN, "ruff", "check"] if "ruff" in deps else PY.lint,
        [*_UV_RUN, "pytest", "-q", "-p", "no:cacheprovider"] if "pytest" in deps else PY.test,
        PY_TEST_GLOBS,
    )


def _khai_bao(pyproject: Path) -> frozenset[str]:
    """Tên gói khách khai trong `[project].dependencies` và `[dependency-groups]`, đã chuẩn hoá.

    Đọc bằng `tomllib` chứ không grep: `pytest` trong một chuỗi mô tả không phải là dependency. Không có bảng
    `[project]` (file chỉ có `[tool.*]`) ⇒ rỗng: `uv run` không chạy được trên thứ không phải dự án."""
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return frozenset()
    project = data.get("project")
    if not isinstance(project, dict):
        return frozenset()
    specs: list[str] = [x for x in (project.get("dependencies") or []) if isinstance(x, str)]
    for group in (data.get("dependency-groups") or {}).values():
        specs += [x for x in (group or []) if isinstance(x, str)]
    for extra in (project.get("optional-dependencies") or {}).values():
        specs += [x for x in (extra or []) if isinstance(x, str)]
    return frozenset(_ten_goi(x) for x in specs)


def _ten_goi(spec: str) -> str:
    """`pytest-django>=4.9` → `pytest-django`; `coverage[toml]>=7.6` → `coverage`."""
    return re.split(r"[\s\[<>=!~;,]", spec.strip(), maxsplit=1)[0].lower()


def _node_stack(pkg: Path) -> Stack:
    """Chỉ khai lệnh khi package.json thật sự có script tương ứng — tránh `npm test` mặc định thoát lỗi."""
    try:
        scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts") or {}
    except (OSError, json.JSONDecodeError):
        scripts = {}
    return Stack(
        "node",
        ["npm", "run", "lint"] if "lint" in scripts else None,
        ["npm", "test", "--", "--watch=false"] if "test" in scripts else None,
        NODE_TEST_GLOBS,
    )
