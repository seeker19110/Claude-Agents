.PHONY: test cov lint types fix golden eval eval-record eval-replay
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
eval:
	uv run python -m keeper.evals $(AGENT)
eval-record:   # chạy model thật, lưu evals/recordings/$(AGENT).json — bắt buộc sau khi đổi prompt/skill
	uv run python -m keeper.evals $(AGENT) --record
eval-replay:   # như CI: phát lại từ bản ghi, không gọi model
	uv run python -m keeper.evals all --replay --strict
