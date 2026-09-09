# CODEMAP.md — software-company: muốn đổi X thì sửa ở đâu

## Tài sản prompt (đổi là phải đi 7 bước `../CONTRIBUTING.md` §3)

| Muốn | Sửa |
|---|---|
| Hành vi một agent: PHẢI / KHÔNG ĐƯỢC / DoD / đầu ra | `agents/<khối>/<id>.md` — sáu file sau ADR-0037: `research/product.md`, `engineering/builder.md`, `quality/qa.md`, `quality/security.md`, `operations/ops.md`, `supervisor/supervisor.md`. Hành vi riêng của một PHA nằm trong tiểu mục `### Pha <tên>` (builder: `### Stack <tên>`) của chính file đó, không phải file khác |
| Agent đọc topic nào, ghi topic nào, tier model, ngân sách, tool | front matter của file agent: `reads`, `writes`, `model_tier`, `budget_tokens_per_task`, `tools`, `skills`, `skills_core` |
| Skill chỉ nạp ở MỘT loại lượt của agent | `phases:` trong front matter agent (ADR-0037); lượt nào chạy pha nào: `phase=` của `Route`, hoặc `stack` của ticket với route sửa code (`orch/routes.py::phase_for`) |
| Đổi tên / id một agent (ADR-0037) | `src/company/roles.py` — NƠI DUY NHẤT id agent là chuỗi trong `src/` (`ROLE.*`, nhãn `SOURCE.*` của review, `LEAD_ACTOR`); mọi route/producer/chủ namespace/`truth.py` console tham chiếu hằng; `tests/test_roles.py` chặn literal viết tay và đối chiếu hai chiều với front matter |
| Quy tắc chuyên môn dùng chung | `skills/<tên>.md` (45 file: tiêu chuẩn + quy trình + quy tắc + checklist + ví dụ tốt/xấu); agent chủ quản nạp đầy đủ, agent tuân thủ nạp rút gọn (ADR-0008) |
| Mẫu tài liệu agent phải viết theo | `templates/*.md` (prd, ticket, pull_request, adr, threat_model, runbook, uat_script…) |
| Ca eval của agent | `evals/<id>.yaml`; bản ghi `evals/recordings/<id>.json`; agent bắt buộc có bản ghi: `evals/recordings/REQUIRED.txt` |
| Miễn trừ assetscan có lý do | `assetscan-waivers.txt` |

## Luồng và hợp đồng

| Muốn | Sửa | Test đối chiếu |
|---|---|---|
| Agent nào nhận event nào, điều kiện gì | `ROUTES`, `THREAT_ROUTE`, `PLAN_INPUTS`, `STAGING_ROUTE`/`PROD_ROUTE` trong `src/company/orchestrator.py` | `tests/test_routing.py`; bảng Consumer `docs/architecture.md` |
| Khung event chung (`Envelope`, `AuditLog`, `SharedContext`, `SupervisorAction`, `can_transition`) | `xagents-core/src/xagents_core/events.py` — **LỚP CƠ SỞ** từ K3.5a; `src/company/events.py` kế thừa và thêm trường phạm vi của mình, thu hẹp `topic`/`namespace` về Literal. Model miền, `PAYLOAD_MODELS`, `TRANSITIONS` ở LẠI package | `xagents-core/tests/test_events.py` |
| Thêm/đổi trường của một topic | `topics/schemas/<topic>.json` **và** model trong `src/company/events.py` (`PAYLOAD_MODELS`) | `tests/test_schema_consistency.py` |
| Ai được ghi namespace blackboard nào | `NAMESPACE_OWNERS` trong `events.py`; bảng `topics/README.md` | — |
| Nạp agent/skill từ đĩa (front matter, `phases`, skill rút gọn, cổng chủ quản ADR-0008) | `xagents-core/src/xagents_core/registry.py` từ K3.6a — `src/company/registry.py` chỉ còn `AgentSpec = ` lớp core + ba hàm giữ chữ ký cũ; `ROOT`/`AGENTS_DIR`/`SKILLS_DIR` suy từ `CORE.root` | `xagents-core/tests/test_registry.py`, `tests/test_registry.py` |
| Blackboard (`shared-context`): version, phân vùng dự án, mirror ra file | `xagents-core/src/xagents_core/blackboard.py` từ K3.6b — `src/company/blackboard.py` còn lớp con + bảng `EXT`; `knowledge` là namespace toàn công ty khai ở `CORE.global_namespaces` | `xagents-core/tests/test_blackboard.py`, `tests/test_bus.py`, `tests/test_process_review_fixes.py` |
| Ai được publish topic nào | bảng `TOPIC_PRODUCERS`/`HUMAN_TOPICS` ở `core.py`; cơ chế ở `xagents_core/bus.py` `_check_publish` | `tests/test_bus.py`, `xagents-core/tests/test_bus.py` |
| Bus bền vững trên đĩa (ghi, `poll` giữa tiến trình, `replay`, `latest`, `Lease`) | `xagents-core/src/xagents_core/sqlite_bus.py` từ K3.5c — `src/company/sqlite_bus.py` chỉ còn lớp con mỏng ghép bus company + bus đĩa của core; tên file mặc định ở `CORE.db_name` | `xagents-core/tests/test_sqlite_bus.py`, `tests/test_bus.py` |
| Trạng thái ticket và chuyển đổi | `TicketState`, `TRANSITIONS` trong `events.py`; máy trạng thái `src/company/delivery.py` | `tests/test_delivery_and_gates.py` |
| Review nào bắt buộc cho ticket | `DeliveryLead.required_reviews` (`delivery.py`); `RISK_TAGS` trong `events.py` | `tests/test_release_flow.py` |
| Checklist human gate | `gates/checklists.md` → nguồn bằng chứng `src/company/gate_checklists.py` → `make subagents` | `tests/test_gate_brief.py`, `test_subagents.py` |
| Gate: hạn, nhắc, four-eyes, allowlist | `src/company/gates.py`, bền qua restart: `gate_cli.PersistentGate` | `tests/test_gate_trust.py` |
| Điều kiện cho phép GIAO ticket (kế hoạch không có gate, ADR-0037) | `_check_plan` trong `orch/ticket_fsm.py` (danh sách `problems`) → `lead.plans_ok` → guard trong `DeliveryLead.dispatch`; dựng lại khi mở bus: `orch/rehydrate.py` nhánh `plan.proposed` | `tests/test_check_plan_adr0037.py`, `tests/test_bo_gate_plan_adr0037.py` |

## Bằng chứng do code sinh

| Muốn | Sửa |
|---|---|
| Lint/test thật trong worktree ticket, `local_checks` | `TicketWorkspace.run_checks` (`src/company/workspace.py`); lệnh theo stack: `src/company/stacks.py` |
| Sổ Ruling: trường `rulings` mọi topic, audit `ruling`, `Orchestrator.rulings()`, CLI `rulings`, mục trong gate_brief | `events.py` (`Ruling`), 19 schema, `runner.publish`, `orchestrator.py`, `gate_brief.py` — ADR-0030 |
| Smoke sau deploy staging (`runtime` của spec) | `src/company/smoke.py`; hook `Orchestrator._smoke`; `_release_evidence` mang sang production |
| Deploy thật bằng `docker compose` (`deployed` = container đang chạy; `deploy_failed`; `skipped`) | `src/company/deploy.py` (`deploy`, `DeployRecord`, `project_name`, `COMPANY_DEPLOY*`); hook `orch/verify.py::deploy_release` gọi từ `orch/release_fsm.py::_release`; `runtime.deploy` trong `topics/schemas/approved-specs.json` + `smoke.parse_runtime`; `status`/`evidence` trong `topics/schemas/release-events.json`; bậc phễu console `console/src/console/truth.py`; ADR-0039 |
| Diff gửi lượt chấm (`qa[review]`, `security`; ưu tiên mã nguồn, cắt có khai) | `TicketWorkspace.diff`, `GENERATED_PATTERNS` (`workspace.py`) |
| Merge vào nhánh tích hợp, xung đột | `Integration.merge`; `_integrate`, `_integrate_approved` (orchestrator) |
| Giao hàng: tag `v<version>`, nhánh `company/release`, push, rollback | `Integration.deliver` / `rollback_delivery`; `_deliver` / `_rollback_delivery` (orchestrator); ADR-0027 |
| PR thật cho khách review trước UAT (`--deliver-pr`): mở/dùng lại, không merge; lý do bỏ qua/lỗi | `github_pr.open_pr` (+ `github_slug`, `_gh`); `orch/release_fsm.py::_delivery_pr` → trường `pr` trong `delivery.done`, audit `delivery.pr_*`; `Integration.remote_url/base_branch`; mục `acceptance.pr-giao-hang` (`gate_brief`, `gate_checklists`); ADR-0038 | `tests/test_delivery_real.py` §ADR-0038, `test_gate_brief.py::test_acceptance_pr_giao_hang…` |
| Tool agent được cấp, allowlist `run`, khoá đường dẫn, lọc env | `src/company/tools.py`; `SECRET_ENV`, `NO_HOOKS`, `clean_env` trong `workspace.py` |
| Vùng ghi của `qa[author]` vs `builder` (ADR-0028) | `Stack.test_globs` (`stacks.py`); phân quyền trong `tools.py`; lượt mù ở `runner.py` |
| Chống prompt injection | Bảng mẫu + lọc: `xagents-core/src/xagents_core/guard.py` (K3.4, chung hai công ty). CHÍNH SÁCH của company — topic nào ngoài/dẫn xuất, trường nào không tin cậy — ở `src/company/core.py` (`CORE`); `src/company/guard.py` chỉ còn là shim gắn `CORE`. Gọi từ `runner.py`, `web.py`, `supervisor.py`, `mcp_bridge.py`; `assetscan.py` quét file prompt bằng `guard.COMPILED` | `tests/test_adr0012.py`, `xagents-core/tests/test_guard.py` |
| Hạn mức ngữ cảnh, cắt | `src/company/context.py` |

## Model và chi phí

| Muốn | Sửa |
|---|---|
| Adapter provider (anthropic / openai / claude-code / codex / fake), retry, bảng giá | `src/company/llm.py` |
| Chọn backend theo tier, xoay khi hết quota, `prefer` | `xagents-core/src/xagents_core/routing.py` (K3.3d — `src/company/routing.py` chỉ còn là shim); cấu hình `llm.yaml` (`llm.example.yaml`, `llm.claude-gateway.yaml`) |
| Tool của công ty vào `claude -p` qua MCP | `src/company/mcp_bridge.py` (ADR-0024); dò chế độ: `probe.py` |
| Ngân sách ticket/dự án, watchdog, pause/escalate, bài học | `src/company/supervisor.py`; `BUDGET_FACTOR` trong `events.py` |
| Nợ kiến trúc treo: mã nợ `DEBT_RE`, đếm liên tiếp theo nguồn, bảng `debt_table`; gate cấp dự án `_check_debt`; ngưỡng `debt_reviews` | `supervisor.py`, `orchestrator.py`, `llm.py` (`LLMConfig.debt_reviews`) — ADR-0032 |
| Số liệu từ audit-log | `src/company/metrics.py` |
| Dòng thời gian một ticket/release/dự án (`orchestrator trace <id> [--json]`) | `src/company/trace.py`; test `tests/test_trace.py` |

## Vận hành và giao diện người

| Muốn | Sửa |
|---|---|
| Lệnh CLI orchestrator (`run`, `status`, `diagnose`, `publish`, `redeploy`, `takeover`…) | cờ và subcommand: `_parser()` trong `src/company/orch/cli.py`; **thân từng lệnh**: `src/company/orch/cli_cmds.py` (`BUS_CMDS` chỉ cần bus, `ORCH_CMDS` cần `Orchestrator`) — thêm lệnh mới là thêm parser + một hàm + một dòng bảng; tự khởi động lại khi mã đổi: `run --watch` |
| Hồ sơ bằng chứng gate (`make gate-brief`, `/gate-brief`) | `src/company/gate_brief.py`; slash command `../.claude/commands/gate-brief.md` |
| Trợ lý kiểm duyệt `sc-*` | `src/company/subagents.py` sinh từ agents + skills + checklists — không sửa tay đầu ra |
| Quét tài sản prompt, ngân sách prompt tĩnh | `src/company/assetscan.py` (ADR-0022) |
| Tool web cho `product` pha research | `src/company/web.py` |
| Mô phỏng cả công ty offline | `src/company/demo.py`, `examples/donghanhcungban_demo.py`, `examples/relay_client.py` |
| Yêu cầu mẫu để publish | `examples/yeu-cau-mau-web-app.json` |

## Tài liệu phải sửa kèm

| Khi | Sửa |
|---|---|
| Thêm file test / ADR | `README.md` mục "Cấu trúc" (số ca/file test, `ADR (0001–00xx)`) — `tests/test_review_fixes_2026_09.py::test_readme_khop_so_lieu_that` |
| Thêm route / agent | bảng Consumer `docs/architecture.md` — `tests/test_security_review_fixes.py` |
| Đổi kiến trúc | `docs/adr/00xx-*.md` + link trong PR |
| Sự cố vận hành đáng kể | `docs/reports/<ngày>-<slug>.md` + mục trong `TRAPS.md` |
