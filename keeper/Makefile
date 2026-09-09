.PHONY: test cov lint types fix
test:
	uv run pytest -q
cov:
	uv run pytest -q --cov
types:
	uv run mypy src/keeper --ignore-missing-imports
lint:
	uv run ruff check src tests
	uv run mypy src/keeper --ignore-missing-imports
fix:
	uv run ruff check --fix src tests
