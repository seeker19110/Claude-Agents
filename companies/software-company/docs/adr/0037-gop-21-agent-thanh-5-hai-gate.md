# ADR-0037: Gộp 21 agent thành 5; hai human gate của công ty là `spec` và `release`

Trạng thái: Đề xuất · Ngày: 2026-09-07 · Sửa ADR-0003, ADR-0006, ADR-0009, ADR-0021, ADR-0028 · Giữ nguyên ADR-0017, ADR-0034
· Đặc tả triển khai: `docs/DAC-TA-TRIEN-KHAI-ADR-0037.md`

> ADR này chỉ quyết định **ranh giới vai và số gate**. Cài đặt đi theo đặc tả kèm, mỗi PR một scope, sau khi ADR
> được chấp nhận. Chưa có dòng code nào đổi cùng ADR.

## Bối cảnh

Công ty có 21 agent (`agents/`, khoá ở `tests/test_registry.py`) và 5 `GateKind` (`spec`, `plan`, `release`,
`acceptance`, `escalation`), kết quả của bốn lần đổi liên tiếp: 18 → 22 (ADR-0003) → 20 (ADR-0006, ADR-0009) → 21
(ADR-0028). Mỗi lần tách có lý do, nhưng cộng lại một ticket bình thường đi qua 8–9 lượt gọi model, người trực phải
hiểu 21 vai, và id agent nằm rải trong 31 file mã nguồn (179 chỗ).

Chủ dự án yêu cầu 5 agent, 2 gate. Rà từng vai theo một câu hỏi — *có cơ chế nào trong code cần vai này khác vai
kia không?* — thì chỉ ba ranh giới được code giữ:

1. **Người viết test ≠ người viết code** (ADR-0028; route `tools="tests"` chỉ ghi `tests/`, chạy trước code).
2. **Người review ≠ người làm security** (ADR-0003; `ReviewSource` tách `reviewer`/`security`; `required_reviews`
   thêm `security` khi có `risk_tags`).
3. **Người ký nghiệm thu là khách** (ADR-0017; `HumanGate.decide` cưỡng chế `decided_by != created_by`).

Mọi ranh giới khác là ranh giới prompt, gộp được.

## Quyết định

### 1. Năm agent

| # | Agent | Gộp từ | Khối | Namespace sở hữu |
|---|---|---|---|---|
| 1 | `product` | intake, clarifier, researcher, synthesizer, spec-writer, risk, delivery-lead (phần prompt) | research | `prd`, `glossary`, `design`, `architecture`, `api-contract` |
| 2 | `builder` | backend, frontend, mobile, database, platform, data | engineering | `api-contract` (đồng sở hữu), `schema`, `infra`, `analytics` |
| 3 | `qa` | test-author, reviewer, qa-debugger | quality | — |
| 4 | `security` | security-engineer | quality | `threat-model` |
| 5 | `ops` | release-engineer, support-docs, account-manager | operations | `docs`, `contract` |

`supervisor` **không đếm**: watchdog chạy bằng code (timeout gate, review quá hạn, budget, escalate), giữ
`knowledge`. Giữ nguyên.

Phần **code** của delivery-lead (`src/company/delivery.py`: lập lịch theo `depends_on`/`priority`, chờ đủ review, tạo
release, xin gate, mở lại ticket khi rollback) **ở lại orchestrator**, không thuộc agent nào; event nó phát giữ
`actor="delivery-lead"` như một *actor của code* (cùng hàng với `orchestrator`, `supervisor`, `human:*`). Chỉ phần
prompt (C4, ADR, chia ticket, estimate) đi vào `product`.

### 2. Bất biến được giữ và cách giữ

- **Bất biến 1 (test ≠ code)**: `qa` có **hai route** trên hai topic khác nhau với hai bộ tool khác nhau:
  `tasks → qa` (`tools="tests"`, chỉ ghi `tests/`, lượt MÙ, `BLIND_STRIP` như cũ) chạy **trước** `builder`;
  `pull-requests → qa` (`tools="ro"`) chạy **sau**. Cùng tên agent, khác lượt gọi, khác tool, khác ngữ cảnh — cái
  ADR-0028 cần là *tác nhân sinh test không nhìn code*, và lượt viết test vẫn không nhìn code.
- **Bất biến 2 (review ≠ security)**: `security` giữ riêng, tier `strong`, threat model trước ticket đầu như cũ.
- **Bất biến 3 (khách ký)**: `ops` tạo gate `acceptance` (thay account-manager) → `decided_by != created_by` vẫn
  cưỡng chế khách ≠ công ty.

### 3. Điều mất, nói rõ

- **ADR-0021 một nửa**: `qa-debugger` không còn là lượt riêng ở PR cho ticket có `risk_tags`; `RISK_REVIEWS` thu về
  `{security}`. `qa` ở lượt PR nay chấm cả diff lẫn test và nhận thêm `chan_doan` (lịch sử hỏng của ticket). Nguồn
  `qa` trong `ReviewSource` **vẫn tồn tại** — phát khi `qa` hồi quy trên staging (`ticket_id = release_id`).
- **Người viết spec và người tổ chức UAT**: vẫn khác (`product` ≠ `ops`) — không mất.
- **Chủ namespace `architecture`/`api-contract` là product, không phải kỹ sư**: builder đồng sở hữu `api-contract`
  để cập nhật contract khi cài; `architecture` chỉ product ghi. Đây là đổi chủ, không mất chủ.

### 4. Hai human gate của công ty

| Gate | Kind | Mở khi | Người ký |
|---|---|---|---|
| Gate 1 — Spec | `spec` | product publish PRD đủ `prd`, `acceptance-criteria`, `ux-flow`, `risks`, `runtime` (ADR-0031) | người trực |
| Gate 2 — Release | `release` | `qa` pass trên staging (+ `security` pass nếu có `risk_tags`), smoke `ok` (ADR-0029/0036) | người trực ≠ người tạo release |

**Bỏ `GateKind` `plan`.** Khoá của nó thành điều kiện chặn bằng code (`_check_plan`), plan hợp lệ dispatch thẳng;
`threat-model` và `architecture` dời thành điều kiện mở Gate 2. Chi tiết ở đặc tả §3.

Giữ nguyên, không đếm là gate công đoạn: `acceptance` (chữ ký khách, ADR-0017) và `escalation` (kênh ngoại lệ).
`GateKind` sau ADR: `spec`, `release`, `acceptance`, `escalation`.

### 5. Ngữ cảnh theo pha

`product` gánh 7 vai cũ, `builder` 6. Không nạp toàn bộ skill vào một prompt. Front matter khai `phases:`, route khai
`phase=`, runner nạp đúng skill của pha (mở rộng ADR-0008, ADR-0020). `assetbudget` đo theo pha.

## Hệ quả

- `test_registry.py` khoá 5. `Assignee` = `{"builder"}`. `NAMESPACE_OWNERS` theo bảng §1. `GateKind` bỏ `plan`.
- 21 file `agents/` → 5; mỗi agent mới đi đủ 7 bước `CONTRIBUTING.md` §3. `.claude/agents/sc-*`: 5 + 2 = 7 file.
- Mỗi ticket: 3 lượt gọi (qa-test → builder → qa-review), 4 khi có `risk_tags` (+security), 5 khi vào RC (+ops
  staging, qa hồi quy). Trước: 8–9.
- Mất điểm người nhìn plan trước khi tiêu token. Bù bằng `_check_plan` chặn hết và `sprint_report`. Sau ba dự án nếu
  rework do plan sai vượt chi phí một gate → ADR mới đưa `plan` về.
