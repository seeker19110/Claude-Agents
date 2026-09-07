# ADR-0037: Gộp 21 agent thành 8; hai human gate của công ty là `spec` và `release`

Trạng thái: Đề xuất · Ngày: 2026-09-07 · Sửa ADR-0003, ADR-0006, ADR-0009, ADR-0028 · Giữ nguyên ADR-0017, ADR-0021, ADR-0034

> ADR này chỉ quyết định **ranh giới vai và số gate**. Việc cài đặt đi theo checklist 7 bước `CONTRIBUTING.md` §3
> cho từng agent mới, trên PR riêng, sau khi ADR này được chấp nhận. Chưa có dòng code nào đổi cùng ADR.

## Bối cảnh

Công ty có 21 agent (`agents/`, khoá ở `tests/test_registry.py`) và 5 `GateKind` (`spec`, `plan`, `release`,
`acceptance`, `escalation`). Con số này là kết quả của bốn lần đổi liên tiếp: 18 → 22 (ADR-0003) → 20 (ADR-0009,
ADR-0006 gộp 4 vai nghiên cứu) → 21 (ADR-0028 thêm `test-author`). Mỗi lần tách đều có lý do, nhưng cộng lại thì một
ticket bình thường đi qua 8–9 lượt gọi model và người trực phải hiểu 21 vai để biết việc đang kẹt ở đâu.

Chủ dự án yêu cầu giảm xuống 8 agent và 2 gate. Rà lại từng vai theo một câu hỏi duy nhất — *có cơ chế nào trong
code cần vai này khác vai kia không?* — thì thấy phần lớn ranh giới hiện tại là ranh giới **prompt**, không phải
ranh giới **cưỡng chế**. Chỉ có ba ranh giới được code giữ:

1. **Người viết test ≠ người viết code** (ADR-0028; route riêng, tool riêng).
2. **Người review ≠ người làm security** (ADR-0003; `ReviewSource` tách `reviewer`/`security`, `required_reviews`
   thêm `security` khi có `risk_tags`).
3. **Người ký nghiệm thu là khách, không phải công ty** (ADR-0017; `HumanGate.decide` cưỡng chế
   `decided_by != created_by`).

Mọi ranh giới khác gộp được mà không mất bất biến nào.

## Quyết định

### 1. Tám agent

| # | Agent mới | Gộp từ | Khối | Namespace sở hữu |
|---|---|---|---|---|
| 1 | `product` | intake, clarifier, researcher, synthesizer, spec-writer, risk | research | `prd`, `glossary`, `design` |
| 2 | `planner` | delivery-lead (phần prompt), database, platform, data | engineering | `architecture`, `api-contract`, `schema`, `infra`, `analytics` |
| 3 | `builder` | backend, frontend, mobile | engineering | `api-contract` (đồng sở hữu với planner) |
| 4 | `test-author` | test-author | quality | — |
| 5 | `reviewer` | reviewer, qa-debugger | quality | — |
| 6 | `security` | security-engineer | quality | `threat-model` |
| 7 | `release` | release-engineer, support-docs | operations | `docs` |
| 8 | `account-manager` | account-manager | operations | `contract` |

`supervisor` **không đếm**: nó là watchdog chạy bằng code (timeout gate, review quá hạn, budget, escalate) và giữ
`knowledge`. Giữ nguyên, không phải một công đoạn.

Phần **code** của `delivery-lead` (`src/company/delivery.py`: lập lịch theo `depends_on`/`priority`, chờ đủ review theo
`risk_tags`, tạo release, xin gate, mở lại ticket khi rollback) **ở lại orchestrator**, không thuộc agent nào. Chỉ
phần prompt (kiến trúc C4, ADR, chia ticket) đi vào `planner`. Đây là lý do không gọi vai này là "architect": tên đó
sẽ khiến người sau đi tìm phần lập lịch trong prompt và không thấy (bài học ADR-0009).

### 2. Vì sao dừng ở 8, không ít hơn

- `test-author` không gộp vào `builder`: ADR-0028. Có thể gộp vào `reviewer` (cùng agent, hai route, route viết test
  chỉ ghi `tests/` và chạy trước builder) — để dành cho ADR sau nếu cần xuống 7, không làm ở đây.
- `security` không gộp vào `reviewer`: ADR-0003. Scan (SAST/SCA/DAST) là tool nên độc lập bằng máy; threat model là
  lời khai nên độc lập bằng vai.
- `account-manager` không gộp vào `product`: product *tạo* spec, account-manager tổ chức UAT để khách *ký* spec đó.
  Gộp là cùng một tác nhân soạn tiêu chí và soạn kịch bản chấm tiêu chí.
- `planner` không gộp vào `product`: planner ghi `schema`, `infra` — hai namespace mà code hạ tầng đọc trực tiếp;
  product không có tool để kiểm chứng những gì nó viết ở đó.

### 3. Luồng một ticket

```
tasks → test-author (ghi tests/ từ Gherkin)
      → builder     (ghi code cho xanh; nạp skill theo `stack` của ticket)
      → reviewer    (diff + chạy test + scan tự động)
      → security    (chỉ khi ticket có `risk_tags` — ADR-0021 giữ nguyên)
      → release     (gộp vào RC, staging, xin Gate 2)
```

Năm lượt gọi tối đa, ba lượt cho ticket không có `risk_tags`. `BASE_REVIEWS = {reviewer}` và `required_reviews`
không đổi; `ReviewSource` giữ ba giá trị `reviewer`/`qa`/`security` — `qa` nay do `reviewer` phát khi hồi quy staging
(`ticket_id = release_id`, ADR-0006 mục 3).

### 4. Hai human gate của công ty

| Gate | Kind | Mở khi | Người ký |
|---|---|---|---|
| Gate 1 — Spec | `spec` | product publish PRD đủ `prd`, `acceptance-criteria`, `ux-flow`, `risks`, `runtime` (ADR-0031) | người trực |
| Gate 2 — Release | `release` | reviewer `qa` pass trên staging (+ `security` pass nếu có `risk_tags`), smoke `ok` (ADR-0029/0036) | người trực ≠ người tạo release |

**Bỏ `GateKind` `plan`.** Các khoá của nó chuyển thành điều kiện chặn bằng code, không xin người:

- `tickets` ≤ 1 ngày / ≤ 200k token, `estimate_tokens`, `budget_tokens ≥ estimate × 1.5`, `risk_tags`, `depends_on`
  không vòng → `_check_plan` (`orch/ticket_fsm.py`) đã chặn một phần; ADR này yêu cầu chặn **hết**, plan có
  `problems` bị trả về `planner` với lý do, không có đường xin người duyệt.
- `threat-model` (High/Critical có mitigation) và `architecture` (C4 L1–L2) → dời thành điều kiện mở Gate 2 và mục
  "người tự kiểm thêm" của Gate 2 trong `gates/checklists.md`; `security` vẫn viết threat model **trước** ticket đầu
  (route `plans → security` giữ nguyên), chỉ không còn người ký riêng cho nó.
- Điều kiện `gate.is_approved(plan_id)` ở `delivery.py:115` đổi thành kiểm `_check_plan` không có `problems`.

Hai `GateKind` còn lại **không phải gate công đoạn** và giữ nguyên:

- `acceptance` — chữ ký của **khách**, không phải công ty duyệt. Bỏ nó là quay lại đúng lỗi ADR-0017 sửa (UAT không
  hạn, không nhắc, không ai ký). Về mặt tài liệu, gọi đây là "nghiệm thu", không gọi là "Gate 3".
- `escalation` — kênh ngoại lệ khi timeout 24h, review quá 2h, vượt budget, smoke `unverified` (ADR-0036). Không có
  nó thì quá hạn là im lặng.

`GateKind` sau ADR: `spec`, `release`, `acceptance`, `escalation`.

### 5. Ngữ cảnh theo pha, không theo vai

`product` và `planner` gánh nhiều vai cũ nhất. Không nạp toàn bộ skill của các vai cũ vào một prompt — `assetbudget`
sẽ đỏ và chất lượng từng pha loãng. Thay vào đó front matter agent khai `phases:` và runner nạp skill theo pha của
lượt gọi hiện tại (mở rộng ADR-0008 tiering và ADR-0020 context-by-role):

- `product`: `intake` (nhận yêu cầu, câu hỏi cho người) · `research` (4 mục domain/ux/codebase/tech) · `spec` (PRD,
  Gherkin, risk).
- `planner`: `architecture` · `schema` · `infra` · `plan` (chia ticket, estimate).
- `builder`: theo `stack` của ticket (ADR-0013 đã có per-stack checks).

Route theo topic giữ nguyên hình dạng; chỉ đổi đích: `research-requests → product`, `plans → planner`,
`tasks → test-author` rồi `builder`, v.v.

## Hệ quả

- `tests/test_registry.py` khoá 8 thay vì 21. `Assignee` thu về `{"builder", "planner"}`; `NAMESPACE_OWNERS` ánh xạ
  theo bảng §1. `GateKind` bỏ `plan`; `gates/checklists.md` còn Gate 1, Gate 2, mục Nghiệm thu, mục Gate bất thường;
  `gate_checklists.py` khai lại nguồn bằng chứng cho mục dời từ plan sang release.
- 21 thư mục `agents/<khối>/<id>.md` thay bằng 8; mỗi agent mới đi đủ 7 bước (`version`, `make golden`,
  `make eval-record` bằng model thật, `assetscan`, `assetbudget`, `make subagents`). `.claude/agents/sc-*` sinh lại:
  8 agent + 2 gate = 10 file, không còn 26.
- `make assetbudget` cần ngưỡng theo **pha**, không theo agent, nếu không `product` chắc chắn vượt.
- ADR-0003 (tách security/platform/data), ADR-0006 (gộp research, thêm account-manager), ADR-0009 (không tách ux),
  ADR-0028 (test-author) đọc kèm ADR này: bất biến của chúng còn nguyên, ranh giới vai thì đổi. ADR-0021 (review lean)
  và ADR-0034 (tách máy trạng thái) không đổi.
- Mất một điểm con người nhìn plan **trước** khi tiêu token cho code. Bù bằng `_check_plan` chặn hết bằng code và
  `sprint_report` (estimate vs actual) để nhìn lại sau. Nếu sau ba dự án thấy rework do plan sai vượt chi phí một
  gate, mở ADR mới đưa `plan` về — không âm thầm thêm lại.
- Chi phí thật giảm ở hai chỗ, không phải ở số agent: số lượt gọi mỗi ticket (8–9 → 3–5) và `model_tier`
  (`strong` chỉ cho `product`, `planner`, `security`; còn lại `standard`).

## Thứ tự cài đặt (PR riêng, mỗi PR một scope)

1. `fix(company)`: `_check_plan` chặn hết khoá của gate plan; test hai chiều.
2. `refactor(company)`: bỏ `GateKind` `plan`, `delivery.py:115` đổi điều kiện; `gates/checklists.md`; `make subagents`.
3. `feat(company)`: front matter `phases:` + runner nạp skill theo pha; `assetbudget` theo pha.
4. `refactor(company)` ×8: mỗi agent mới một PR, đủ 7 bước; agent cũ xoá trong cùng PR với agent thay nó.
5. `docs`: `ARCHITECTURE.md`, `CODEMAP.md`, `docs/HUONG-DAN-VAN-HANH.md`, `CHANGELOG.md`.

Không gộp bước 4 thành một PR: 21 bộ golden + recording đổi cùng lúc thì không review được.
