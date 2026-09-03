.PHONY: llm probe test cov lint types fix demo golden gate eval eval-record eval-replay run watch status report metrics assetscan assetbudget
llm:           # cài hồ sơ model chạy thật: make llm PROFILE=claude-gateway (không ghi đè llm.yaml đang có)
	@test -f llm.yaml && echo "llm.yaml đã có, không ghi đè (xoá nó nếu muốn cài lại)" || \
	 (cp llm.$(or $(PROFILE),claude-gateway).yaml llm.yaml && echo "đã tạo llm.yaml từ llm.$(or $(PROFILE),claude-gateway).yaml")
probe:         # CLI `claude` trên máy này chạy được chế độ tool nào (mcp | cli | none) — gọi model THẬT một lượt
	PYTHONPATH=src uv run python -m company.probe $(if $(BACKEND),--backend $(BACKEND),)
test:
	uv run pytest -q
cov:
	uv run pytest -q --cov
types:
	uv run mypy src/company --ignore-missing-imports
demo:
	PYTHONPATH=src uv run python -m company.demo
lint:
	uv run ruff check src tests
	uv run mypy src/company --ignore-missing-imports
fix:
	uv run ruff check --fix src tests
golden:
	UPDATE_GOLDEN=1 uv run pytest -q tests/test_golden_agents.py
gate:
	PYTHONPATH=src uv run python -m company.gate_cli list
assetscan:     # quét tài sản prompt của cả hai công ty (ADR-0022); miễn trừ ở assetscan-waivers.txt
	PYTHONPATH=src uv run python -m company.assetscan scan . ../Studio-creators
assetbudget:   # prompt tĩnh chiếm bao nhiêu phần ngân sách token của từng agent
	PYTHONPATH=src uv run python -m company.assetscan budget . ../Studio-creators
eval:
	PYTHONPATH=src uv run python -m company.evals $(AGENT)
eval-record:   # chạy model thật, lưu evals/recordings/$(AGENT).json — bắt buộc sau khi đổi prompt/skill (ADR-0010)
	PYTHONPATH=src uv run python -m company.evals $(AGENT) --record
eval-replay:   # như CI: phát lại từ bản ghi, không gọi model
	PYTHONPATH=src uv run python -m company.evals all --replay
run:
	PYTHONPATH=src uv run python -m company.orchestrator run
watch:
	PYTHONPATH=src uv run python -m company.orchestrator run --watch 5
status:
	PYTHONPATH=src uv run python -m company.orchestrator status
report:
	PYTHONPATH=src uv run python -m company.orchestrator report
metrics:       # gọi/token/USD/thời gian theo agent, model, ticket; thêm PROM=1 để xuất Prometheus text
	PYTHONPATH=src uv run python -m company.orchestrator metrics $(if $(PROM),--prometheus,)
