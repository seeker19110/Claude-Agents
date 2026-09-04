# ADR-0026: Không thay harness bằng Agent SDK; adapter `claude-code` phải theo kịp CLI (`--effort` trước)

## Bối cảnh
Câu hỏi đặt ra (09/2026): "nâng cấp harness" có cần không? *Harness* ở repo này là lớp chạy agent tự viết: `runner`
(vòng tool, ngân sách, cắt ngữ cảnh), `tools.py` (sandbox), `llm.py` (adapter từng provider), `mcp_bridge` (ADR-0024),
`orchestrator`. "Nâng cấp" có hai nghĩa, phải trả lời riêng:

1. **Thay lõi** bằng Claude Agent SDK (Python `claude-agent-sdk`) hoặc coi Claude Code là harness.
2. **Theo kịp CLI**: `claude -p` đã có thêm cờ mà adapter chưa dùng, hoặc dùng sai.

Đo được, không đoán:
- Agent SDK vẫn spawn CLI Claude Code bên dưới và chỉ phục vụ Claude; chạy async (`anyio`), kéo thêm `mcp`. Repo có năm
  provider (`anthropic`, `openai`-compat/gateway, `claude-code`, `codex`, `fake`) và routing xoay gói (ADR-0019), nên SDK
  nhiều nhất là adapter thứ sáu — không thay được `runner`. Những gì SDK có (hooks, MCP in-process, permission callback,
  budget, structured output) repo đã có bản riêng, có test, và gắn với thứ SDK không có: bus, blackboard, human gate,
  routing, eval replay.
- CLI `claude` 2.1.261 (bản mới nhất npm cùng ngày): mọi cờ adapter đang dùng đều có; `--restricted` có từ 2.1.248 nên
  chế độ `cli_tools` (ADR-0023) cần bản ≥ 2.1.248, `make probe` đã dò được. Changelog 06–09/2026 không có thay đổi gãy
  nào chạm cờ đang dùng.
- **Lỗi thật**: CLI có `--effort <low|medium|high|xhigh|max>`; adapter `anthropic` truyền `effort` qua `output_config`,
  `codex` qua `model_reasoning_effort`, còn `ClaudeCodeClient` **không truyền gì**. `effort: {strong: high}` trong
  `llm.yaml` với gói Claude bị bỏ qua âm thầm — cùng loại lỗi #38 vừa sửa cho codex (`none` bị đổi thành `medium`).
- Chú thích "CLI không có structured output" đã lỗi thời: gọi thật một lượt với `--json-schema`, CLI trả thêm
  `structured_output` đã parse. JSON kết quả còn có `subtype` (`error_max_turns`, `error_max_budget_usd`…) mà `_parse`
  chưa đọc, nên hết lượt bị báo thành "thiếu trường result". CLI có `--max-budget-usd` (cắt ngay trong phiên, bịt một
  phần đánh đổi ADR-0023/0024 "ngân sách chỉ kiểm sau khi CLI trả về") và `--no-session-persistence` (mỗi lượt `-p`
  hiện ghi transcript chứa nội dung repo khách ra `~/.claude/projects`).
- `--bare` KHÔNG dùng được: nó tắt OAuth, chỉ nhận `ANTHROPIC_API_KEY`, phá tiền đề "gói Claude không cần key".
- `Studio-creators` giữ bản `ClaudeCodeClient` cũ hơn: system prompt qua argv (trần 30K trên Windows), truyền nguyên
  `os.environ` vào CLI, codex chưa có `none`. Đó là nợ harness thật, không phải SDK.

## Quyết định
1. **Giữ harness tự viết.** Không đưa Agent SDK vào; không có adapter SDK. Lý do ghi ở trên: trung lập provider là
   nguyên tắc đầu tiên của hub, và SDK không thêm năng lực nghiệp vụ nào mà chỉ thay một lớp đã có test.
2. **Adapter `claude-code` truyền `effort`** (bước 1, làm ngay trong ADR này): `--effort <mức>` theo tier ở cả ba chế độ
   (không tool, `cli_tools`, `mcp_tools`). Bảng `CLAUDE_EFFORT` **đóng**, không có `.get(..., mặc định)`: giá trị CLI không
   nhận (`none`, `minimal` của codex, gõ sai) là `LLMError` nói rõ các mức hợp lệ; tier không khai `effort` thì không thêm
   cờ, CLI dùng mặc định của nó. Test hai chiều trong `tests/test_routing.py`.
3. **Các bước sau, mỗi bước một PR nhỏ, không cần ADR mới**: (a) `--json-schema` + đọc `structured_output`, bỏ lượt "ép
   chốt bằng JSON" cho provider này; đọc `subtype` để báo đúng lỗi; thêm `--no-session-persistence`. (b) Đồng bộ adapter
   của `Studio-creators` theo bản `software-company`. (c) Nối `--max-budget-usd` với `budget_usd`.
4. **Không dùng `--bare`.** Ghi lại để không ai thử thêm nó "cho nhanh".

## Hệ quả
- `effort` trong `llm.yaml` có hiệu lực với gói Claude như với hai provider kia; agent tier `strong` chạy `high` thật
  thay vì mặc định của CLI. Cấu hình đang chạy: mặc định `{strong: high, standard: medium, light: low}` đều hợp lệ nên
  không đổi hành vi ngoài việc CLI giờ nhận cờ; ai khai `effort: {light: none}` ở cấp trên cho codex thì backend
  `claude-code` sẽ hỏng rõ ràng và phải khai `effort:` riêng cho backend đó — đúng ý: thà hỏng còn hơn chạy sai mức.
- CLI cũ không biết `--effort` sẽ thoát mã lỗi "unknown option" → `LLMError`; bản có `--restricted` (≥ 2.1.248) đã có
  `--effort`, nên trần phiên bản không tăng.
- Bảng đối chiếu "CLI có gì, adapter dùng gì" nằm ở ADR này; sửa adapter lần sau đọc `claude --help` trước, không tin
  chú thích cũ.
