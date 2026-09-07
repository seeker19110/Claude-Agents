# ADR-0004: đối chiếu `neo4j-labs/agent-memory` — lấy tệp ngôn ngữ, quyết định `knowledge` là bộ sưu tập

Ngày: 2026-09-07 · Trạng thái: **được chấp nhận** (người dùng: "tốt hơn thì phải cập nhật") · Liên quan: ADR-0001
(K3.6), ADR-0003 (nghi thức tự kiểm)

## Bối cảnh

`neo4j-labs/agent-memory` là SDK bộ nhớ ba lớp cho agent (ngắn hạn: hội thoại; dài hạn: đồ thị thực thể; **suy
luận**: vết reasoning + tool call, "học từ quyết định cũ") trên Neo4j hoặc dịch vụ hosted NAMS. Cùng bộ lọc với
ADR-0003: **cơ chế nào có ích cho dự án này**, kiểm ngược với mã của ta trước khi kết luận thiếu.

Đo trên bản clone `--depth 50` tại `0186a93` (2026-09-05): 1.064 file theo git; **44.834 dòng Python `src/` và
45.906 dòng `tests/`** (tỷ lệ 1:1, 143 file test); `mypy strict = true` (`pyproject.toml:203`); ngưỡng coverage
**55 % dự án / 65 % patch** (`codecov.yml`); trạng thái tự khai "Experimental" (badge README). Đây là repo cùng
tầm kỷ luật với ta về kiểu tĩnh, lỏng hơn về coverage, và **bắt buộc một Neo4j** (bolt) hoặc một dịch vụ ngoài.

### Kiểm ngược ba điểm với mã của ta

**1. Vòng học từ kết quả cũ — ta đã có, và đã đóng vòng.** `orch/gates_flow.py::_record_lessons` ghi mỗi ticket
đóng một bài học (`estimate_tokens`, `actual_tokens`, `ratio`, `retry`, `risk_tags`, `hint`) lên namespace
`knowledge`; `supervisor.calibration()` lấy median `actual/estimate` theo assignee bằng replay bus, và
`orch/ticket_fsm.py:83` **đưa bảng đó vào payload planning của delivery-lead** — vòng học đóng ở đúng chỗ ước
lượng lần sau. `get_similar_traces` của họ (tìm vết theo embedding của task) không thêm gì cho vòng này.

**2. Nhưng `knowledge` mà agent *nhìn thấy* chỉ là một bản.** Blackboard giữ **bản mới nhất mỗi namespace**
(`blackboard.py::_latest`), và `knowledge` được ghi **mỗi ticket một version** với `content=None` — nên
`snapshot()` đưa vào prompt mọi agent đúng **một JSON của ticket đóng gần nhất**. Prompt `supervisor.md:28`
nói "bài học được runner đưa vào ngữ cảnh mọi agent qua blackboard" — về mặt chữ là đúng, về mặt ích lợi là một
dòng nhiễu trong mọi prompt. Bảng hiệu chỉnh (thứ có ích) đi đường riêng, không qua blackboard. Đây là chỗ mô
hình của agent-memory nói đúng một điều cấu trúc: **bộ nhớ tình tiết là một bộ sưu tập có truy vấn, không phải
một tài liệu có version.** Blackboard của ta là loại thứ hai — đúng cho `prd`/`architecture`, sai cho `knowledge`.

**3. `TraceOutcome.error_kind` (phân loại kết quả để lọc nhanh) — không có gì để phân loại.** Ta chỉ có **một**
đường mở lại ticket: `gates_flow.py:179` sau escalation, với lý do là văn bản người duyệt gõ (`hint`). Không có
nhiều loại nguyên nhân để đánh chỉ mục; thêm trường `error_kind` là thêm một cột luôn mang cùng một giá trị.

### Thứ đáng lấy nhất lại là một file 35 dòng

`CONTEXT.md` của họ: mục "Language" liệt kê thuật ngữ, nghĩa **ở repo này**, và một dòng `_Avoid_` — cách gọi
đã gây nhầm (ví dụ "NAMS Platinum", "Person, Organization, Location, Event + Object" — một đảo thứ tự "đã xuất
hiện trong một audit"). Nhật ký phiên của ta cùng ngày ghi **hai** lần nhầm do một chữ hai nghĩa: K1.x đánh số
khác nhau ở hai file đặc tả (`docs/sessions/2026-09-07.md:12`), và một bảng đối chiếu ghi tên hàm + cờ `legacy`
không tồn tại (`:201`). Ta có 9 file khung nhưng không file nào trả lời "chữ này ở đây nghĩa là gì, và đừng gọi
nó là gì".

## Quyết định

**1. Thêm `docs/NGON-NGU.md`** — file thứ 10 của bộ khung (`AGENTS.md` dòng 4): bảng *thuật ngữ · nghĩa ở repo
này · tránh*, 18 mục, mỗi mục "tránh" trỏ về một lần nhầm thật hoặc một luật đang có. Quy tắc thêm mục: có dòng
nhật ký phiên chỉ vào một lần nhầm — không thêm để cho đủ. **Làm trong PR này.**

**2. `knowledge` không phải một tài liệu có version — quyết định cho K3.6.** Khi blackboard vào `xagents_core`
(bước K3.6 của ADR-0001), `knowledge` tách khỏi cơ chế "bản mới nhất mỗi namespace":
- lưu trữ: vẫn là event `shared-context` trên bus (nguồn sự thật, replay được) — không đổi;
- đọc: `supervisor.lessons()` (mọi bài học) và `calibration()` là API đọc duy nhất; **`snapshot()` không còn
  đưa `knowledge` vào prompt**;
- chọn lọc cho prompt: runner nhận `lessons_for(ticket)` — bài học của ticket cùng `assignee` hoặc giao `risk_tags`,
  có `retry > 0` (tức có `hint` của người), **cắt ≤ 5 bản mới nhất**. Không embedding, không vector: khoá lọc là
  ba trường đã có trên `Task`.
Không làm trước K3.6 — blackboard đổi ở company rồi đổi lại khi vào core là làm hai lần (ADR-0001 §5). Khi làm
thì kèm sửa `supervisor.md:28` theo đủ bảy bước `CONTRIBUTING.md` §3; tới lúc đó, dòng ấy là một mục "việc để lại"
trong `docs/reports/2026-09-07-tu-kiem.md`.

### Đã kiểm và loại

| Cơ chế của agent-memory | Vì sao không lấy |
|---|---|
| Neo4j / đồ thị thực thể / POLE+O / trích xuất thực thể (spaCy, GLiNER, LLM) | Tri thức của ta là **artifact có chủ** (PRD, C4, OpenAPI) chứ không phải thực thể rời trích từ hội thoại. Thêm một cơ sở dữ liệu đồ thị là thêm một dịch vụ phải chạy, trái "self-hosted, resume được" bằng SQLite. |
| `get_similar_traces` (embedding của task) | Vòng học của ta đóng bằng `calibration()` theo assignee; lọc theo `assignee`/`risk_tags` (quyết định 2) đủ, không cần vector — cùng lý do ADR-0003 loại HNSW. |
| `TraceOutcome.error_kind` | Một đường mở lại duy nhất (`gates_flow.py:179`); nguyên nhân đã nằm trong `hint`. |
| Cạnh audit `:TOUCHED` (bước suy luận → thực thể) | Mỗi bản ghi blackboard đã mang `actor` trong `Envelope`; mọi lượt chạy đã có audit-log với `phase` (ADR-0037 PR-3). |
| `client.eval.run(suite)` | Đã có `evals/` + bản ghi + `evals all --replay --strict` trong CI. |
| Buffered writes, multi-tenant `user_identifier` | Bus SQLite ghi đồng bộ là chủ đích (khôi phục sau restart); phân vùng dự án đã có (ADR-0018). |
| TCK conformance đa ngôn ngữ, OpenWiki sinh tự động | Một ngôn ngữ, một SDK; wiki sinh máy là bản dẫn xuất nữa phải giữ đồng bộ. |

## Hệ quả

**Được.** Một file ngôn ngữ trả lời trước hai loại nhầm đã xảy ra; một quyết định thiết kế được chốt **trước** khi
K3.6 chạm tới blackboard, nên người làm K3.6 không phải mở lại câu hỏi. Sáu lời từ chối có địa chỉ.

**Mất.** Bộ khung thành 10 file; `docs/NGON-NGU.md` là chỗ mới có thể lệch với mã — nó thuộc phạm vi tự kiểm
(ADR-0003), mỗi mục có `file:dòng` để đo. Quyết định 2 làm K3.6 dày thêm một hàm `lessons_for` + test hai chiều.

**Rủi ro đã chặn.** Cám dỗ ở đây khác ADR-0003: không phải chép kiến trúc to, mà là chép **mô hình ba lớp bộ
nhớ** vì nó nghe đúng. Kiểm ngược cho thấy hai lớp ta đã có dưới tên khác (blackboard, bus) và lớp thứ ba
(`knowledge`) chỉ sai ở **cách đọc**, không thiếu ở cách lưu.

**Chưa làm.** Quyết định 2 chờ K3.6. ADR này không đổi một dòng mã nào.

## Liên quan

- `docs/adr/0001-loi-chung-xagents-core.md` §5 — thứ tự bước; K3.6 là nơi thực thi quyết định 2.
- `docs/adr/0003-doi-chieu-ruflo.md` — cùng phương pháp; `docs/NGON-NGU.md` nằm trong phạm vi tự kiểm.
- `software-company/src/company/blackboard.py::_latest`, `supervisor.py::lessons/calibration`,
  `orch/gates_flow.py::_record_lessons`, `orch/ticket_fsm.py:83` — bằng chứng cho §"Kiểm ngược".
- `docs/sessions/2026-09-07.md:12,201` — hai lần nhầm làm ra `docs/NGON-NGU.md`.
- Nguồn ngoài: `neo4j-labs/agent-memory` @`0186a93` — `CONTEXT.md`, `src/neo4j_agent_memory/memory/reasoning.py`,
  `schema/models.py::TraceOutcome`, `codecov.yml`, `pyproject.toml:203`.
