# ADR-0040: Gộp `security` vào `qa` thành pha thứ ba; bốn agent công đoạn

Trạng thái: Chấp nhận · Ngày: 2026-09-13 · Sửa ADR-0037 (bất biến #2), ADR-0003 · Giữ nguyên ADR-0017, ADR-0028

> ADR này **lật một bất biến mà ADR-0037 tuyên bố là không được phá**. Lý do lật, cái mất, và cách bù đều ghi
> ở đây để lần sau ai muốn đưa `security` trở lại có đủ dữ kiện mà không phải đọc lại lịch sử chat.

## Bối cảnh

ADR-0037 gộp 21 agent xuống 5 và giữ lại đúng ba ranh giới vì *có cơ chế trong code cần vai này khác vai kia*:

1. test ≠ code (ADR-0028) — giữ nguyên, ADR này không đụng tới.
2. **review ≠ security** (ADR-0003) — `ReviewSource` tách `reviewer`/`security`, `RISK_REVIEWS` bắt buộc thêm
   review nhãn `security` khi ticket có `risk_tags`.
3. khách ký (ADR-0017) — giữ nguyên.

Chủ dự án yêu cầu giảm tiếp số vai với lý do vận hành: **nhiều cổng dễ tắc**. Ranh giới #2 là ranh giới duy nhất
còn gộp được mà không chạm hai ranh giới kia.

Cần phân biệt hai thứ mà ADR-0037 gộp làm một khi nói "ranh giới #2":

- **Ranh giới AGENT** — ai là tác nhân chạy lượt model. Đây là ranh giới prompt + tier, gộp được.
- **Ranh giới BẰNG CHỨNG** — `review-results` có một dòng `source="security"` riêng, và `required_reviews` đếm nó.
  Đây là ranh giới do code cưỡng chế, và nó **không cần agent riêng để tồn tại**.

ADR-0037 PR-5c đã lập chính xác tiền lệ này: `test-author` + `reviewer` + `qa-debugger` gộp thành một agent `qa`,
trong khi `SOURCE.REVIEWER` và `SOURCE.QA` vẫn sống như hai góc nhìn chấm riêng.

## Quyết định

### 1. Bốn agent công đoạn

| # | Agent | Gộp từ | Khối |
|---|---|---|---|
| 1 | `product` | (không đổi) | research |
| 2 | `builder` | (không đổi) | engineering |
| 3 | `qa` | `qa` + **`security`** | quality |
| 4 | `ops` | (không đổi) | operations |

`supervisor` vẫn không đếm (watchdog chạy bằng code). `agents/quality/security.md` biến mất, nội dung thành pha
`security` của `qa`; `ROLE.SECURITY` không còn, id cũ `security` vào `MIGRATED` trỏ về `"qa"`.

### 2. Ba pha của `qa`

| Pha | Lượt | Tool | Gộp từ |
|---|---|---|---|
| `author` | `tasks` → trước builder, lượt MÙ | `tests` (chỉ ghi `tests/`) | test-author |
| `review` | `pull-requests` → sau builder | `ro` | reviewer + qa-debugger |
| `security` | `approved-specs` (threat model), `pull-requests` khi có `risk_tags`, `release-candidates` | `ro` | security |

Bất biến #1 **không suy suyển**: pha `author` vẫn là lượt riêng, mù, tool chỉ ghi `tests/`, chạy trước `builder`.

### 3. Ranh giới BẰNG CHỨNG giữ nguyên, không nhân nhượng

- `SOURCE.SECURITY` **ở lại** trong `ReviewSource`. `review-results` của ticket rủi ro vẫn phải có một dòng
  `source="security"` riêng, phát ở một **lượt gọi model riêng** (pha `security`), khác lượt `review`.
- `RISK_REVIEWS = {SOURCE.SECURITY}` **giữ nguyên** — ticket có `risk_tags` vẫn chờ đủ hai dòng review.
- Namespace `threat-model` vẫn là namespace ghi bắt buộc, nay thuộc `qa`.
- `REVIEW_AGENT[SOURCE.SECURITY]` đổi từ `ROLE.SECURITY` sang `ROLE.QA` — **đây là toàn bộ thay đổi định tuyến**.

Nói cách khác: số **lượt gọi model** cho một ticket rủi ro KHÔNG giảm. Cái giảm là số **vai** người trực phải
hiểu và số file agent phải bảo trì.

### 4. Điều mất, nói rõ

- **Mất người chấm bảo mật độc lập với người chấm code.** Trước: `security` là một agent khác, prompt khác, tier
  khác, không thấy verdict của reviewer. Nay: cùng một agent `qa`, cùng một file prompt, chỉ khác pha và khác
  ngữ cảnh nạp. Một model hiểu sai threat model sẽ hiểu sai nhất quán ở cả pha `review` lẫn pha `security` — đúng
  lập luận mà ADR-0028 dùng để giữ test ≠ code, nay ta chấp nhận nó ở mặt security.
  **Bù bằng**: mục threat-model trong checklist pha `security` là *hard fail* — thiếu là gate đỏ, không phải nit.
  Không bù được phần "góc nhìn độc lập"; đây là mất thật, chấp nhận có ý thức.
- **`Phase` không có `model_tier` riêng** (`xagents_core.registry.Phase` chỉ mang `skills`/`skills_core`), nên
  `qa` phải nâng `model_tier` từ `standard` lên `strong` để pha `security` không tụt chất lượng. Hệ quả: **mọi**
  lượt `qa` (author, review) nay chạy tier `strong` → chi phí token mỗi ticket tăng. Đây là giá của việc gộp.
  Cách khác (thêm `model_tier` vào `Phase`) là đổi lõi `xagents-core`, để dành một ADR riêng nếu chi phí thành vấn đề.
- **`sc-security` biến mất** khỏi trợ lý kiểm duyệt; checklist gate `spec`/`release` trỏ `sc-qa` cho cả hai góc nhìn.

### 5. Khi nào đưa `security` trở lại

Bất kỳ điều nào sau đây xảy ra thì mở ADR đưa vai `security` về, không cần tranh luận lại từ đầu:

- Một lỗ hổng lọt tới production mà pha `security` đã chấm pass, và nguyên nhân gốc là "cùng model nên cùng điểm mù".
- Chi phí tier `strong` cho mọi lượt `qa` vượt phần tiết kiệm được từ việc bớt một agent.

## Hệ quả

- `tests/test_registry.py` khoá 5 file agent (4 công đoạn + supervisor); `test_roles.py` thêm `"security": "qa"`
  vào `MIGRATED`.
- `ROLE.SECURITY` bị xoá khỏi `roles.py`; `SOURCE.SECURITY` giữ. Chuỗi `"security"` ngoài `roles.py` bị cấm như
  mọi id đã gộp khác.
- `agents/quality/qa.md`: `version` tăng, thêm pha `security`, `reads` thêm `approved-specs`/`release-candidates`,
  `context_namespace_write: threat-model`, `model_tier: strong`. Đi đủ 7 bước `CONTRIBUTING.md` §3.
- `.claude/agents/sc-*`: 10 file → 9 (mất `sc-security`).
- Số lượt gọi model mỗi ticket: **không đổi**. Số vai: 5 → 4.
