# ADR-0011: Hợp nhất thành một công ty phần mềm duy nhất; cải tổ cấu trúc thư mục thành `platform/` + `companies/`

Trạng thái: Đề xuất · Ngày: 2026-09-10 · Giữ nguyên ADR-0001 (lõi chung), ADR-0006 (keeper) · Liên quan
`docs/KIEN-TRUC-4-LOP.md` §E

> ADR này quyết định **ranh giới thư mục, một entrypoint hợp nhất, và hai chế độ duyệt gate**. Cài đặt đi theo
> từng PR một scope sau khi ADR được chấp nhận; PR di chuyển thư mục **không đổi một dòng logic nào**.

## Bối cảnh

Repo (trước ADR này) có năm package phẳng ngang hàng ở gốc: `software-company/`, `keeper/`, `gateway/`,
`console/`, `xagents-core/`. Layout phẳng đó che mất một khác biệt có thật về vai trò:

- `xagents-core`, `gateway`, `console` là **hạ tầng dùng chung** — không thuộc công ty nào. `gateway` phục vụ
  bất kỳ `llm.yaml` nào trỏ tới nó; `console` đã có tab riêng cho cả `software-company` lẫn `keeper`.
- `software-company` và `keeper` là **công ty** — có agent, topic, human gate, khách hàng riêng.

Chủ dự án yêu cầu ba thứ: (1) một công ty phát triển phần mềm duy nhất, có agent lo phần quyết định duyệt;
(2) bộ máy agent của công ty đó; (3) nối model qua tài khoản subscription trước, API trả phí sau. Kèm theo:
**chạy một lệnh thì tất cả cùng chạy**, và cải tổ cấu trúc thư mục.

Rà lại thì (3) phần lớn đã có: `gateway` xoay pool tài khoản Google Antigravity, `llm.yaml` khai nhiều backend
theo thứ tự ưu tiên (`docs/DIEU-PHOI-MODEL.md` §1). Cái thiếu là thứ tự mặc định chưa được chốt thành tài liệu
cho công ty hợp nhất. Còn (1) va vào một nguyên tắc đã ghi cứng ở `ARCHITECTURE.md`: *"Gate là thật... lời khai
không là bằng chứng"*.

## Quyết định

### 1. `software-company` là công ty duy nhất trong phạm vi hợp nhất; `keeper` ở ngoài

`keeper` **giữ nguyên code, test và CLI**, vẫn tự chạy độc lập, vẫn có tab riêng ở console. Nó chỉ **không**
nằm trong entrypoint hợp nhất và **không** gộp registry/gate/topic với `software-company`. Lý do không xoá: 10
agent bảo trì đã có mã thật và test riêng (ADR-0006, BT1–BT7); xoá là mất, giữ thì không tốn gì ngoài một dòng
trong workspace members.

Lý do không gộp: hai công ty có `GateKind`, topic schema và vòng đời ticket khác nhau; gộp registry sẽ buộc một
trong hai đổi schema — chi phí lớn, không phục vụ yêu cầu nào của chủ dự án.

### 2. Cấu trúc thư mục: `platform/` + `companies/`

```
platform/     xagents-core/  gateway/  console/      # hạ tầng dùng chung, không thuộc công ty nào
companies/    software-company/  keeper/            # công ty, mỗi cái có agent + gate + khách riêng
```

Không di chuyển `gateway` hay `console` vào trong `software-company`: cả hai phục vụ nhiều hơn một công ty,
nhét vào trong một công ty là nói dối về ranh giới và phá quyền dùng chung của `keeper`.

`keeper` **có** di chuyển vào `companies/` — chỉ đổi đường dẫn cho nhất quán về đặt tên, không đụng nội dung.

PR thực hiện việc này là **PR thuần di chuyển**: `git mv` + sửa đường dẫn tham chiếu (workspace members, CI
`working-directory`, `Makefile`, `parents[N]` nào trỏ tới gốc repo, liên kết tài liệu). Không đổi logic. CI xanh
là bằng chứng đường dẫn đúng.

### 3. Một entrypoint: chạy một lệnh thì cả ba cùng chạy

Một lệnh ở gốc khởi động theo đúng thứ tự phụ thuộc, và một lệnh tắt cả ba:

```
gateway daemon start → chờ /health xanh → company orchestrator run --watch → console --allow-decide
```

Entrypoint chỉ **điều phối khởi động**, không đổi hành vi bên trong từng phần: nó gọi đúng các lệnh đã có
(`platform/gateway` daemon, `python -m company.orchestrator`, `python -m console`). `keeper` không nằm trong
chuỗi này. Gateway không lên được thì dừng lại và báo, không im lặng chạy tiếp với công ty không có model.

**Cài đặt (giai đoạn 2/5, đã xong):** console đã tự bật `orchestrator run --watch` từ trước qua `--allow-engine`
(ADR-0004 của console) — phần entrypoint hợp nhất còn thiếu duy nhất là gateway. Cờ mới `--with-gateway` gọi
`python -m gateway start` như tiến trình con TRƯỚC khi console phục vụ; `gateway start` đã idempotent và tự
chờ `/health` xanh, nên `start_gateway()` không dựng lại vòng chờ nào, chỉ tin mã thoát của nó — khác 0 thì
console dừng lại và báo, không phục vụ. Một lệnh: `python -m console --with-gateway --allow-decide --allow-engine`.

### 4. Duyệt gate: hai chế độ, cấu hình được, mặc định là người ký

Agent hồ sơ gate **luôn** soạn hồ sơ quyết định (`root_cause` + `decision` + `hint`, ≥ 20 ký tự — đúng chuẩn đã
dùng ở console) cho mọi gate. Từ đó hai chế độ:

| Bậc rủi ro | Hành vi | Ai ký |
|---|---|---|
| thấp, có luật cứng bằng code | tự động qua, ghi audit `verified_by=code` | code |
| trung / cao | dừng chờ người, hồ sơ chỉ để người đọc nhanh hơn | `human:<id>` |

Ba ràng buộc để chế độ tự động không thành cửa sau:

1. Bậc rủi ro do **code** xếp, không do model khai — cùng mẫu đã chạy ở keeper (`risk_tier`).
2. Mặc định tắt: không cấu hình thì mọi gate vẫn chờ người. Bật là một quyết định có chủ ý, ghi trong
   `HUONG-DAN-VAN-HANH.md`.
3. Agent hồ sơ **không bao giờ** ký. Nó chỉ đọc và soạn; chữ ký là của code (rủi ro thấp) hoặc của người.
   Điều này giữ nguyên nguyên tắc "lời khai không là bằng chứng": hồ sơ do model soạn không phải là căn cứ
   duyệt, nó chỉ là bản tóm tắt bằng chứng do code thu thập.

### 5. Subscription trước, API sau

Thứ tự backend mặc định trong `llm.example.yaml` của công ty hợp nhất:

```
claude-code (sub) → codex (sub) → gateway (sub Google Antigravity) → model local → API trả phí
```

Không đổi cơ chế (`routing.prefer` đã có), chỉ chốt thứ tự mặc định thành tài liệu.

**Cài đặt (giai đoạn 4/5, đã xong):** thứ tự khai báo mẫu trong `companies/software-company/llm.example.yaml`
đã đúng thứ tự trên từ trước (không cần đổi mã); phần thiếu là (1) chốt câu trên thành tài liệu tường minh ở
`docs/DIEU-PHOI-MODEL.md` §4 (mục "Thứ tự mặc định cho công ty hợp nhất") thay vì chỉ ngụ ý qua bảng tình huống,
và (2) ví dụ backend `provider: anthropic` (API trả phí) — trước đó không có ví dụ nào cho nhánh cuối cùng của
chuỗi, dễ khiến người đọc tưởng hub không hỗ trợ. Không đổi `RoutingClient`/cơ chế xoay.

## Hệ quả

- Mọi đường dẫn trong CI, `pyproject.toml` gốc, `Makefile`, `CODEMAP.md`, `ARCHITECTURE.md` và tài liệu đổi một
  lần. Đây là PR có sức công phá lớn nhất của loạt này, nên nó đi riêng và đi trước.
- `docs/adr/` gốc vẫn là nơi cho ADR cấp hub; ADR của từng package vẫn ở `<pkg>/docs/adr/`.
- Bốn PR tiếp theo, mỗi PR một scope: entrypoint hợp nhất · agent hồ sơ gate + bậc rủi ro · `llm.example.yaml` ·
  console một view.

## Cái ADR này KHÔNG quyết

- Không xoá `keeper`, không đổi hành vi của nó.
- Không đổi số agent, số gate hay vòng đời ticket của `software-company` (ADR-0037 giữ nguyên).
- Không đổi cơ chế xoay tài khoản của `gateway` (ADR-0001/0002/0003 của package đó giữ nguyên).
