"""Registry của company — cơ chế ở `xagents_core.registry` (K3.6a của ADR gốc 0001).

Còn lại ở đây đúng ba thứ: `ROOT`/`AGENTS_DIR`/`SKILLS_DIR` (tên cũ, nay đọc từ `CORE.root`), lớp `AgentSpec`
của company (bằng đúng lớp core — company là bản vào core), và hai hàm giữ chữ ký cũ để mọi nơi đang
`from .registry import load_agents` không phải đổi.
"""
from __future__ import annotations

from xagents_core.registry import CORE_SECTIONS as CORE_SECTIONS
from xagents_core.registry import AgentSpec as AgentSpec
from xagents_core.registry import Phase as Phase
from xagents_core.registry import _load_phases as _core_load_phases
from xagents_core.registry import load_agents as _load_agents
from xagents_core.registry import load_skill as _load_skill
from xagents_core.registry import split_front_matter as split_front_matter

from .core import CORE

_split = split_front_matter  # tên cũ (có gạch dưới) mà test và script cũ nhập

ROOT = CORE.root
AGENTS_DIR, SKILLS_DIR = CORE.agents_dir, CORE.skills_dir


def load_skill(name: str, core_only: bool = False) -> str:
    """Chữ ký cũ `(name, core_only)` — thư mục skill nay đến từ `CORE`, không phải hằng module."""
    return _load_skill(SKILLS_DIR, name, core_only)


def load_agents(check_owners: bool = True) -> dict[str, AgentSpec]:
    return _load_agents(AGENTS_DIR, SKILLS_DIR, AgentSpec, check_owners=check_owners)


def _load_phases(spec: AgentSpec) -> None:
    """Chữ ký cũ `(spec)` — thư mục skill nay là tham số của core, không phải hằng module."""
    _core_load_phases(SKILLS_DIR, spec)
