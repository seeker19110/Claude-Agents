.PHONY: test cov lint types fix golden
test:
	uv run pytest -q
golden:        # cập nhật golden prompt sau khi sửa keeper/agents/ (ADR-0004)
	UPDATE_GOLDEN=1 uv run pytest -q tests/test_golden_agents.py
cov:
	uv run pytest -q --cov
types:
	uv run mypy src/keeper --ignore-missing-imports
lint:
	uv run ruff check src tests
	uv run mypy src/keeper --ignore-missing-imports
fix:
	uv run ruff check --fix src tests
