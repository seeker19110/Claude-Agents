# Đặc tả triển khai ADR-0037 — 21 agent → 5, `GateKind` 5 → 4 (hai gate công đoạn)

Tài liệu này là bản chỉ dẫn từng PR để cài ADR-0037. Mỗi mục có: file chạm, thay đổi cụ thể, test hai chiều, lệnh
kiểm, tài liệu đi kèm. Đọc `AGENTS.md` trước: mỗi PR một scope, tiêu đề `<type>(company): …`, không hạ coverage,
`agents/`/`skills/` đổi thì đủ 7 bước `CONTRIBUTING.md` §3.

Số liệu nền (đo trên `main` 2026-09-07): 21 agent, 45 skill, 19 topic, 5 `GateKind`, id agent xuất hiện trong 31
file `src/` + `console/src/console/truth.py` (179 chỗ; nhiều nhất `delivery-lead` 30, `release-engineer` 15,
`security-engineer` 13, `supervisor` 13, `account-manager` 11, `spec-writer` 11).

## Cách dùng tài liệu này khi giao cho agent thực thi

Mỗi phiên agent nhận **đúng một PR** trong bảng §0, với câu lệnh dạng:
`Triển khai PR-<n> theo docs/DAC-TA-TRIEN-KHAI-ADR-0037.md §<mục>. Đọc AGENTS.md, CLAUDE.md, TRAPS.md trước.`

Luật cho phiên đó:
1. Không làm PR khác trong cùng phiên, kể cả khi "tiện tay". Không làm trước PR có phụ thuộc chưa merge.
2. Mọi mục "Test hai chiều" phải có bằng chứng trong commit message: dán output `pytest` **đỏ** khi tắt bản sửa và
   **xanh** khi bật (AGENTS.md bắt buộc §4).
3. "Xong" = output của đúng ba lệnh CI trong phiên: `uv run ruff check src tests` · `uv run mypy src/company
   --ignore-missing-imports` · `uv run pytest -q -n auto --cov` (coverage 100). PR-5x thêm `make golden`,
   `make assetscan`, `make assetbudget`, `make subagents-check`, `make eval-replay`.
4. PR-5x cần bản ghi eval bằng model thật (`make eval-record AGENT=<id>` hoặc workflow Actions `eval-record`).
   Không có key → dừng và nói rõ, **không** ghi tay recording, không xoá agent khỏi `REQUIRED.txt`.
5. Gặp điều đặc tả không nói: nêu giả định thành lời trong PR body và đi tiếp; chỉ hỏi khi sai giả định làm việc
   vô dụng (AGENTS.md "Khi bối rối").
6. Tiêu đề PR đúng regex `AGENTS.md` §7; scope một từ `company` (`console` cho phần console của PR-2/PR-6);
   bật auto-merge squash; `gh pr list --state open` trước — chỉ một PR mở tại một thời điểm.
7. Không sửa `.claude/agents/sc-*`, `tests/golden/`, `evals/recordings/` bằng tay — chỉ qua `make`.

## 0. Thứ tự PR và phụ thuộc

```
PR-1 fix(company): _check_plan chặn hết khoá của gate plan      ← không phụ thuộc, làm được ngay
PR-2 refactor(company): bỏ GateKind plan                          ← sau PR-1
PR-3 feat(company): skill theo pha (phases) + assetbudget theo pha ← độc lập với PR-1/2
PR-4 refactor(company): bảng route + hằng tên vai (ROLE) một chỗ  ← sau PR-2, PR-3; KHÔNG đổi agent nào
PR-5a..5e refactor(company): từng agent mới, xoá agent cũ          ← sau PR-4; thứ tự: security → ops → qa → builder → product
PR-6 docs(company): README/ARCHITECTURE/CODEMAP/HUONG-DAN, console
```

Tại sao thứ tự 5a→5e: `security` là gộp 1:1 (đổi tên) — dùng nó để chứng minh quy trình đổi tên chạy qua CI trước
khi làm agent gộp nhiều nguồn. `product` cuối cùng vì nó chạm nhiều route nhất.

Mỗi PR-5x **phải xanh toàn bộ** (kể cả `eval-replay --strict`) trước khi mở PR-5 kế tiếp. Trong lúc chuyển, hệ ở
trạng thái lai (một số agent mới, một số cũ) — đó là lý do PR-4 gom tên vai về một chỗ.

## 1. Trạng thái đích

### 1.1 Front matter năm agent

Trường mới `phases:` (PR-3). `skills`/`skills_core` cấp agent = nạp ở **mọi** pha; `phases.<tên>.skills(_core)` = nạp
thêm khi route khai `phase=<tên>`. Quy tắc chủ quản (ADR-0016) tính trên hợp của cấp agent và mọi pha.

```yaml
# agents/research/product.md
id: product
block: research
model_tier: strong
reads: [research-requests, research-findings, requirements-draft, clarification-answers, change-requests,
        approved-specs, incidents, acceptance-results, review-results]
writes: [research-findings, requirements-draft, clarification-questions, approved-specs, tasks, audit-log]
context_namespace_write: [prd, glossary, design, architecture, api-contract]
context_namespace_read: [threat-model, schema, infra, knowledge, contract]
max_input_chars: 100000
skills: [requirements-engineering, technical-writing]
skills_core: [customer-acceptance]
phases:
  intake:   {skills: [domain-research], skills_core: []}                                   # intake + clarifier
  research: {skills: [tech-evaluation, codebase-analysis, ui-ux-design, legacy-modernization],
             skills_core: [accessibility, license-compliance, ai-feature-engineering]}     # researcher
  spec:     {skills: [risk-analysis],
             skills_core: [threat-modeling, privacy-compliance, ai-governance, license-compliance, project-management]}  # synthesizer + spec-writer + risk
  plan:     {skills: [project-management, architecture, cost-estimation],
             skills_core: [api-contract, release, event-driven-architecture, incident-management]}  # delivery-lead
budget_tokens_per_task: 100000
max_retries: 2
timeout_minutes: 120
version: 1
```

```yaml
# agents/engineering/builder.md
id: builder
block: engineering
model_tier: strong
reads: [tasks, test-suites]
writes: [pull-requests]
context_namespace_write: [api-contract, schema, infra, analytics]
context_namespace_read: [prd, architecture, threat-model]
max_input_chars: 100000
skills: [engineering-common]
skills_core: [observability, testing, security]
phases:                       # chọn theo `stack` của ticket (ADR-0013), KHÔNG theo route
  backend:  {skills: [backend, api-contract, ai-feature-engineering, event-driven-architecture], skills_core: [i18n, database]}
  frontend: {skills: [frontend, accessibility, i18n], skills_core: [ui-ux-design, performance-testing]}
  mobile:   {skills: [mobile, accessibility], skills_core: [ui-ux-design, i18n, performance-testing]}
  database: {skills: [database], skills_core: [privacy-compliance, performance-testing]}
  platform: {skills: [iac-platform, devops, observability, disaster-recovery, resilience-testing, secrets-management],
             skills_core: [finops, incident-management]}
  data:     {skills: [data-engineering], skills_core: [database, privacy-compliance, event-driven-architecture]}
budget_tokens_per_task: 120000
max_retries: 3
timeout_minutes: 180
version: 1
```

```yaml
# agents/quality/qa.md
id: qa
block: quality
model_tier: standard
reads: [tasks, pull-requests, release-events]
writes: [test-suites, review-results]
context_namespace_write: null
context_namespace_read: [prd, api-contract]
max_input_chars: 70000
skills: [testing]
skills_core: [engineering-common, api-contract, accessibility]
phases:
  author: {skills: [], skills_core: []}                                                   # test-author: lượt MÙ
  review: {skills: [code-review, code-ownership, debugging, performance-testing],
           skills_core: [security, license-compliance, observability]}                    # reviewer + qa-debugger
budget_tokens_per_task: 60000
max_retries: 1
timeout_minutes: 60
version: 1
```

```yaml
# agents/quality/security.md      — đổi tên security-engineer, giữ nguyên nội dung, version tăng
id: security
block: quality
model_tier: strong
max_input_chars: 70000
skills: [threat-modeling, security, license-compliance, privacy-compliance, dependency-management]
skills_core: [ai-governance, devops]
# reads/writes như security-engineer hiện tại
```

```yaml
# agents/operations/ops.md
id: ops
block: operations
model_tier: standard
reads: [release-candidates, release-events, external-feedback, incidents, acceptance-results]
writes: [release-events, incidents, research-requests, change-requests]
context_namespace_write: [docs, contract]
context_namespace_read: [prd, architecture, infra, knowledge]
max_input_chars: 70000
skills: []
skills_core: [observability]
phases:
  deploy:  {skills: [release, devops], skills_core: [incident-management, license-compliance, security]}   # release-engineer
  docs:    {skills: [technical-writing, incident-management], skills_core: [requirements-engineering]}       # support-docs
  account: {skills: [customer-acceptance, handover], skills_core: [project-management, cost-estimation, risk-analysis]}  # account-manager
budget_tokens_per_task: 60000
max_retries: 2
timeout_minutes: 60
version: 1
```

`supervisor` giữ nguyên (`ai-governance`, `prompt-engineering`, `finops`).

Kiểm chủ quản (ADR-0016) trên bảng trên: cả 45 skill đều có ít nhất một chỗ nạp đầy đủ — `ai-governance`, `finops`,
`prompt-engineering` ở supervisor; `dependency-management`, `privacy-compliance`, `license-compliance` ở security;
`performance-testing`, `debugging`, `code-review`, `code-ownership` ở qa[review]; `handover` ở ops[account]; số còn
lại ở product/builder theo pha. Quy tắc trùng mở rộng ở PR-3: một skill được nạp **đầy đủ ở pha** và **rút gọn ở cấp
agent** (vd. `observability` của builder) — pha thắng khi pha đó chạy; cấm trùng trong cùng một cấp.

### 1.2 Bảng route đích (`src/company/orch/routes.py`)

```python
ENGINEERING = ("builder",)
REVIEW_AGENT = {"reviewer": "qa", "qa": "qa", "security": "security"}
BUILD_PHASES = ("backend", "frontend", "mobile", "database", "platform", "data")  # = Task.stack

ROUTES = (
    # nghiên cứu → spec: một agent, bốn pha, guard giữ nguyên
    Route("research-requests",     "product", "research-findings",      phase="intake"),
    Route("research-findings",     "product", "research-findings",      _from_kind("intake"), tools="research", phase="research"),
    Route("research-findings",     "product", "requirements-draft",     _from_kind("research"), enrich=_with_intake, phase="spec"),
    Route("requirements-draft",    "product", "clarification-questions", _from_phase("spec"), phase="intake"),
    Route("clarification-answers", "product", "clarification-questions", _answers_incomplete, enrich=_with_draft, phase="intake"),
    Route("clarification-answers", "product", "approved-specs",         _spec_ready, enrich=_with_draft, phase="spec"),
    # ticket
    Route("tasks",         "qa",      "test-suites",   _can_author_tests, tools="tests", phase="author"),
    Route("tasks",         "builder", "pull-requests", _no_test_author, tools="rw"),           # phase = payload.stack
    Route("test-suites",   "builder", "pull-requests", enrich=_with_task, tools="rw"),
    Route("pull-requests", "qa",      "test-suites",   _has_dispute, enrich=_with_diff, tools="tests", phase="author"),
    Route("pull-requests", "qa",      "review-results", enrich=lambda e,o: {**_with_diff(e,o), **_with_chan_doan(e,o)}, tools="ro", phase="review"),
    Route("pull-requests", "security","review-results", _needs_security, enrich=_with_diff, tools="ro"),
    # release
    STAGING_ROUTE := Route("release-candidates", "ops", "release-events", target_env="staging", phase="deploy"),
    Route("release-candidates", "security", "review-results", _release_needs_security),
    Route("release-events", "qa",  "review-results", _deployed("staging"), tools="ro", phase="review"),
    Route("release-events", "ops", CONTEXT_ONLY, _deployed("production"), phase="docs"),
    # khách, hậu release
    Route("external-feedback",  "ops",     "change-requests", phase="account"),
    Route("external-feedback",  "ops",     "incidents", many=True, phase="docs"),
    Route("incidents",          "ops",     "research-requests", _field("root_cause_class", "requirement"), many=True, phase="docs"),
    Route("acceptance-results", "ops",     "change-requests", _field("verdict", "conditional"), many=True, phase="account"),
    Route("change-requests",    "product", "audit-log", _field("decision", "pending"), phase="plan"),
    Route("change-requests",    "product", "research-findings", _cr_accepted_needs_research, phase="intake"),
)
PROD_ROUTE   = Route("release-candidates", "ops", "release-events", target_env="production", phase="deploy")
THREAT_ROUTE = Route("approved-specs", "security", "review-results")
```

**Guard theo pha thay guard theo actor.** Hiện `_from("intake")`, `_from("researcher")`, `_from("risk")` phân biệt
lượt bằng `env.actor`. Khi ba lượt cùng actor `product`, guard phải đọc pha đã sinh event: runner ghi
`payload["_phase"]` (PR-3) và `_from_phase(name)` so với nó. Chuỗi research-findings có `kind` (`intake`/…) sẵn
trong payload — `_from_kind` dùng nó, không cần `_phase`.

Chuỗi `requirements-draft`: synthesizer → risk → clarifier hiện là ba lượt. Đích gộp thành **một lượt pha `spec`**
(product viết draft đã kèm mục risk) rồi **một lượt pha `intake`** sinh câu hỏi. `Route("requirements-draft", "product",
"requirements-draft", _from("synthesizer"))` (lượt risk) **bị bỏ**; prompt pha `spec` phải ghi mục `risks` trong
draft (schema `requirements-draft.json` đã có trường này — kiểm ở PR-5e).

### 1.3 Plan không qua gate (đích của PR-1 + PR-2)

```
approved-specs ──gate spec──► security (threat model) ──► product[plan] (many=True → tasks)
        │                                                        │
        │                                              _check_plan(tickets) có problems?
        │                                     có ─► audit plan_rejected + escalation (như cũ)
        │                                     không ─► audit plan.proposed → _dispatch_plan NGAY
```

## 2. PR-1 `fix(company): _check_plan chặn đủ khoá của gate plan`

Mục tiêu: mọi mục "Code gửi kèm" của Gate 2 hiện tại trở thành `problems` của `_check_plan`, để PR-2 bỏ gate mà
không mất kiểm nào.

### 2.1 `src/company/orch/ticket_fsm.py::_check_plan`

Chữ ký đổi: `_check_plan(o, tickets, project: str) -> list[str]`. Thêm:

| Mục gate plan cũ | Kiểm mới trong `_check_plan` | Thông điệp |
|---|---|---|
| ticket ≤ 1 ngày / ≤ 200k token | `t.estimate_days > 1` hoặc `t.estimate_tokens > MAX_TICKET_TOKENS` (=200_000, hằng ở `events.py`) | `"<id> quá 1 ngày/200k token: chia nhỏ"` |
| `risk_tags` cho ticket chạm auth/payment/… | không có `risk_tags` **và** `title+scope+acceptance` (lowercase) chứa một từ trong `RISK_HINTS` (`events.py`: `{"auth","login","password","payment","thanh toán","pii","cccd","email","crypto","upload","admin","webhook","external"}`) | `"<id> chạm <từ> nhưng không có risk_tags"` |
| `threat-model` | `f"SPEC-{project}" in o.missing_threat_model` **hoặc** `o.latest("review-results", f"SPEC-{project}")` là `None` | `"thiếu threat model cho SPEC-<project>"` |
| `architecture`, `api-contract` | `o.blackboard.snapshot(project)` thiếu namespace tương ứng (chỉ khi `o.blackboard` có) | `"blackboard thiếu architecture"` |

Các kiểm cũ giữ nguyên (`estimate_tokens`, `budget ≥ estimate×1.5`, `acceptance`, `depends_on`, vòng).

Lưu ý thứ tự trong `_plan`: `g.context_writes` được ghi lên blackboard **trước** `_check_plan` (dòng 95–96 hiện tại)
— giữ, để kiểm `architecture` thấy được bản product vừa ghi.

### 2.2 Test hai chiều (`tests/test_check_plan_adr0037.py`, file mới → sửa số file test trong README)

- `test_ticket_qua_lon_bi_tu_choi`: `estimate_tokens=250_000` → có problem; hạ về 100_000 → không.
- `test_risk_hint_khong_tag`: title "Đăng nhập OAuth" không `risk_tags` → problem; thêm `risk_tags=["auth"]` → không.
- `test_thieu_threat_model`: không có `review-results` key `SPEC-P` → problem; publish một `review-results` verdict
  pass → không.
- `test_thieu_architecture_tren_blackboard`: blackboard rỗng → problem; ghi `architecture` → không.
- Chiều "tắt bản sửa": mỗi test kèm `monkeypatch` bỏ kiểm tương ứng (đặt `MAX_TICKET_TOKENS=10**9`,
  `RISK_HINTS=frozenset()`) và assert problem **không** xuất hiện — chứng minh test đo đúng dòng.

### 2.3 Lệnh kiểm

```bash
cd software-company && uv run ruff check src tests && uv run mypy src/company --ignore-missing-imports \
  && uv run pytest -q -n auto --cov
```

Tài liệu: `gates/checklists.md` Gate 2 thêm dòng ghi chú "mọi khoá Code gửi kèm nay bị `_check_plan` chặn trước";
`TRAPS.md` không đổi.

## 3. PR-2 `refactor(company): bỏ GateKind plan`

### 3.1 Code

| File | Đổi |
|---|---|
| `src/company/gates.py:7` | `GateKind = Literal["spec", "release", "escalation", "acceptance"]` |
| `src/company/orch/ticket_fsm.py::_plan` | nhánh `else` (dòng 123–130): sau `plan.proposed` gọi `o._dispatch_plan(plan_id)` ngay, `res.actions.append(f"dispatch:{','.join(done)}")`; xoá `gate.request(kind="plan")`. Dòng 76–77 `live` đổi điều kiện `pid in o.gate.pending or o.gate.is_approved(pid)` → `pid in o.plans and not o.plans[pid]["problems"]` (plan sống = đã dispatch) |
| `src/company/delivery.py:113–116` | `dispatch(task, plan_id)`: bỏ `gate.is_approved`; thay bằng `if not self.replaying and plan_id not in self.plans_ok: raise PermissionError("plan chưa qua _check_plan")`; thêm `self.plans_ok: set[str] = set()`; orchestrator `o.lead.plans_ok.add(plan_id)` ngay trước `_dispatch_plan` — vẫn là guard bằng code, chỉ đổi nguồn sự thật từ gate sang `_check_plan` |
| `src/company/orch/gates_flow.py:39–43` | xoá nhánh `if sid in o.plans` trong `_on_gate_decide` |
| `src/company/orch/rehydrate.py:80–82` | xoá nhánh dựng lại từ `gate.decide` approve plan; thay: mọi `plan.proposed` trong audit → `o.plans[...]`, `o.lead.plans_ok.add`, `_dispatch_plan(..., replaying=True)` |
| `src/company/orch/release_fsm.py:57` | `extra["gate_release"]` giữ; không đụng |
| `src/company/gate_checklists.py` | xoá `"plan"` khỏi `SELF_CHECK_SOURCES`, `EXPERTS`; parser tự yêu cầu `checklists.md` khớp `GateKind` |
| `src/company/gate_brief.py:138,601` | xoá `_brief_plan` và nhánh gọi; `--all` liệt kê 4 kind |
| `src/company/demo.py:44` | gate demo đổi sang `kind="spec"` |
| `gates/checklists.md` | xoá mục "Gate 2 — Duyệt plan"; đánh số lại: Gate 1 spec, Gate 2 release; mục "Nghiệm thu" (kind `acceptance`) và "Gate bất thường" giữ nguyên tiêu đề dạng `## Gate … (kind \`acceptance\`…)` vì parser bắt `## Gate`. Chuyển hai mục tự kiểm của plan ("Ước lượng có cơ sở", "Ngân sách token dự án") sang "Người tự kiểm thêm" của Gate release, thêm nguồn ở `SELF_CHECK_SOURCES["release"]` |
| `console/src/console/truth.py:68,85,102` | xoá nhánh `plan` trong `NEXT_AGENT`, `gate_reject_effect`, `gate_effect` (PR riêng scope `console` nếu CI console tách; nếu không, cùng PR) |
| `tests/test_subagents.py:20` | `N_GATES = 4` |

### 3.2 Test hai chiều

- `tests/test_delivery_and_gates.py`: các test mở gate plan → đổi thành assert `dispatch:` xuất hiện trong
  `res.actions` ngay sau `plan.proposed`, và `gate.pending` **không** có `PLAN-*`.
- Test mới `test_plan_khong_qua_check_thi_khong_dispatch`: plan có problem → không ticket nào `dispatched`, có gate
  `escalation` (hành vi cũ giữ).
- Test mới `test_dispatch_tu_choi_plan_chua_check`: gọi `lead.dispatch(task, "PLAN-X")` khi `PLAN-X ∉ plans_ok` →
  `PermissionError`. Tắt guard → test đỏ.
- `test_orch_state_rehydrate.py`: kịch bản có `plan.proposed` trong audit, mở lại bus → ticket ở `dispatched`,
  không cần `gate.decide`.
- `test_gate_brief.py`: `--all` không còn `plan`.

### 3.3 Sinh lại và kiểm

```bash
make subagents && make subagents-check     # sc-gate-plan.md biến mất; commit .claude/agents/
uv run pytest -q -n auto --cov
```

Tài liệu cùng PR: `README.md` (dòng 38, 148: "4 human gate" → "2 human gate công đoạn + nghiệm thu + escalation";
`GateKind = spec|release|acceptance|escalation`), `CLAUDE.md` dòng 3, `docs/architecture.md` mục gate.

## 4. PR-3 `feat(company): skill theo pha`

### 4.1 `src/company/registry.py`

```python
@dataclass
class Phase:
    skills: list[str] = field(default_factory=list)
    skills_core: list[str] = field(default_factory=list)

class AgentSpec:
    phases: dict[str, Phase] = field(default_factory=dict)
    _phase_text: dict[str, tuple[str, str]]   # tên pha → (skill_text, skill_core_text) đã nạp

    def system_prompt(self, phase: str | None = None) -> str:
        # phần chung như cũ + phần pha nối sau, tiêu đề "# Skills của pha <tên>"
    @property
    def all_skills(self): return hợp của cấp agent và mọi pha
```

`load_agents`: parse `phases`, kiểm (a) tên pha không trùng skill cấp agent (`dup` như hiện có, mở rộng), (b)
`check_owners` tính chủ quản trên hợp `skills` cấp agent ∪ mọi `phases.*.skills`, (c) pha khai trong front matter mà
không route nào dùng → không kiểm ở đây (PR-4 `check_routes` làm).

### 4.2 `src/company/orch/routes.py`

`Route` thêm `phase: str | None = None`. `check_routes`: `r.phase` phải ∈ `spec.phases` (hoặc `None`). Với route
`tools="rw"` tới `builder`, pha lấy từ `payload["stack"]` lúc chạy: thêm vào `Task` trường
`stack: Literal[BUILD_PHASES] | None = None` (schema `topics/schemas/tasks.json` cùng lúc — `test_schema_consistency`),
product điền khi chia ticket; thiếu → `_check_plan` báo `"<id> thiếu stack"`. (Trường `assignee` giữ để tương thích
schema, giá trị duy nhất `builder`; bỏ hẳn ở một PR sau khi đã chạy ổn.)

### 4.3 `src/company/runner.py`

`generate(..., phase: str | None = None)` và `generate_in_workspace(...)`, `run_context(...)` nhận `phase`; dùng
`spec.system_prompt(phase)`; `fit(...)` tính trên prompt đúng pha. Ghi `phase` vào audit của lượt (`_audit(..., phase=)`)
và vào payload đầu ra `_phase` (guard `_from_phase` ở §1.2 đọc trường này; schema các topic thêm `_phase` optional).

`Orchestrator._call`: `phase = r.phase or (inp.payload.get("stack") if r.tools == "rw" else None)`; truyền xuống.

### 4.4 `src/company/assetscan.py::agent_weights`

Mỗi agent có `phases` → một `Weight` cho **mỗi pha** (`agent="product[plan]"`), tokens = thân + skill chung + skill
pha. Ngưỡng 50% `budget_tokens_per_task` áp cho từng dòng. Agent không có pha: như cũ.

### 4.5 Test hai chiều

- `test_registry.py`: agent giả có `phases` → `system_prompt("x")` chứa skill pha, `system_prompt()` không; skill
  chỉ nằm trong pha vẫn tính là có chủ quản (tắt (b) → `test_every_skill_has_an_owning_agent` đỏ với fixture).
- `test_routing.py`: `Route(phase="lạ")` → `check_routes` báo.
- `test_runner_and_persistence.py`: `generate(phase="x")` → audit có `phase="x"`, prompt gửi client chứa skill pha.
- `test_assetscan.py`: agent hai pha → hai dòng `Weight`.

Không đổi agent nào trong PR này → không cần 7 bước.

## 5. PR-4 `refactor(company): gom tên vai về một chỗ`

Mục tiêu: sau PR này, đổi tên một agent chỉ sửa **một** file mã và file `agents/`.

- Tạo `src/company/roles.py`:
  ```python
  # Tên vai. ADR-0037: đây là NƠI DUY NHẤT id agent xuất hiện dưới dạng chuỗi trong src/ (ngoài agents/*.md).
  PRODUCT, BUILDER, QA, SECURITY, OPS = "product", "builder", "qa", "security", "ops"
  SUPERVISOR = "supervisor"          # code, không phải công đoạn
  LEAD_ACTOR = "delivery-lead"       # actor của event do delivery.py phát — không phải agent
  ```
  Ở PR-4 các hằng vẫn mang giá trị **cũ** (`PRODUCT = "spec-writer"`… tạm), chỉ thay chuỗi literal trong 31 file
  bằng hằng. Không đổi hành vi; diff thuần cơ học.
- Test bảo vệ `tests/test_roles.py::test_khong_con_id_agent_dang_chuoi_trong_src`: grep `src/company/**/*.py`
  (trừ `roles.py`) và `console/src/console/truth.py` không chứa `"<id>"`/`'<id>'` cho mọi id trong `load_agents()`
  và mọi id cũ trong `OLD_IDS` (21 tên). Chiều ngược: thêm tạm một literal → test đỏ.
- `REVIEW_AGENT`, `ENGINEERING`, `NAMESPACE_OWNERS`, `EXPERTS`, `NEXT_AGENT` đều tham chiếu `roles`.

Ghi chú triển khai (đã làm, PR-4): hằng gom trong namespace `ROLE` (`ROLE.SECURITY`…), tên theo đích gộp cho agent sẽ
giữ tên, tên cũ cho agent bị gộp (`ROLE.INTAKE`, `ROLE.REVIEWER`…) — PR-5x đổi GIÁ TRỊ hằng, không đổi tên. Khoá của
`REVIEW_AGENT` (`reviewer|qa|security`) là nhãn `source`, không phải id agent → nhóm `SOURCE.*` riêng; `Assignee`/
`ReviewSource` (`Literal`) sống trong `roles.py`. Test dùng `tokenize` thay grep, miễn trừ duy nhất `payload.get("data")`.

## 6. PR-5a..5e — từng agent mới

Khuôn chung cho mỗi PR (đúng 7 bước `CONTRIBUTING.md` §3):

1. Tạo `agents/<khối>/<mới>.md` (front matter §1.1; thân bài gộp từ các file cũ: giữ nguyên mục *Definition of
   done* của từng vai cũ dưới tiêu đề pha tương ứng — `test_prompts_have_skills_and_dod` cần chuỗi đó).
2. Xoá các file `agents/` cũ **trong cùng PR**. `tests/test_registry.py::EXPECTED` cập nhật; `len == 21` giảm
   tương ứng (cuối PR-5e = 5).
3. `roles.py`: đổi giá trị hằng; `NAMESPACE_OWNERS` theo §1 ADR.
4. `evals/<mới>.yaml`: gộp ca của các agent cũ, mỗi ca khai `phase:`; `evals.py` truyền `phase` vào `generate`.
   Xoá yaml + recording cũ; `REQUIRED.txt` thay tên.
5. `make golden` → commit `tests/golden/agents/`.
6. `make eval-record AGENT=<mới>` (model thật, hoặc workflow Actions) → commit recording.
7. `make assetscan && make assetbudget` (theo pha, PR-3) → xanh.
8. `make subagents` → `.claude/agents/sc-<mới>.md` thay các `sc-<cũ>.md`.
9. `README.md` số agent/số file `sc-*`; `docs/dac-ta-tro-ly-kiem-duyet.md` bảng 77/325.

Riêng từng PR:

| PR | Agent | Việc riêng |
|---|---|---|
| 5a | `security` | Đổi tên thuần. `THREAT_ROUTE`, `_threat_model` (ticket_fsm 183–185), `RISK_REVIEWS` giữ `{"qa","security"}` tới 5c. `test_review_tiers_per_adr0021` đổi tên. |
| 5b | `ops` | Ba route `release-engineer` (+`PROD_ROUTE`, `_recall` ở gates_flow 47, release_fsm), hai route `support-docs`, hai route `account-manager` → `ops` với `phase`. `_open_acceptance_gate` `created_by=OPS`. `_close_acceptance_gate` audit `agent`. `EXPERTS["acceptance"]`, `["release"]`. `NAMESPACE_OWNERS`: `docs`, `contract` → `ops`. `context_namespace_read` test dòng 119 đổi danh sách agent có trần 70k. |
| 5c | `qa` | Hai route `test-author` → `qa` `phase="author"`; `reviewer` + `qa-debugger` → `qa` `phase="review"` (enrich gộp `_with_diff` + `_with_chan_doan` cho mọi ticket). `REVIEW_AGENT`. **`RISK_REVIEWS = {"security"}`** (ADR-0037 §3); `test_review_tiers_per_adr0021` sửa theo. `o.test_author` (cờ bật ADR-0028) giữ tên. `_with_task`: `"tests_authored_by": QA`. `runner._author_tests` audit tên. `EXPERTS["escalation"]`. Test mới `test_qa_hai_route_khac_tool`: lượt `author` không thấy `diff`/`hint` (BLIND_STRIP) và toolbox `write_scope="tests"`; lượt `review` toolbox read-only — tắt `phase` → hai lượt cùng prompt → test đỏ. |
| 5d | `builder` | `ENGINEERING=("builder",)`; `Assignee = Literal["builder"]` + schema `tasks.json` enum; `_rework_after_error`, `_engineer`, worktree_flow audit tên; `sc-<assignee>` trong `EXPERTS["escalation"]` → `sc-builder`. `stacks.py` không đổi (stack là của repo). `_call`: pha = `payload["stack"]`. Test: ticket `stack="frontend"` → prompt chứa skill `frontend`, không chứa `backend`. |
| 5e | `product` | Bảy route nghiên cứu (§1.2), `_plan` gọi `o.runner.generate(PRODUCT, inp, "tasks", many=True, phase="plan")`, `_spec_runtime_missing` `_recall(PRODUCT)` + route pha `spec`, `_act_clarification_fallback`, `PLAN_INPUTS` check (`check_routes` dòng 310–311 → `agents[PRODUCT]`), `_stall`/`RESEARCH_TOPICS` không đổi. Bỏ lượt `risk` (§1.2). `NAMESPACE_OWNERS`: `prd, glossary, design, architecture` → `product`; `api-contract` → `{product, builder}`. `MAX_CLARIFY_ROUNDS` giữ. Test: chuỗi research end-to-end với client giả đi `intake → research → spec → intake(câu hỏi) → spec(approved)` đúng 5 lượt, audit `phase` đúng thứ tự; guard `_from_phase` tắt → chuỗi lặp vô hạn hoặc sai thứ tự → test đỏ. |

Sau 5e: `tests/test_registry.py::EXPECTED = {product, builder, qa, security, ops, supervisor}`... **lưu ý**:
`supervisor` là một file trong `agents/` (khối `supervisor`) nên `load_agents()` trả **6**; ADR nói "5 agent, supervisor
không đếm". Test khoá `len == 6` với comment nêu rõ; README ghi "5 agent + supervisor (code)".

## 7. PR-6 `docs(company)` + `docs(console)`

- `README.md` (gốc + package): 21 → 5(+1), 26 → 7 subagent, "4 human gate" → "2 gate công đoạn + nghiệm thu +
  escalation", ADR 0001–0037, số test/file đo lại (`test_readme_khop_so_lieu_that`).
- `ARCHITECTURE.md`, `CODEMAP.md`, `docs/architecture.md` (bảng Consumer theo route mới), `docs/HUONG-DAN-VAN-HANH.md`,
  `docs/TRUC-VA-DUNG-KHAN.md` (tên agent trong lệnh takeover/hint), `docs/DIEU-PHOI-MODEL.md` (tier: strong =
  product, builder, security; standard = qa, ops).
- `.claude/CLAUDE.md` dòng 21 (7 trợ lý); `.claude/agents/` đã sinh ở các PR-5.
- `CHANGELOG.md` một dòng cho mỗi PR đã merge; `docs/sessions/<ngày>.md`.
- Console: `truth.py` `NEXT_AGENT = {"release": "ops", "spec": "security + product", "acceptance": "ops", …}`.

## 8. Rủi ro và cách lùi

| Rủi ro | Dấu hiệu | Lùi |
|---|---|---|
| `product` pha `plan` chia ticket kém hơn delivery-lead cũ (prompt loãng) | `plan_rejected` tăng trong `metrics`, `sprint_report` ratio xấu | tách pha `plan` thành agent thứ 6 `planner` — một PR, không cần đổi route khác |
| Mất gate plan → token đốt cho plan sai | `ticket_lead_seconds` và `retry` tăng ở 3 dự án đầu | ADR mới đưa `plan` về; PR-2 đảo được vì `plans_ok` là superset của `is_approved` |
| `qa` lượt review nhìn thấy test của chính nó | không phải rủi ro: reviewer cũ cũng đọc test của test-author; bất biến là *lượt author không thấy code* | — |
| Bản ghi eval model thật cho 5 agent mới | thiếu → CI đỏ có chủ đích | không lách; dùng workflow `eval-record` |
| Rehydrate log cũ có `gate.decide` cho `PLAN-*` | mở lại bus dự án cũ | PR-2 rehydrate bỏ qua decide của subject không còn kind → chỉ audit, không lỗi |

## 9. Định nghĩa "xong" của toàn bộ ADR-0037

- `uv run pytest -q -n auto --cov` xanh với `fail_under = 100` ở cả 5 package.
- `make subagents-check`, `make assetscan`, `make assetbudget`, `make eval-replay` (strict) xanh.
- `uv run python -m company.orchestrator status` trên dự án demo: một `research-requests` đi tới `UAT-*` với đúng
  số lượt gọi ADR §Hệ quả (3/4/5), đọc từ `metrics`.
- Không còn chuỗi id agent cũ trong `src/`, `console/`, `docs/` (trừ ADR lịch sử và `CHANGELOG.md`).

## 10. Thân bài (prompt) của năm agent

Khuôn mục giữ nguyên như mọi agent hiện có — `# <id>` · `## Vai trò` · `## Bạn PHẢI` · `## Bạn KHÔNG ĐƯỢC` ·
`## Đầu vào` · `## Đầu ra (schema trong topics/schemas/)` · `## Definition of done` · `## Quy tắc chung` —
vì `subagents.sections()` cắt theo các H2 này và `test_than_bai_co_du_bon_khoi` đếm chúng. Với agent nhiều pha, mỗi
mục có **tiểu mục H3 theo pha** (`### Pha intake`, …); phần trước H3 đầu tiên là phần chung cho mọi pha.

Nguyên tắc ghép: **chép nguyên văn** các dòng "PHẢI/KHÔNG ĐƯỢC" của agent cũ vào H3 pha tương ứng, không viết lại
bằng lời khác — mỗi dòng ấy là một bài học đã trả giá (ADR-0004, `docs/reports/`). Chỉ xoá dòng nói về *một agent khác
mà nay cùng là mình* (vd. intake "gửi cho researcher" → "sang pha research").

### 10.1 `product`

- Chung: "Model quyết định, code hành động" — bạn không tạo ticket, không xin gate; orchestrator làm. Đọc `_phase`
  của lượt để biết mình đang ở pha nào; **không tự nhảy pha**.
- `### Pha intake` ← intake.md + clarifier.md: tách yêu cầu thành mục tiêu/ràng buộc/giả định; câu hỏi có lựa chọn
  sẵn, tối đa 2 vòng (`MAX_CLARIFY_ROUNDS`), gom một lần.
- `### Pha research` ← researcher.md: báo cáo 4 mục domain/ux/codebase/tech (ADR-0006); sở hữu `glossary`, `design`.
- `### Pha spec` ← synthesizer.md + spec-writer.md + risk.md: draft thống nhất, khử trùng lặp, **mục `risks` nằm
  ngay trong draft** (thay lượt risk); PRD theo `templates/prd.md`, Gherkin 100% Must, `kind` + `runtime` bắt buộc
  (ADR-0031).
- `### Pha plan` ← delivery-lead.md: C4 L1–L2 + ADR lên `architecture`, contract lên `api-contract` **trước** khi trả
  ticket; ticket ≤ 1 ngày/200k token, `estimate_tokens`, `budget_tokens ≥ ×1.5`, `risk_tags`, `depends_on`, **`stack`**
  (mới, §4.2); nhận `estimate_calibration` từ supervisor.
- DoD: mỗi pha một dòng DoD riêng, giữ nguyên chữ "Definition of done" ở H2.

### 10.2 `builder`

- Chung ← engineering-common + phần chung của backend/frontend/mobile: nhận `test_suite` của qa, **không sửa được
  test** (tool chặn) — bất đồng thì ghi `test_dispute`; `local_checks` do code điền (ADR-0010); rulings (ADR-0030).
- `### Stack backend|frontend|mobile|database|platform|data` ← file tương ứng. Pha chọn theo `payload.stack`,
  không theo route; ticket không có `stack` không tới được đây (`_check_plan` chặn).
- KHÔNG ĐƯỢC: tự đổi `stack`; ghi vào `architecture` (chỉ product).

### 10.3 `qa`

- `### Pha author` ← test-author.md **nguyên văn** (khối trích ở trên là chuẩn): viết MÙ, chỉ ghi `tests/`, test đỏ vì
  chưa có code là ĐÚNG; lượt `test_dispute` mới được xem diff.
- `### Pha review` ← reviewer.md + qa-debugger.md: đọc diff bằng tool, không tin `summary`; chấm test có phủ
  Gherkin không; `chan_doan` (lịch sử hỏng của ticket) để không chẩn đoán lại từ đầu; trên `release-events`
  staging: hồi quy + perf + a11y, `source: qa`, `ticket_id = release_id`, verdict bị `_verdict_with_run` đối chiếu
  với smoke (ADR-0029/0036).
- Chung KHÔNG ĐƯỢC: ở pha review nới assert của test mình viết ở pha author để PR xanh — nếu test sai đặc tả thì
  ghi `finding` cho builder mở `test_dispute`, không tự sửa.

### 10.4 `security` — thân bài security-engineer.md không đổi; đổi tên trong `# security` và các câu tự xưng.

### 10.5 `ops`

- `### Pha deploy` ← release-engineer.md: staging trước, production chỉ sau gate `release` (`PROD_ROUTE`), `env` và
  `release_id` là của route không phải lời khai; rollback theo SLO.
- `### Pha docs` ← support-docs.md: Diátaxis, Keep a Changelog, incident → `root_cause_class`.
- `### Pha account` ← account-manager.md: SOW/UAT trong `contract`, change request có impact, **không ký thay khách**
  (gate `acceptance` do bạn tạo nên bạn không thể là người quyết — code cưỡng chế, prompt nhắc).

## 11. Eval theo pha (`evals/<id>.yaml`, `src/company/evals.py`)

- Ca eval thêm trường `phase:` (bắt buộc với agent có `phases`; `evals.py` báo lỗi nếu thiếu, và nếu `phase` không
  có trong front matter). `load_cases` truyền `phase` vào `runner.generate`. Bản ghi `evals/recordings/<id>.json`
  khoá theo `(agent, version, case, phase)`.
- Gộp ca: `product.yaml` = intake.yaml + clarifier.yaml + researcher.yaml + synthesizer.yaml + spec-writer.yaml +
  risk.yaml + delivery-lead.yaml, mỗi ca gắn `phase` tương ứng; ca của risk chuyển thành `expect.min_len:
  {risks: 1}` trên `requirements-draft` của pha `spec`. Tương tự `builder.yaml` (6 file, `phase` = stack),
  `qa.yaml` (3 file), `ops.yaml` (3 file). `security.yaml` đổi tên.
- Ca mới bắt buộc, mỗi agent ≥ 1: **"nhầm pha"** — input của pha A gửi với `phase: B` → `expect.refuses` (agent
  ghi `notes`/`findings` nói sai pha thay vì làm bừa). Đây là ca đo được nhất cho rủi ro "prompt loãng".
- `REQUIRED.txt`: 6 dòng (5 + supervisor). README dòng 56: "đủ 5 agent + supervisor, mỗi agent ≥ 2 ca/pha".

## 12. `gates/checklists.md` đích (PR-2)

Giữ đúng cú pháp parser (`## Gate … (kind \`x\`, subject …)`, hai dòng đầu mục `Code gửi kèm:` / `Người tự kiểm thêm:`).

```
## Gate 1 — Duyệt spec (kind `spec`, subject `SPEC-<project>`)           ← nguyên văn hiện tại
## Gate 2 — Duyệt release production (kind `release`, subject `<release_id>`)
Điều kiện mở: qa `pass` trên staging (+ security `pass` nếu release chứa ticket có `risk_tags`); threat model
`review-results` key `SPEC-<project>` tồn tại và không `block`; blackboard có `architecture` (dời từ gate plan cũ).
Code gửi kèm: tests, scan, regression-staging, smoke, perf, a11y, runbook, rollback, threat-model, architecture
- [ ] … 8 mục cũ giữ nguyên
- [ ] `threat-model` — threat model v1 có; High/Critical có mitigation hoặc ADR có người ký
- [ ] `architecture` — C4 L1–L2 và ADR trên blackboard
Người tự kiểm thêm:
- [ ] … 4 mục cũ
- [ ] Ước lượng có cơ sở (tham chiếu `knowledge` hoặc PERT)            ← dời từ plan
- [ ] Ngân sách token cho dự án được đặt; tổng estimate ≤ ngân sách     ← dời từ plan
## Gate nghiệm thu của khách (kind `acceptance`, subject = `UAT-<release_id>`)   ← nội dung Gate 4 cũ, bỏ số
## Gate bất thường (kind `escalation`, subject = ticket_id)                       ← nguyên văn; đoạn "Escalation cấp dự án"
   đổi danh sách agent thành "product (mọi pha nghiên cứu)"
```

`SELF_CHECK_SOURCES["release"]` thêm hai khoá dời từ `["plan"]` (giữ nguyên `id` cũ `plan.uoc-luong-co-co-so`… để hồ sơ
gate_brief cũ còn đọc được); `_maybe_open_release_gate` (delivery.py:323) thêm `threat-model`, `architecture` vào
`checklist=[…]`; `gate_brief._brief_release` đọc thêm hai nguồn đó.

## 13. Schema và topic (không thêm topic mới)

| File | Đổi | PR |
|---|---|---|
| `topics/schemas/tasks.json` | `assignee.enum` → `["builder"]`; thêm `stack` enum 6 giá trị (required) | 4.2 / 5d |
| mọi `topics/schemas/*.json` | thêm `_phase: {type: string}` optional | 3 |
| `topics/schemas/requirements-draft.json` | `risks` required (đã có trường; nâng lên required) | 5e |
| `topics/schemas/review-results.json` | `source` enum giữ `reviewer|qa|security` | — |
| `src/company/events.py` | `Assignee`, `Task.stack`, `MAX_TICKET_TOKENS`, `RISK_HINTS`, `NAMESPACE_OWNERS` | 1, 3, 5x |

`tests/test_schema_consistency.py` đối chiếu Pydantic ↔ JSON schema: đổi hai chỗ cùng PR.
