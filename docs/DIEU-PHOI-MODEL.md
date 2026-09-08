# Điều phối model theo gói tài khoản (subscription)

Các công ty trong X-Agents **không mua token qua API**. Chúng dùng những gói đăng ký đang có trên máy và tự chia việc
cho đúng model theo mức độ khó của từng agent, ưu tiên gói nào đang còn hạn mức. Tài liệu này là nguồn sự thật cho
ba câu hỏi: gói nào dùng được, agent nào cần model mức nào, và code điều phối ra sao.
Quyết định kiến trúc: `software-company/docs/adr/0019-subscription-routing.md`, `Studio-creators/docs/adr/0006-subscription-routing.md`.

## 1. Các gói tài khoản (backend)

| Backend | Cách nối | Model có | Đặc điểm |
|---|---|---|---|
| **Claude Pro/Max** | provider `claude-code`: CLI `claude -p` đã `claude login` trên máy | Opus / Sonnet / Haiku theo gói | Suy luận và code tốt nhất; hạn mức theo cửa sổ 5 giờ + tuần; `effort` → `--effort` (ADR-0026); tool-use bật bằng `mcp_tools: true` (ADR-0024, tool của công ty qua cầu MCP — giữ nguyên sandbox `tools.py`) hoặc `cli_tools: true` (ADR-0023, CLI tự cầm tool của nó); không bật thì backend này không nhận việc có tool. Nhiều tài khoản Claude trên một máy: mỗi tài khoản một backend với `config_dir` riêng (`CLAUDE_CONFIG_DIR`) |
| **ChatGPT Plus/Pro** | provider `codex`: Codex CLI `codex exec --json` đã `codex login` (app Codex trên Windows đi kèm CLI, tự tìm trong `%LOCALAPPDATA%/OpenAI/Codex/bin`) | GPT theo gói (vd. `gpt-5.6-terra`); `effort` → `model_reasoning_effort` | Structured output qua `--output-schema`; sandbox read-only trong thư mục rỗng; **không tool-use** của công ty. Nhiều tài khoản ChatGPT: mỗi tài khoản một backend với `config_dir` riêng (`CODEX_HOME`) |
| **Google Antigravity** | provider `openai` → `../gateway` (`http://127.0.0.1:1123/v1`), xoay vòng nhiều tài khoản Google | `gemini-3.7-flash` (+`-medium`/`-low`), `gemini-3.6-flash`, `gemini-3.1-pro`, `claude-sonnet-4-6` (alias khác map về 4 model upstream này, xem `gateway/README.md`) | Miễn phí theo quota từng tài khoản; gateway tự đổi tài khoản, hết cả pool thì trả 429 kèm "thử lại sau khoảng Ns"; có tool-use |
| **Model local** | provider `openai` → Ollama / vLLM / LM Studio | qwen3, llama, gemma... | Không bao giờ hết quota; chất lượng thấp hơn — lưới đỡ cuối cho việc nhẹ |
| (API trả phí) | provider `anthropic` / `openai` với key | tuỳ | Vẫn hỗ trợ, nhưng không phải mặc định của hub |

Khai báo trong `llm.yaml` của từng công ty dưới khoá `backends:` (mẫu trong `llm.example.yaml`). Thứ tự khai báo là
thứ tự ưu tiên; `routing.prefer` ghi đè theo tier. Khi mọi backend đều đang nghỉ: software-company ném `TransientError`
(orchestrator hoãn event, nhịp sau thử lại), Studio-creators ném `LLMError` (chạy lại `run` sau). Backend CLI có thể ép
`supports_tools: true` nếu muốn thử tool-use qua đó (mặc định false).

## 2. Ba tier

| Tier | Dùng cho | Model gợi ý (Claude sub / Antigravity / local) |
|---|---|---|
| `strong` | Suy luận nhiều bước, viết/sửa code, review có hậu quả, sáng tác cần chất lượng | Opus 5 / claude-sonnet-4-6 / qwen3:32b |
| `standard` | Việc có cấu trúc rõ, đầu vào đã được chuẩn hoá, sai thì có gate hoặc code kiểm lại | Sonnet 5 / gemini-3.7-flash / qwen3:8b |
| `light` | Việc cơ học, ngắn: phân loại, gom, tóm tắt, điền mẫu; sai thì rẻ để sửa | Haiku 4.5 / gemini-3.7-flash-low / qwen3:8b |

Backend thiếu model cho một tier thì dùng `standard`, rồi `strong` (không bao giờ hạ tier của yêu cầu, chỉ nâng khi
không còn lựa chọn).

## 3. Agent → tier

Tiêu chí xếp: (a) độ sâu suy luận cần thiết; (b) hậu quả nếu sai và có lớp nào bắt lỗi phía sau không (gate người,
code kiểm định, agent review khác); (c) độ dài/độ phức tạp đầu ra; (d) tần suất chạy (agent chạy nhiều lượt kéo chi phí).

### software-company (6 agent: 5 công đoạn + supervisor — ADR-0037)

ADR-0037 gộp 21 agent thành 5 công đoạn; mỗi công đoạn nhiều việc thì chia **pha** (`phases:` trong front matter).
Tier là của **agent**, không của pha — một agent chạy mọi pha của nó trên cùng một tier, nên tier phải đủ cho pha
nặng nhất. Đó là thay đổi thực chất so với bảng 21 dòng cũ: `intake`/`clarifier` từng là `light` nay chạy dưới
`product` (`strong`), còn `test-author` từng là `standard` nay chạy dưới `qa` (`standard`, không đổi).

| Agent | Tier | Pha | Vì sao |
|---|---|---|---|
| `product` | strong | `intake`, `research`, `spec`, `plan` | Pha `research` và `plan` quyết định tier: gom 4 mảng nghiên cứu có nguồn (eval `de-bai-day-du-phai-ra-4-muc-co-nguon` đo thật — không model `standard` nào đạt, xem ghi chú dưới), và kiến trúc/ước lượng/chia ticket có `depends_on` — sai kế hoạch kéo cả dự án. Pha `intake` nhẹ hơn nhưng đi chung agent nên đi chung tier |
| `builder` | strong | 6 stack (`backend`…`data`) | Viết code thật trong worktree, tool-use nhiều lượt, PR phải qua lint/test thật |
| `security` | strong | — | Threat model STRIDE, DAST; hậu quả sai cao, chạy ít lượt |
| `qa` | standard | `author`, `review` | Pha `author` viết test từ đặc tả, không nhìn code (ADR-0028): đầu vào hẹp, sai thì lộ ra ngay ở vòng `test_dispute`. Pha `review` đọc diff và chẩn đoán nguyên nhân — nặng hơn, nhưng phía sau còn gate `release` và smoke do orchestrator chạy. Theo dõi `review_catch_rate`: bỏ sót ca biên rõ rệt thì nâng `strong` kèm bằng chứng eval |
| `ops` | standard | `deploy`, `docs`, `account` | Cả ba pha là quy trình cố định trên đầu vào đã chuẩn hoá: gộp → build → staging → gate (phần nguy hiểm — merge, deploy, tag — là code); tài liệu Diátaxis + `root_cause_class`; SOW/UAT/change request theo mẫu, khách ký nghiệm thu là gate |
| `supervisor` | light | — | Phần xác định (ngân sách, watchdog) là code; model chỉ diễn giải và ghi bài học; chạy nhiều lượt nhất |

Ghi chú lịch sử còn giá trị (2026-09-03, khi `researcher` còn là agent riêng): hạ nó xuống `standard` đã hỏng —
eval đòi ≥3 glossary, ≥2 persona, ≥1 flow, ≥1 option kỹ thuật và trích đúng số hiệu văn bản; `gemini-3.8-flash-medium/high`,
`gemini-pro-agent`, `claude-sonnet-4-6` đều 0/2, `claude-sonnet-5` và `opus-5` pass 2/2. Đầu ra nghiên cứu mỏng thì
pha `spec` không cứu được: nó khử mâu thuẫn chứ không đi nghiên cứu lại. Đó là lý do `product` giữ `strong`.

### Studio-creators (14 agent)

| Agent | Tier | Vì sao |
|---|---|---|
| channel-strategist | strong | Kế hoạch biên tập có ước lượng/ưu tiên/rủi ro; gate `plan` duyệt nhưng chất lượng kế hoạch quyết định cả kênh |
| script-writer | strong | Sáng tác: hook, giữ chân, CTA, sổ claim có nguồn; chất lượng nội dung là sản phẩm |
| fact-checker, rights-checker, quality-reviewer | strong | Ba cổng review độc lập trước gate publish; sai ở đây là đăng nội dung sai/vi phạm bản quyền |
| trend-researcher | standard | Gom nguồn, bằng chứng, đối thủ theo mẫu dossier; script-writer và fact-checker (strong) dùng lại |
| production-manager | standard | Chia kịch bản thành scene manifest có cấu trúc; renderer là code, editor xem lại |
| editor | standard | Quyết định cut-list sửa/khoá cảnh; tối đa 3 vòng, quality-reviewer kiểm sau |
| seo-optimizer | standard | Metadata theo kho từ khoá; preflight là code kiểm lại |
| analytics-analyst | standard | Diễn giải số liệu đã được code tính (retention map, A/B đã kiểm định) |
| thumbnail-designer | light *(trước: standard)* | Đặc tả prompt + chữ phủ cho 2–3 biến thể; CTR đo thật, A/B chọn |
| publisher | light *(trước: standard)* | Chỉ mô tả hành động đăng sau khi gate đã duyệt; mọi thứ đã được chốt |
| community-manager | light *(trước: standard)* | Phân loại bình luận, nháp trả lời theo giọng kênh; gate `replies` duyệt từng câu |
| supervisor | light *(trước: standard)* | Như software-company |

Đổi tier của agent = sửa `model_tier` trong front matter + `make golden` (registry golden ghi tier); không cần tăng
`version` hay ghi lại bản ghi eval vì system prompt không đổi.

## 4. Chiến lược ưu tiên theo tier (gợi ý `routing.prefer`)

| Tình huống | prefer |
|---|---|
| Có Claude Max + Antigravity | `strong: claude-sub`, `standard: antigravity`, `light: antigravity` — việc nặng dùng gói mạnh, việc nhẹ dùng gói miễn phí để giữ hạn mức Claude cho code |
| Chỉ Claude Pro (hạn mức thấp) + Antigravity | `strong: antigravity` (claude-sonnet-4-6 qua gateway), `standard/light: antigravity`; Claude Pro làm dự phòng |
| Chỉ Antigravity | một backend; gateway tự xoay tài khoản |
| Có thêm Ollama | để cuối danh sách, không `prefer`; chỉ nhận việc khi mọi gói khác nghỉ |

Khối kỹ thuật của software-company (tool-use) luôn bỏ qua backend `codex`. Với `claude-code` thì tuỳ cấu hình: bật
`mcp_tools: true` (khuyến nghị) hoặc `cli_tools: true` là nhận việc có tool, không bật thì bị bỏ qua như trước. Muốn code bằng
model khác thì cho `claude-sonnet-4-6` qua Antigravity hoặc dùng provider `anthropic` có key.

## 5. Cơ chế xoay (code)

`RoutingClient` (`src/<company>/routing.py`) bọc mọi backend thành một `ModelClient`:

- Chọn backend: `prefer[tier]` trước, rồi theo thứ tự khai báo; bỏ backend không hỗ trợ tool khi request có tool.
- Hết quota (429/402, `RESOURCE_EXHAUSTED`, "usage limit", "thử lại sau Ns"...) → backend nghỉ `cooldown_s` (mặc định
  1 giờ) hoặc đúng số giây provider bảo; lượt đó đi backend kế.
- Lỗi mạng / 5xx / timeout → nghỉ `transient_cooldown_s` (mặc định 60 s).
- Lỗi nội dung (JSON hỏng, model từ chối) → ném ra ngay, không xoay: đó là việc của agent/supervisor.
- Mọi backend đều nghỉ → lỗi "thử lại sau Ns"; software-company hoãn event (TransientError), Studio ghi audit và
  supervisor thấy.
- Mỗi lần xoay được ghi vào audit `llm_retry` (qua `drain_retries()`), nên `report` cho thấy gói nào đang gánh việc.
- `Completion.model` vẫn là tên model thật để bảng giá `prices` khớp; gói subscription thì giá 0 nhưng vẫn phải có
  dòng giá để không bị đếm là `unpriced`.

Kiểm nhanh trạng thái gateway: `cd gateway && make status`. Trạng thái backend trong tiến trình orchestrator: ghi chú
`llm_retry` trong audit-log.
