# Đặc tả kịch bản B — nền tảng "công ty AI" trên một lõi chung

Ngày lập: 2026-09-06 · Căn cứ: `docs/DANH-GIA-VA-TAM-NHIN-2026-09.md` (§5 chọn kịch bản B, §7 bốn quyết định),
`docs/DAC-TA-NANG-CAP-2026-09.md` (40 mục, sáu đợt), khảo sát mã nguồn tại `main@d7c8271`.
Tài liệu triển khai (PR theo PR, file:dòng): `docs/DAC-TA-TRIEN-KHAI-KICH-BAN-B.md`.

Tài liệu này là **đặc tả mức epic**: mỗi mục nói *cái gì phải đúng* và *kiểm bằng lệnh nào*. Nó không thay đặc tả
tháng 9 mà **bọc** nó: các mục B/C/D/S/E của đặc tả tháng 9 vẫn giữ mã, ở đây chỉ đổi thứ tự và thêm chín epic
mới mã `K1`–`K9`.

## 0. Tuyên bố và thước đo

> X-Agents là nền tảng dựng "công ty AI" tự vận hành. Model đề xuất, code kiểm chứng, người ký ở gate. Không
> trường "đã xong" nào do model điền. Một công ty mới là một thư mục cấu hình, không phải một bản fork.

Kịch bản B "xong" khi cả bốn câu sau trả lời **có, kèm bằng chứng máy sinh**:

| # | Câu hỏi | Bằng chứng chấp nhận | Epic |
|---|---|---|---|
| T1 | Công ty thứ ba dựng bằng cấu hình, không fork code? | `software-company/src/company/` và `Studio-creators/src/studio/` không còn `bus.py sqlite_bus.py llm.py routing.py runner.py guard.py context.py evals.py` (chỉ còn shim ≤ 3 dòng); `grep -c "from xagents_core" Studio-creators/src` > 0 | K3 |
| T2 | Có lời khai nào của model thành sự thật mà không qua code? | test bảng liệt kê mọi trường `verified_by` trong `topics/schemas/`; `smoke.unverified` chặn dự án mới | K1, K2 |
| T3 | Người thứ hai vận hành được trong 30 phút? | báo cáo `docs/reports/` do người chưa từng mở repo viết: request → 4 gate → sản phẩm chạy | K9 |
| T4 | Repo có tự khoá khi người 1 vắng không? | workflow `eval-record` chạy được từ GitHub Actions với secret; `make eval-record` không còn là đường duy nhất | K5 |

Bốn câu Q1–Q4 của đặc tả tháng 9 vẫn có hiệu lực; T1–T4 là điều kiện **thêm**, không thay.

## 1. Bất biến — đúng ở mọi PR của chương trình

1. **Tương thích ngược qua shim.** Mọi tên `company.X` / `studio.X` mà console, test, hoặc tài liệu đang import
   vẫn import được suốt chương trình. Shim là `from xagents_core.X import *` (+ `__all__`). Console và gateway
   **không sửa một dòng** vì lý do tách lõi.
2. **Test đi cùng code trong cùng commit.** Dòng nào chuyển package thì test phủ dòng đó chuyển theo; `fail_under
   = 100` giữ ở cả năm package. Không `pragma: no cover` mới để lách.
3. **Không bước nào làm CI đỏ giữa chừng.** Mỗi PR tự đứng: merge PR n mà không merge PR n+1 thì `main` vẫn
   chạy được và test xanh.
4. **ADR trước code** cho K1, K2, K3, K4 (mã ADR ghi ở từng mục). ADR ở cấp repo đặt tại `docs/adr/` (thư mục
   mới), đánh số từ 0001; ADR riêng package giữ chỗ cũ.
5. **Mọi thuộc tính state mới** trả lời "mở lại bus dựng lại từ đâu" (TRAPS khuôn 2); **mọi khoá once mới** mang
   thế hệ (khuôn 3); **mọi `sort` theo thời gian** có khoá phụ `seq` (khuôn 5).
6. **Prompt là code**: chạm `agents/`/`skills/`/`gates/checklists.md` → 7 bước `CONTRIBUTING.md` §3. Chương trình
   này cố ý **không chạm prompt** ở K1–K8 để không phải ghi lại 35 recording; chỉ K9 (chạy thật) được phép.
7. **Không hạ ngưỡng, không xoá test, không bỏ job** khỏi `needs` của `quality`.

## 2. Thứ tự và phụ thuộc

```
K0 vệ sinh (½ ngày)
 ├─ K1 tách orchestrator (ADR-0037)  ──┐
 ├─ K8 tài liệu + luật PR (song song) │
 └─ K2 sandbox (ADR-0035 mở rộng) ────┤   (K1, K2 độc lập; K2 chạm smoke.py/tools.py, K1 chạm orchestrator.py)
                                       ▼
                     K3 xagents-core (ADR gốc 0001) — 7 bước, mỗi bước một PR
                                       │
                 ┌─────────────────────┼──────────────────────┐
                 ▼                     ▼                      ▼
     K4 bus migration + lười    K5 eval từ CI          K7 console (module, danh tính, contract test)
     (ADR gốc 0002)             (sau K3 bước 3: llm)   (độc lập K3, chỉ cần K8 xong)
                 └─────────────────────┼──────────────────────┘
                                       ▼
                        K6 mypy strict theo module (trên core trước)
                                       ▼
                        K9 chạy thật: B8, S7, người thứ hai (T3)
```

Vì sao thứ tự này:

- K1 trước K3: `orchestrator.py` là file mà ba đợt tính năng (D, C, S) đều chạm; tách trước thì phiên song song
  không giẫm nhau. K3 không phụ thuộc K1 (K3 không chạm orchestrator) nhưng K1 xong thì `_call` và `process` mỏng,
  chuyển `runner` sang core dễ hơn.
- K2 trước K3 vì sandbox là P0 an toàn (§4.3 đánh giá) và `Sandbox` là interface core sẽ nhận.
- K5 sau K3 bước 3 vì workflow ghi eval dùng `xagents_core.llm` với `prefix` tham số; làm trước sẽ phải làm hai lần.
- K7 độc lập; có thể chạy phiên riêng từ đầu.
- K9 cuối vì cần mọi thứ trên ổn định để đo T3 có ý nghĩa.

Đặc tả tháng 9 đặt lại như sau: đợt 0 = K0; B6, B8 giữ; **E1 = K1 (kéo lên)**; **D2 = K2 (P1 → P0, mở rộng
phạm vi)**; E4 xong; E5 nhập K8; E2 (Redis) **hoãn vô hạn** thay bằng K4; E3 xây trên K5; đợt 3 còn C9 làm **sau
K7**; đợt 4 S1 làm **sau K3 bước 3**; D1, D3, D4, D5 giữ nguyên nhưng xếp sau K3.

## 3. Các epic

Quy ước cột: **Mục tiêu** · **Phạm vi** (file/module chạm) · **Yêu cầu** (đánh số, kiểm được) · **Nghiệm thu**
(lệnh) · **Không thuộc phạm vi** · **ADR**.

### K0 — Vệ sinh (Q4)

| # | Yêu cầu | Nghiệm thu |
|---|---|---|
| K0.1 | Bảng theo dõi đặc tả tháng 9 phản ánh đúng: V1–V5 phần lớn đã xong ở #98, ghi số PR | `grep -n "V1–V5" docs/DAC-TA-NANG-CAP-2026-09.md` không còn "chưa" |
| K0.2 | Root `README.md` khớp số thật: ADR company 0001–0032, 21 agent; `software-company/pyproject.toml` description "21 agent" | test mới `tests/test_readme_goc.py` đếm `ls docs/adr` và `agents/*/*.md` so với README gốc |
| K0.3 | `gateway/.env.example` không còn `8100` | `grep -c 8100 gateway/.env.example` = 0 |
| K0.4 | Tạo `docs/adr/README.md` (quy ước ADR cấp repo) | file tồn tại |
| K0.5 | Sửa dẫn chiếu trong ADR-0030/0031 thành đường dẫn từ gốc repo (`../../docs/DAC-TA-NANG-CAP-2026-09.md`) | link mở được từ vị trí file |

### K1 — Tách máy trạng thái khỏi `orchestrator.py` (T2, Q1)

**Mục tiêu.** `orchestrator.py` từ 2.269 dòng / 110 hàm còn ≤ 300 dòng; bốn FSM và scheduler mỗi cái một module
với bảng chuyển trạng thái tường minh và test bảng; năm khuôn lỗi TRAPS §1 có test tương ứng.

**Phạm vi.** `software-company/src/company/orchestrator.py` → gói `software-company/src/company/orch/` gồm
`routes.py`, `state.py`, `rehydrate.py`, `scheduler.py`, `ticket_fsm.py`, `release_fsm.py`, `gates_flow.py`,
`worktree_flow.py`, `verify.py`, `cli.py`. `orchestrator.py` còn lại là lớp `Orchestrator` mỏng + re-export.

**Yêu cầu.**

| # | Yêu cầu | Nghiệm thu |
|---|---|---|
| K1.1 | Mọi tên public cũ (`Orchestrator`, `ROUTES`, `PROD_ROUTE`, `THREAT_ROUTE`, `PLAN_INPUTS`, `check_routes`, `key_for`, `spec_runtime_gap`, `source_fingerprint`, `main`, `StepResult`) import được từ `company.orchestrator` | 28 file test chạm orchestrator không đổi dòng import; `uv run pytest -q -n auto --cov` xanh |
| K1.2 | Toàn bộ state của `Orchestrator` (§2 báo cáo bản đồ: 30 thuộc tính) gom vào một dataclass `OrchState`; mỗi trường có docstring ghi **topic/audit dựng lại** hoặc `RAM-only` kèm lý do | test `test_orch_state_moi_truong_co_nguon_dung_lai` đọc `fields(OrchState)` và bắt buộc metadata `rehydrate=` khác rỗng |
| K1.3 | `ticket_fsm.py` có bảng `TICKET_TRANSITIONS: list[Transition(from, event, guard, to)]` và `release_fsm.py` có `RELEASE_TRANSITIONS`; code chuyển trạng thái **tra bảng**, không `if` rải rác | test bảng: với mỗi `(state, event)` liệt kê ở §4 báo cáo bản đồ (13 dòng ticket, 12 dòng release) → đúng `to`; cặp không có trong bảng → `superseded`/no-op có audit, không exception |
| K1.4 | Ba khoá once chưa có thế hệ (`gate.escalate:{sid}`, `smoke.unverified:{rid}`, `delivery.skipped:{rid}`, `no-test-author:{tid}`) được thêm thế hệ: `gate.escalate:{sid}:{lần quá hạn}`, `smoke.unverified:{rid}:{event_id}`, `delivery.skipped:{rid}:{event_id}`, `no-test-author:{tid}:{retry}` | test hai chiều cho từng khoá: kịch bản lặp hợp lệ lần hai → gate/audit mở lần hai; bỏ thế hệ → test đỏ |
| K1.5 | `smoke.unverified` chỉ được chấp nhận khi spec `kind != application` **hoặc** dự án có cờ `legacy: true` trong `research-requests.payload`; dự án mới `kind=application` mà `unverified` → `status=failed` + gate escalation (đường như smoke fail hiện tại `orchestrator.py:1317`) | test: spec `kind=application`, không `runtime` → release không lên `deployed`; thêm `legacy: true` → đi tiếp với audit `smoke.unverified` |
| K1.6 | Năm khuôn TRAPS §1 có test đặt tên theo khuôn trong `tests/test_orch_khuon_loi.py`: (1) mọi nhánh `except` chung trong `orch/` ghi `kind` phân biệt; (2) bất biến restart; (3) mọi `once` có thế hệ — test grep chuỗi `_remember(f"` và bắt buộc ≥ 2 thành phần; (4) event cũ không phát lại — dùng kịch bản QLKH-004; (5) mọi `sorted(` theo `at`/`ts` có khoá phụ `seq` | file test tồn tại, 5 test, hai chiều |
| K1.7 | `_call` và `process` ở lại `orchestrator.py`; không FSM nào import FSM khác trực tiếp — chỉ qua `OrchCtx` (Protocol) | `grep -n "from .ticket_fsm\|from .release_fsm" orch/*.py` chỉ hiện ở `orchestrator.py` |
| K1.8 (**sửa tiêu chí 2026-09-07, #131**) | ~~`wc -l orchestrator.py` ≤ 300~~ → **thân hàm trong `orchestrator.py` ≤ 260 dòng**; không module trong `orch/` > 400 dòng; `main` ≤ 60 dòng (subcommand tách thành hàm). **Vì sao đổi:** mốc ≤ 300 tính cả import, re-export và bảng gán `x = module.fn` — đo được 250/498 dòng là phần đó, tức là chính bề mặt shim mà K1.7/K1.1 CỐ Ý tạo ra; cắt nó là đảo ngược K1.7 (K1.7 yêu cầu `_call`/`process` ở lại). Mốc cũ phạt đúng cái refactor đã làm đúng. Tiêu chí mới đo phần thật sự khó đọc — thân hàm — và vẫn chặn được đúng thứ nó sinh ra để chặn: logic nghiệp vụ mới lén vào `orchestrator.py` thay vì vào một module `orch/` | test `test_k18_orchestrator_chi_con_wiring_va_dispatcher`, `test_k18_main_duoi_60_dong`, `test_k18_moi_lenh_cli_co_dung_mot_ham_trong_bang`, `test_kich_thuoc_module_orch_duoi_400_dong` — cả bốn hai chiều |

**Không thuộc phạm vi.** Đổi hành vi nghiệp vụ (trừ K1.4, K1.5 là sửa lỗi có chủ ý); đổi schema topic; đổi prompt.

**ADR.** `software-company/docs/adr/0037-tach-may-trang-thai.md`. Luật PR: sau khi ADR-0037 merge, PR tiêu đề
`fix(company)` chạm `orchestrator.py` hoặc `orch/` phải dẫn `ADR-0037` trong thân — bước CI ở K8.

### K2 — Sandbox tiến trình cho mọi lệnh do model hoặc khách sinh (T2, an toàn)

**Mục tiêu.** Không lệnh nào có đối số hoặc nội dung do model/repo khách sinh chạy trực tiếp bằng quyền người
vận hành khi máy có container runtime; khi không có, chạy như cũ nhưng **audit ghi `sandbox=none`** và console
hiện cảnh báo.

**Phạm vi.** Mới: `software-company/src/company/sandbox.py`. Sửa: `tools.py:245-257` (`run`), `workspace.py:125`
(lint/test), `smoke.py:107` (Popen), `llm.py` (đọc cấu hình), `runner.py`/`orchestrator.py` (truyền xuống).
Studio: `media.py:622` (`CommandTTS`), `media.py:787` (ffmpeg) và `qc.py:52` dùng cùng interface (sau K3 thì
import từ core; trước đó copy có ghi chú).

**Yêu cầu.**

| # | Yêu cầu | Nghiệm thu |
|---|---|---|
| K2.1 | Interface `Sandbox` với `run(RunSpec) -> Result` và `spawn(RunSpec) -> Handle` (poll/kill, cho smoke); hai backend `SubprocessSandbox` (hành vi hiện tại, kể cả `clean_env`, timeout, cắt output) và `ContainerSandbox` | `tests/test_sandbox.py`: cả hai backend qua cùng bộ test hợp đồng (exit code, timeout, cắt output, env không có `SECRET_ENV`) |
| K2.2 | `ContainerSandbox` argv chuẩn: `docker run --rm --network none --cpus <n> --memory <m> --pids-limit 256 -u <uid>:<gid> -v <worktree>:/w:rw -w /w --env-file - <image> <argv>`; `network=True` chỉ cho smoke: `--network bridge -p 127.0.0.1:<port>:<port>` | test fake runner khẳng định từng cờ; test `network=False` mặc định |
| K2.3 | Chọn backend: `llm.yaml` `sandbox: auto|subprocess|container`, `sandbox_image`, `sandbox_runtime: docker|podman`; env `COMPANY_SANDBOX` thắng file; `auto` = container nếu `shutil.which(runtime)` có, ngược lại subprocess; `container` mà thiếu binary → **fail-closed** (`SandboxError`, không âm thầm rơi về subprocess) | test ba giá trị + test fail-closed |
| K2.4 | Phạm vi bắt buộc đi qua `Sandbox`: `tools.run` (lint/test/git_status/git_diff), `TicketWorkspace._run` (lint/test), `run_smoke` (`runtime.command`), studio `CommandTTS`, `FFmpegVideo._run`, `qc._run`. **Git** (`workspace._git`, `_git_ok`, merge) ở lại subprocess có `core.hooksPath` vô hiệu — ghi rõ lý do trong ADR | grep `subprocess.` trong các file trên chỉ còn trong `sandbox.py` và các hàm git được liệt kê |
| K2.5 | Bằng chứng: `ToolBox.calls[].sandbox`, `local_checks.sandbox`, `smoke.sandbox`, studio `render.*` audit `sandbox` — giá trị `container:<image>` hoặc `subprocess` | schema `pull-requests.local_checks` và `release-events.smoke` thêm trường `sandbox` (optional, string); test golden không đổi vì optional |
| K2.6 | Studio `CommandTTS`: env đi qua `clean_env()` (hiện `{**os.environ}` không lọc, `media.py:614-622`); `FFmpegVideo._run` có timeout (hiện không) | test hai chiều |
| K2.7 | Console: tile cảnh báo "sandbox=none" khi có audit `sandbox: subprocess` trong 24h trên máy có docker (cờ `sources.company.sandbox_available`) | test render |
| K2.8 | `SECURITY.md` §"Lệnh con của repo khách" viết lại: hàng rào là tiến trình khi có container; `README.md` company mục "chưa có" bỏ dòng sandbox | grep |

**Không thuộc phạm vi.** seccomp/gVisor; sandbox cho CLI `claude -p`/`codex` (đã có `--restricted`/`-s read-only`,
để ADR sau); mạng allowlist trong container (D2 gốc nói "không mạng trừ allowlist" — bước này là **không mạng**,
allowlist để sau).

**ADR.** `software-company/docs/adr/0035-sandbox-tien-trinh.md` (mã giữ theo đặc tả tháng 9; nội dung mở rộng
phạm vi sang smoke/stacks/studio).

### K3 — Package lõi chung `xagents-core` (T1)

**Mục tiêu.** Một package thứ năm `xagents-core/` (module `xagents_core`) chứa mọi thứ hai công ty đang fork;
`company` và `studio` import từ đó; studio nhận toàn bộ lớp cứng hoá của company (TransientError, hoãn event,
RetryingClient, Pricing, MCP, `CLI_NO_TOOL_TURNS`, guard, context, Lease, chốt version recording).

**Phạm vi.** Mới: `xagents-core/{pyproject.toml,src/xagents_core/,tests/}`; root `pyproject.toml` (members,
sources); `ci.yml` (+`core-static`, `core-unit`, nối `quality.needs`); `.github/rulesets/main.json` (+2 context);
`Makefile` gốc. Sửa: 16 module lõi ở cả hai package thành shim; `console` **0 dòng**.

**Nguyên tắc tham số hoá.** Core không biết tên công ty. Mọi điểm package-specific đi qua một đối tượng
`CoreConfig(prefix="COMPANY"|"STUDIO", root=Path, db_name="company.sqlite"|"studio.sqlite",
schema_dir=root/"topics/schemas", topic_acl=TopicACL(...), external_topics=..., derived_topics=...,
payload_models=..., namespace_owners=..., transitions=...)`. Mỗi package có `company/core.py` /
`studio/core.py` dựng `CORE = CoreConfig(...)` một lần; mọi shim truyền `CORE`.

**Yêu cầu.** Bảy bước, mỗi bước một PR, thứ tự bắt buộc:

| Bước | Module chuyển | Tham số hoá | Nghiệm thu riêng |
|---|---|---|---|
| K3.0 | Khung package + CI + ruleset; chưa chuyển code | — | `quality` xanh với hai job mới; `protection-guard` xanh |
| K3.1 | `context.py` (126 dòng, trung lập tuyệt đối) | không | studio `runner` bắt đầu dùng `fit` |
| K3.2 | `tools.py` phần khung: `ToolError/ToolSpec/ToolCall/ToolBox`; `tools_prompt` **ở lại** (chữ ký lệch) | không | `WorkspaceTools` (company) và `WebTools` (studio) kế thừa từ core |
| K3.3 | `llm.py` + `routing.py` **cùng PR** (chu trình import) | `prefix`, `root`, `config_file`; `ModelClient.complete(..., workdir=None)` default để studio tương thích; chuỗi lỗi tier nhúng `prefix` | studio nhận `TransientError`, `RetryingClient`, `Pricing`, MCP; studio `TRANSIENT_PATTERNS` xoá; `anthropic_input_tokens` thống nhất 3-tuple |
| K3.4 | `guard.py` | `external_topics`, `derived_topics` | xoá `studio/runner.py:29-81` (bản injection cũ); studio `LLMError` giữa chừng → hoãn event như company |
| K3.5 | `events.py` phần chung (`Envelope` có `correlation_id/causation_id/schema_version`, `SharedContext`, `AuditLog`, `SupervisorAction`, `can_transition`) + `bus.py` + `sqlite_bus.py` | `schema_dir`, `topic_acl`, `payload_models`, `namespace_owners`, `db_name`; `Topic`/`Namespace` Literal ở lại package | studio `Envelope` thêm 3 trường có default → file sqlite cũ vẫn đọc; `Lease` sang studio; console test 0 đổi |
| K3.6 | `registry.py`, `blackboard.py`, `runner.py`, `evals.py` | `root`; `runner` nhận hook `toolbox_for(spec)`; `evals` `evals_dir` | studio `RecordingClient` chốt version ở `__init__` và merge khi save; studio blackboard có project scope |
| K3.7 | `gates.py`, `gate_cli.py`, `supervisor.py` — **hợp nhất hai chiều** | `approvers_env`; supervisor nhận `ticket_model` | company nhận `gate_approvers` + four-eyes `enforce`; studio nhận `trusted_decision`, debt, budget USD |

Yêu cầu chung cho mọi bước:

| # | Yêu cầu | Nghiệm thu |
|---|---|---|
| K3.a | Sau mỗi bước, module cũ ở hai package là shim ≤ 3 dòng (`from xagents_core.X import *` + `__all__`), có ghi chú "xoá khi console đổi import" | `wc -l` shim |
| K3.b | Test của module chuyển sang `xagents-core/tests/` cùng PR; test riêng package (assert chuỗi `COMPANY_MODEL_...`) giữ ở package | coverage 100% ở cả ba nơi |
| K3.c | Hai công ty chạy demo offline xanh sau mỗi bước: `make demo` ở cả hai | output demo |
| K3.d | Kết thúc K3.7: `make test` gốc chạy năm package; `ARCHITECTURE.md` gốc vẽ lại sơ đồ có `xagents-core`; `CODEMAP.md` "muốn đổi bus/llm/runner → sửa ở core" | tài liệu |
| K3.e | Sau K3.5 giữ ổn định **≥ 5 ngày lịch** (một lần chạy thật của company) trước khi K3.6 | ngày merge trong CHANGELOG |

**Không thuộc phạm vi.** Hợp nhất `events` miền (Task vs VideoBrief); hợp nhất `tools` miền; đổi tên module
`company`/`studio`; xoá shim (làm ở chân trời 3).

**ADR.** `docs/adr/0001-loi-chung-xagents-core.md` (cấp repo). Studio ghi thêm `Studio-creators/docs/adr/0010`
"nhận lớp cứng hoá từ core" — mã 0010 hiện đặc tả tháng 9 dành cho reviewer đa phương thức (S1); S1 lấy 0011.

### K4 — Bus có phiên bản, có migration, đọc lười (Q1 lâu dài)

**Mục tiêu.** File sqlite sống nhiều tháng: code mới nâng cấp file cũ; code cũ **từ chối** file mới thay vì
im lặng sai; mở bus không nạp toàn log vào RAM.

**Phạm vi.** `xagents_core/sqlite_bus.py` (sau K3.5), `bus.py` (`__len__`), `blackboard.py:113`,
`metrics.py:46,168`, `gate_brief.py:212-556` (cache theo topic).

| # | Yêu cầu | Nghiệm thu |
|---|---|---|
| K4.1 | `PRAGMA user_version`; `SCHEMA_VERSION = 1` cho DDL hiện tại; `_MIGRATIONS: dict[int, list[str]]`; `ver > SCHEMA_VERSION` → `BusError("file bus mới hơn code")` | test: file version 0 → 1; file version 99 → lỗi rõ; migration chạy trong một transaction, lỗi giữa chừng không để file nửa vời |
| K4.2 | Bỏ vòng nạp `sqlite_bus.py:38-40`; `_seq = MAX(seq)`; `__len__` = `COUNT(*)`; `_seen` thay bằng `UNIQUE` + bắt `IntegrityError` | test: mở bus 100k event < 200 ms (đo bằng `time.perf_counter`, ngưỡng nới 5× trên CI) |
| K4.3 | `replay()` trả iterator lười (cursor) — nơi gọi cần list tự `list(...)` | grep `replay(` ở hai công ty + console, sửa chỗ cần index |
| K4.4 | Index `ix_events_topic(topic)`; `gate_brief` cache replay theo topic trong một lần dựng hồ sơ | `EXPLAIN QUERY PLAN` trong test dùng index |
| K4.5 | `orchestrator status` in `bus_schema_version` | output |

**Không thuộc phạm vi.** Redis/Kafka (E2 hoãn); nhiều tiến trình ghi cùng file.

**ADR.** `docs/adr/0002-bus-phien-ban-va-doc-luoi.md`.

### K5 — Eval ghi được từ CI (T4)

**Mục tiêu.** Người có quyền bấm một nút trên GitHub là 21 (+14) recording được ghi lại bằng API key trong
Secrets, kết quả về dưới dạng PR; máy cá nhân không còn là đường duy nhất.

**Phạm vi.** `.github/workflows/eval-record.yml` (mới), `evals.py` (cờ `--jobs`), `CONTRIBUTING.md` §3,
`software-company/TRAPS.md`.

| # | Yêu cầu | Nghiệm thu |
|---|---|---|
| K5.1 | Workflow `workflow_dispatch` input `package: company|studio`, `agents: all|<danh sách>`, `provider: anthropic|openai`; env `<PREFIX>_LLM_PROVIDER`, `<PREFIX>_MODEL_STRONG/STANDARD/LIGHT`, key từ Secrets; `timeout-minutes: 45` | chạy thử một agent, artifact có `recordings/<id>.json` |
| K5.2 | Kết quả mở PR `chore(<scope>): ghi lại eval <agents>` bằng `peter-evans/create-pull-request` hoặc tương đương, nhãn `no-changelog`; **không** push thẳng `main` (ruleset chặn) | PR mở tự động |
| K5.3 | `evals.py` thêm `--jobs N` chạy song song theo agent (thread pool; `RecordingClient.save` đã merge nên an toàn) | 21 agent ≤ 10 phút với `--jobs 3` |
| K5.4 | Điểm chấm (`cases_ok`) in bảng trong summary job; cổng vẫn là `gate_ok` | `$GITHUB_STEP_SUMMARY` |
| K5.5 | `CONTRIBUTING.md` §3 bước "eval-record" ghi hai đường: máy cá nhân hoặc workflow | tài liệu |

**Không thuộc phạm vi.** E3 ngưỡng trung vị (xây sau, trên K5); chạy eval-record tự động mỗi PR (tốn tiền).

### K6 — mypy strict theo module

| # | Yêu cầu | Nghiệm thu |
|---|---|---|
| K6.1 | `xagents-core/pyproject.toml` `[tool.mypy] strict = true` từ ngày đầu (K3.0) | CI `core-static` |
| K6.2 | company/studio: `[[tool.mypy.overrides]]` bật `disallow_untyped_defs` cho `orch/*` (sau K1) và mọi module mới | CI |
| K6.3 | Ranh giới orchestrator ↔ runner: `StepResult`, `Generated`, `RunResult` là dataclass/pydantic có kiểu, không `dict[str, Any]` | grep `dict[str, Any]` trong `orch/` giảm ≥ 50% so với `orchestrator.py` hiện tại (đếm trước/sau ghi trong PR) |

### K7 — Console: ES module, danh tính người duyệt, contract test (Q3)

**Phạm vi.** `console/src/console/static/index.html` → `static/js/{util,api,stream,router,drawer,render,charts,main}.js`;
`server.py:455` (`_api_decide`), `__main__.py` (cờ `--approver`), `collect.py`, `tests/`.

| # | Yêu cầu | Nghiệm thu |
|---|---|---|
| K7.1 | `index.html` chỉ còn HTML + CSS + một `<script type="module" src="/static/js/main.js">`; JS tách ≥ 7 file, không file > 400 dòng; không build step, không CDN | `wc -l`; test `_serve_static` phục vụ `.js` với `Content-Type: text/javascript` |
| K7.2 | `window.__CONSOLE__` inline thay bằng `GET /api/boot` (token vẫn qua header sau lần đầu; lần đầu đọc từ query một lần rồi xoá khỏi URL — hoặc giữ inline nhưng ghi nonce sẵn cho CSP) | test |
| K7.3 | Danh tính: `--approver human:<tên>` (lặp được) sinh **một token mỗi người**; `_api_decide` điền `by` từ token, **bỏ qua** `by` trong body; không `--approver` → hành vi cũ + cảnh báo ở đầu trang "duyệt không danh tính" | test: token A gửi body `by=human:B` → audit ghi `human:A`; four-eyes với hai token khác nhau qua, cùng token bị chặn |
| K7.4 | Contract test: `tests/test_hop_dong_schema.py` nạp `topics/schemas/*.json` của hai công ty và khẳng định mọi trường `collect()` đọc (`collect.py:29-46` và `truth_block`) tồn tại trong schema; đổi schema công ty → test console đỏ | test hai chiều bằng cách xoá một trường trong bản copy schema |
| K7.5 | `API.md` rút còn bảng route + link tới test hợp đồng (tự nó ghi "xoá khi hợp đồng vào test") | tài liệu |
| K7.6 | C9 (màn xưởng video) làm **sau** K7.1, trong file `static/js/video.js` riêng | — |

### K8 — Tài liệu và luật PR (Q4)

| # | Yêu cầu | Nghiệm thu |
|---|---|---|
| K8.1 | `gateway/README.md` thêm §"Rủi ro tài khoản" ngay dưới `make login`: điều khoản Google/Anthropic/OpenAI về nhiều tài khoản, hậu quả là khoá tài khoản, trách nhiệm người vận hành; `gateway/docs/adr/0004-ranh-gioi-dieu-khoan.md` | file; link từ root README dòng gateway |
| K8.2 | `make llm` mặc định trỏ **một** tài khoản; hồ sơ nhiều tài khoản là lựa chọn có tên riêng | `make llm` không chép `llm.claude-gateway.yaml` nếu chưa có `gateway/auth/*.json` |
| K8.3 | `pr-policy.yml` bước 3: PR đổi `software-company/src/company/orchestrator.py` hoặc `orch/` mà tiêu đề `fix(` → thân phải chứa `ADR-0037` | PR thử |
| K8.4 | `pr-policy.yml` bước 4: ngày có PR merge phải có `docs/sessions/<ngày>.md` — **cảnh báo** (`::warning`), không đỏ | PR thử |
| K8.5 | `docs/HUONG-DAN-VAN-HANH.md` mục "Ngày đầu của người thứ hai": 30 phút, từng lệnh, kết thúc bằng một gate tự duyệt trên demo | tài liệu; là kịch bản của K9.3 |
| K8.6 | Gateway `stop` kiểm cmdline trên Windows/macOS (`psutil` optional hoặc `tasklist`/`ps -o command`) | test mock |

### K9 — Chạy thật và người thứ hai (Q1, Q2, T3)

| # | Yêu cầu | Nghiệm thu |
|---|---|---|
| K9.1 | B8: dự án mẫu 2 (UI + API + DB) từ request tới acceptance, sandbox `container`, ≤ 2 takeover | `docs/reports/2026-xx-du-an-mau-2.md` ghi takeover, token, thời gian, `sandbox` trong evidence |
| K9.2 | S7: một video tiếng Việt 3–5 phút, provider thật, qua 3 review + gate publish, đăng kênh thử | `docs/reports/2026-xx-video-that-dau-tien.md` + `output/<video>/final_v<n>.mp4` |
| K9.3 | T3: người chưa từng mở repo làm theo K8.5, ghi lại từng chỗ vấp | `docs/reports/2026-xx-nguoi-thu-hai.md`; mỗi chỗ vấp thành mục TRAPS hoặc sửa tài liệu trong cùng tuần |
| K9.4 | T4: chạy workflow K5 cho 21 agent, PR merge | CHANGELOG |

## 4. Ước lượng

| Epic | PR | Ngày-phiên | Song song được với |
|---|---|---|---|
| K0 | 1 | ½ | — |
| K1 | 7 | 4 | K2, K7, K8 |
| K2 | 3 | 3 | K1, K7, K8 |
| K3 | 8 | 8 (có 5 ngày chờ ổn định sau K3.5) | K7 |
| K4 | 2 | 2 | K5, K7 |
| K5 | 1 | 1 | K4, K7 |
| K6 | 3 | 2 | rải theo K1/K3 |
| K7 | 4 | 3 | mọi thứ |
| K8 | 2 | 1 | mọi thứ |
| K9 | 0 (báo cáo) | 4 | — |
| **Tổng** | **31** | **~28 tuần tự, ~16 lịch với 3 phiên** | |

Nếu chỉ làm được một nửa: **K0, K1, K2, K3.0–K3.5, K8.3, K9.1**. Đó là phần trả lời T2 và mở đường cho T1.

## 5. Rủi ro

| Rủi ro | Dấu hiệu | Gỡ |
|---|---|---|
| K3.5 vỡ dữ liệu sqlite của studio (Envelope thêm trường) | `pydantic ValidationError` khi mở file cũ | default cho ba trường mới; test mở file fixture ghi bởi bản 0.1.0 |
| Ba phiên cùng sửa `orchestrator.py` | conflict PR K1 | K1 là **một phiên duy nhất** tới khi xong; D/C/S không chạm orchestrator trong lúc đó |
| Coverage tụt khi chuyển module | CI đỏ ở package nguồn hoặc core | test chuyển cùng commit (bất biến 2); chạy `--cov` cả ba nơi trước push |
| Container sandbox chậm hoặc thiếu image trên máy trực | smoke timeout | `sandbox_image` mặc định `python:3.12-slim` + node; cache layer; timeout smoke tính từ lúc container `running` |
| Shim để mãi | console vẫn `from company.bus` sau 3 tháng | chân trời 3 có mục xoá shim; K3.d ghi ngày dự kiến |
| Eval ghi bằng API model khác recording cũ → điểm rớt | `cases_ok` false | điểm không phải cổng (K5.4); ghi `models` trong recording, so sánh có chủ ý |
| Danh tính người duyệt làm chậm vận hành một người | người trực phải thêm cờ | không `--approver` = hành vi cũ có cảnh báo (K7.3) |

## 6. Bảng theo dõi

| Mã | Trạng thái | PR | Ghi chú |
|---|---|---|---|
| K0 | xong | #114 | vệ sinh số liệu trôi |
| K1.1 | xong | #115, #117, #120, #122–124 | mọi tên public cũ vẫn import được qua `company.orchestrator` — không PR K1.x nào đổi dòng import của 28 file test |
| K1.2 | xong | #117 | `OrchState` dataclass, 24 trường (không phải 30 như báo cáo bản đồ gốc — một số đã gộp/bỏ dọc đường), mỗi trường có metadata `rehydrate` |
| K1.3 | xong | #125 | `orch/fsm.py` (`Transition`/`step()`) + `TICKET_TRANSITIONS`/`RELEASE_TRANSITIONS` tra bảng; #124 trước đó chỉ di chuyển thuần (chưa dựng bảng) |
| K1.4 | xong | #125, #127 | #125 thêm thế hệ cho `no-test-author:{tid}` (`:{retry}`); #127 cho ba khoá còn lại — `gate.escalate:{sid}:{created_at của GateRequest}` (`orch/scheduler.py`, kèm `gate:{sid}:{pha}` cùng họ), `smoke.unverified:{rid}:{rc.event_id}` (`orch/verify.py`), `delivery.skipped:{rid}:{env.event_id}` (`orch/release_fsm.py`). Thế hệ của gate là `created_at` chứ không phải "lần quá hạn" như đặc tả viết: `HumanGate.pending` khoá theo `subject_id` nên gate mới ghi đè gate cũ, `created_at` là thứ duy nhất phân biệt được hai thế hệ |
| K1.5 | xong | | **Dòng cũ ghi "xong (từ trước)" là SAI** — nó dẫn `orch/verify.py:109-111` làm bằng chứng, nhưng đó là `verdict_with_run` (đường QA hồi quy), còn K1.5 nói về `smoke()` (đường deploy staging): `smoke()` không đọc `kind`, và cờ `legacy` không tồn tại ở đâu trong repo (`grep -rn legacy src/` rỗng). Đối chiếu nhầm hàm. Nay làm thật: `verify._chua_kiem` là chỗ quyết duy nhất cho cả hai nhánh không-smoke-được, `kind=application` (mặc định khi thiếu) mà không có `legacy: true` trong `research-requests.payload` → `status=failed` + gate escalation. Lý do chặn ở smoke thay vì để QA chặn như cũ: **`Delivery.waive_release_findings` waive MỌI nguồn chưa pass, kể cả `qa`** — người duyệt gate escalation (cơ chế dành cho finding không có code để sửa: DPIA, license) waive luôn cả "chưa bao giờ kiểm sản phẩm có chạy không", rồi Gate 3 mở và RC lên production. Đó chính là hình dạng QLKH 2026-09-06. ADR-0036 |
| K1.6 | xong | #125 | `tests/test_orch_khuon_loi.py` — 7 test (5 khuôn TRAPS.md §1 + 2 test chốt thêm) |
| K1.7 | xong | #125 | xác nhận: không `orch/*.py` nào `from .ticket_fsm`/`from .release_fsm`; `_call`/`process` vẫn ở `orchestrator.py` |
| K1.8 | xong (tiêu chí đã sửa) | #131 | `main` 162 → **29 dòng** (13 subcommand tách sang `orch/cli_cmds.py`, hai bảng dispatch `BUS_CMDS`/`ORCH_CMDS` — ranh giới là chỗ dựng `Orchestrator`); thân hàm `orchestrator.py` = **245/260**; mọi module `orch/` ≤ 400. Mốc "tổng ≤ 300 dòng" bị BỎ, lý do ở dòng K1.8 của bảng Yêu cầu — không phải hạ ngưỡng để qua cổng, mà là mốc cũ mâu thuẫn với K1.7 và đo sai thứ cần đo |
| K2.1 | xong | #116 | `company/sandbox.py` — interface `Sandbox`/`RunSpec`/`Result`/`Handle`, `SubprocessSandbox`, `ContainerSandbox` |
| K2.2 | xong | #116 | argv `ContainerSandbox` chuẩn (`--network none`, `--cpus`/`--memory`/`--pids-limit`, `-u uid:gid`, `--env-file -`) đã trong `sandbox.py` cùng PR K2.1 |
| K2.3 | xong | #116 | `sandbox_from_config` — `auto`/`subprocess`/`container` qua `COMPANY_SANDBOX*` + `llm.yaml`, fail-closed `SandboxError` khi thiếu binary |
| K2.4 | xong | #119, #129 | studio (`CommandTTS`, `FFmpegAssembler._run`, `qc._run`) ở #119; company ở #129 — `WorkspaceTools.run` (tool `run` của model), `TicketWorkspace._run` (lint/test của `run_checks`), `smoke.run_smoke` đều qua `Sandbox`. Sandbox đi THEO worktree (`TicketWorkspace.sandbox`) nên `runner.py` không phải đổi dòng nào. `git` và CLI model (`claude`/`codex`) là ngoại lệ có lý do; test quy ước grep `subprocess.run|Popen` toàn `src/company/` chặn PR sau lỡ thêm lệnh mới |
| K2.5 | xong | #119, #129 | studio `render.*` ở #119; company ở #129 — `pull-requests.local_checks.sandbox` và `release-events.smoke.sandbox`, cả hai schema đã khai trường |
| K2.6 | xong | #119 | `CommandTTS` qua `clean_env()`; `FFmpegAssembler._run` có `render.timeout_s` (mặc định 600s) |
| K2.7 | xong | #133 | `truth.sandbox()` đếm lượt chạy mã khách trong 24h theo tên sandbox, từ ba chỗ CODE điền bằng chứng (`local_checks.sandbox`, `smoke.sandbox`, audit `tools_used`) — không đọc cấu hình. Ô chỉ sáng khi `unsandboxed > 0` **và** `sources.<công ty>.sandbox_available` (máy có docker/podman): cảnh báo một việc người không làm được ngay là nhiễu |
| K2.8 | xong | #129, #133 | `SECURITY.md` mục **Sandbox tiến trình** ở #129; `software-company/README.md` mục "Chưa có" + "Bước tiếp theo" cập nhật ở #133 (dòng cũ nói sandbox chỉ là allowlist + env — đã sai từ #129) |
| ADR gốc 0001 | xong | #143 | đo lại thực trạng thay vì chép số đặc tả: **1.707 dòng trùng** trên 14 module (không phải ~1.200), 0 import chéo, và chỗ nguy hơn phần trùng là `context.py`/`guard.py` company **có** mà studio **không** |
| K3.0 | xong | | khung `xagents-core/` + `CoreConfig`/`TopicACL` + hai job CI `core-static`/`core-unit` nối vào `quality.needs`; `Makefile` và workspace lên **năm** member; `xagents-core` đã là phụ thuộc khai báo của cả hai công ty (chưa import) để K3.1 là một bước chuyển mã thuần. **Ruleset KHÔNG phải sửa**: required check chỉ có `quality` + `metadata`, nối vào `needs` là đủ (đặc tả để ngỏ điều này). Gồm luôn **K6.1** — `strict = true` ngay từ đầu, và `types` của core cố ý KHÔNG có `--ignore-missing-imports` |
| K3.1 | xong (phần chuyển mã) | | `context.py` (126 dòng, trung lập tuyệt đối) sang core + shim `company.context` 2 dòng; test đơn vị của `fit`/`trim_payload`/`cut_middle` chuyển theo sang `xagents-core/tests/test_context.py` (phần TÍCH HỢP ở `test_adr0012.py` ở lại company). Hai thứ đặc tả không lường: (1) **`py.typed` (PEP 561)** — thiếu nó thì mypy coi cả core là untyped, shim `import *` mang sang **0 tên** và `company/runner.py` gọi `fit` báo `has no attribute`; tức `strict` của core chỉ bảo vệ chính core. Có test canh. (2) mypy `strict` của core bắt **3 lỗi `tuple` trần** mà mypy lỏng của company bỏ qua — đã sửa bằng kiểu bí danh `Path` |
| K3.1b | **xong** | | studio dùng `fit`: `max_input_chars` (config + env + client) và `AgentRunner` cắt payload/enrich chung một hạn mức trước khi dựng prompt, audit `context_trimmed`. Blackboard mới chỉ được **đo**, chưa cắt — `studio.events.SharedContext` chưa có `content` (đổi mô hình dữ liệu, để bước sau) |
| K3.2–K3.7 | chưa | | K3.6 đợi ≥ 5 ngày lịch sau K3.5 (K3.e) |
| K4.1–K4.5 | chưa | | ADR gốc 0002 |
| K5.1–K5.5 | xong | #134 | `.github/workflows/eval-record.yml` (`workflow_dispatch`: package/agents/provider/jobs, timeout 45', key từ Secrets, tên model từ Variables) → PR `chore(<package>): ghi lại eval <agents>` nhãn `no-changelog` qua `peter-evans/create-pull-request`, KHÔNG push thẳng `main`; `--jobs N` ở CẢ HAI package (`ThreadPoolExecutor`, thứ tự in vẫn theo id); bảng điểm vào `$GITHUB_STEP_SUMMARY`, cổng vẫn là `gate_ok`; `CONTRIBUTING.md` §3 bước 3 ghi hai đường. Bảng theo dõi ghi "sau K3.3" là sai — K5 không phụ thuộc K3 |
| K6.1 | xong | | `xagents-core/pyproject.toml` `[tool.mypy] strict = true` từ commit đầu tiên của package, cùng PR K3.0 đúng như đặc tả xếp. Core chưa có dòng mã nào nên đây là lần duy nhất bật `strict` mà không phải trả nợ chú kiểu |
| K6.2 | xong | #141 | `[[tool.mypy.overrides]] module = "company.orch.*"` bật `disallow_untyped_defs` + `disallow_incomplete_defs`; 46 hàm trong `gates_flow/release_fsm/scheduler/ticket_fsm` nhận `o` nay có `o: Orchestrator` (chú kiểu là CHUỖI nhờ `from __future__ import annotations`, nên không tạo vòng import). Khoá theo TIỀN TỐ nên module mới trong `orch/` tự nằm trong phạm vi. ``warn_unused_ignores`` cố ý KHÔNG bật — nó báo `ctypes.windll` thừa trên Windows mà cần trên Linux, tức một cổng đúng-sai theo máy chạy |
| K6.3 | xong (**tiêu chí đã sửa**) | #141 | Vế 1 (`StepResult`/`Generated`/`RunResult` là dataclass có kiểu) đã đạt từ trước — nay có test chốt. Vế 2 (`dict[str, Any]` trong `orch/` ≤ 14) **bỏ, có lý do**: đo lại thì 25/25 chỗ còn lại phần lớn là `payload` của bus, tức JSON mà hợp đồng đã ở `topics/schemas/*.json`; dựng TypedDict cho chúng là chép 19 schema sang hệ kiểu và tạo nguồn sự thật thứ hai. Thay bằng **chốt bánh cóc** (trần 25, chỉ được giảm) giữ được ý định mà không ép sai thiết kế — cùng khuôn với K1.8, xem TRAPS §2 |
| K7.1, K7.2, K7.5 | xong | #142 | `index.html` 1850 → 759 dòng (HTML+CSS + một thẻ module); JS thành 14 module trong `static/js/`, dài nhất 173 dòng. K7.2 chọn **nonce + CSP** (một trong hai phương án đặc tả) thay vì `GET /api/boot`: phương án kia đưa token phiên vào query string, mà token là thứ duy nhất chặn trang khác trên cùng máy gọi vào console. K7.5: `API.md` tự khai phần nào đã vào test và "chỗ nào lệch thì TEST đúng" |
| K7.6 | **không áp dụng** | | "C9 (màn xưởng video) làm sau K7.1, trong `video.js` riêng" — C9 chưa được làm bao giờ, nên không có gì để tách. Khi nào làm C9 thì `console/CLAUDE.md` đã ghi luật: thêm màn = HTML + một module + nhập nó trong `main.js` |
| K7.3 | **hoãn có chủ ý** (2026-09-07) | | Chủ repo quyết: hiện **một người duy nhất duyệt gate**, nên token danh tính chỉ thêm bước gõ mà không thêm bảo vệ thật — four-eyes không có ai để "bốn mắt". **Điều kiện kích hoạt lại: có người thứ hai chạm vào console** (kể cả chỉ để xem) — K7.3 phải xong TRƯỚC lần duyệt đầu tiên của họ, vì tới lúc đó `by` lấy từ body request là ai cũng ký được dưới tên bất kỳ và audit-log ghi lại như thật. Đừng đề xuất lại trước điều kiện đó, và đừng quên sau nó |
| K7.4 | xong | #136 | `console/tests/test_hop_dong_schema.py` — QUÉT mã nguồn `collect.py`/`truth.py` lấy tên trường console đọc (không chép tay: danh sách chép tay xanh vì rỗng, đúng bệnh nó chữa), rồi so với `topics/schemas/` của cả hai công ty. Trường lồng một tầng (`local_checks.sandbox`, `smoke.sandbox` của K2.5) canh riêng vì regex chỉ thấy tầng ngoài |
| K8.1 | xong | #137 | `gateway/README.md` §Rủi ro tài khoản (ngay dưới `make login`, không phải cuối file) + ADR-0004 `ranh-gioi-dieu-khoan`; dòng gateway ở README gốc dẫn tới đó. Cố ý KHÔNG cảnh báo lúc chạy: biến quyết định pháp lý thành thao tác bấm qua, và người gõ `login` lần hai thì đã quyết rồi |
| K8.2 | xong | #139 | `python -m gateway ready` (exit 2 nếu chưa đăng nhập tài khoản nào) gác `make llm` của cả hai công ty. **Lệch đặc tả**: nghiệm thu viết "chưa có `gateway/auth/*.json`" — token KHÔNG nằm trong repo (ADR-0003), nó ở `$XAGENTS_HOME/auth/`, nên kiểm qua `AntigravityAuthManager` thay vì đường dẫn. `ready` cố ý KHÔNG đòi daemon đang chạy: `make llm` là bước CÀI, `make start` là bước CHẠY |
| K8.5 | xong | #140 | `docs/HUONG-DAN-VAN-HANH.md` §0 "Ngày đầu của người thứ hai" — 6 bước, ~30 phút, provider giả nên không tốn hạn mức, kết thúc bằng chính người đó **ký một gate** bằng `gate_cli`. **Mọi lệnh trong mục đã được chạy thật trước khi viết**, kèm output thật. Điểm dạy chọn có chủ ý: bước 4 CỐ Ý để `FakeClient` hết câu trả lời, vì phản ứng của hệ (pause dự án + mở gate `escalation`) dạy triết lý vận hành tốt hơn một đường chạy trơn. Có mục "Bạn vấp ở đâu?" — nghiệm thu K9.3 |
| K8.6 | xong | #138 | `_cmdline()` ba nền: `/proc` (Linux), `ps -o command=` (macOS/BSD), `tasklist` (Windows). Trước đó mọi hệ không phải Linux trả `True` — `stop` giết BẤT KỲ PID nào trong PID file. Trả **ba** giá trị phân biệt (`None` không đọc được → giữ hành vi cũ; `""` không tồn tại → không giết; có dòng lệnh → so tên). Windows chỉ cho tên ảnh nên phép kiểm là "có phải python đang chạy không" — nói rõ giới hạn thay vì giả vờ chặt hơn thực tế. Không thêm `psutil` |
| K8.3 | xong | #130 | `pr-policy.yml` bước 3: PR `fix(` chạm `orchestrator.py`/`orch/` mà thân không dẫn `ADR-0034` thì đỏ. **Dùng ADR-0034 chứ không phải "ADR-0037" như đặc tả viết** — repo này không có file 0037; chính ADR-0034 §Hệ quả đã ghi lại chỗ lệch số. `refactor(` không bị soi (tách module là làm đúng theo ADR; `fix(` mới là sửa hành vi máy trạng thái) |
| K8.4 | xong | #130 | `pr-policy.yml` bước 4: thiếu `docs/sessions/<ngày UTC>.md` → `::warning`, KHÔNG đỏ — nhật ký là việc cuối phiên, chặn merge từng PR là phạt sai chỗ |
| K9.1–K9.4 | chưa | | |

Cập nhật bảng trong cùng PR của mục. Mục "xong" phải có số PR; K9 phải có đường dẫn báo cáo.
