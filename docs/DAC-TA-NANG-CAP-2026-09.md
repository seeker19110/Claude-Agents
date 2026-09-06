# Đặc tả nâng cấp X-Agents — chương trình "hoàn thiện" tháng 9/2026

Ngày lập: 2026-09-06 · Căn cứ: đánh giá toàn diện tại `main@113833f` (#90), báo cáo
`software-company/docs/reports/2026-09-06-ban-giao-khong-chay-duoc.md`, đánh giá
`Studio-creators/docs/DANH-GIA-NANG-CAP-XUONG-VIDEO.md`, ghi nhận vận hành console đêm 05–06/09.

Tài liệu này là **kế hoạch + đặc tả mức epic**. Mỗi mục là một hoặc vài PR; chi tiết mức ticket nằm ở ADR của
mục đó (ghi trong cột "ADR"). Cách dùng: lấy một mục, đọc tiêu chí nghiệm thu, mở nhánh, làm, PR; xong thì đánh dấu
ở bảng theo dõi cuối file.

## 0. "Hoàn thiện" nghĩa là gì — bốn câu hỏi đo được

Dự án được coi là hoàn thiện khi trả lời **có, kèm bằng chứng máy sinh** cho cả bốn câu:

| # | Câu hỏi | Bằng chứng chấp nhận | Hiện trạng 06/09 |
|---|---|---|---|
| Q1 | Khách đưa yêu cầu, công ty phần mềm giao được **sản phẩm chạy** mà không cần người sửa tay? | Một dự án mẫu đi từ `request` tới `acceptance` với `evidence.smoke` ở staging **và** production, 0 lần takeover | Không: QLKH cần takeover nhiều lần; production vẫn là mô tả |
| Q2 | Xưởng video đưa ra **một video đăng được** với provider thật? | `output/<video>/final_v<n>.mp4` + audit `publish.done` + báo cáo như QLKH | Không: chưa có sqlite/artifacts nào của studio |
| Q3 | Người trực nhìn console **biết đúng** hệ đang kẹt ở đâu, không cần mở CLI? | 10 ghi nhận hiểu nhầm đêm 05/09 đều có màn hình tương ứng; bế tắc im lặng = 0 | Không: mới có lớp "sự thật giao hàng" (#76) |
| Q4 | Người mới vào **vận hành được trong 30 phút** và không lặp lại bẫy đã ghi? | Bộ khung 9 file đủ, CHANGELOG không hụt PR, không nhánh/worktree rác | Gần: CHANGELOG hụt #92 #93, 18 nhánh rác |

Mọi mục dưới đây đều truy được về một trong bốn câu này. Mục nào không truy được thì không nằm trong chương trình.

## 1. Hiện trạng tóm tắt (đo ngày 06/09)

- 4 package, 1617 test pass, coverage ép 100%, ruff + mypy sạch, CI main xanh.
- 163 file markdown, 40 ADR (company 29, studio 9, console 2, gateway 0).
- 57 PR merge trong 5 ngày; 22/30 PR gần nhất là `fix(company)` cùng một họ (trạng thái không sống qua restart, event
  cũ phát lại, "ticket ma", lời khai của model bị tin là bằng chứng). `orchestrator.py` 2039 dòng.
- 6 đề xuất của báo cáo 06/09: đã làm 3 (smoke ADR-0029, tool đọc cho reviewer #87, env từ route #72/#75), đang wip 1
  (sổ Ruling ADR-0030), chưa làm 2 (trace end-to-end, ảnh chụp UI trong DoD).
- Studio: điều phối tốt, render v2 đã kiểm bằng ffmpeg thật; reviewer "mù", chưa nhạc, chưa footage, chưa tính tiền media.
- Gateway: hoàn thiện nhưng không ADR — hộp đen với người mới.

## 2. Nguyên tắc chương trình

1. **Bằng chứng thay lời khai** ở mọi ranh giới model → code (`verified_by=workspace|orchestrator`). Đây là chủ đề
   xuyên suốt, kế thừa ADR-0027/0029.
2. **Sửa gốc, không vá nhánh.** Fix thứ 23 cùng họ không được merge nếu không kèm hoặc tham chiếu ADR tách máy trạng thái (mục 4.E1).
3. **Prompt là code**: mọi mục chạm `agents/`, `skills/`, `gates/checklists.md` đi đủ 7 bước `CONTRIBUTING.md` §3.
4. **Mỗi đợt kết thúc bằng một lần chạy thật và một báo cáo** trong `docs/reports/` — đợt không có báo cáo là đợt chưa xong.
5. **Không hạ ngưỡng** (coverage, gate, allowlist) để qua đợt.

## 3. Lộ trình — sáu đợt, thứ tự bắt buộc giữa đợt, song song bên trong đợt

```
Đợt 0 vệ sinh (½ ngày)
  └─ Đợt 1 bằng chứng thay lời khai — company (3–4 ngày)   ──► Q1
       ├─ Đợt 2 giao hàng thật: deploy, sandbox, thông báo (4–5 ngày) ──► Q1
       ├─ Đợt 3 console thiết kế lại (3 ngày)                 ──► Q3
       └─ Đợt 4 studio ra video thật (4–5 ngày)               ──► Q2
            └─ Đợt 5 nền tảng: máy trạng thái, bus, eval, gateway ADR (5 ngày) ──► Q1 Q4
```

Đợt 2, 3, 4 độc lập nhau, có thể chạy ba phiên song song (mỗi phiên một worktree). Đợt 5 có mục E1 nên bắt đầu ngay
khi đợt 1 xong vì nó là điều kiện để họ fix cùng khuôn dừng lại.

## 4. Đặc tả từng mục

Quy ước cột: **Mục tiêu** (một câu) · **Phạm vi** (file/agent chạm) · **Nghiệm thu** (kiểm được bằng lệnh) · **ADR** ·
**PR** dự kiến.

### Đợt 0 — Vệ sinh (Q4)

| Mã | Mục tiêu | Phạm vi | Nghiệm thu |
|---|---|---|---|
| V1 | PR #94 hết CONFLICTING, CI chạy, merge | rebase lên main (xung đột 1 dòng `software-company/README.md`) | `gh pr view 94 --json mergeable` = MERGEABLE, auto-merge xong |
| V2 | CHANGELOG đủ #91 #92 #93 và mọi PR sau | `CHANGELOG.md` | `for n in 91 92 93; grep "#$n" CHANGELOG.md` đều khớp; thêm check CI: PR merge phải có dòng CHANGELOG (mở rộng workflow `PR policy`) |
| V3 | Xoá 18 nhánh local đã merge squash, gỡ worktree `wt-gitdoc` `wt-khung` `wt-smoke` | git local | `git branch --no-merged main` chỉ còn nhánh có PR mở hoặc wip có chủ |
| V4 | `.gitignore` chặn `llm.yaml.bak*`, `media.yaml.bak*`, `*.sqlite*.bak*` | `.gitignore` | `git status --short` không hiện 3 file `.bak` |
| V5 | `ARCHITECTURE.md` ghi mốc commit đầu thực của X-Agents (lịch sử trước đó là fork 12-factor-agents + MEP-Agents) | `ARCHITECTURE.md` | có mục "Lịch sử repo" nêu hash mốc |

### Đợt 1 — Bằng chứng thay lời khai, company (Q1)

Hoàn tất 6 đề xuất của báo cáo 06/09 cộng ba việc dở ghi ở nhật ký phiên.

| Mã | Mục tiêu | Phạm vi | Nghiệm thu | ADR |
|---|---|---|---|---|
| B1 | Gate 1: spec phải có `runtime` (lệnh khởi động, cổng, phụ thuộc ngoài); thiếu → `request_changes` | `templates/prd.md`, spec-writer, `gates/checklists.md`, `sc-gate-spec` | golden spec-writer có mục runtime; test: spec thiếu runtime → gate spec không mở | ADR-0031 |
| B2 | Gate 2: `plan.proposed` có `open_decisions[]`; ≥1 quyết định treo không có ticket ADR + người ký → `problems`; plan đầu tiên của ứng dụng bắt buộc có ticket "điểm vào chạy được" | delivery-lead (v11), schema `plan.proposed`, orchestrator | test hai chiều: plan né quyết định → không xin gate; plan có ticket entrypoint → qua | ADR-0030 (sổ Ruling, đang wip) |
| B3 | Gate 3: `regression-staging` mang `evidence.run` (lệnh, mã thoát, mã HTTP) do tool `run` của QA hồi quy sinh theo `runtime` của spec | qa-debugger, `smoke.py` (dùng lại ADR-0029), `tools.py` | verdict không có `evidence.run` → orchestrator từ chối như từ chối `deployed` không smoke | mở rộng ADR-0029 |
| B4 | Gate 4: `gate_brief` cho acceptance tự khởi động sản phẩm theo `runtime`, đính kết quả smoke; khách ký trên thứ đã chạy | `gate_brief.py`, `/gate-brief`, `sc-gate-acceptance` | `gate-brief REL-xxx` in mục "Đã chạy" với mã HTTP thật; test với fake runtime | — |
| B5 | Supervisor đếm nợ kiến trúc treo: cùng mã nợ (DEF-xx, SD-xx) xuất hiện ≥ N lần review liên tiếp → escalation cấp dự án | supervisor, `audit` query | test: 3 review liên tiếp nhắc DEF-01 → gate escalation mở với danh sách nợ | ADR-0032 |
| B6 | DoD chung một dòng cho delivery-lead, release-engineer, account-manager: *"sản phẩm khởi động bằng một lệnh ghi trong README và trả lời một request thật"*; DoD frontend thêm ảnh chụp giao diện đính vào PR | 3 agent + frontend, skill `handover.md`, `frontend.md` | golden 4 agent đổi; tool `screenshot` (playwright headless) trả file vào `evidence.screenshots[]` | ADR-0033 (ảnh chụp) |
| B7 | Trace một ticket từ intake tới deploy: một lệnh in dòng thời gian (event, agent, tier, token, tool, gate, thời gian chờ) | `orchestrator trace <TICKET>`, skill `observability.md` | chạy trên QLKH-012 ra đủ 4 gate và mọi lượt retry; test với bus fake | — |
| B8 | Chạy thật: dự án mẫu thứ hai (nhỏ, có UI + API + DB) từ request tới acceptance, đếm số takeover | `docs/reports/2026-09-xx-du-an-mau-2.md` | báo cáo ghi số takeover, thời gian, token; mục tiêu ≤ 2 takeover | — |

### Đợt 2 — Giao hàng thật: deploy, sandbox, thông báo (Q1)

| Mã | Mục tiêu | Phạm vi | Nghiệm thu | ADR |
|---|---|---|---|---|
| D1 | Release-engineer có tool `deploy` thật: chạy `docker compose` (hoặc lệnh ghi ở `runtime.deploy`) trên máy trực, staging và production là hai compose project; `deployed` chỉ khi container up + smoke qua | release-engineer, `tools.py`, `smoke.py`, `runtime` schema | REL mới của QLKH lên production bằng compose, `evidence.deploy` có container id + smoke; REL-019 hết kẹt | ADR-0034 |
| D2 | Sandbox cho `run`: chạy trong container (docker) có mount worktree chỉ đường dẫn ticket, không mạng trừ allowlist; fallback allowlist hiện tại khi không có docker và ghi `sandbox=none` vào audit | `tools.py`, `SECURITY.md` | test: lệnh ghi ra ngoài worktree bị chặn trong sandbox; audit ghi loại sandbox | ADR-0035 |
| D3 | Thông báo webhook (Discord/Telegram/generic) khi gate mở, gate quá hạn, bế tắc im lặng, ngân sách 80/100 | module `notify.py` dùng chung company/studio, config `notify.yaml.example` | test với server giả; gate mở → 1 POST trong 5 s | ADR-0036 |
| D4 | Giao diện UAT cho khách: console phục vụ trang chỉ đọc theo token một lần, hiện `gate_brief` acceptance + nút ký | console `uat/`, `gate_brief` | khách ký qua trang → `gate.decide` với actor `customer`; test token hết hạn | — |
| D5 | Xung đột merge: thử rebase tự động trước khi huỷ RC | orchestrator release | test: RC xung đột trivial được rebase, xung đột thật vẫn `release.void` | — |

### Đợt 3 — Console thiết kế lại (Q3)

Mười ghi nhận đêm 05/09 thành mười mục; mỗi mục một màn hình hoặc một cột.

| Mã | Ghi nhận gốc | Mục tiêu | Nghiệm thu |
|---|---|---|---|
| C1 | #1–#3 số xanh vì rỗng | Phễu release theo **sản phẩm**: request → spec → ticket → RC → staging (smoke) → production (smoke) → nghiệm thu; ô rỗng hiện xám, không xanh | trang `/funnel`; test render với dữ liệu rỗng không có ô xanh |
| C2 | #4–#5 gate không kèm hậu quả | Mỗi gate hiện: duyệt thì agent nào chạy lại, từ chối thì ticket về đâu; hint người sắp gửi hiện nguyên văn | test HTML chứa hai câu hậu quả |
| C3 | #6 quyết định chưa áp | Cột "đang chờ áp dụng" kèm lượt đang chạy và đã chạy bao lâu | test: gate quyết định nhưng chưa có event xử lý → hiện badge |
| C4 | #7 blocked không gate = bế tắc | Cảnh báo đỏ riêng, đếm số, có ở đầu trang | test: ticket blocked, 0 gate → cảnh báo |
| C5 | #8 verdict trên bằng chứng bị cắt | Cạnh verdict hiện `context_trimmed` và file bị cắt | test |
| C6 | #9 hint máy vs hint người | Hiện cả `hint` và `human_hint`; chặn duyệt bằng chuỗi < 20 ký tự (đã có #80), thêm gợi ý mẫu root_cause/decision/hint | test |
| C7 | #10 blocked hai nghĩa | Cột "commit vượt integration" từ `git rev-list --count` | test với repo giả |
| C8 | gate_brief | Hồ sơ `gate_brief` cạnh nút duyệt, không cần CLI | test |
| C9 | studio | Màn "Xưởng video": thẻ video, lưới cảnh + narration, thumbnail A/B, SRT, deep-link từ gate `PUB-*` (studio C2) | test phục vụ `output/` chỉ đọc |
| C10 | bộ nhớ chỉ RAM | Console không giữ state ngoài sqlite của hai công ty; F5 không mất gì | test restart |

ADR-0003 (console) mô tả mô hình "sự thật giao hàng" mở rộng; C1–C10 chung một ADR.

### Đợt 4 — Studio ra video thật (Q2)

| Mã | Mục tiêu | Phạm vi | Nghiệm thu | ADR |
|---|---|---|---|---|
| S1 | Reviewer đa phương thức: `ModelClient.complete(attachments=[image])`, editor/quality-reviewer/rights-checker khai `inputs: [images]`, runner gắn ảnh cảnh ≤ 512 px; eval lưu hash ảnh | `llm.py`, `runner.py`, 3 agent | eval ghi lại bằng model thật cho 3 agent; test fake provider nhận attachments | ADR-0010 |
| S2 | QC lớp code thêm OCR chữ trong ảnh (tesseract nếu có), phát hiện khuôn mặt (opencv haar), whisper local so narration; thiếu phụ thuộc → finding `skipped` có lý do | `qc.py` | test với ảnh có chữ → finding block | mở rộng ADR-0009 |
| S3 | Thư viện nhạc có license: `music/LICENSES.yaml`, renderer chọn theo `mood`, ducking dưới giọng, provenance `licensed/cc-by`, seo-optimizer ghi công | `media.py`, `renderer.py`, seo-optimizer | ffmpeg thật: final có 2 track, loudnorm giữ -14 LUFS | ADR-0011 |
| S4 | `visual_kind: image | clip | chart`: clip từ Pexels/Pixabay (source_url + license vào provenance), chart do matplotlib vẽ từ claim đã fact-check | manifest schema, `media.py` | test mỗi loại; chart không đi qua ảnh AI | ADR-0012 |
| S5 | Tính tiền media: `pricing:` trong `media.yaml`, audit `render.*` ghi USD, supervisor ngưỡng 80/100, console hiện | `media.py`, supervisor, console | test: vượt 100% → gate escalation | — |
| S6 | Phụ đề karaoke từ timestamps từng từ (ElevenLabs/Gemini) khi provider hỗ trợ; fallback SRT theo câu | `media.py`, `renderer.py` | test | — |
| S7 | Chạy thật: một video tiếng Việt 3–5 phút, provider thật, qua 3 review + gate publish, đăng lên kênh thử | `docs/reports/2026-09-xx-video-that-dau-tien.md` | báo cáo ghi chi phí, lỗi, số vòng sửa cảnh; `output/` có final | — |

### Đợt 5 — Nền tảng (Q1, Q4)

| Mã | Mục tiêu | Phạm vi | Nghiệm thu | ADR |
|---|---|---|---|---|
| E1 | Tách máy trạng thái khỏi `orchestrator.py`: ba module `state/ticket.py`, `state/release.py`, `state/gate.py`, mỗi module một bảng chuyển trạng thái tường minh (from, event, guard, to) và một test bảng; orchestrator chỉ nối bus với bảng | `software-company/src/company/` | `orchestrator.py` < 900 dòng; test bảng liệt kê mọi cặp (state, event) kể cả cặp cấm; 4 khuôn lỗi TRAPS §1 có test tương ứng | ADR-0037 |
| E2 | Bus adapter Redis Streams giữ nguyên interface (kể cả `poll`), SQLite vẫn mặc định; `--workers` thành nhiều tiến trình | `bus.py` | test với fakeredis; chạy 2 tiến trình không giao trùng | ADR-0038 |
| E3 | Eval có răng: ghi lại 21 agent với model thật; CI so điểm với ngưỡng dao động đo được (memory: một lần đỏ chưa phải hồi quy → chạy 3 lần, lấy trung vị) | `evals/`, workflow CI | 21 recordings mới; CI đỏ khi trung vị tụt > ngưỡng | — |
| E4 | Gateway: 3 ADR (xoay vòng tài khoản, giữ cổng, ranh giới bảo mật), `TRAPS.md`/`CODEMAP.md` riêng như ba package kia | `gateway/docs/adr/` | `ls gateway/docs/adr` ≥ 3; bộ khung 4 file có đủ | ADR gateway 0001–0003 |
| E5 | Bảo vệ CHANGELOG và session log bằng CI: PR không có dòng CHANGELOG → `PR policy` đỏ; ngày có PR merge mà không có `docs/sessions/<ngày>.md` → cảnh báo | `.github/workflows` | test workflow bằng `act` hoặc PR thử | — |

## 5. Ước lượng và ưu tiên

| Đợt | Số mục | Ước lượng | Trả lời | Ưu tiên |
|---|---|---|---|---|
| 0 | 5 | ½ ngày | Q4 | ngay |
| 1 | 8 | 3–4 ngày | Q1 | P0 |
| 2 | 5 | 4–5 ngày | Q1 | P0 (D1) · P1 (D2–D5) |
| 3 | 10 | 3 ngày | Q3 | P1 |
| 4 | 7 | 4–5 ngày | Q2 | P1 (S1 S7) · P2 (còn lại) |
| 5 | 5 | 5 ngày | Q1 Q4 | P0 (E1) · P1 (E3 E4) · P2 (E2 E5) |

Tổng khoảng 20–22 ngày-phiên tuần tự, rút còn ~12 ngày lịch nếu ba phiên chạy song song đợt 2/3/4. Nếu chỉ làm
được một nửa: **đợt 0, đợt 1, D1, E1, S1, S7**. Đó là phần trả lời được Q1 và Q2 ở mức "có bằng chứng".

## 6. Rủi ro và cách gỡ

| Rủi ro | Dấu hiệu | Gỡ |
|---|---|---|
| Fix cùng họ tiếp tục thay vì E1 | PR `fix(company)` thứ 23+ về trạng thái/khoá/event cũ | Luật mục 2.2: PR fix phải link ADR-0037 hoặc thêm test bảng |
| Eval model thật tốn tiền, điểm dao động | recordings đỏ ngẫu nhiên | E3: chạy 3 lần lấy trung vị; ghi ngưỡng vào `evals/thresholds.yaml` |
| Deploy thật chạm máy trực | container chiếm cổng, REL cũ kẹt | D1: hai compose project tách cổng; lệnh dừng khẩn trong `TRUC-VA-DUNG-KHAN.md` mở rộng cho container |
| Ba phiên song song sửa chung `orchestrator.py` | xung đột PR | E1 làm trước khi tách phiên; đợt 2/3/4 chạm module khác nhau |
| Studio provider thật thiếu key | S7 không chạy được | S7 chấp nhận `command` TTS (Piper) + `gemini` ảnh; ghi rõ provider đã dùng trong báo cáo |

## 7. Cách thực thi một mục

1. Đọc mục, đọc ADR (hoặc viết ADR trước nếu cột ADR có mã mới).
2. `git worktree add ../Claude-Agents-wt-<mã> -b <type>/<mã-ngắn> main`.
3. Viết test đo hai chiều trước, rồi code; chạm agent/skill → 7 bước `CONTRIBUTING.md` §3.
4. PR tiêu đề `<type>(<scope>): <mã> — <một câu>`; bật auto-merge; xác nhận commit vào PR.
5. Thêm dòng `CHANGELOG.md`, cập nhật bảng theo dõi dưới đây, ghi `docs/sessions/<ngày>.md`.
6. Đợt xong → chạy thật (B8, S7, C1 với dữ liệu thật) → báo cáo trong `docs/reports/`.

## 8. Bảng theo dõi

| Mã | Trạng thái | PR | Ghi chú |
|---|---|---|---|
| V1–V5 | chưa | | |
| B1–B8 | B2 wip (ADR-0030 nhánh `feat/so-ruling-adr-0030`) | | |
| D1–D5 | chưa | | |
| C1–C10 | C6 một phần (#80), C1 một phần (#76) | | |
| S1–S7 | S2 một phần (ADR-0009) | | |
| E1–E5 | E4 xong | E4: #101 | E4: `gateway/docs/adr/0001–0003`, bộ khung 4 file dẫn `file:dòng` |

Cập nhật bảng này trong cùng PR của mục. Mục "xong" phải có số PR và, với B8/S7, đường dẫn báo cáo.
