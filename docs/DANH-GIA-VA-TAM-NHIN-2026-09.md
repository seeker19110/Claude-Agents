# Đánh giá sâu và tầm nhìn phát triển X-Agents — 09/2026

Ngày lập: 2026-09-06 · Căn cứ: `main@d7c8271` (#108), khảo sát mã nguồn và tài liệu cả bốn package, ba báo cáo
trước (`software-company/docs/reports/2026-09-06-ban-giao-khong-chay-duoc.md`,
`Studio-creators/docs/DANH-GIA-NANG-CAP-XUONG-VIDEO.md`, `docs/DAC-TA-NANG-CAP-2026-09.md`).

Tài liệu này **không lặp lại** đặc tả nâng cấp tháng 9 (40 mục, sáu đợt). Nó trả lời ba câu đặc tả đó chưa hỏi:
(1) sau khi làm xong 40 mục thì dự án là *cái gì*; (2) những vấn đề cấu trúc nào không nằm trong 40 mục và sẽ
làm 40 mục đắt lên; (3) người chủ dự án phải ký quyết định nào trước khi đi tiếp. Mọi con số đo tại commit trên;
số dòng đọc bằng `wc -l`, số hàm bằng `grep -c def`.

## 1. Kết luận trong mười dòng

1. Đây là một hệ đa agent **có kỷ luật kỹ thuật hiếm gặp**: coverage 100% thật ở bốn package (9 dòng `no cover`
   trên 10k dòng ở company), prompt được version + golden + eval replay khớp 21/21, CI tự đối chiếu ruleset
   GitHub, tài liệu tự phê bình có ngày và số PR.
2. Nhưng sản phẩm của nó **chưa có bằng chứng "đầu-cuối chạy được"** nào: QLKH cần takeover nhiều lần, production
   vẫn là mô tả, studio chưa có một video thật nào đăng lên kênh thật.
3. Vấn đề của dự án hiện tại không còn là "thiếu tính năng". Là **ba lựa chọn cấu trúc** đã hết hạn sử dụng:
   `orchestrator.py` gộp mọi thứ, hạ tầng bị fork nguyên văn giữa hai công ty, và lệnh do model sinh chạy không
   có sandbox tiến trình.
4. Đặc tả tháng 9 nhìn thấy hai trong ba (E1 tách máy trạng thái, D2 sandbox) nhưng xếp E1 ở đợt cuối và không
   có mục nào cho package lõi chung. Thứ tự đó sai: E1 và lõi chung phải đi trước đợt 2/3/4, nếu không ba phiên
   song song sẽ cùng sửa một file 2.269 dòng.
5. Rủi ro lớn nhất không nằm trong code: **bus factor = 1** kết hợp với cổng eval `--strict` đòi bản ghi model
   thật chỉ ghi được trên máy cá nhân. Người duy nhất rời đi thì repo tự khoá.
6. Gateway là package chín nhất về kỹ thuật, nhưng tài liệu của nó né đúng câu duy nhất người dùng cần hỏi:
   "xoay nhiều tài khoản Google có bị khoá không". Câu trả lời hiện nằm ở một dòng trong hướng dẫn vận hành chung.
7. Console là package chín nhất về **thiết kế sản phẩm** ("ô rỗng là ô xám, không bao giờ xanh"), nhưng
   `index.html` 1.830 dòng một file sẽ vỡ khi thêm màn video (C9).
8. Studio thấp hơn company một bậc rõ rệt: không guard, không trace, không metrics, reviewer mù, `LLMError`
   dừng cả run thay vì hoãn.
9. Tầm nhìn đề xuất: **một nền tảng "công ty AI" tự vận hành, trong đó mọi lời khai của model đều bị code kiểm
   trước khi thành sự thật**. Không phải "nhiều công ty" — mà là một lõi chứng minh được, và các công ty là
   cấu hình trên lõi đó.
10. Ba chân trời: 1 tháng (chứng minh Q1/Q2 bằng một dự án và một video thật), 3 tháng (lõi chung + sandbox +
    người thứ hai vận hành được), 12 tháng (công ty thứ ba dựng bằng cấu hình, không fork code).

## 2. Dự án đang ở đâu — đo, không kể

| Chỉ số | company | studio | gateway | console |
|---|---|---|---|---|
| Dòng src / dòng test | 10.132 / 12.232 | 6.080 / 6.023 | 2.484 / 3.360 | 2.286 / 2.945 |
| File lớn nhất | `orchestrator.py` 2.269 (110 hàm) | `media.py` 895, `orchestrator.py` 877 | `client.py` 1.055 | `index.html` 1.830 |
| ADR | 32 | 9 | 3 | 3 |
| `pragma: no cover` | 9 | 7 | ít | ít |
| Bằng chứng chạy thật trong repo | QLKH: 25 RC, 0 điểm vào (trước #90); sau đó có smoke | ffprobe xác nhận khung/thời lượng; **0 video đăng** | 216 test mock, chạy thật hằng ngày theo session log | 10 ghi nhận vận hành thật đêm 05–06/09 |
| Module thiếu so với company | — | guard, workspace, trace, metrics, gate_brief, smoke, mcp_bridge, probe (16 module) | — | — |

Ba điểm mà bảng trên không nói:

- **Tỷ lệ tài liệu/code ≈ 0,55** (~25.800 dòng markdown / ~46.500 dòng Python). Toàn bộ tiếng Việt, kể cả tên test.
  Đây là tài sản thật với người Việt và là rào cản thật với mọi người khác — cần quyết định có chủ ý (§6, quyết
  định 4).
- **mypy không strict ở cả bốn package**, chỉ `--ignore-missing-imports`. Payload giữa 30 module là `dict[str,
  Any]` truyền tay, dù Pydantic có sẵn trong `events.py`. Đây là mắt xích yếu duy nhất trong một chuỗi cổng chất
  lượng rất chặt.
- **Bus SQLite không có migration** (`sqlite_bus.py` DDL `IF NOT EXISTS`, không `user_version`), nạp toàn bộ
  log vào RAM lúc mở, một tiến trình theo lease file. Đủ cho hôm nay, không đủ cho một bus sống 6 tháng.

## 3. Điểm mạnh thật — giữ bằng mọi giá

1. **Ranh giới "model khai – code chứng"** được thực thi bằng code và có lịch sử sự cố cho từng lớp:
   `local_checks.verified_by=workspace`, `smoke.verified_by=orchestrator`, identity từ ROUTE, console không
   bao giờ ghi thẳng sqlite mà đi qua `HumanGate`. ADR 0028–0032 đều là hệ quả của một sự cố thật được mổ xẻ.
2. **Prompt là code, thật sự**: 21/21 recording khớp version agent, `golden-check` chặn quên commit golden,
   `asset-scan` coi prompt là chuỗi cung ứng.
3. **`TRAPS.md` ba cấp** (repo, package, console) với năm khuôn lỗi lặp lại được đặt tên. Ít dự án có thứ này.
4. **Dependency gần bằng không**: company chỉ jsonschema + pydantic + pyyaml; console chỉ stdlib; gateway ba gói.
   Rất dễ bảo trì lâu dài.
5. **Cổng chất lượng khắt khe và tự kiểm**: `protection-guard` đối chiếu ruleset hai chiều; `filterwarnings =
   error`; matrix Windows chặn merge.

## 4. Bảy vấn đề cấu trúc — không phải bug, là quyết định đã hết hạn

Mỗi mục ghi: triệu chứng đo được → vì sao đặc tả tháng 9 chưa đủ → việc cần thêm.

### 4.1 `orchestrator.py` là God object (2.269 dòng, 110 hàm, `main` 161 dòng)

Nó vừa là bảng ROUTES, vừa là FSM ticket, FSM release, scheduler/retry/deferral, và CLI. 22/30 PR gần nhất là
`fix(company)` cùng một họ (state trong RAM, khoá once, event cũ phát lại) — TRAPS §1 gọi tên năm khuôn, và cả năm
đều sống trong file này. Đặc tả có E1 (tách thành `state/ticket.py`, `state/release.py`, `state/gate.py`, ADR-0037)
nhưng xếp **đợt 5**, sau ba đợt sửa tính năng. Việc cần thêm: **đưa E1 lên ngay sau đợt 1**, và luật "PR `fix`
thứ 23 cùng họ phải link ADR-0037" (đặc tả §2.2) phải thành check CI, không phải lời dặn.

### 4.2 Hạ tầng bị fork nguyên văn giữa company và studio

`grep "from company" Studio-creators/src` = 0. ~1.200 dòng giống nguyên văn (`llm`, `evals`, `runner`, `routing`,
`gate_cli`, `registry`, `sqlite_bus`, `bus`), ~55–60% trùng về API. Hệ quả đã xảy ra: fix `claude -p` thoát mã 1
chỉ vá company; studio còn `LLMError` dừng orchestrator thay vì hoãn. Đặc tả tháng 9 **không có mục nào** cho
việc này. Việc cần thêm: package thứ năm `xagents-core` (bus, llm, routing, runner, gates, evals, guard,
supervisor) và hai công ty import nó. Làm **trước** khi công ty thứ ba xuất hiện, và trước S1 (studio cần
`attachments` trong `llm.py` — nếu làm trên bản fork là fork sâu thêm).

### 4.3 Lệnh do model sinh chạy không có sandbox tiến trình

`smoke.py` chạy `runtime.command` lấy từ spec do model viết; `stacks.py` chạy lint/test theo stack; `tools.py`
`run` chỉ có allowlist + khoá path + lọc env. README company tự ghi guard injection là "lưới chắn theo mẫu, không
phải hàng rào". Đây là RCE thực tế trên máy trực, không phải lý thuyết. Đặc tả có D2 (docker sandbox, ADR-0035)
ở **P1**. Việc cần thêm: nâng D2 lên P0 ngang D1, và mở rộng phạm vi từ `run` sang cả `smoke` và `stacks` —
đặc tả hiện chỉ ghi `tools.py`.

### 4.4 `smoke.unverified` giữ status xanh

`smoke.py:75` trả `{"unverified": True, ...}` cho dự án cũ không có `runtime`; orchestrator không chặn. Đây là
đúng khuôn tạo ra sự cố QLKH, dời một bậc. Việc cần thêm: `unverified` chỉ được chấp nhận khi spec có
`kind != application` hoặc dự án được đánh dấu legacy tường minh; dự án mới thì `unverified` = chặn.

### 4.5 Bus factor = 1, và cổng eval khoá cứng repo khi người đó vắng

`evals/recordings/REQUIRED.txt` + `--strict`: sửa prompt thì phải `make eval-record` bằng model thật trên máy có
gói Claude đăng nhập. Không có cách nào ghi lại trong CI. Cộng với ruleset phải import tay, `make llm PROFILE`
trên máy cá nhân. Đặc tả có E3 (eval có răng) nhưng nó **tăng** phụ thuộc vào máy cá nhân (21 recording mới,
3 lần lấy trung vị). Việc cần thêm: (a) một workflow `workflow_dispatch` ghi eval bằng API key trong GitHub
Secrets, chạy khi người có quyền bấm; (b) tài liệu "người thứ hai làm gì trong ngày đầu" là Q4 nhưng chưa có mục
nào của đặc tả kiểm nó bằng người thật.

### 4.6 Console: `index.html` 1.830 dòng một file, `API.md` là hợp đồng không ai enforce

C9 (màn video: lưới cảnh, thumbnail A/B, SRT) sẽ thêm ≥ 500 dòng vào một file đã 1.830 dòng. Company đổi shape
event thì console vỡ lúc runtime, không có contract test. Và `--allow-decide` cho duyệt dưới **bất kỳ tên nào**
— four-eyes tựa vào chuỗi người dùng tự gõ; một người thì được, hai người là lỗ hổng. Việc cần thêm: tách ES
module trước C9; contract test đọc `topics/schemas/` của hai công ty và so với `collect()`; danh tính người
duyệt từ token cấp theo người (đơn giản: `--user <tên>` khi khởi động, token gắn tên).

### 4.7 Gateway: tài liệu né rủi ro tài khoản, `.env.example` còn cổng 8100

Ba ADR phân tích ACL Windows, đồng hồ thô, keyring — nhưng không một dòng "Google có thể khoá tài khoản". Câu duy
nhất ở `docs/HUONG-DAN-VAN-HANH.md:314`. `gateway/.env.example` ghi 8100 ở 4 chỗ trong khi mọi nơi khác là 1123 —
tài liệu lạc hậu đang dạy người dùng vào đúng cái bẫy ADR-0002 dựng ra để tránh. `stop` chỉ kiểm cmdline trên
Linux. Không có supervisor cho daemon. Việc cần thêm: §"Rủi ro tài khoản" trong `gateway/README.md` + ADR-0004
ranh giới ToS; sửa `.env.example`; console dựng lại daemon khi chết (hoặc ghi rõ là không).

## 5. Tầm nhìn — dự án này muốn thành gì

Ba kịch bản khả dĩ, mỗi cái kéo lộ trình về một hướng khác:

| Kịch bản | Nghĩa là | Đòi hỏi | Không đòi hỏi |
|---|---|---|---|
| **A. Công cụ cá nhân** | Một người chạy một công ty phần mềm + một xưởng video cho việc của mình | Q1, Q2 có bằng chứng; sandbox | lõi chung, người thứ hai, tiếng Anh |
| **B. Nền tảng "công ty AI"** | Lõi chứng minh được; mỗi công ty là bộ agent/topic/gate cấu hình trên lõi | lõi chung (4.2), E1, sandbox, eval chạy được trong CI, người thứ hai vận hành được | tiếng Anh ngay |
| **C. Sản phẩm mở** | Người ngoài dùng, đóng góp | tất cả của B + tiếng Anh + gỡ phụ thuộc gateway lách hạn mức khỏi đường mặc định | — |

**Khuyến nghị: B.** Lý do: A đã gần xong về tính năng nhưng đang trả giá vì kiến trúc của B chưa có (4.1, 4.2);
C chưa đến lúc vì chưa có bằng chứng Q1/Q2, và gateway xoay tài khoản là thứ không thể đứng ở đường mặc định
của một sản phẩm mở. B là điểm mà mọi việc đang làm hội tụ, và là điểm duy nhất trả lời được "công ty thứ ba tốn
bao nhiêu".

Câu tuyên bố tầm nhìn đề xuất, để dán ở đầu README:

> X-Agents là nền tảng dựng "công ty AI" tự vận hành. Model đề xuất, code kiểm chứng, người ký ở gate. Không
> trường "đã xong" nào do model điền. Một công ty mới là một thư mục cấu hình, không phải một bản fork.

Thước đo của tầm nhìn đó, đo được bằng lệnh:

| # | Câu hỏi | Bằng chứng |
|---|---|---|
| T1 | Công ty thứ ba dựng mất bao lâu? | thư mục `<công ty>/` chỉ có `agents/ skills/ topics/ gates/ templates/ evals/`, không có `src/<pkg>/{bus,llm,runner,routing}.py` |
| T2 | Có lời khai nào của model thành sự thật mà không qua code? | `grep verified_by` trên mọi trường "đã làm được" trong schema; test bảng liệt kê từng trường |
| T3 | Người thứ hai vận hành được không? | một người chưa từng mở repo đưa yêu cầu → duyệt 4 gate → sản phẩm chạy, ≤ 30 phút, ghi vào `docs/reports/` |
| T4 | Repo tự khoá khi người 1 vắng không? | eval-record chạy được từ CI với secret; ruleset import tự động |

## 6. Lộ trình ba chân trời

Chân trời 1 giữ nguyên đặc tả tháng 9 nhưng **đổi thứ tự**; chân trời 2 và 3 là phần đặc tả chưa có.

### Chân trời 1 — 1 tháng: chứng minh, không thêm tính năng

Mục tiêu: Q1 và Q2 trả lời "có" kèm bằng chứng máy sinh. Thứ tự bắt buộc:

1. Đợt 0 (V1–V5) — còn "chưa" trong bảng theo dõi dù nhiều mục đã làm rời (#98). Chốt bảng.
2. Đợt 1 còn lại: B6 (DoD một dòng + ảnh chụp UI), B8 (dự án mẫu 2, ≤ 2 takeover).
3. **E1 tách máy trạng thái** — kéo từ đợt 5 lên đây. Điều kiện để mở ba phiên song song.
4. **D2 sandbox** lên P0, mở rộng phạm vi sang `smoke` và `stacks` (4.3). Đi cùng D1 deploy thật.
5. Đợt 3 còn C9 — **tách `index.html` trước** (4.6), rồi mới C9.
6. Đợt 4: S1 (reviewer đa phương thức) và S7 (video thật) — nhưng S1 chạm `llm.py`, nên làm **sau** khi có lõi
   chung (chân trời 2, mục 1) hoặc chấp nhận vá hai chỗ và ghi nợ tường minh.
7. Mỗi đợt kết thúc bằng một báo cáo `docs/reports/` — đặc tả đã đòi, chưa đợt nào có.

Không nhận PR `fix(company)` cùng họ trạng thái/khoá/event cũ mà không link ADR-0037. Biến luật này thành check
trong `pr-policy.yml` (grep thân PR).

### Chân trời 2 — 3 tháng: lõi chung, người thứ hai

1. **`xagents-core`** (4.2): tách theo thứ tự ít rủi ro nhất — `sqlite_bus` + `bus` → `routing` + `llm` →
   `runner` + `gates` + `evals` → `guard` + `supervisor`. Mỗi bước một PR, test của cả hai công ty xanh, studio
   nhận ngay `TransientError` hoãn thay vì dừng. ADR chung ở `docs/adr/` gốc (hiện chưa có thư mục này).
2. **Bus có migration** (`user_version`, script nâng cấp) và không nạp toàn log vào RAM; E2 Redis Streams đợi
   sau, vì nhu cầu thật là "bus sống 6 tháng", chưa phải "nhiều tiến trình".
3. **mypy strict theo module**: bật `disallow_untyped_defs` cho `xagents-core` từ ngày đầu, company/studio siết
   dần theo file. Thay `dict[str, Any]` bằng model Pydantic ở ranh giới orchestrator ↔ runner.
4. **Eval ghi được từ CI** (4.5): `workflow_dispatch` với API key trong Secrets; E3 (ngưỡng trung vị) xây trên đó.
5. **Người thứ hai**: một phiên thật, người chưa từng mở repo, đo T3. Kết quả là báo cáo, và mọi chỗ vấp thành
   mục `TRAPS.md` hoặc sửa tài liệu. Đây là bài kiểm duy nhất cho Q4.
6. Console: danh tính người duyệt gắn token (4.6); contract test với schema hai công ty.
7. Gateway: ADR-0004 ranh giới ToS + §rủi ro tài khoản trong README; sửa `.env.example`; quyết định supervisor.

### Chân trời 3 — 12 tháng: công ty thứ ba bằng cấu hình

1. Dựng công ty thứ ba (gợi ý: thứ có vòng đời khác hẳn hai cái hiện có, ví dụ "phòng nghiên cứu" đọc tài liệu
   → tổng hợp → phản biện → xuất bản, không cần worktree lẫn ffmpeg) **chỉ bằng thư mục cấu hình**. Nếu phải sửa
   `xagents-core` quá 200 dòng thì lõi chưa đủ chung — đó là kết quả có giá trị, không phải thất bại.
2. Thông báo và UI UAT (D3, D4) — chỉ khi đã có khách ngoài người chủ.
3. Quyết định tiếng Anh (quyết định 4 dưới đây) — chỉ khi chọn kịch bản C.

## 7. Bốn quyết định người chủ phải ký trước khi đi tiếp

Mỗi cái là một ADR gốc; không ký thì lộ trình trên là đoán.

1. **Kịch bản A/B/C** (§5). Khuyến nghị B. Hệ quả tức thì: `xagents-core` vào lộ trình, E1 lên trước đợt 2/3/4.
2. **Sandbox là P0 hay chấp nhận rủi ro có ghi**. Khuyến nghị P0. Nếu chấp nhận rủi ro: ghi vào `SECURITY.md`
   rằng máy trực là máy dùng riêng, không có dữ liệu khác, và `smoke`/`stacks` chỉ chạy dự án tin cậy.
3. **Gateway xoay tài khoản có ở đường mặc định không**. Hiện `llm.claude-gateway.yaml` là hồ sơ "chép là chạy".
   Khuyến nghị: giữ, nhưng README gateway phải nói rõ rủi ro khoá tài khoản ngay dưới lệnh `make login`, và
   `make llm` mặc định trỏ một tài khoản.
4. **Ngôn ngữ**. Tiếng Việt toàn bộ là lựa chọn có chủ ý và đang phục vụ đúng người. Chỉ đổi khi chọn C; khi
   đó đổi từ `xagents-core` ra, không dịch 25.800 dòng cũ.

## 8. Những gì đánh giá này không làm

- Không chạy orchestrator với model thật; mọi nhận định "chưa có bằng chứng chạy thật" dựa trên thứ có trong
  repo (báo cáo, session log, CHANGELOG, `output/`), không dựa trên máy trực.
- Không đo hiệu năng, chi phí token thật.
- Không đọc lịch sử trước `main@2438d2f` (clone nông); nhận xét về nhịp commit chỉ đúng cho 2026-09-05/06.
- Không đánh giá chất lượng nội dung prompt của 35 agent — đó là việc của eval, không phải của một lần đọc.
