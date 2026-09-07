# Hợp đồng nội bộ của `console` (không phải tài liệu người dùng)

File này là hợp đồng giữa ba lớp của gói `console`. Đọc trước khi sửa bất kỳ lớp nào.
Xoá file này khi console đã ổn định và hợp đồng chuyển hết vào docstring + test.

## Lớp

```
collect.py   đọc SQLite bus của hai công ty + trạng thái gateway  → dict thuần
truth.py     sự thật giao hàng của software-company: phễu release, quyết định chưa áp, bế tắc im lặng
decide.py    ghi quyết định gate thật qua HumanGate của từng công ty
server.py    ThreadingHTTPServer stdlib, phục vụ static/index.html + /api/*
static/      trang console (đã có thiết kế, chỉ cần nối dữ liệu)
```

Không dùng framework web. Chỉ `http.server`, `json`, `sqlite3` và hai gói `company`,
`studio` qua path dependency.

## `collect.py`

```python
def collect(company_db: Path | None, studio_db: Path | None,
            gateway_token_file: Path | None = None,
            gateway_url: str = "http://127.0.0.1:1123") -> dict
```

Trả về đúng cấu trúc dưới đây. Mọi khoá luôn có mặt; thiếu dữ liệu thì trả list rỗng
hoặc `None`, **không ném lỗi** — DB không tồn tại là trạng thái bình thường (chưa chạy
công ty đó bao giờ).

```jsonc
{
  "generated_at": "2026-09-03T08:41:12+07:00",
  "sources": {                       // để trang báo phần nào đang trống và vì sao
    "software-company": {"ok": true,  "db": "software-company/company.sqlite", "events": 238, "error": null,
                         "sandbox_available": true},   // K2.7: MÁY chạy console có docker/podman không
    "Studio-creators":  {"ok": false, "db": null, "events": 0, "error": "chưa có file DB",
                         "sandbox_available": true},
    "gateway":          {"ok": true,  "url": "http://127.0.0.1:1123", "error": null}
  },
  "tiles": {
    "events": 238, "queue": 12, "model_calls": 45, "tool_calls": 27,
    "tokens": 71500, "project_budget_tokens": 1200000,
    "rework_rate": 0.25, "review_catch_rate": 0.6,
    "prs_unverified": 0, "cost_today_usd": 3.41, "tokens_today": 412000,
    "stuck_tickets": 2,
    "project_cost_usd": 18.74, "project_budget_usd": 40.0,
    "unpriced_calls": 12, "calibration": 1.18
  },
  "gates": [{
    "id": "PUB-vid-042", "xuong": "Studio-creators", "kind": "publish",
    "by": "desk", "trigger": "human:owner", "hours": 26, "sev": "over",   // over|warn|calm
    "effect": "Duyệt = … (hậu quả của việc duyệt, theo kind; rỗng khi xưởng không nói)",
    "reject": "Từ chối = … (ticket/RC về đâu; rỗng khi xưởng không nói)",   // C2
    "agent":  "release-engineer",                                          // agent chạy lại sau khi duyệt; "" khi không biết
    "title": "…", "facts": [["video_id","vid-042"], …],
    "cl": [["review:fact:pass","mô tả ngắn lấy từ checklist/evidence"], …]
  }],
  "tickets": [{"id":"TCK-112","st":"in_review","who":"backend","t":"…",
               "used":82400,"out":9800,"bud":120000,"est":78000,"retry":0,   // used = tổng token; out = đầu ra (ngân sách so với out)
               "integrated":true,"sha":"b1b3e4b","human_hint":"","hint":"","gate":null,
               "ahead": 3,            // C7: commit của ticket/<id> CHƯA có trên nhánh tích hợp; null = không đo được ≠ 0 = đã gộp hết
               "pending_decision": {"id":"TCK-112","decision":"approve","by":"human:owner","kind":"escalation","minutes":14,"reason":"…"}
               }],                    // C3: chữ ký người đã ghi mà orchestrator chưa áp; null khi đã áp
  "prs":     [{"id":"TCK-112","br":"…","s":"…","lint":"pass","tests":"pass","v":"workspace"}],
  "reviews": [{"id":"TCK-112","src":"security","v":"block","f":"block · …","trim":"cắt api-contract 13.170 ký tự",
               "trim_src":[{"src":"api-contract","chars":13170},{"src":"payload","chars":804}],   // C5: từng nguồn bị cắt, hiện cạnh verdict
               "at":"04:07"}],
  "videos":  [{"id":"vid-039","st":"published","t":"…","fmt":"long","used":132000,"bud":150000}],
  "perf":    [{"id":"vid-039","imp":41200,"views":7840,"ctr":0.19,"avd":284}],
  "retention": {"video_id": "vid-039", "points": [[0,100],[15,88], …]},
  "cost_days": {"days":["21/8", …], "series":[[0.42,0.31,0.06], …]},  // [strong, standard, light]
  "agents":  [["backend", 4.82], …],                                   // giảm dần, tối đa 10
  "backends":[{"n":"claude-code","tiers":"strong · standard","tools":"có",
               "ok":true,"st":"Sẵn sàng","calls":128,"fail":2,"note":"…"}],
  "product_funnel": [{"project_id":"QLKH",           // C1: một phễu cho MỖI sản phẩm; [] khi không đọc được xưởng
    "delivered": false,                                // lên production VÀ đã nghiệm thu
    "stages": [{"stage":"request","label":"Yêu cầu khách","n":1,"empty":false,"smoke":""},
               {"stage":"staging","label":"Staging (smoke)","n":1,"empty":false,"smoke":"ok"},   // ok|fail|unverified|""
               …]}],                                   // `empty` (n===0) → trang tô XÁM, không bao giờ xanh
  "silent_deadlocks": [{"kind":"ticket","id":"QLKH-010","state":"blocked","why":"…","integrated":true}],  // C4
  // K2.7 (ADR-0035): lượt CHẠY MÃ CỦA KHÁCH trong 24h, đếm theo tên sandbox. Nguồn là bằng chứng do code điền
  // (`local_checks.sandbox`, `smoke.sandbox`, audit `tools_used`), KHÔNG phải cấu hình đọc lại lúc mở trang.
  // Trang chỉ cảnh báo khi `unsandboxed > 0` VÀ `sources.<công ty>.sandbox_available` — máy không có runtime
  // thì im. `null` khi xưởng không đọc được.
  "sandbox": {"window_h":24,"runs":12,"unsandboxed":9,"by_name":{"subprocess":9,"container:python:3.12-slim":3},
              "last_at":"2026-09-07T03:11:28+00:00"},
  "supervisor":[{"t":"TCK-118","a":"budget_cut","r":"…","w":"08:12"}],
  "log":     [{"t":"08:41","a":"backend","ac":"produced:pull-requests","k":"TCK-112","tok":8420,"c":0.21}],
  // ---- sự thật giao hàng của software-company (console/truth.py) — null/[] khi xưởng không đọc được ----
  "delivery": {
    "releases_total": 19, "releases_live": 14, "void": 5, "production": 0, "delivered": 0,
    "latest_tag": null, "latest_release": null, "integration_sha": "d16289b", "integrated_tickets": 18,
    "funnel": [{"stage":"void","label":"Bị huỷ","n":5,"ids":["REL-009", …]}, …],   // đủ 12 bậc, thứ tự đi tới
    "releases": [{"id":"REL-019","stage":"production_pending_human","label":"…","version":"0.11.1",
                  "tickets":["QLKH-012"],"sha":"964b704","gate":null,"at":"10:06","summary":"…","runbook":"…",
                  "next":"Agent tự dừng, KHÔNG gate nào mở: …"}]
  },
  "pending_decisions": [{"id":"REL-020","decision":"approve","by":"human:lead","kind":"escalation","minutes":12,"reason":"…"}],
  "running": {"queue": 7, "head": {"topic":"tasks","key":"TCK-…","minutes": 5}, "last_event_minutes": 1, "topics": ["tasks"]},
  "deadlocks": [{"kind":"ticket|release|idle","id":"QLKH-010","state":"blocked","why":"…","integrated":true}]
}
```

Nguồn của từng phần:

| Phần | Lấy từ |
|---|---|
| `tiles`, `agents`, `cost_days`, `supervisor` | `supervisor.sprint_report()` + quét `audit-log` |
| `gates` | `gate.request` chưa có `gate.decide` tương ứng, tính `hours` từ timestamp |
| `tickets` | `tasks` + `TicketState` suy ra như `orchestrator.status()` |
| `prs`, `reviews` | topic `pull-requests`, `review-results` |
| `videos`, `perf`, `retention` | `video-briefs`, `performance-snapshots` |
| `backends` | `routing.status()` nếu đọc được `llm.yaml`, nếu không thì gateway `/auth/status` |
| `log` | `audit-log`, mới nhất trước, tối đa 200 bản ghi |
| `delivery`, `pending_decisions`, `running`, `deadlocks` | `truth.py`: `release-candidates` + `release-events` + audit (`delivery.done`, `release.void`, `release.staged`, `integration.merged`, `orchestrated`, `gate.decide`) + `gate.pending/history` |
| `tickets[].integrated/sha/human_hint/hint/gate`, `reviews[].trim/at`, `gates[].effect` | `truth.py` — sự thật git (merge commit), hint agent đang cầm, ngữ cảnh bị cắt khi chấm, hậu quả khi duyệt |

`hours` làm tròn xuống. `sev`: `over` khi ≥ 24 giờ (quá hạn), `warn` khi ≥ 12 giờ
(đến hạn nhắc), còn lại `calm` — khớp `GATE_TIMEOUT_H` / `GATE_REMIND_H` của repo.

## `decide.py`

```python
def decide(company_db: Path | None, studio_db: Path | None, *,
           subject_id: str, xuong: str, decision: str, by: str, reason: str) -> dict
```

- `xuong` ∈ `{"software-company", "Studio-creators"}` chọn DB và lớp `HumanGate` tương ứng.
- `decision` phải nằm trong `Decision` của công ty đó; sai thì `ValueError`.
- Gọi đúng `HumanGate.decide(...)` của công ty, **không tự dựng event**, để four-eyes,
  allowlist người duyệt và ghi audit đi qua đúng đường của repo.
- Trả `{"ok": true, "subject_id": …, "decision": …, "event_id": …}` hoặc ném
  `GateError` với thông điệp tiếng Việt để server đổi thành HTTP 4xx.

## `submit.py`

```python
def submit(company_db: Path | None, studio_db: Path | None, *,
           xuong: str, topic: str, payload: dict, actor: str) -> dict
```

- Giao việc = publish một event do NGƯỜI tạo vào bus SQLite của xưởng. `FORMS` liệt kê topic nạp tay được
  và trường payload làm `key`: software-company `research-requests` / `clarification-answers` (key `project_id`),
  Studio-creators `channel-briefs` (key `channel_id`) — cùng quy ước với CLI `publish` của từng công ty.
- Đi qua đúng `SQLiteBus` + `Envelope` của công ty nên payload được kiểm theo `topics/schemas/<topic>.json`;
  bus từ chối → `SubmitError` (400) nguyên văn. Sai `xuong`/`topic`/`actor`/thiếu key → `ValueError` (400).
- File bus chưa có thì tạo (như CLI): yêu cầu đầu tiên của công ty chưa chạy lần nào là chuyện bình thường.
- Trả `{"ok": true, "xuong", "topic", "key", "event_id"}`.

## `server.py`

```
GET  /                  → static/index.html, chèn <script>window.__CONSOLE__={token,readonly,can_submit}</script>
GET  /static/*          → file tĩnh trong static/
GET  /sw.js             → static/sw.js — PHẢI ở gốc, service worker chỉ điều khiển được
                          những đường trong thư mục chứa nó, mà nó cần điều khiển "/"
GET  /manifest.webmanifest → static/manifest.webmanifest (application/manifest+json)
GET  /api/state         → collect(...)
GET  /api/stream        → SSE: `event: state` mỗi khi bus đổi, `event: error` khi collect() ném,
                          `: ping` giữ nhịp 15 giây. Không có Content-Length; đóng kết nối là hết thân bài.
GET  /api/gate/brief    → ?id=<subject>[&xuong=software-company][&closed=1]
                          {"ok":true,"subject_id","kind","md"} — Markdown y hệt `python -m company.gate_brief <subject>`;
                          {"ok":false,"subject_id","error"} khi không dựng được (200, không phải 5xx).
                          CHỈ ĐỌC: không cần --allow-decide — đọc bằng chứng phải rẻ hơn ký (ADR-0003 §7)
GET  /api/settings      → settings.read_settings(...) + {"can_edit": bool}
POST /api/settings      → body {company, models?, prefer?, enable?, disable?}  (cần --allow-config)
POST /api/gate/decide   → body {subject_id, xuong, decision, by, reason}      (cần --allow-decide)
POST /api/request       → body {xuong, topic, payload, actor}                 (cần --allow-submit)
                          giao việc: submit.submit(...) publish event vào bus của xưởng, chỉ nhận
                          topic do người nạp (`submit.FORMS`); payload kiểm theo schema của topic
GET  /healthz           → {"ok": true}
```

Bảo mật — bắt buộc, đây là bề mặt đầu tiên cho phép duyệt gate qua HTTP:

1. Chỉ bind loopback. `--host` khác `127.0.0.1`/`::1` thì **từ chối khởi động**, trừ khi
   có cờ `--i-know` kèm cảnh báo in ra.
2. Mọi `/api/*` yêu cầu header `X-Console-Token` khớp token phiên. Token sinh ngẫu nhiên
   bằng `secrets.token_urlsafe(32)` mỗi lần chạy, ghi `console/.console-token` quyền 0600,
   và chèn vào trang. Không có token hợp lệ → 401.
3. Chống DNS rebinding: từ chối request có `Host` không phải loopback (404), và từ chối
   `Origin` khác `http://127.0.0.1:<port>` (403). Token nằm ở header chứ không phải cookie
   nên trang ngoài không giả mạo được POST.
4. Ba quyền ghi TÁCH RIÊNG, không cái nào mở cái nào: `--allow-decide` cho `/api/gate/decide`,
   `--allow-config` cho `POST /api/settings`, `--allow-submit` cho `POST /api/request`. Duyệt gate,
   đổi model và giao việc mới là ba rủi ro khác nhau.
5. `--readonly` (mặc định **bật**) chặn mọi POST. Muốn duyệt gate từ trang thì chạy
   `--allow-decide`, và trang hiện rõ đang ở chế độ nào.
6. Không log token, không log body. Vì `log_message` ghi nguyên dòng request, token **không được**
   đi qua query string — đó là lý do trang đọc `/api/stream` bằng `fetch` + `ReadableStream`
   (đặt được header) chứ không phải `EventSource` (không đặt được).

Lỗi trả `{"error": "…"}` kèm mã HTTP đúng nghĩa: 400 sai tham số, 401 sai token,
403 bị chặn, 404 không có, 409 gate đã quyết rồi, 500 lỗi không lường trước.

## `settings.py`

```python
def read_settings(paths: dict[str, Path] | None = None, gateway_url: str = ...) -> dict
def update_settings(path: Path, *, models=None, prefer=None, enable=None, disable=None) -> dict
```

- **Mặc định = hiện trạng.** Không có bảng giá trị mặc định riêng: cái đang nằm trong `llm.yaml` là cái hiển thị.
- **Tắt backend phải tắt thật.** `company.llm.load_config` bỏ qua khoá lạ nên `enabled: false` vô tác dụng;
  tắt = chuyển phần tử sang `disabled_backends:` (loader không đọc), bật = chuyển ngược.
- `prefer` trỏ vào backend đang tắt bị bỏ, ghi rõ trong `changes` — để trống thì router chọn hụt.
- Validate xong mới ghi (đổi trọn hoặc không đổi gì); ghi nguyên tử, để lại `llm.yaml.bak`.
- `catalog` lấy từ `GET <gateway>/v1/models`; gateway tắt → rỗng và **không** cảnh báo tên model, vì backend
  `claude-code`/`codex` vốn không đi qua gateway.
- Không có file → `ok: false` kèm lý do, không ném lỗi.

## `static/index.html`

Một file, không framework, không bước build. Phần dữ liệu:

- Khi tải: hiện khung xám, rồi nối `GET /api/stream`.
- **Đẩy trước, hỏi sau.** Có stream thì trạng thái mới về trong khoảng một giây (nhãn *trực tiếp*).
  Stream đứt → lùi về `GET /api/state` mỗi 10 giây (nhãn *hỏi lại 10s*) và thử nối lại với backoff
  gấp đôi, trần 60 giây. Mất stream chỉ là chậm hơn, không phải hỏng.
- **Không vẽ đè dưới tay người đang đọc.** Ngăn kéo đang mở hoặc đã bấm Tạm dừng thì trạng thái mới
  được giữ lại và hiện nút *Có dữ liệu mới — xem*; bấm mới vẽ.
- Lỗi mạng hoặc 5xx: hiện dải cảnh báo trên cùng, giữ dữ liệu lần cuối đọc được.
- `sources[x].ok === false`: phần của xưởng đó hiện trạng thái rỗng có lý do, không hiện số 0 giả.
- Nút quyết định gate gọi `POST /api/gate/decide`; `readonly` thì nút bị khoá kèm giải thích
  cách bật `--allow-decide`.
- Khối **Giao việc** ở đầu màn của từng xưởng — KHÔNG gộp chung một màn: *Xưởng phần mềm* có form yêu cầu
  phần mềm (kèm nơi lưu dự án `repo`/`base`, ADR-0025 của công ty) và trả lời câu hỏi làm rõ; *Xưởng video*
  có form brief kênh. Ba form = ba topic trong `submit.FORMS`. Trang chỉ gom trường thành payload đúng hình
  schema (danh sách: mỗi dòng một mục; trả lời: `question_id: nội dung`), gọi `POST /api/request`;
  `can_submit` false thì nút khoá kèm cách bật `--allow-submit`. Gửi xong hiện key + event id.
- Không còn dữ liệu mẫu nào trong file.

Vỏ PWA — `manifest.webmanifest` + `sw.js`, để trang cài được thành app có cửa sổ riêng.
Service worker **không bao giờ** cache `/api/*` (dữ liệu sống; `/api/stream` là luồng không kết thúc,
cache là treo) và **không bao giờ** cache `/` (HTML mang token phiên, token đổi mỗi lần chạy server).
Chỉ icon được cache. Icon sinh lại bằng `uv run python tools/make_icons.py` (stdlib, không Pillow).

Điều hướng — địa chỉ là trạng thái:

```
#/<màn>                     truc-ban | phan-mem | video | chi-phi | nhat-ky | cai-dat
#/<màn>/gate/<id>           màn đó, ngăn kéo gate đang mở
#/<màn>/ticket/<id>         ngăn kéo ticket
#/<màn>/video/<id>          ngăn kéo video
```

Dùng hash chứ không `history.pushState`: server chỉ phục vụ một đường `/`, đẩy đường dẫn thật vào
thanh địa chỉ thì F5 ăn 404. Back đóng ngăn kéo thay vì rời trang; địa chỉ trỏ tới id không còn tồn
tại thì tự rút về màn tương ứng, không để thanh địa chỉ nói dối.

Lọc, tìm, sắp xếp — hoàn toàn phía client trên dữ liệu đã có, không thêm vòng gọi server nào:

- Ô tìm chung (phím `/`) lọc gate, ticket, video, PR, review, số liệu và audit-log cùng lúc.
  Gấp dấu tiếng Việt bằng NFD nên gõ `ong kinh` ra `Ống kính`; chỗ khớp được tô khi gõ có dấu.
- Bảng ticket và video có chip lọc theo trạng thái kèm số đếm; chọn một trạng thái thì thu về một cột.
- `<th data-k>` trong `<tr data-sort>` sắp xếp được, `data-t="n"` là cột số. Trạng thái sắp xếp nằm
  ở `aria-sort` nên đọc màn hình cũng biết.
- Phím tắt: `/` vào ô tìm, `1`–`6` nhảy màn, `g` về Trực ban, `Esc` xoá ô tìm hoặc đóng ngăn kéo.
