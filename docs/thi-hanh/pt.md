# Ponytail — năm thứ đáng chép từ một plugin chống over-engineering

Ngày lập: 2026-09-15 · căn cứ `main@b821470` (#303) · Đề bài đến từ một lượt đánh giá kho ngoài
[`DietrichGebert/ponytail`](https://github.com/DietrichGebert/ponytail) (MIT, tạo 2026-06-12): *"đánh giá những
thứ hay có thể áp dụng vào dự án hiện tại"*, rồi *"lên kế hoạch tích hợp tất cả"*.
File này dùng cho phiên thi hành `/thi-hanh pt`; đọc trước khi chạm bất kỳ file nào trong bảng B.

> **Cái đáng lấy không phải cái người ta bán.** Ponytail bán một *skill* (thang 7 bậc chống over-engineering) và
> một bộ số (−54% LOC, −20% chi phí). Bộ số thì **không lấy**: n=4, một model, một repo, và chính họ thừa nhận
> con số 80–94% ở bản cũ là *"artifact do baseline hội thoại bị độn"*. Cái đáng lấy là **bộ đo và bộ hàng rào
> quanh skill đó** — thứ họ dựng để tự chứng minh skill có tác dụng, và là thứ repo này đang thiếu.
>
> Một mục đã bị loại **sau khi đo, trước khi lập kế hoạch**: `--rescore` (tính lại số đo từ workspace giữ lại,
> không gọi lại API) — repo đã có nguyên si dưới tên `make eval-replay` + `ReplayClient`
> (`platform/xagents-core/src/xagents_core/evals.py:204`). Không mở gói cho việc đã có (`TRAPS.md` §2; đúng lỗi
> phiên `p3` đã mắc hai lần).

## A. Hiện trạng

### A1. Kết luận (≤ 6 dòng)

1. **Đo hiện trạng tìm ra hai lỗi thật, không phải hai chỗ "có thể cải thiện".** Bốn file luật harness đã **trôi
   rồi**: chúng chép lại danh sách file cấm commit nhưng **thiếu "khoá/token, dữ liệu khách thật"** có ở
   `AGENTS.md:34`. Và `evals/thresholds.yaml:15` ghi `ops: cases: 8` trong khi `evals/ops.yaml` có **9** ca —
   cổng chống thu nhỏ bộ ca đang hở một ca. Cả hai đều là thứ không cổng nào đang canh.
2. **`SubagentStart` không có dấu vết nào trong repo** — grep toàn repo cho `SubagentStart`/`SessionStart`/
   `UserPromptSubmit`/`PreCompact`/`SubagentStop` trả 0. Chỉ `PreToolUse`/`PostToolUse` tồn tại
   (`.claude/settings.json:23,33`). Mọi subagent `sc-*` và mọi `Task` đang chạy **không** được hook nhắc luật nào.
3. **Scorer eval chưa bao giờ phải chứng minh nó bắt được lỗi.** `check()` ở
   `xagents_core/evals.py:72` hỗ trợ 6 loại assertion, nhưng ít nhất **6 ca** có `expect:` lỏng tới mức một
   output sai vẫn PASS (A2 #12) — trong đó có ca mà `contains: {summary: i18n}` cho qua cả một PR hard-code chuỗi
   rồi viết "chưa làm i18n".
4. **`evals/recordings/builder.json` không có trường `score`** ⇒ bản ghi hiện tại tạo với `RUNS=1`, tức chưa đo
   độ dao động — đúng thứ bộ nhớ đã cảnh báo ("một lần đỏ chưa phải hồi quy").
5. Ba hook bash hiện có cùng một khuôn chặt (`set -uo pipefail` · `payload="$(cat)"` · `jq` rồi lùi về python ·
   exit 2 chặn / 0 qua · **fail-open có nói ra**) và cổng khung tự bắt hook mới phải có test
   (`test_cong_khung.py:365,380`). Thêm hook thứ tư là việc có khuôn, không phải việc mở đường.
6. Tài sản prompt builder: nguồn `companies/software-company/agents/engineering/builder.md` (191 dòng,
   `version: 1` ở `:23`), `budget_tokens_per_task: 120000` — thêm bốn câu là nhiễu so với trần `assetbudget` 50%.

### A2. Bảng đối chiếu

| # | Đề bài (ponytail) đòi gì | Repo có gì | Ở đâu (`file:dòng`) | Mã việc |
|---|---|---|---|---|
| 1 | Kiểm bản sao luật không trôi khỏi nguồn (`scripts/check-rule-copies.js`) | Chỉ kiểm **tồn tại** + có chuỗi `"AGENTS.md"` | `platform/console/tests/test_cong_khung.py:437-442` | `pt.1` |
| 2 | — | 4 file luật, 3 file (`.cursorrules`/`.windsurfrules`/`.clinerules`) **giống hệt nhau từng chữ**, 13 dòng | `.cursorrules:1-13` | `pt.1` |
| 3 | — | **ĐÃ TRÔI**: bản sao liệt kê file cấm commit nhưng thiếu "khoá/token, dữ liệu khách thật" | `.cursorrules:9-10` vs nguồn `AGENTS.md:34` | `pt.1` |
| 4 | — | Danh sách gói `company\|gateway\|console\|core\|keeper\|all` chép cứng ở 4 nơi | `.cursorrules:12`, `GEMINI.md:15-17`, nguồn `AGENTS.md:82` | `pt.1` |
| 5 | — | Regex `^\d+\. \*\*(.+?)\*\*` khớp 18/19 mục luật; **sót luật bắt buộc 4** vì phần in đậm trải hai dòng | `AGENTS.md:87-88` | `pt.1` |
| 6 | — | Test đặt trong `test_cong_khung.py` bị **skip cả file** khi không có bash (`pytestmark`) | `test_cong_khung.py:73-74` | `pt.1` |
| 7 | Sổ nợ từ marker comment (`/ponytail-debt`, cờ `no-trigger`) | **không có** quy ước marker nào; `TRAPS.md` chỉ ghi bẫy **đã mắc** | — | `pt.2`, `pt.3` |
| 8 | — | `.claude/commands/` có 5 file; cổng chỉ bắt buộc `gate`/`debug`/`adr` tồn tại | `test_cong_khung.py:429-431` | `pt.3` |
| 9 | Hook phát luật vào subagent (`SubagentStart`) | **không có**: grep toàn repo 0 kết quả; chỉ `PreToolUse`/`PostToolUse` | `.claude/settings.json:22-40` | `pt.4`, `pt.5` |
| 10 | — | Khuôn hook bash đã chuẩn hoá; cổng tự bắt hook mới phải khai trong settings **và** có test | `test_cong_khung.py:365`, `:380`, `:387` (EOL=LF) | `pt.5` |
| 11 | — | CRLF làm hook chết im lặng — đã mắc, **chưa vào `TRAPS.md`** | `docs/sessions/2026-09-14.md:72-74` | `pt.5` |
| 12 | Scorer phải tự chứng minh bắt được lỗi (`run.py --selftest`) | `check()` có 6 assertion, **không có phép tự kiểm nào**; ≥ 6 ca lỏng | `xagents_core/evals.py:72-89`; ca lỏng: `security.yaml:156`, `builder.yaml:84`, `builder.yaml:230`, `qa.yaml:32`, `supervisor.yaml:43`, `ops.yaml:58` | `pt.6`, `pt.7` |
| 13 | — | `--strict` chỉ gác **bản ghi** (thiếu/lệch prompt), không gác chất lượng scorer | `company/evals.py:220,226-228,239-240` | `pt.6` |
| 14 | — | **HỞ**: `thresholds.yaml:15` ghi `ops: cases: 8`, `ops.yaml` có 9 ca | `evals/thresholds.yaml:15` vs `evals/ops.yaml` | `pt.9` |
| 15 | Judge phải qua selftest mới được tin | Không có judge LLM — repo chấm bằng assertion tất định | `xagents_core/evals.py:72` | *(cố ý không làm)* |
| 16 | `--rescore`: tính lại không gọi API | **ĐÃ CÓ**: `ReplayClient` + `make eval-replay` | `xagents_core/evals.py:204-222`; `Makefile:42` | *(cố ý không làm)* |
| 17 | Bốn câu chống over-engineering trong prompt | `## Definition of done` + `## Bạn PHẢI` có TDD/coverage, **không có** câu nào về over-engineering / root-cause / "giải thích dài hơn code" | `builder.md:157-158`, `:57-58` | `pt.8` |
| 18 | Đối chứng "prompt rẻ" (arm `yagni` 7 chữ) | **không có** — chưa ai hỏi prompt dài có hơn một câu không | — | `pt.8` |
| 19 | — | `builder.json` **không có** trường `score` ⇒ ghi với `RUNS=1`, chưa đo dao động | `evals/recordings/builder.json`, đối chiếu `CONTRIBUTING.md:83-86` | `pt.8` |
| 20 | — | `assetbudget` đếm bằng `CHARS_PER_TOKEN = 4` (ước lượng), trần 50% của `budget_tokens_per_task: 120000` | `assetscan.py:209,261`; `builder.md:20` | `pt.8` |
| 21 | — | Bảy bước sửa `agents/` đầy đủ, bước 3 cần model thật | `CONTRIBUTING.md:64-118` | `pt.8` |
| 22 | *(không phải đề bài — đo được trong lúc soạn file này)* | **`pre-commit-gate.sh` canh nhầm cây trong phiên worktree**: `ROOT` = `CLAUDE_PROJECT_DIR` = checkout chính. Đo 2026-09-15: hook chặn với "đang đứng trên nhánh 'main'" trong khi `git rev-parse --abbrev-ref HEAD` ở worktree trả `worktree-ponytail-pt` | `pre-commit-gate.sh:17` (`ROOT=`), `:61` (`git -C "$ROOT" branch --show-current`), `:70`, `:80`, `:88+` | `pt.10` |

## B. Kế hoạch

| Mã | Việc | Mảng | Hạng mục (PR) | Mức | Ưu | Nhược | Khi nào |
|---|---|---|---|---|---|---|---|
| `pt.10` | **`pre-commit-gate.sh` đang canh nhầm cây trong phiên worktree** (A2 #22): `ROOT` = `CLAUDE_PROJECT_DIR` = checkout chính, nên phép 1 đọc nhánh `main` → chặn oan mọi commit, còn phép 2–4 đọc index rỗng → không bao giờ bắn | console | **H0** `hook-worktree` | C3 `high` | Hàng rào đang hỏng cho đúng quy trình `CLAUDE.md` bắt buộc | Sửa hook là sửa thứ đang chặn chính mình | |
| `pt.1` | Cổng chặn 4 file luật harness trôi khỏi `AGENTS.md`: trích **hai danh sách chép cứng** (file cấm commit, tên gói) từ nguồn, assert mọi bản sao đủ phần tử. Sửa luôn chỗ đã trôi (A2 #3) | console | **H1** `luat-sao` | C2 | Bắt được một lỗi **đang tồn tại**, không phải lỗi giả định | Chỉ canh danh sách, không canh mọi câu diễn giải | |
| `pt.2` | Quy ước marker nợ `# no-ky-thuat: <trần>, <điều kiện nâng cấp>` + đoạn `AGENTS.md` phân định với `TRAPS.md` | docs | **H2** `no-ky-thuat` | C1 | Nợ cố ý hết mục ngầm; phân biệt "bẫy đã mắc" với "nợ cố ý tạo ra" | Thêm một quy ước phải nhớ | |
| `pt.3` | Lệnh `.claude/commands/no-ky-thuat.md` thu hoạch marker thành sổ, cờ `no-trigger` cho marker không nêu điều kiện quay lại + mở rộng cổng lệnh bắt buộc | console | **H2** | C2 | Marker mà không có lệnh đọc thì chính nó là nợ | Lệnh chỉ đọc, không chặn ai quên đặt marker | |
| `pt.4` | **Đo trước khi sửa**: `SubagentStart` có tồn tại ở bản Claude Code đang chạy không, **và hợp đồng output của nó là gì** (stdout thô? JSON?) — bằng chứng máy sinh | — | **H3** `hook-subagent` | C2 | Chặn đúng chỗ luật bắt buộc 6 hay bị bỏ qua | Một gói không sinh code | |
| `pt.5` | Hook bash `.claude/hooks/phat-luat-subagent.sh` phát 7 dòng luật vào mọi subagent; fail-open **có nói ra**; **không chờ stdin** ở đường mặc định; nối `settings.json`; test; bảng hàng rào `AGENTS.md`; mục CRLF vào `TRAPS.md` | console | **H3** | C3 `high` | Bịt A2 #9 — lỗ hổng lớn nhất tìm được | Hook chạy mỗi lần spawn; sai là treo mọi subagent | |
| `pt.6` | ADR-0042 (software-company): scorer eval phải tự chứng minh bắt được lỗi — vì sao `--replay --strict` chưa đủ (A2 #13), phương án đã loại | docs | **H4** `selftest-eval` | C3 `xhigh` | Đổi cách đo agent là đổi kiến trúc (luật bắt buộc 2) | Một vòng PR chỉ có tài liệu | |
| `pt.7` | `--selftest`: mỗi ca thêm khối `bad:`, chạy `check()` với `bad:` của chính ca đó, **không gọi model**; ca cho `bad` qua ⇒ đỏ; ca thiếu `bad:` ⇒ cảnh báo `chua-chung-minh`; nối `ci.yml` | core+company | **H4** | C3 `high` | Đúng chỗ bộ nhớ đã ghi: "CI không bắt được bản ghi tụt điểm" | Kỳ vọng đỏ diện rộng lần chạy đầu — là phát hiện, không phải sự cố | |
| `pt.9` | Sửa `thresholds.yaml` `ops: cases: 8` → `9` cho khớp bộ ca thật (A2 #14) | company | **H4** | C1 | Bịt hở cổng chống thu nhỏ bộ ca | Không | |
| `pt.8` | Bốn câu chống over-engineering vào `builder.md` + đối chứng prompt rẻ + đủ bảy bước `CONTRIBUTING.md` §3 (**`RUNS=3`** để bản ghi có `score`, vá A2 #19) | company | **H5** `builder-luoi` | C3 `high` | Trả lời câu chưa ai đặt: prompt dài có hơn một câu không? | Kích `eval-record` model thật, tốn tiền | |

### Cố ý không làm

| Không làm | Lý do |
|---|---|
| `--rescore` (tính lại số đo không gọi API) | **Đã có**: `ReplayClient` (`xagents_core/evals.py:204`) + `make eval-replay`. Mở gói cho việc đã có là lỗi đã mắc hai lần. |
| Judge LLM chấm over-engineering (`judge.py`) | Repo chấm bằng assertion **tất định** (A2 #15). Thêm một judge LLM là thêm một thứ phải tự kiểm trước khi tin — `pt.7` làm phần tự kiểm cho scorer đã có, đó mới là việc thiếu. |
| Benchmark agentic đầy đủ (phiên headless trên repo seed) | Hạ tầng lớn, và software-company **đã** chạy code thật trên worktree khách — trùng mục đích. Muốn làm thì mở ADR riêng. |
| Hạ tầng đa nền tảng kiểu ponytail (20+ plugin manifest) | Repo chỉ cần Claude Code + 4 file con trỏ. `pt.1` làm 4 file đó chắc hơn là đủ. |
| Công tắc cường độ `lite\|full\|ultra` | Chống over-engineering ở repo này là **luật thường trực**, không phải chế độ ai đó quên bật. |
| Chép nguyên `SKILL.md` ponytail thành skill mới | Trùng phần lớn luật bắt buộc 4/5/6 đã có. `pt.8` chỉ lấy **bốn câu** nó nói hay hơn bản mình đang có. |
| Con số −54% LOC / −20% chi phí | Lấy **cách đo**, không lấy số. |
| Viết hook bằng Node như ponytail | Ba hook bash sẵn cùng một khuôn (A2 #10). Thêm phụ thuộc `node` cho một hook 30 dòng là đúng thứ `pt.8` đang cấm. |
| Siết mọi câu diễn giải trong 4 file luật, không chỉ hai danh sách | So khớp văn xuôi tự do là bài toán không có đáp án tất định; cổng đoán mò sẽ bị tắt sau ba lần đỏ oan. Hai danh sách là phần **chép cứng**, chúng bắt được lỗi thật (A2 #3). |

### Rủi ro của chính file này

- Bảng A2 là ảnh chụp `main@b821470`. PR nào merge xen giữa có thể làm `file:dòng` lệch — phiên thi hành phải
  `git fetch` và **kiểm lại chữ ký hàm trước khi giao subagent**, không tin số dòng trong file này.
- `pt.4` có quyền giết cả **H3**. Nếu `SubagentStart` không tồn tại ở bản Claude Code đang chạy thì `pt.5` là
  code viết cho một sự kiện không bao giờ bắn — ghi `chờ người` và đi tiếp H4, **không** tự chế cơ chế thay thế.
- `pt.7` là gói duy nhất có thể làm CI đỏ diện rộng (mọi ca lỏng lộ ra cùng lúc; A2 #12 mới là 6 ca *đã điểm
  mặt*, tổng 59 ca chưa rà hết). Nếu số ca đỏ vượt quá một PR chịu nổi: siết 6 ca đã điểm mặt trước, phần còn
  lại tách mã mới trong bảng B — **không hạ tiêu chuẩn `--selftest` cho vừa một PR**.
- Đề bài đến từ việc đọc kho người khác. Nguy cơ đặc trưng là **chép cơ chế vì nó hay, không vì mình thiếu**.
  Mỗi gói ở C phải chỉ được ra chỗ repo đang thiếu bằng `file:dòng` ở A2; gói nào không chỉ được thì bỏ. Ba mục
  đã bị bỏ đúng theo luật này (A2 #15, #16, và benchmark agentic).

## C. Gói việc

> Mỗi khối 7 mục theo `docs/TASK-PACK.md`. Mục 5 là **khung mức chữ ký**, viết sau khi đọc code thật ở
> `main@b821470` — nhưng vẫn phải `git fetch` kiểm lại trước khi giao (xem "Rủi ro"). Mục 7 luôn có **ca chiều
> ngược** (luật bắt buộc 4).

### `pt.10` — `pre-commit-gate.sh` phải canh CÂY ĐANG COMMIT, không phải checkout chính

1. **Mục tiêu** — A2 #22. `CLAUDE.md` luật 2 **bắt buộc** mỗi phiên một worktree, nhưng hook cổng commit lại
   đọc `git -C "$ROOT"` với `ROOT` = `CLAUDE_PROJECT_DIR` = checkout chính. Hậu quả hai chiều, cả hai đều xấu:
   phép 1 thấy nhánh `main` của checkout chính nên **chặn oan mọi commit**; phép 2–4 đọc index của checkout
   chính (rỗng) nên **file cấm, hạ `fail_under`, và cổng gói không được canh gì cả**. Hàng rào vừa cản người
   đúng luật vừa buông người sai luật — đúng khuôn "chế độ hỏng không tự khai báo" trong bộ nhớ repo.
2. **Kết quả mong đợi** — hook canh đúng cây đang commit trong cả hai hoàn cảnh (checkout chính và worktree);
   bốn phép kiểm bắn đúng trong worktree; cổng khung xanh; một mục `TRAPS.md`.
3. **Phạm vi** — ĐƯỢC chạm: `.claude/hooks/pre-commit-gate.sh`, `platform/console/tests/test_cong_khung.py`,
   `TRAPS.md`. **KHÔNG** chạm: `block-dangerous-git.sh` và `auto-format.sh` ở gói này (**xem mục 7: phải ĐO
   xem chúng có cùng lỗi không trước, rồi mới quyết định tách mã mới hay gộp** — luật bắt buộc 5, rà cả họ lỗi),
   `.claude/settings.json`.
4. **Bối cảnh** — `pre-commit-gate.sh:17,61,70,80,88+`; `CLAUDE.md` luật 2 (mỗi phiên một worktree);
   `AGENTS.md:125-141` (bảng hàng rào); `test_cong_khung.py:86-98` (`_chay` truyền `CLAUDE_PROJECT_DIR`),
   `:109` (fixture `kho_main` — khuôn dựng repo giả), `:254-341` (bộ ca cổng commit).
5. **Ràng buộc kỹ thuật** — cây đang commit là **cwd của lệnh `git commit`**, không phải `CLAUDE_PROJECT_DIR`:
   ```bash
   # ROOT giữ nguyên cho việc tìm script trong repo (dev-task.sh, pyproject…).
   # THÊM một biến riêng cho cây đang commit — đừng dùng chung một biến cho hai nghĩa khác nhau.
   CAY="$(git rev-parse --show-toplevel 2>/dev/null || printf '%s' "$ROOT")"
   # rồi mọi phép kiểm 1-4 dùng `git -C "$CAY"`, còn đường dẫn script vẫn theo "$ROOT".
   ```
   Cân nhắc và ghi lại lựa chọn: hook chạy với cwd nào? Nếu `PreToolUse` không chạy ở cwd của lệnh thì phải lấy
   cây từ payload (`tool_input.command` có `cd …`) — **đo trước, đừng đoán** (luật bắt buộc 6).
   `ROOT` vẫn phải dùng cho `scripts/dev-task.sh` vì worktree có bản sao riêng của script.
6. **Bẫy đã biết** — (a) sửa xong mà chỉ thử ở checkout chính thì **không thấy gì** — lỗi chỉ hiện trong
   worktree; ca test phải dựng worktree thật; (b) `git rev-parse --show-toplevel` trong worktree trả đường dẫn
   worktree (đúng ý), nhưng trong submodule/không-phải-repo thì trả rỗng → phải có lùi về `$ROOT`;
   (c) cám dỗ "cứ `--no-verify` cho nhanh" — đó chính là cách lỗi này sống sót tới hôm nay; (d) phép 4 chạy
   `dev-task.sh gate` — chạy nhầm cây nghĩa là chạy test của **code khác** với code đang commit, xanh cũng vô nghĩa.
7. **Cách kiểm và cách báo**
   - **ĐỎ trước, hai chiều, bắt buộc**: dựng một worktree tạm trên nhánh khác `main`, stage một file, chạy hook
     với `CLAUDE_PROJECT_DIR` trỏ checkout chính (đang ở `main`).
     - chiều 1: hook **chặn** với lý do "đang đứng trên nhánh 'main'" dù nhánh thật khác → ca
       `test_cong_commit_khong_chan_oan_trong_worktree` ĐỎ.
     - chiều 2: stage một `llm.yaml` **trong worktree** → hook **cho qua** (index checkout chính rỗng) → ca
       `test_cong_commit_van_chan_file_cam_trong_worktree` ĐỎ. Dán cả hai output.
   - **Rà cả họ lỗi (luật bắt buộc 5)**: chạy cùng phép thử cho `block-dangerous-git.sh` và `auto-format.sh`,
     ghi lại **cả chỗ an toàn và vì sao**. Có lỗi cùng kiểu → mở mã mới trong bảng B, không lặng lẽ sửa kèm.
   - XANH sau: cả hai ca xanh; bộ ca cổng commit cũ (`:254-341`) **vẫn xanh** ở checkout chính;
     `scripts/dev-task.sh gate console` dán output.
   - `sc-ops` + `sc-security` chấm (hàng rào thi hành).
   - Tiêu đề PR: `fix(khung): pre-commit-gate canh cây đang commit, không phải checkout chính`

### `pt.1` — cổng chặn bản sao luật trôi

1. **Mục tiêu** — bốn file luật cho harness khác tự khai "cố ý không chép lại luật" (`.cursorrules:4`) nhưng
   thực tế có chép, và **đã trôi**: thiếu "khoá/token, dữ liệu khách thật" so với `AGENTS.md:34`. Agent không
   phải Claude Code đọc bản thiếu đó sẽ commit khoá mà không biết mình sai luật.
2. **Kết quả mong đợi** — (a) một cổng đỏ khi bất kỳ bản sao nào thiếu phần tử của hai danh sách chép cứng;
   (b) bốn file được sửa cho đủ; (c) `scripts/dev-task.sh gate console` xanh.
3. **Phạm vi** — ĐƯỢC chạm: `platform/console/tests/test_cong_repo.py`, `.cursorrules`, `.windsurfrules`,
   `.clinerules`, `GEMINI.md`. **KHÔNG** chạm: `AGENTS.md` (nguồn, không sửa để vừa cổng), `test_cong_khung.py`
   (xem mục 6), bất kỳ file nào trong `companies/`.
4. **Bối cảnh** — `AGENTS.md` luật cấm 3 (`:34`) và luật bắt buộc 3 (`:82`); `TRAPS.md` §1; báo cáo A2 #1–#6;
   `test_cong_repo.py:180-195` (khuôn parametrize sẵn có).
5. **Ràng buộc kỹ thuật** — đặt trong `platform/console/tests/test_cong_repo.py` (**không** `test_cong_khung.py`:
   `pytestmark` ở `:73-74` skip cả file khi máy không có bash — cổng chết im lặng, đúng thứ file đó tự cảnh báo).

   ```python
   BAN_SAO_LUAT = (".cursorrules", ".windsurfrules", ".clinerules", "GEMINI.md")

   def _muc_luat(phan: str, so: int) -> str:
       """Nguyên văn một mục luật của `AGENTS.md`. `phan`: 'Luật cấm' | 'Luật bắt buộc'.
       Mục in đậm có thể trải hai dòng (`AGENTS.md:87-88`) nên regex phải DOTALL."""

   # (nhãn, phần tử bắt buộc xuất hiện trong MỌI bản sao) — trích từ nguồn, không chốt cứng ở test
   def _danh_sach_file_cam() -> tuple[str, ...]:   # từ _muc_luat("Luật cấm", 3)
   def _danh_sach_goi() -> tuple[str, ...]:        # từ _muc_luat("Luật bắt buộc", 3)

   @pytest.mark.parametrize("ten", BAN_SAO_LUAT)
   def test_ban_sao_luat_khong_thieu_phan_tu_danh_sach(ten: str) -> None: ...
   ```
   Cấm chốt cứng danh sách trong test (chốt cứng = bản sao thứ năm, trôi tiếp).
6. **Bẫy đã biết** — (a) `pytestmark` skip cả file, xem mục 5; (b) regex `^\d+\. \*\*(.+?)\*\*` **sót luật bắt
   buộc 4** vì in đậm trải hai dòng (A2 #5) — phải DOTALL và non-greedy, có ca kiểm đếm đủ 8 + 11 mục;
   (c) `.cursorrules`/`.windsurfrules`/`.clinerules` giống hệt nhau — sửa một file quên ba file là lỗi hiển nhiên,
   cổng phải parametrize cả bốn.
7. **Cách kiểm và cách báo**
   - ĐỎ trước (chiều ngược, **bắt buộc**): chạy cổng mới trên 4 file **chưa sửa** → phải đỏ ở đúng phần tử
     "khoá/token"; dán output. Đây là bằng chứng cổng bắt được lỗi thật, không phải lỗi dựng.
   - Ca: `test_ban_sao_luat_khong_thieu_phan_tu_danh_sach` ×4; `test_trich_du_moi_muc_luat_cua_agents_md`
     (đếm 8 mục cấm + 11 mục bắt buộc — ca này chính là ca bắt bẫy (b)).
   - XANH sau: sửa 4 file → cổng xanh; `scripts/dev-task.sh gate console` dán output.
   - Tiêu đề PR: `test(khung): cổng chặn 4 file luật harness trôi khỏi AGENTS.md`

### `pt.2` — quy ước marker nợ kỹ thuật

1. **Mục tiêu** — repo không có cách nào ghi **nợ cố ý tạo ra** (A2 #7). `TRAPS.md` ghi bẫy *đã mắc*; một đơn
   giản hoá có trần đã biết thì hôm nay không sai, nhưng không ai biết khi nào phải quay lại.
2. **Kết quả mong đợi** — một đoạn trong `AGENTS.md` định nghĩa quy ước, nêu rõ ranh giới với `TRAPS.md`, và ≥ 1
   ví dụ đúng khuôn. `gate console` xanh (đụng file gốc → cổng chạy cả workspace, `test_cong_khung.py:333`).
3. **Phạm vi** — ĐƯỢC chạm: `AGENTS.md`, `CLAUDE.md` (một dòng trỏ tới). **KHÔNG** chạm: code, test, `TRAPS.md`
   (ranh giới nằm ở `AGENTS.md`, không nhân đôi).
4. **Bối cảnh** — `AGENTS.md` mục "Luật bắt buộc"; `TRAPS.md` §6 (bảng biện hộ); `docs/NGON-NGU.md` (cách gọi
   phải tránh — kiểm tên `no-ky-thuat` không đụng thuật ngữ đã dùng).
5. **Ràng buộc kỹ thuật** — khuôn marker, một dòng, greppable bằng regex đơn:
   ```
   # no-ky-thuat: <trần đã biết>, <điều kiện quay lại>
   // no-ky-thuat: <trần đã biết>, <điều kiện quay lại>
   ```
   Regex thu hoạch (dùng lại ở `pt.3`): `(#|//) ?no-ky-thuat:`. Dấu phẩy tách trần với điều kiện.
   Tên tiếng Việt không dấu để grep được trên mọi shell (Windows `PYTHONIOENCODING` — `CLAUDE.md`).
6. **Bẫy đã biết** — (a) quy ước không có lệnh đọc sẽ tự mục, nên `pt.2` **không tự đứng**, phải đi cùng `pt.3`
   trong một PR; (b) cám dỗ đặt marker cho mọi TODO — đoạn văn phải nói rõ marker chỉ dành cho **đơn giản hoá
   cắt góc thật có trần đã biết**, không phải TODO chung; (c) `test_cong_khung.py:422-426` bắt mọi đường dẫn
   trong backtick phải tồn tại — ví dụ minh hoạ không được trỏ file không có.
7. **Cách kiểm và cách báo** — không có ca test riêng (thuần tài liệu); ca của hạng mục nằm ở `pt.3`.
   Báo: dán diff `AGENTS.md` + output `gate console`. Không mở PR riêng — chung PR với `pt.3`.

### `pt.3` — lệnh thu hoạch sổ nợ

1. **Mục tiêu** — biến marker của `pt.2` thành một bảng đọc được, và **gắn cờ chính những marker sẽ mục**
   (không nêu điều kiện quay lại).
2. **Kết quả mong đợi** — `/no-ky-thuat` in một hàng mỗi marker, nhóm theo file, kết bằng
   `<N> marker, <M> không có điều kiện quay lại`; không có marker thì nói rõ là sổ sạch. Cổng bắt buộc lệnh này
   tồn tại.
3. **Phạm vi** — ĐƯỢC chạm: `.claude/commands/no-ky-thuat.md`, `platform/console/tests/test_cong_khung.py`
   (chỉ danh sách lệnh bắt buộc ở `:429`). **KHÔNG** chạm: hook, code Python, các lệnh khác.
4. **Bối cảnh** — `.claude/commands/gate.md:1-3` (khuôn frontmatter: đúng một trường `description:`);
   `test_cong_khung.py:414-431`; `docs/TASK-PACK.md`.
5. **Ràng buộc kỹ thuật** — lệnh là markdown, **không phải code Python** (bậc 3 của thang ponytail: `grep` đã
   làm được việc này). Frontmatter đúng một trường:
   ```markdown
   ---
   description: Sổ nợ kỹ thuật — thu mọi marker `no-ky-thuat:` thành một bảng, gắn cờ marker không có điều kiện quay lại
   ---
   ```
   Lệnh grep trong thân: `grep -rnE '(#|//) ?no-ky-thuat:' .` kèm loại trừ `.venv`, `.git`, `node_modules`,
   `.claude/worktrees`. Mở rộng `:429` thành `["gate", "debug", "adr", "no-ky-thuat"]`.
6. **Bẫy đã biết** — (a) mọi đường dẫn trong backtick của file lệnh phải tồn tại thật
   (`test_cong_khung.py:422-426`) — đây là chỗ file lệnh hay chết; (b) grep trên Git Bash đếm sai với ký tự đặc
   biệt (`TRAPS.md:123`) — lệnh mô tả cho agent chạy, không tự parse kết quả bằng đếm dòng shell;
   (c) `test_cong_khung.py:414-419` bắt file bắt đầu bằng `---` và có `description:`.
7. **Cách kiểm và cách báo**
   - ĐỎ trước: thêm `"no-ky-thuat"` vào parametrize `:429` **trước khi** tạo file lệnh → đỏ "thiếu
     /no-ky-thuat"; dán output.
   - XANH sau: tạo file lệnh → xanh; cộng ca frontmatter và ca đường dẫn tự chạy theo glob.
   - `scripts/dev-task.sh gate console` dán output.
   - Tiêu đề PR (chung với `pt.2`): `feat(khung): quy ước nợ kỹ thuật no-ky-thuat và lệnh thu hoạch`

### `pt.4` — đo: `SubagentStart` có thật không, hợp đồng output là gì

1. **Mục tiêu** — `pt.5` chỉ có nghĩa nếu sự kiện tồn tại **và** ta biết hook phải in gì ra để nội dung tới được
   subagent. Repo có 0 dấu vết (A2 #9); bằng chứng duy nhất hiện có là "ponytail dùng nó", tức **lời khai của
   kho người khác** — luật cấm 8 không cho tin.
2. **Kết quả mong đợi** — một kết luận có bằng chứng máy sinh cho **hai** câu hỏi: (a) bản Claude Code đang chạy
   có bắn `SubagentStart` không; (b) hook phải trả gì (stdout thô? JSON có khoá gì?) để nội dung vào được
   system prompt của subagent. Ghi vào `docs/sessions/2026-09-15.md`.
3. **Phạm vi** — ĐƯỢC chạm: `docs/sessions/2026-09-15.md`, một hook thử **trong scratchpad** (không commit).
   **KHÔNG** chạm: `.claude/settings.json` của repo (thử nghiệm không được đổi hàng rào đang chạy), không viết
   `phat-luat-subagent.sh` ở gói này.
4. **Bối cảnh** — `.claude/settings.json:1-41`; `AGENTS.md` luật bắt buộc 6 (đo trước khi sửa) và luật cấm 8;
   `TRAPS.md` §2; `docs/sessions/2026-09-14.md:58-79`.
5. **Ràng buộc kỹ thuật** — phép thử phải **đối chứng**, không chỉ "thấy chạy":
   ```
   hook thử: ghi một dòng có dấu nhận dạng duy nhất vào <scratchpad>/subagent-hook.log kèm $(date) và payload
   phép thử 1: spawn một subagent bất kỳ → log có dòng mới không?  (sự kiện có bắn không)
   phép thử 2: hook in một câu mốc ("mã nhận dạng XYZ") → hỏi subagent câu mốc đó
               → subagent đọc được ⇒ hợp đồng output đúng; không đọc được ⇒ sai dạng output
   đối chứng : tắt hook, lặp lại cả hai → phải KHÔNG có dòng log và subagent KHÔNG biết mã
   ```
   Không có đối chứng thì không được ghi kết luận (chính bẫy `feedback-do-truoc-khi-sua`).
6. **Bẫy đã biết** — (a) tài liệu sự kiện hook **không có trong repo**, chỉ có `$schema` trỏ ra ngoài
   (`.claude/settings.json:2`) — tra tài liệu ngoài thì ghi rõ nguồn và ngày, đừng coi là chân lý;
   (b) hook không chạy vì CRLF trông y hệt hook không được gọi (`docs/sessions/2026-09-14.md:72-74`) — phép thử
   phải phân biệt được hai ca này, nếu không sẽ kết luận "sự kiện không có" trong khi chỉ là file sai EOL.
7. **Cách kiểm và cách báo** — không sinh code sản phẩm nên không có ca test. Báo ≤ 20 dòng: bốn output dán
   nguyên (hai phép thử × có/không hook), kết luận **có/không** cho từng câu hỏi (a), (b), và một dòng khuyến
   nghị: `pt.5` chạy được / `pt.5` → `chờ người`. Không commit gì ngoài mục session log.

### `pt.5` — hook phát luật vào subagent

1. **Mục tiêu** — bịt A2 #9: mọi subagent `sc-*` và mọi `Task` đang chạy mà không hook nào nhắc luật. Phiên chính
   có `CLAUDE.md`, subagent thì không.
2. **Kết quả mong đợi** — hook mới chạy ở `SubagentStart`, phát 7 dòng luật; `settings.json` khai nó; cổng khung
   xanh (nó tự bắt hook mới phải có test, `test_cong_khung.py:365,380`); bảng hàng rào `AGENTS.md` + `CLAUDE.md`
   cập nhật; một mục CRLF mới trong `TRAPS.md`.
3. **Phạm vi** — ĐƯỢC chạm: `.claude/hooks/phat-luat-subagent.sh` (mới), `.claude/settings.json`,
   `platform/console/tests/test_cong_khung.py`, `AGENTS.md` (bảng hàng rào), `CLAUDE.md` (mục "Hàng rào tự
   động"), `TRAPS.md`. **KHÔNG** chạm: ba hook cũ, `scripts/dev-task.sh`, bất kỳ file nào trong `companies/`.
4. **Bối cảnh** — kết luận `pt.4` (**điều kiện tiên quyết**); `block-dangerous-git.sh:19-48` và `auto-format.sh:1-15`
   (khuôn); `test_cong_khung.py:86-101` (helper `_chay`/`_payload`), `:245-249` (ca fail-open mẫu), `:365`, `:380`,
   `:387`; `AGENTS.md:125-141`; `CLAUDE.md:30-37`.
5. **Ràng buộc kỹ thuật** — theo đúng khuôn ba hook cũ, không phát minh khuôn mới:
   ```bash
   #!/usr/bin/env bash
   # phat-luat-subagent.sh — hook SubagentStart. Subagent không thấy CLAUDE.md; phát 7 dòng luật vào nó.
   # Luôn exit 0: hook này không được cản luồng vì bất cứ lý do gì (cùng lý do auto-format.sh:5).
   set -uo pipefail
   ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
   # KHÔNG đọc stdin ở đường mặc định — xem mục 6 (b).
   ```
   - Nội dung phát: 7 dòng đầu `CLAUDE.md` ("Bảy điều nếu chỉ đọc được bảy dòng"), **đọc từ file**, không chép
     cứng vào hook (chép cứng = bản sao luật thứ năm, đúng thứ `pt.1` vừa dựng cổng để chặn).
   - Dạng output: **theo đúng kết luận `pt.4` mục (b)**. Gói này không được đoán.
   - Fail-open **có nói ra**: thiếu `CLAUDE.md`, đọc lỗi, bất cứ gì → `exit 0` nhưng in một dòng ra stderr
     (khuôn `block-dangerous-git.sh:44-48`; ca mẫu `test_cong_khung.py:245-249`).
   - File `.sh` phải EOL=LF (`test_cong_khung.py:387` tự bắt).
6. **Bẫy đã biết** — (a) **fail-open im lặng** là bẫy đã có tên: người tưởng hàng rào đang canh suốt phiên
   (`test_cong_khung.py:247`); (b) **không chờ stdin ở đường mặc định** — ponytail issue #443: wrapper PowerShell
   nuốt JSON piped nên `stdin 'end'` không bao giờ fire và **mọi lần spawn subagent bị treo**; ba hook cũ dùng
   `payload="$(cat)"` được vì `PreToolUse`/`PostToolUse` luôn có stdin, hook này thì không cần payload nên đừng
   đọc; (c) CRLF làm hook chết **im lặng** (`docs/sessions/2026-09-14.md:72-74`) — mục `TRAPS.md` mới phải ghi
   cả dấu hiệu nhận biết, không chỉ cách sửa; (d) `test_moi_hook_khai_trong_settings_ton_tai_that` (`:365`) và
   `test_moi_hook_deu_co_test_trong_file_nay` (`:380`) sẽ tự đỏ nếu quên một nửa — đừng "sửa" hai test đó.
7. **Cách kiểm và cách báo**
   - ĐỎ trước: thêm ca `test_phat_luat_subagent_in_du_bay_dong` → đỏ vì chưa có hook; dán output. Thêm ca fail-open
     `test_phat_luat_thieu_claude_md_thi_noi_ra` → đỏ; dán output.
   - **Ca chiều ngược bắt buộc**: `test_phat_luat_khong_cho_stdin` — chạy hook **không cấp stdin** và assert nó
     kết thúc dưới 2 giây. Đổi hook sang `payload="$(cat)"` thì ca này phải ĐỎ (treo/timeout). Dán cả hai chiều.
   - XANH sau: `scripts/dev-task.sh gate console` dán output; `:365`/`:380`/`:387` xanh.
   - `sc-ops` + `sc-security` chấm trước khi commit.
   - Tiêu đề PR: `feat(khung): phát luật vào subagent qua hook SubagentStart`

### `pt.6` — ADR-0042: scorer eval phải tự chứng minh bắt được lỗi

1. **Mục tiêu** — `pt.7` đổi **cách đo chất lượng agent**; luật bắt buộc 2 đòi ADR trước. Và ADR là chỗ duy nhất
   trả lời được câu "vì sao `--replay --strict` chưa đủ" bằng bằng chứng, thay vì bằng trực giác.
2. **Kết quả mong đợi** — `companies/software-company/docs/adr/0042-selftest-scorer-eval.md` đúng khuôn repo:
   đo hiện trạng **bằng số** trước, nêu phương án đã loại và vì sao, link trong PR `pt.7`.
3. **Phạm vi** — ĐƯỢC chạm: file ADR mới, `companies/software-company/docs/adr/README.md` (nếu có mục lục).
   **KHÔNG** chạm: code, yaml, test — ADR đi trước, một mình.
4. **Bối cảnh** — `/adr` (skill có sẵn, dùng nó chứ đừng tự bịa khuôn); A2 #12, #13, #14; ADR-0010, ADR-0015
   (hai ADR đã đặt cổng bản ghi — ADR mới phải nói rõ nó **bổ sung** chứ không thay); `xagents_core/evals.py:72-89`;
   `evals/thresholds.yaml:1-8` (phần chú thích nói rõ nó gác *điểm*, không gác *scorer*).
5. **Ràng buộc kỹ thuật** — ADR phải chứa **số đo thật**, tối thiểu: tổng số ca (59), số ca có `expect:` chỉ gồm
   `equals` trên trường định danh + một `contains` chung chung, và **≥ 3 ví dụ dẫn `file:dòng`** lấy từ A2 #12.
   Phương án phải nêu và loại tường minh: (1) judge LLM chấm như ponytail — loại, thêm một thứ phải tự kiểm;
   (2) siết tay từng ca, không cần cơ chế — loại, không chống được ca mới viết lỏng; (3) coi `--strict` là đủ —
   loại, nó gác bản ghi chứ không gác scorer (A2 #13).
6. **Bẫy đã biết** — (a) ADR viết sau code là ADR hợp thức hoá, không phải ADR quyết định — gói này **phải**
   merge trước `pt.7`; (b) cám dỗ mở rộng sang "đo chất lượng agent nói chung" — ADR này chỉ về **scorer tự kiểm**,
   phạm vi rộng hơn thì tách ADR khác.
7. **Cách kiểm và cách báo** — không có ca test. Kiểm: số ADR chưa bị dùng (`ls docs/adr/ | tail`); mọi `file:dòng`
   trong ADR trỏ đúng (mở từng chỗ); `gate company` xanh. Báo: đường dẫn ADR + ba số đo.
   Tiêu đề PR: `docs(company): ADR-0042 scorer eval phải tự chứng minh bắt được lỗi`
   *(H4 mở PR nháp từ `pt.6`, `gh pr ready` khi `pt.7`+`pt.9` xong — `QUY-TRINH-GIT.md` §2d.)*

### `pt.7` — `--selftest`: mỗi ca phải bác được bản `bad`

1. **Mục tiêu** — A2 #12: `check()` chưa bao giờ phải chứng minh nó bắt được lỗi. Một `expect:` lỏng làm ca đó
   **luôn xanh vĩnh viễn** — tệ hơn không có ca, vì nó tính vào `min_pass_ratio` như một ca thật.
2. **Kết quả mong đợi** — `uv run python -m company.evals all --selftest` chạy **không gọi model**, đỏ khi một
   `expect:` cho `bad:` của chính nó đi qua; liệt kê ca thiếu `bad:` dưới nhãn `chua-chung-minh`; chạy trong CI
   cạnh `--replay --strict`; **mọi** ca trong 6 file yaml có `bad:`.
3. **Phạm vi** — ĐƯỢC chạm: `platform/xagents-core/src/xagents_core/evals.py`,
   `companies/software-company/src/company/evals.py`, `companies/software-company/evals/*.yaml`,
   `.github/workflows/ci.yml`, test của cả hai package. **KHÔNG** chạm: `evals/recordings/` (không ghi lại eval ở
   gói này — `bad:` không đổi prompt nên không kích bảy bước §3), `evals/thresholds.yaml` (là `pt.9`),
   `companies/keeper/` (cùng lõi nhưng khác công ty — tách mã mới nếu muốn, đừng nới phạm vi).
4. **Bối cảnh** — ADR-0042 (`pt.6`); `xagents_core/evals.py:62` (`_get`), `:72-89` (`check`), `:271-273`
   (`load_cases`), `:92-107` (`CaseResult`); `company/evals.py:186-212` (`main`, nhóm cờ loại trừ ở `:189`);
   `ci.yml:68-84`; A2 #12 (6 ca lỏng đã điểm mặt).
5. **Ràng buộc kỹ thuật**
   - Khoá yaml mới, **cùng cấp** với `expect:`, hình dạng = payload đầu ra (để `check()` dùng lại nguyên si):
     ```yaml
     expect:
       contains: {summary: idempotency}
     bad:                      # payload hợp lý nhưng SAI — `check` phải bác nó
       ticket_id: TCK-10
       branch: ticket/TCK-10
       summary: "Thêm endpoint POST /payments, có test"
     ```
   - Lõi, đặt ngay dưới `check()` ở `xagents_core/evals.py:89` (dùng lại `check`, không viết bộ so khớp thứ hai):
     ```python
     def selftest_case(case: dict[str, Any]) -> str | None:
         """`None` = scorer bác được `bad`. Chuỗi = lý do hỏng.
         Không `bad:` → "chua-chung-minh"; `check(bad, expect) == []` → "khong-bat-duoc"."""

     class EvalSuite:
         def selftest(self, agent_id: str) -> list[tuple[str, str]]:
             """[(tên ca, lý do)] cho mọi ca hỏng. Không gọi model, không đọc bản ghi."""
     ```
   - CLI ở `company/evals.py`: `--selftest` vào **cùng nhóm loại trừ** với `--record`/`--replay` (`:189`) — nó
     không phải chế độ chạy model. Mã thoát 1 khi có ca `khong-bat-duoc`; `chua-chung-minh` in cảnh báo và
     **cũng** đỏ khi chạy `all` (nếu không, ca mới viết lỏng lại lọt).
   - `ci.yml`: thêm một `- run:` ngay trên `:83`, cùng `working-directory`.
   - Coverage `fail_under = 100` cho cả hai package — mọi nhánh mới phải có ca.
6. **Bẫy đã biết** — (a) `contains` **không phân biệt hoa thường và không phân biệt khẳng định/phủ định**
   (`xagents_core/evals.py:77-78`) — nên `bad:` của ca `de-bai-co-chuoi-cung-van-khong-duoc-hard-code`
   (`builder.yaml:84`) phải là bản có chữ "i18n" mà vẫn hard-code, đúng kịch bản A2 nêu; viết `bad:` không chứa
   "i18n" là **tự làm dễ đề**, ca sẽ xanh giả; (b) `any_of` chỉ cần một nhánh đạt (`:85-88`) — `bad:` cho
   `security.yaml:156` phải nhắm nhánh **lỏng nhất**, không phải nhánh chặt; (c) `min_len` chỉ đếm độ dài
   (`:79-80`) — `bad:` cho `qa.yaml:32` là `notes` một phần tử vô nghĩa; (d) đây là gói dễ "sửa `expect:` cho
   vừa `bad:`" — sai chiều: `bad:` tả **output sai thật**, `expect:` phải siết để bác nó, không phải ngược lại.
7. **Cách kiểm và cách báo**
   - ĐỎ trước (**bắt buộc, và kỳ vọng đỏ diện rộng**): cài `--selftest` + viết `bad:` cho 6 ca A2 #12 **trước
     khi** sửa `expect:` nào → phải đỏ đúng 6 ca; dán output. Đây là bằng chứng cơ chế bắt được lỗi có thật.
   - **Ca chiều ngược**: `test_selftest_bat_duoc_expect_long` — một ca dựng sẵn `expect: {contains: {s: x}}` với
     `bad: {s: "x"}` phải bị bác; nới `expect` thì ca phải ĐỎ.
   - Ca: `test_selftest_khong_goi_model` (client giả, assert 0 lời gọi) · `test_ca_thieu_bad_bi_gan_chua_chung_minh`
     · `test_ma_thoat_1_khi_co_ca_khong_bat_duoc` · `test_selftest_loai_tru_voi_record_va_replay`.
   - XANH sau: siết 6 `expect:` → `--selftest` xanh; **`--replay --strict` vẫn xanh** (không được làm tụt
     `min_pass_ratio`); `scripts/dev-task.sh gate core` và `gate company` dán output cả hai.
   - `sc-qa` chấm.
   - Tiêu đề PR (hạng mục H4): `test(company): selftest scorer eval — mỗi ca phải bác được bản bad`

### `pt.9` — vá hở `ops: cases` trong thresholds

1. **Mục tiêu** — A2 #14: `thresholds.yaml:15` ghi `cases: 8` trong khi `ops.yaml` có 9 ca. Cổng chỉ kiểm
   `total < cases` (`xagents_core/evals.py:433`) nên **xoá một ca của ops vẫn xanh** — đúng thứ cổng đó sinh ra
   để chặn.
2. **Kết quả mong đợi** — `ops: cases: 9`; và một ca test chặn tái diễn cho **cả sáu** agent, không chỉ ops.
3. **Phạm vi** — ĐƯỢC chạm: `companies/software-company/evals/thresholds.yaml`, một file test trong
   `companies/software-company/tests/`. **KHÔNG** chạm: `evals/*.yaml` (không thêm/bớt ca ở gói này),
   `min_pass_ratio` (không đụng số điểm).
4. **Bối cảnh** — `evals/thresholds.yaml:1-8` (chú thích nói rõ `cases` = chống thu nhỏ bộ);
   `xagents_core/evals.py:420-436` (`check_thresholds`); `xagents_core/evals.py:271-273` (`load_cases`).
5. **Ràng buộc kỹ thuật**
   ```python
   # companies/software-company/tests/test_evals_thresholds.py (file đã có)
   @pytest.mark.parametrize("agent_id", sorted(load_thresholds()))
   def test_cases_trong_thresholds_khop_bo_ca_that(agent_id: str) -> None:
       """`cases` là số ca ĐANG có. Lệch xuống = cổng chống thu nhỏ bộ hở đúng phần lệch."""
   ```
   Đọc số ca thật bằng `load_cases`, **không** đếm `- name:` bằng regex.
6. **Bẫy đã biết** — (a) cám dỗ sửa `ops.yaml` xoá bớt một ca cho khớp `8` — sai chiều: bộ ca là sự thật, con số
   là bản chép; (b) ca test này sẽ **đỏ ngay lần đầu** cho ops — đó là mục đích, đừng `xfail`.
7. **Cách kiểm và cách báo**
   - ĐỎ trước: thêm ca test **trước khi** sửa số → đỏ đúng ở `ops` (8 ≠ 9); dán output.
   - **Chiều ngược**: sửa `cases: 9` → `8` lại thì ca phải đỏ lại.
   - XANH sau: `cases: 9` → xanh; `--replay --strict` vẫn xanh; `gate company` dán output.
   - Vào chung PR H4 với `pt.6`/`pt.7`.

### `pt.8` — bốn câu chống over-engineering cho builder, có đối chứng

1. **Mục tiêu** — A2 #17: `builder.md` có TDD và coverage nhưng **không có câu nào** về over-engineering,
   root-cause, hay "giải thích dài hơn code". Và A2 #18: chưa ai hỏi prompt dài có hơn một câu không.
2. **Kết quả mong đợi** — bốn câu vào `builder.md`; `version: 1` → `2`; đủ bảy bước `CONTRIBUTING.md` §3 với
   **`RUNS=3`** (vá A2 #19: bản ghi hiện tại không có `score`); một bảng đối chứng prompt-rẻ trong PR;
   `--replay --strict` xanh và điểm không tụt dưới `min_pass_ratio: 0.95`.
3. **Phạm vi** — ĐƯỢC chạm: `companies/software-company/agents/engineering/builder.md`,
   `evals/recordings/builder.json` (sinh lại), `tests/golden/` (sinh lại), `.claude/agents/sc-builder.md` (sinh
   lại). **KHÔNG** chạm: `skills/` (bốn câu vào agent, không rải vào skill), năm vai còn lại, `thresholds.yaml`
   (không nới ngưỡng để vừa điểm mới — luật cấm 6 cùng tinh thần).
4. **Bối cảnh** — `CONTRIBUTING.md:64-118` (bảy bước, **đọc trước khi bắt đầu**); `builder.md:23` (`version`),
   `:55-62` (`## Bạn PHẢI`), `:157-158` (DoD); ADR-0004 (prompt là code), ADR-0010, ADR-0015, ADR-0022;
   `assetscan.py:209,261` (trần budget); `TRAPS.md` §2.
5. **Ràng buộc kỹ thuật** — bốn câu, đặt vào `## Bạn PHẢI` (`builder.md:55-62`), **không** tạo mục mới:
   ```
   - Sửa bug = sửa GỐC, không sửa triệu chứng: grep mọi caller của hàm sắp đụng trước khi sửa. Một guard ở hàm
     dùng chung là diff NHỎ HƠN một guard ở mỗi caller — vá đúng gốc cũng là vá lười hơn.
   - Không bao giờ lười ở khâu hiểu vấn đề. Diff nhỏ nhất đặt sai chỗ không phải lười, đó là bug thứ hai.
   - Code không có phép kiểm là chưa xong: mỗi logic không tầm thường (một nhánh, một vòng, một parser, một
     đường tiền/bảo mật) để lại MỘT phép kiểm chạy được — cái nhỏ nhất mà sẽ hỏng nếu logic hỏng.
   - Không trừu tượng ngoài yêu cầu: không interface một cài đặt, không factory một sản phẩm, không config cho
     giá trị không bao giờ đổi. Giải thích dài hơn code thì xoá giải thích.
   ```
   Đối chứng prompt rẻ (chạy **một lần**, ghi số vào PR, **không** commit thành cơ chế thường trực):
   ```
   arm A = builder.md hiện tại (version 1)   arm B = + bốn câu (version 2)
   arm C = builder.md rút còn một câu "Viết ít code nhất có thể; không trừu tượng ngoài yêu cầu."
   đo: pass_rate trên 13 ca × RUNS=3, và `make assetbudget` (token prompt tĩnh) cho cả ba
   ```
6. **Bẫy đã biết** — (a) **bảy bước không có ngoại lệ vì "đang thi hành tự động"** (`KHUON-THI-HANH.md` §3.6);
   (b) bản ghi eval **dao động** — một ca đỏ chưa phải hồi quy, nên `RUNS=3` là bắt buộc chứ không phải tuỳ chọn
   (`CONTRIBUTING.md:83-86`); (c) `make assetscan` đỏ vì mẫu dạy học thì **thêm dòng waiver có lý do**, đừng nới
   regex (`CONTRIBUTING.md:107-109`); (d) quên `make subagents` → `subagents-check` đỏ (`subagents.py:300-305`);
   (e) arm C là prompt **thật rút gọn**, không phải prompt rỗng — so với rỗng là tự thắng.
7. **Cách kiểm và cách báo**
   - **Chiều ngược** (luật bắt buộc 4 áp cho prompt): chạy eval builder ở arm A và arm B cùng `RUNS=3`. Nếu B
     không hơn A ở ca nào và không kém ở ca nào, **nói ra** — bốn câu là trung tính, không được báo là cải thiện.
   - Bảy bước dán output từng bước: `version` → `make golden` → `make eval-record AGENT=builder RUNS=3` →
     `make assetscan` → `make assetbudget` → `make subagents` → `git status` cho thấy đã commit đủ 4 nhóm file.
   - `--replay --strict` xanh; `scripts/dev-task.sh gate company` dán output.
   - `sc-builder` + `sc-qa` chấm.
   - Bảng đối chứng A/B/C vào mô tả PR.
   - Tiêu đề PR: `feat(company): builder — bốn câu chống over-engineering, có đối chứng`

## D. Điều phối

### Đợt — song song là song song **phát triển**, không song song mở PR (`QUY-TRINH-GIT.md` §2c/§2d)

| Đợt | Phát triển song song (worktree riêng) | Thứ tự PR | Điều kiện vào đợt |
|---|---|---|---|
| 0 | `pt.10` | **H0** | không — chạy trước mọi thứ: hàng rào đang hỏng thì mọi gói sau commit trong tình trạng không được canh |
| 1 | `pt.1` · `pt.2`+`pt.3` · `pt.4` | H1 merge → H2 mở | H0 merge |
| 2 | `pt.5` | H3 | `pt.4` kết luận **có** `SubagentStart` **và** biết hợp đồng output; H2 merge; `rebase origin/main` |
| 3 | `pt.6` → (`pt.7` ∥ `pt.9`) | H4 (PR nháp từ `pt.6`) | H3 merge hoặc H3 ghi `chờ người` |
| 4 | `pt.8` | H5 | H4 merge **và** người duyệt chi tiêu API |

Đồ thị phụ thuộc không vòng: `pt.4 → pt.5`; `pt.2 → pt.3`; `pt.6 → pt.7`; `pt.6 → pt.9`; còn lại độc lập.
Mỗi đợt ≤ 3 gói. Trần hạng mục ≤ 8 mã, ≤ 2 package: H4 có 3 mã / 2 package (core + company) — đạt trần, không thêm.

### Mức → model (`KHUON-THI-HANH.md` §2 — không hạ C3, không nâng C1)

| Mức | Gói | Model · effort |
|---|---|---|
| C1 | `pt.2` · `pt.9` | Haiku 4.5 |
| C2 | `pt.1` · `pt.3` · `pt.4` | Sonnet 5 `medium` |
| C3 `high` | `pt.10` · `pt.5` · `pt.7` · `pt.8` | Opus 5 `high` |
| C3 `xhigh` | `pt.6` (có ADR) | Opus 5 `xhigh` |

### `sc-*` chấm gói nào

| Gói | Trợ lý chấm | Vì sao |
|---|---|---|
| `pt.10` | `sc-ops` + `sc-security` | Sửa hàng rào thi hành đang hỏng |
| `pt.5` | `sc-ops` + `sc-security` | Đụng hàng rào thi hành; fail-open là quyết định bảo mật |
| `pt.7` | `sc-qa` | Phương pháp đo chất lượng agent |
| `pt.8` | `sc-builder` + `sc-qa` | Đổi prompt vai builder; ngưỡng eval |
| `pt.1`–`pt.4`, `pt.6`, `pt.9` | một lượt cuối hạng mục | C1/C2, hoặc thuần tài liệu |

### Khuôn giao việc

Dán nguyên khuôn ở `docs/KHUON-THI-HANH.md` §4, kèm khối 7 mục của gói ở phần C trên. Không chép lại ở đây.
`pt.4` là ngoại lệ về hình dạng: nó **không sinh code**, nên khuôn bỏ bước "(1) test đỏ / (2) code / (3) test
xanh" và thay bằng "chạy bốn phép thử ở mục 5, dán cả bốn output, kết luận có/không".

### Tiêu đề PR (luật bắt buộc 7 — scope **một từ, chữ thường**)

| Hạng mục | Mã | Tiêu đề |
|---|---|---|
| H0 | `pt.10` | `fix(khung): pre-commit-gate canh cây đang commit, không phải checkout chính` |
| H1 | `pt.1` | `test(khung): cổng chặn 4 file luật harness trôi khỏi AGENTS.md` |
| H2 | `pt.2`, `pt.3` | `feat(khung): quy ước nợ kỹ thuật no-ky-thuat và lệnh thu hoạch` |
| H3 | `pt.5` | `feat(khung): phát luật vào subagent qua hook SubagentStart` |
| H4 | `pt.6`, `pt.7`, `pt.9` | `test(company): selftest scorer eval — mỗi ca phải bác được bản bad` |
| H5 | `pt.8` | `feat(company): builder — bốn câu chống over-engineering, có đối chứng` |

Mỗi PR mang theo dòng `CHANGELOG.md` + mục `docs/sessions/2026-09-15.md` **trong chính nó** (luật 10), điền
`(#<n>)` ngay sau `gh pr create` rồi commit tiếp vào chính PR đó. Trước mỗi `gh pr create`: tìm PR/issue trùng
(luật bắt buộc 11).

## F. Lệnh thi hành

```
/thi-hanh pt                          # thi hành tới xong (idempotent, chạy lại tiếp từ chỗ dở)
/thi-hanh pt --dung-sau-ke-hoach      # chỉ in bảng B rồi dừng
```

Trước khi gõ:

1. PR chứa chính file này (`docs(khung)`) đã merge và `main` đã `git fetch` — bảng B vừa là kế hoạch vừa là
   bảng theo dõi, nó phải nằm trên `main` thì phiên sau mới đọc được trạng thái.
2. `gh` đã đăng nhập; `gh pr list --state open` **rỗng** (luật 2b).
3. Hai gói sẽ dừng hỏi người, đã biết trước và đã ghi vào bảng B:
   - `pt.4` nếu kết luận `SubagentStart` **không** có (hoặc không xác định được hợp đồng output) → cả H3 thành
     `chờ người: sự kiện hook không dùng được`. Không tự chế cơ chế thay thế.
   - `pt.8` cần **duyệt chi tiêu API** (`make eval-record AGENT=builder RUNS=3`, model thật, × 3 arm đối chứng)
     → `chờ người` tới khi được gật.
4. Worktree `port-khung-template` của phiên khác đang mở — không đụng vào (`git worktree list` để kiểm).
5. Ba lỗi **đang tồn tại** mà đo hiện trạng tìm ra (A2 #3, #14, và A2 #11 chưa vào `TRAPS.md`) nằm trong
   `pt.1`/`pt.9`/`pt.5`. Nếu vì lý do gì mà bỏ ba gói đó, ba lỗi này vẫn phải được vá — chúng không phải
   "cải tiến lấy từ ponytail", chúng là lỗi của repo mà việc đọc ponytail tình cờ soi ra.
