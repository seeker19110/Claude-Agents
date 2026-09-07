# console — luật riêng (bổ sung `../AGENTS.md`, không thay)

Package `console`. Trực ban hợp nhất tại `127.0.0.1:8200`: một trang HTML tĩnh + `http.server` thư viện chuẩn, đọc
bus SQLite của hai công ty **chỉ đọc**, duyệt gate qua đúng `HumanGate` của từng công ty, giao việc qua đúng bus +
schema. Không framework, không CDN, không phụ thuộc ngoài hai công ty.

## Chạy ở đâu

```bash
cd console
uv run pytest -q --cov && uv run ruff check src tests && uv run mypy src/console --ignore-missing-imports
uv run python -m console                          # chỉ đọc; terminal in địa chỉ kèm token phiên
uv run python -m console --allow-decide --allow-submit --allow-config
uv run python -m console models --company software-company --set antigravity.standard=<model>
```

**Bật console thì bật luôn `orchestrator run --watch` của công ty** — console chỉ hiển thị và publish; không có
orchestrator thì việc giao và quyết định nằm im trên bus.

## Ba điều không được phá

1. **Console không tự dựng event.** Quyết định đi qua `HumanGate` của công ty (four-eyes, allowlist, audit-log giữ
   nguyên); việc mới đi qua `SQLiteBus` của công ty và bị kiểm JSON Schema y như CLI `publish`.
2. **Chỉ đọc là mặc định**: không cờ `--allow-*` thì mọi POST 403 và nút khoá; token phiên sinh mới mỗi lần chạy;
   service worker **không** cache `/api/*` và `/` — số liệu cũ trên mặt kính trực ban là thứ tệ nhất.
3. **Mỗi ô trả lời một câu hỏi của người trực; ô không có dữ liệu là ô XÁM** (ADR-0003). Mỗi con số phải nói nó đo cái gì. Nhãn FSM (`merged`) tách khỏi sự thật git; `delivery` phải hiện "đã giao
   n/m"; xanh vì rỗng phải có cảnh báo. Xem `TRAPS.md` — 10 chỗ đã đánh lừa người trực một đêm.

## Sửa cái gì phải làm gì

| Sửa | Phải |
|---|---|
| đọc thêm dữ liệu từ bus | `src/console/collect.py`; hợp đồng trong `API.md`. Trường payload mới phải có trong `topics/schemas/` của công ty — `tests/test_hop_dong_schema.py` (K7.4) quét mã nguồn console và đỏ khi console đọc một trường không tồn tại, hoặc khi công ty đổi tên trường console đang đọc |
| phễu release / phễu sản phẩm, bế tắc im lặng, quyết định chưa áp | `src/console/truth.py` ("sự thật giao hàng", #76; ADR-0003) |
| cột "commit vượt integration" | `src/console/git_truth.py` — `git rev-list --count`, **không** `branch --contains` |
| hồ sơ bằng chứng cạnh nút duyệt | `src/console/brief.py` → `company.gate_brief`; route `GET /api/gate/brief` |
| quyết định gate | `src/console/decide.py` — gọi `HumanGate` công ty; lý do ≥ 20 ký tự |
| form giao việc | `src/console/submit.py` — payload theo schema topic của công ty |
| giao diện | `src/console/static/index.html` (HTML + CSS) và `static/js/*.js` (14 ES module, K7.1 — không build step). Thêm màn mới: HTML + một module + **nhập nó trong `main.js`** (không nhập = không bao giờ chạy, `tests/test_es_module.py` canh). Gán vào biến nhập từ module khác thì phải qua setter. Route hash `#/<màn>/gate/<id>`… trong `API.md` |
| đổi hợp đồng giữa lớp | `API.md` cùng PR |
| kiến trúc | `docs/adr/` (0001–0003) |
