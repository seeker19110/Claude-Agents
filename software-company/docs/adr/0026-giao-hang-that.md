# ADR-0026: Giao hàng thật — tag phiên bản + nhánh `company/release` trong repo khách khi release production được duyệt

## Bối cảnh
Từ ADR-0011 tới ADR-0025, "làm code thật" dừng ở nhánh `company/integration`: ticket rẽ từ đó, merge `--no-ff` vào đó,
release-engineer nhận `integration_sha` rồi *mô phỏng* deploy staging/production, gate 3 được người duyệt, khách ký
nghiệm thu. Nhưng **không có thứ gì trong repo khách nói "đây là bản đã giao"**: không tag, không nhánh ổn định, và
`rollback` chỉ đổi trạng thái ticket. README ghi thẳng ở mục *Chưa có*: "Deploy thật: chưa đẩy `company/integration`
lên `main`/tag phiên bản". Vòng đời của công ty hiện kết thúc bằng một sự kiện trên bus, còn khách vẫn phải tự lần
theo sha trong `release-events` để biết mình nhận được gì.

Câu hỏi thiết kế là *giao ở đâu*. Đẩy thẳng vào `main` của khách là cách README từng hình dung, nhưng:

- `main` thường đang được checkout ở cây làm việc chính của khách; git từ chối cập nhật nhánh đang checkout từ một
  worktree khác, và làm được thì cũng là sửa cây làm việc của người khác sau lưng họ.
- Hook, CI và quy tắc bảo vệ nhánh của khách áp lên `main`. Orchestrator cố ý không chạy hook của khách (`NO_HOOKS`,
  ADR-0010); cho nó vượt qua các cổng đó là đi ngược nguyên tắc "`main` của khách không bị chạm" (ADR-0011).

## Quyết định
1. **Bật bằng cờ, mặc định tắt.** `orchestrator run --deliver` (hoặc `Orchestrator(deliver=True)`). Không bật thì hành vi
   y như trước — không có tag, không có nhánh mới.
2. **Giao khi production được duyệt và deploy.** Khi `release-events{env=production, status=deployed}` của một release mà
   gate `release` đã được người duyệt, orchestrator gọi `Integration.deliver(version, …)` trên repo của **dự án chứa
   release** (ADR-0025):
   - tag chú thích **`v<version>`** đặt tại sha hiện tại của `company/integration` (`version` là của RC, delivery-lead
     suy ra; model không ghi đè được — F9);
   - nhánh **`company/release`** (đổi bằng `--release-branch`) được **fast-forward** tới sha đó (tạo từ sha đó nếu chưa có).
   Idempotent: tag đã có đúng sha → không làm gì; tag đã có ở sha khác → audit `delivery.tag_conflict`, **không ghi đè**;
   `company/release` không fast-forward được (ai đó commit lên nó) → audit `delivery.diverged`, nhánh giữ nguyên, tag vẫn
   được tạo. Mọi kết quả ghi audit `delivery.done` (sha, tag, nhánh, sha trước, vấn đề, push).
3. **Rollback là lùi con trỏ, không rewrite lịch sử.** `release-events{env=production, status∈{rolled_back, failed}}` của
   một release đã giao → `company/release` trở về sha đã giao trước đó (xoá nhánh nếu đây là lần giao đầu); **tag giữ
   nguyên** — tag là lịch sử bất biến, `company/release` là "phiên bản đang chạy production". Audit `delivery.rolled_back`.
   Khách muốn bản tái lập được thì merge từ tag; muốn "bản mới nhất đang chạy" thì theo `company/release`.
4. **Push là tuỳ chọn và hướng ra ngoài.** `--push-remote <tên remote>`: sau khi giao, `git push <remote> company/release
   refs/tags/v<version>`; khi rollback, push `--force-with-lease=company/release:<sha đã giao>`. Push lỗi (mạng, quyền)
   → audit `delivery.push_failed` kèm stderr rút gọn, **không dừng** vòng đời — tag và nhánh cục bộ đã có, người push tay.
   Lệnh con vẫn chạy với env đã lọc bí mật (`clean_env`) nên thông tin đăng nhập phải nằm trong cấu hình git trên đĩa
   (credential helper, URL remote), không qua biến môi trường.
5. **`main`/`--base` của khách không bị chạm** — ADR-0011 giữ nguyên. Đưa `company/release` vào `main` là quy trình của
   khách (PR, CI, hook của họ chạy ở đó), không phải của orchestrator.
6. **Bền qua restart.** `Orchestrator.delivered` (release → sha/tag/sha trước) dựng lại từ `delivery.done` và
   `delivery.rolled_back` trong `audit-log`; `status()` có mục `delivery`. Mở lại bus không tag lại, không lùi lại lần hai.

## Hệ quả
- Khách nhận được **bản giao có tên** (`v0.1.1`) và một nhánh ổn định để kéo, ngay trong repo của họ; bằng chứng release
  trên bus truy ngược được về đúng commit.
- Không có history rewrite trên tag; `company/release` **có thể lùi** khi rollback — đây là con trỏ "đang chạy", được ghi
  rõ trong README để khách không coi nó là nhánh lịch sử.
- Vẫn chưa có deploy hạ tầng thật (container, k8s, CI/CD cho sản phẩm khách): release-engineer vẫn mô tả deploy; ADR này
  chỉ làm phần **git** của việc giao hàng thành thật. Phần hạ tầng là bậc sau.
- Tag trùng phiên bản (`delivery.tag_conflict`) hay nhánh release bị đụng tay (`delivery.diverged`) không tự sửa: chúng
  hiện trong audit và `status` để người xử lý — nhất quán với "hết ngưỡng thì escalate, không âm thầm đi tiếp".
