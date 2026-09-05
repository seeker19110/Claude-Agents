.PHONY: llm probe test cov lint types fix demo golden subagents subagents-check gate gate-brief eval eval-record eval-replay run watch status report metrics assetscan assetbudget
llm:           # cài hồ sơ model chạy thật: make llm PROFILE=claude-gateway (không ghi đè llm.yaml đang có)
	@test -f llm.yaml && echo "llm.yaml đã có, không ghi đè (xoá nó nếu muốn cài lại)" || \
	 (cp llm.$(or $(PROFILE),claude-gateway).yaml llm.yaml && echo "đã tạo llm.yaml từ llm.$(or $(PROFILE),claude-gateway).yaml")
probe:         # CLI `claude` trên máy này chạy được chế độ tool nào (mcp | cli | none) — gọi model THẬT một lượt
	uv run python -m company.probe $(if $(BACKEND),--backend $(BACKEND),)
test:
	uv run pytest -q
cov:
	uv run pytest -q --cov
types:
	uv run mypy src/company --ignore-missing-imports
demo:
	uv run python -m company.demo
lint:
	uv run ruff check src tests
	uv run mypy src/company --ignore-missing-imports
fix:
	uv run ruff check --fix src tests
golden:
	UPDATE_GOLDEN=1 uv run pytest -q tests/test_golden_agents.py
subagents:        # sinh .claude/agents/sc-*.md từ agents/ (dẫn xuất một chiều, phải commit lại)
	uv run python -m company.subagents build
subagents-check:  # CI: gãy nếu bản dẫn xuất lệch nguồn
	uv run python -m company.subagents check
gate:
	uv run python -m company.gate_cli list
gate-brief:       # hồ sơ bằng chứng (chỉ đọc) cho nửa "người tự kiểm thêm" của một gate: make gate-brief SUBJECT=REL-001 [REPO=../khach]
	uv run python -m company.gate_brief $(or $(SUBJECT),--all) $(if $(REPO),--repo $(REPO),)
assetscan:     # quét tài sản prompt của cả hai công ty (ADR-0022); miễn trừ ở assetscan-waivers.txt
	uv run python -m company.assetscan scan . ../Studio-creators
assetbudget:   # prompt tĩnh chiếm bao nhiêu phần ngân sách token của từng agent
	uv run python -m company.assetscan budget . ../Studio-creators
eval:
	uv run python -m company.evals $(AGENT)
eval-record:   # chạy model thật, lưu evals/recordings/$(AGENT).json — bắt buộc sau khi đổi prompt/skill (ADR-0010)
	uv run python -m company.evals $(AGENT) --record
eval-replay:   # như CI: phát lại từ bản ghi, không gọi model
	uv run python -m company.evals all --replay
run:
	uv run python -m company.orchestrator run
watch:
	uv run python -m company.orchestrator run --watch 5
status:
	uv run python -m company.orchestrator status
report:
	uv run python -m company.orchestrator report
metrics:       # gọi/token/USD/thời gian theo agent, model, ticket; thêm PROM=1 để xuất Prometheus text
	uv run python -m company.orchestrator metrics $(if $(PROM),--prometheus,)
