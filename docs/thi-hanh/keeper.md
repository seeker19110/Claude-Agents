# `keeper` — thi hành BT1–BT8 từ đặc tả tới mọi PR merge

Ngày lập: 2026-09-09 · căn cứ `main@1d49da2` (#206) · đặc tả nguồn: `keeper/docs/DAC-TA-KEEPER.md` (BT0 xong ở #207).

File này là **bảng theo dõi duy nhất** của việc thi hành `keeper`. Đặc tả `keeper/docs/DAC-TA-KEEPER.md` giữ vai
trò *gói việc* (mỗi BT là một khối 7 mục đã viết sẵn); file này giữ *hiện trạng đo được*, *chỗ đặc tả sai*, *mức
C1/C2/C3*, *đợt*, và *trạng thái PR*. Bảng §11 của đặc tả đã được thay bằng con trỏ về bảng B dưới đây — một
bảng, không hai (khuôn §6: "không có bảng thứ hai để trôi").

Đọc khi: bắt đầu hoặc tiếp tục `/thi-hanh keeper`; muốn biết BT nào còn dở và vì sao.

---

## A. Hiện trạng

### A1. Kết luận

1. `keeper/` có đúng hai file tài liệu, **chưa một dòng mã**; BT1–BT8 còn nguyên.
2. Lõi `xagents_core` đã đủ cho `keeper`: `CoreConfig` 12 trường (3 bắt buộc), `HumanGate`, `InMemoryBus`/`SQLiteBus`,
   `AgentRunner`, `guard.guard_payload` — không cần thêm trường core nào cho BT6 (xem A2-8).
3. Bốn cơ chế BT2/BT5 định "viết mới" thì **đã có bản chạy được** ở `software-company` để sao khuôn: adapter `gh`,
   `_git`, `TicketWorkspace`, sổ nợ.
4. Đặc tả sai ở **năm chỗ** (A2-6 → A2-10); ba chỗ nếu làm theo nguyên văn sẽ ra mã sai hoặc dạy sai cho agent.
5. BT1 chạm **nhiều gấp đôi** bảng của nó liệt kê — thiếu một chỗ (`ci.yml` `needs`, `uv.lock`) là CI xanh vô nghĩa
   hoặc đỏ ngay.
6. Hai gói chắc chắn `chờ người`: BT7 (bước `make eval-record` cần key model thật) và phần canary của BT8 (cần
   `gh auth login` trên máy + một PR thật được người merge — I1 cấm `keeper` tự merge).

### A2. Bảng đối chiếu

| # | Đặc tả đòi gì | Repo có gì | Ở đâu (`file:dòng`) | Mã việc |
|---|---|---|---|---|
| 1 | `CoreConfig(prefix, root, db_name, topic_acl, payload_models, namespace_owners)` | có, 12 trường, 3 bắt buộc; `env_name()` ghép `prefix` | `xagents-core/src/xagents_core/config.py:29-96` | BT1 |
| 2 | khuôn `pyproject.toml` package mới | `Studio-creators/pyproject.toml` đủ ruff/mypy/coverage/pytest; **không có `omit`**; `warn_unused_ignores` cố ý tắt kèm lý do nguyên văn | `Studio-creators/pyproject.toml` toàn văn | BT1 |
| 3 | job CI `keeper-static` + `keeper-unit` theo khuôn core | `core-static` ubuntu+windows/3.13; `core-unit` ubuntu×{3.11,3.13} + windows/3.13, `shell: bash` cả hai nền | `.github/workflows/ci.yml:331-395` | BT1 |
| 4 | adapter `gh` chỉ đọc, có timeout, không ném | **đã có bản đúng khuôn**: `encoding="utf-8"`, `env=clean_env()`, bắt `FileNotFoundError`/`TimeoutExpired`, cắt stderr `[-300:]` | `software-company/src/company/github_pr.py:62` | BT2 |
| 5 | worktree riêng cho ticket, dọn được | **đã có**: `create()` idempotent, `remove(delete_branch)`, `fresh()`, `exclude_worktrees()` ghi `.git/info/exclude` chứ không `.gitignore` khách | `software-company/src/company/workspace.py:86,103,114,178,62` | BT5 |
| 6 | "9 schema **sinh từ pydantic bằng script**, như hai công ty kia" | ✗ **không có script nào** sinh `topics/schemas/*.json`; 19 file của studio là artefact commit tay, ép khớp bằng test `set(get_args(Topic)) == set(bus._schemas)` | `Studio-creators/tests/test_bus.py:46`; `xagents-core/src/xagents_core/bus.py:73` | BT1 |
| 7 | `SqliteBus` | ✗ tên thật là **`SQLiteBus`** | `xagents-core/src/xagents_core/sqlite_bus.py:57` | BT7 |
| 8 | BT7 "thêm đúng một trường `CoreConfig` nếu đo được là cần" | ✗ **không cần**: `untrusted_fields` + `derived_topics` + `guard_payload()` đã đủ để `verified_by` không nhận từ JSON model | `config.py:55`; `guard.py:178-192` | BT6 |
| 9 | BT4 "dùng lại cơ chế `debt_due` của company, đọc `software-company/src/company/orch/`" | ✗ sai địa chỉ **và** sai cơ chế: `debt_due` ở lõi, và tính quá hạn theo **chuỗi review liên tiếp** (`streak`/`fired`), **không theo ngày**. `DebtEntry(due_at=…)` là cơ chế MỚI | `xagents-core/src/xagents_core/supervisor.py:82,102-123`; tiêu thụ ở `software-company/src/company/orch/gates_flow.py:88` | BT4 |
| 10 | BT7 cạm bẫy "`gate_cli approve` là reopen" | ✗ `decide()` chỉ đóng gate và đẩy vào `history`; reopen là nghĩa riêng của một số escalation do orchestrator quyết theo loại subject | `xagents-core/src/xagents_core/gates.py:87-94`; `orch/gates_flow.py:110-117` | BT7 |
| 11 | `HumanGate.approve()` / `.reject()` | ✗ chỉ có `decide(subject_id, decision, by, reason, *, enforce)`; `request()` từ chối `created_by` rỗng; thế hệ là `GateRequest.seq` do `request()` gán | `gates.py:79-94` | BT7 |
| 12 | I6 core không biết tên công ty | ✅ không nhánh logic nào theo tên; chỉ hai chuỗi hằng chặn biến môi trường bí mật | `llm.py:487`; `sandbox.py:44` | — |
| 13 | BT1 chạm `pyproject.toml` gốc + `ci.yml` | ✗ thiếu: `Makefile:3` (`MEMBERS`), `ci.yml:493` (`needs` của `quality`), `uv.lock`, `.github/dependabot.yml`, `.github/CODEOWNERS`, `.gitignore`, `README.md:111`, `AGENTS.md:17-20`, `ARCHITECTURE.md`, `CODEMAP.md`, `CONTRIBUTING.md:23-25` | như cột trái | BT1 |
| 14 | keeper có `agents/` → `assetscan` phải thấy | ✗ đường dẫn `. ../Studio-creators` hard-code ở **bốn chỗ** | `software-company/Makefile:33,35`; `.github/workflows/ci.yml:412,415` | BT7 |
| 15 | tab console cho công ty thứ ba | ✗ tên công ty hard-code ở **5 chỗ backend** + `VIEWS`/`TITLES`/`SC,ST` frontend; `collect()`/`decide()`/`submit()` nhận đúng hai `Path` vị trí | `console/src/console/collect.py:55`, `decide.py:22`, `brief.py:21`, `settings.py:25`, `server.py:40`; `static/js/router.js:26`, `state.js:9` | BT8 |
| 16 | test hợp đồng schema console | ✅ có, thêm công ty = thêm khoá `PACKAGES` | `console/tests/test_hop_dong_schema.py:24` | BT8 |
| 17 | 8 system prompt + eval recordings | khuôn front matter có; `model_tier` là `str` tự do, ba giá trị thực `strong/standard/light` | `software-company/agents/engineering/builder.md:1-24`; `software-company/src/company/subagents.py:40` | BT7 |
| 18 | golden test cho agent | ✅ khuôn `UPDATE_GOLDEN=1 pytest tests/test_golden_agents.py` ở cả hai công ty | `software-company/Makefile:22`; `tests/test_golden_agents.py:38,43` | BT7 |
| 19 | checklist gate `keeper` | khuôn mục gate: `Code gửi kèm:` → khoá → `Người tự kiểm thêm:` → `Kết quả:`; là nguồn sinh `sc-gate-*` | `software-company/gates/checklists.md:26-42` | BT7 |
| 20 | canary: một chu kỳ thật, PR merge | ✗ cần `gh auth login` trên máy (`clean_env()` lọc `GH_*`) và người merge (I1 cấm keeper merge) | `github_pr.py:11-14`; `DAC-TA-KEEPER.md:29` | BT8 |

Ô ✗ ở #6, #9, #10 là **đặc tả sai**, không phải repo thiếu: sửa đặc tả trong chính PR của BT tương ứng, không mở
PR vá riêng.

---

## B. Kế hoạch

| Mã | Việc | Mảng | Loại PR | Mức | Ưu | Nhược | Khi nào |
|---|---|---|---|---|---|---|---|
| BT1 | khung package: `pyproject` + `core.py` + `events.py` + 10 schema + 2 job CI + nối 11 chỗ workspace | keeper, gốc, CI | `feat(keeper)` | C2 (mã) + C1 (tài liệu/số liệu) | mở đường cho mọi BT sau | chạm nhiều file gốc, dễ sót một chỗ → CI đỏ | **xong #210** |
| BT2 | `github.py` chỉ đọc + `FORBIDDEN_ARGS` + bộ đệm TTL + `FakeGitHub` | keeper | `feat(keeper)` | C2 | I1 thành mã | phụ thuộc khuôn `github_pr.py` | **xong #211** |
| BT3 | `scout/health/drift` + `signals.dedupe` | keeper | `feat(keeper)` | C2 | ba phép so thuần cục bộ, test dễ | phép (c) báo giả trước mốc §10 → cần hằng số ngày có comment | **xong #213** |
| BT4 | `risk.py` bảng dữ liệu + `ledger.py` có `due_at` + `budget.py` + `triage.py` | keeper | `feat(keeper)` | C3 | quyết `due_at` vs `streak` (A2-9) | là cơ chế mới, không phải dùng lại — phải nói rõ trong PR | **xong #215** |
| BT5 | `worktree.py` (bọc `TicketWorkspace`) + `patcher.py` + `FORBIDDEN_PATHS` + `cli.py --dry-run` | keeper | `feat(keeper)` | C3 | chạm git thật, sai là hỏng worktree phiên khác | tuyệt đối không `reset --hard` checkout chung | **xong #217** |
| BT6 | `evidence.require_two_way` + `family.py` + `audit.py` | keeper | `feat(keeper)` | C3 | I2 thành cổng máy | `verified_by` phải do code set, lọc qua `guard` | **xong #218** |
| BT7 | `release.py` + `gates.py` + `orchestrator.py` + 8 agent md + golden + eval recordings + `assetscan` 4 chỗ | keeper | `feat(keeper)` | C3 | công ty chạy được | chạm `agents/` → 7 bước `CONTRIBUTING.md` §3; `eval-record` cần key thật | **xong #221**; bước `make eval-record` = **xong #239** (ghi bằng gói sub CLI, không cần API key) |
| BT8 | tab console + `HUONG-DAN-VAN-HANH` + `TRUC-VA-DUNG-KHAN` + README; **canary** | console, docs | `feat(keeper)` | C2 (console/docs) + `chờ người` (canary) | nghiệm thu thật | canary cần `gh auth` + người merge | **xong #223** (console + tài liệu); **canary: chờ người** — cần `gh auth login` và người merge PR bảo trì đầu tiên (I1 cấm keeper tự merge) |

**Cố ý không làm**

- *Không* thêm trường `CoreConfig` ở BT7 — A2-8 đo được là không cần. Thêm trường không dùng là nợ.
- *Không* viết script sinh `topics/schemas/*.json` (A2-6). Hai công ty kia commit tay và ép khớp bằng test; dựng
  generator chỉ cho package thứ sáu là làm lệch khuôn repo. BT1 viết tay 10 schema + test đối chiếu như studio.
- *Không* sửa `software-company/src/` để dùng chung `github_pr.py`/`workspace.py`. Đặc tả §0 cấm; `keeper` **sao
  khuôn** (đọc và viết lại theo nhu cầu của mình), không import chéo công ty. Nếu sau này đo được là trùng lặp
  thật thì đó là một bước K3 lên `xagents_core`, không phải việc của BT nào.
- *Không* vá `.github/dependabot.yml` cho `xagents-core` (đã sót từ trước) — ngoài phạm vi, sẽ báo chứ không sửa
  (`AGENTS.md` cấm §7).
- *Không* sửa `CONTRIBUTING.md:59` (số coverage lạc hậu 90/84/73) ở BT1 — cùng lý do; ghi thành tín hiệu để chính
  `keeper` bắt sau khi nó chạy được (đó đúng là việc của nó).

**Rủi ro của chính file này**: nó và `keeper/docs/DAC-TA-KEEPER.md` nói về cùng tám việc. Chống trôi bằng đúng một
cách — §11 của đặc tả trỏ về bảng B ở đây, và mọi cập nhật trạng thái chỉ ghi ở đây. PR nào sửa cả hai file mà
làm §11 mọc lại thành bảng thì phải bị chặn khi phiên chính đọc diff.

---

## C. Gói việc

Gói việc đầy đủ (7 mục) **đã nằm trong `keeper/docs/DAC-TA-KEEPER.md`** — BT1 ở §3, BT2 §4, BT3 §5, BT4 §6,
BT5 §7, BT6 §8, BT7 §9, BT8 §10. Không chép lại ở đây. Phần dưới chỉ ghi **delta**: chỗ đặc tả sai phải sửa, và
chỗ thiếu phải bổ sung. Subagent nhận: mục BT tương ứng của đặc tả **+** khối delta dưới đây.

### C-BT1 (delta)

- Bảng file của §3 thiếu, phải thêm vào cùng PR: `Makefile:3` (`MEMBERS` + `keeper/Makefile` có đủ 5 target
  `test cov lint types fix`, thiếu là `make test` gốc đỏ); `.github/workflows/ci.yml:493` (`needs` của job
  `quality` — không nối vào là kết quả không được tính, `ci.yml:501` coi `skipped` là đỏ); **`uv.lock`** (mọi job
  chạy `uv sync --locked`); `.gitignore` (`keeper/keeper.sqlite*`, `keeper/var/`); `.github/CODEOWNERS`;
  `README.md:111` (dòng `fail_under` thành sáu số); `AGENTS.md:17-20`, `ARCHITECTURE.md:9,15,23,28`, `CODEMAP.md`,
  `CONTRIBUTING.md:23-25` (bảng package).
- Sửa câu sai trong §3 của đặc tả: bỏ "sinh từ pydantic bằng script, như hai công ty kia" → "viết tay, ép khớp
  bằng test `set(get_args(Topic)) == set(bus._schemas)` như `Studio-creators/tests/test_bus.py:46`".
- Thay §11 của đặc tả bằng con trỏ về bảng B của file này.
- `keeper/README.md` **không ghi số test** (có cổng tự kiểm số liệu README ở hai công ty; ghi số là tự chuốc một
  cổng nữa mà chưa cần).
- Comment bắt buộc trong `core.py`: trích lý do `prefix` bám tên import từ `Studio-creators/src/studio/core.py:6-7`,
  và `root=parents[2]` vì file ở `src/keeper/`.

### C-BT4 (delta)

- Câu "dùng lại cơ chế `debt_due` của company" sai (A2-9). Gói phải mở bằng một đoạn nói rõ: cơ chế lõi đo **chuỗi
  review liên tiếp**, `keeper` cần **ngày đáo hạn** — đây là cơ chế mới trong `keeper/src/keeper/ledger.py`, không
  import từ `company`. Đọc `xagents_core/supervisor.py:102-123` để **không** đặt trùng tên khái niệm.
- `can_open_pr()` hỏi `gh` thật mỗi lần (trong TTL của BT2), không đếm trong RAM.

### C-BT7 (delta)

- Cạm bẫy "`approve` là reopen" viết sai (A2-10) — thay bằng: `decide()` đóng gate và đẩy vào `history`; muốn
  ticket bảo trì được làm lại thì orchestrator phải tự phát `supervisor-actions{action:"resume"}` như
  `orch/gates_flow.py:110-117`, không trông vào ngữ nghĩa của `approve`.
- `SqliteBus` → `SQLiteBus`; `HumanGate` không có `approve()`/`reject()`, chỉ `decide(...)`; thế hệ chống-trùng
  lấy từ `GateRequest.seq`, không từ `created_at`.
- Thêm `../keeper` vào `assetscan`/`assetbudget` ở **bốn** chỗ (A2-14).
- Bảy bước `CONTRIBUTING.md` §3 áp đủ. Bước `make eval-record AGENT=<id>` cần model thật → gói dừng ở đó với
  `chờ người`, phần còn lại vẫn đi tiếp.

### C-BT8 (delta)

- Console: tên công ty hard-code ở 5 chỗ backend + `router.js:26`/`state.js:9`/`submit.js:14`/`index.html:382-389`;
  `collect()`/`decide()`/`submit()` nhận hai `Path` vị trí — thêm tham số thứ ba, không đổi thứ tự hai cái cũ.
- Thêm `"keeper": "keeper"` vào `PACKAGES` của `console/tests/test_hop_dong_schema.py:24`.
- `docs/TRUC-VA-DUNG-KHAN.md` tổ chức theo **mức dừng**, không theo công ty — mục mới đặt trong Mức 3 ("dừng tất
  cả") dưới dạng "dừng riêng `keeper`", không tạo mục công ty thứ ba.
- Canary là điều kiện nghiệm thu, không phải mã: tách thành mục riêng trong bảng B nếu phải để lại.

---

## D. Điều phối

| Đợt | Song song (phát triển) | Thứ tự PR | Điều kiện vào đợt | `sc-*` chấm |
|---|---|---|---|---|
| 1 | BT1 | BT1 | không | `sc-builder` |
| 2 | BT2, BT3 | BT2 → BT3 | BT1 merge | `sc-builder` (BT2), `sc-qa` (BT3) |
| 3 | BT4 | BT4 | BT2, BT3 merge | `sc-supervisor`, `sc-qa` |
| 4 | BT5, BT6 | BT5 → BT6 | BT4 merge | `sc-security` (BT5), `sc-qa` + `sc-security` (BT6) |
| 5 | BT7 | BT7 | BT5, BT6 merge | `sc-qa`, `sc-security`, `sc-product` |
| 6 | BT8 | BT8 | BT7 merge (phần không chờ người) | `sc-ops`, `sc-qa` |

Mức → model: C1 → Haiku 4.5; C2 → Sonnet 5 `medium`; C3 → Opus 5 `high` (`xhigh` nếu phải quyết điều gói chưa
quyết, ví dụ `due_at` của BT4). Khuôn giao việc: `docs/KHUON-THI-HANH.md` §4, dán nguyên.

Mỗi gói một worktree `../Claude-Agents-wt-keeper-bt<n>`, nhánh `feat/keeper-bt<n>`. Lệnh CI của package:
`cd keeper && uv run ruff check src tests && uv run mypy src/keeper --ignore-missing-imports && uv run pytest -q --cov`.
BT1 chạm gốc nên chạy thêm `make test` ở gốc trước khi mở PR.

---

## F. Lệnh thi hành

```
/thi-hanh keeper                        # thi hành tới xong (idempotent, chạy lại tiếp từ chỗ dở)
/thi-hanh keeper --dung-sau-ke-hoach    # chỉ in bảng B rồi dừng
```

Trước khi gõ:

- Nhánh chứa file này phải đã merge `main` (PR của BT1 mang nó vào) — chạy lại khi chưa merge thì phiên sẽ soạn lại.
- Cần `gh` đã `gh auth login` trên máy: BT2 test bằng `FakeGitHub` nên không cần, nhưng **BT8 canary cần thật**
  (`clean_env()` lọc `GH_*`, xác thực phải nằm trên đĩa).
- Gói sẽ `chờ người`: **BT7** ở bước `make eval-record AGENT=<id>` (cần key model thật, `CONTRIBUTING.md` §3 bước 3);
  **BT8** ở phần canary (I1 cấm `keeper` tự merge PR — người phải merge PR bảo trì đầu tiên).
- Không đợt nào chờ hạng mục lộ trình khác: kịch bản B (K3.7) đã xong ở #198, `keeper` không phụ thuộc nó.
