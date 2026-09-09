"""Registry của `keeper` — cơ chế ở `xagents_core.registry`.

Hai điều đã ĐO, không suy:

- **Không có `AgentSpec` riêng.** studio thêm `tools`, company thêm phần của nó; `keeper` không agent nào khai
  trường ngoài khung chung (kiểm được: `tests/golden/registry.json` liệt kê đúng 11 khoá của `AgentSpec` lõi).
  Nên `spec_cls` là lớp của core — dựng một lớp con rỗng chỉ để "cho giống" là thêm một nơi phải sửa.
- **`check_owners=False`.** `keeper/skills/` chưa tồn tại (chưa agent nào khai `skills`/`skills_core`); bật cổng
  ADR-0008 trước khi có skill thật là một cổng đỏ giả. Cùng lý do đã ghi ở `tests/test_golden_agents.py`.
"""
from __future__ import annotations

from xagents_core.registry import AgentSpec as AgentSpec
from xagents_core.registry import load_agents as _load_agents

from .core import CORE

__all__ = ["AGENTS_DIR", "SKILLS_DIR", "AgentSpec", "load_agents"]

AGENTS_DIR, SKILLS_DIR = CORE.agents_dir, CORE.skills_dir


def load_agents(check_owners: bool = False) -> dict[str, AgentSpec]:
    return _load_agents(AGENTS_DIR, SKILLS_DIR, AgentSpec, check_owners=check_owners)
