# Đối chiếu `superpowers` và các skill thiết kế web với quy trình công ty

Ngày 2026-09-06. Câu hỏi: các plugin/skill đang phổ biến (`superpowers`, `frontend-design`, `hyperframes`,
`caveman`, `skill-creator`…) có giúp gì cho `software-company/` không, và có nên cài không.

Kết luận ngắn: **không cài cái nào**. Nhưng `superpowers` chỉ ra đúng một lỗ hổng thật của công ty, và lỗ hổng
đó trùng với đề xuất 3 và 6 trong báo cáo `2026-09-06-ban-giao-khong-chay-duoc.md`.

## 1. superpowers có gì

14 skill, chia bốn nhóm: testing (TDD), debugging (systematic-debugging, verification-before-completion),
collaboration (brainstorming, writing/executing-plans, dispatching-parallel-agents, requesting/receiving-code-review,
git worktrees, finishing-a-branch, subagent-driven-development), meta (writing-skills, using-superpowers).

Đối chiếu với 43 skill trong `software-company/skills/`:

| superpowers | công ty đã có | ai sâu hơn |
|---|---|---|
| test-driven-development | `testing.md` + agent `test-author` viết test trước khi có code (ADR-0028) | **công ty** — tách hẳn thành một vai, không dựa vào tự giác của người viết code |
| systematic-debugging (4 phase) | `debugging.md` — Zeller, delta debugging, bisect, five whys, timebox | **công ty** |
| requesting/receiving-code-review | agent `reviewer` + `security-engineer` tách vai (separation of duties) | **công ty** |
| writing-plans / executing-plans | gate `plan`, `delivery-lead`, blackboard | **công ty** |
| dispatching-parallel-agents | orchestrator + hàng đợi event | **công ty** |
| using-git-worktrees, finishing-a-branch | quy ước branch/PR sẵn có | hoà |
| writing-skills | `prompt-engineering.md` + quy ước prompt-là-code (ADR-0004) | **công ty** |
| **verification-before-completion** | *(không có tương đương)* | **superpowers** |
| **"Rulings, not stalls"** (trong subagent-driven-development) | *(không có tương đương)* | **superpowers** |

Nói cách khác: 12/14 skill là tập con của những gì công ty đã viết, và bản của công ty có tiêu chuẩn tham chiếu,
checklist chấm gate, ví dụ tốt/xấu — thứ superpowers không có. Chiều ngược lại thì công ty có 43 skill mà
superpowers không chạm tới: threat model, contract testing, accessibility, finops, privacy, incident, i18n…

## 2. Hai thứ superpowers có mà công ty không có

### 2.1 Verification-before-completion — kiểm chứng ở tầng câu nói, không phải ở tầng gate

Luật của nó: *"nếu bạn chưa chạy lệnh kiểm chứng trong chính message này, bạn không được nói là nó pass"*, kèm
bảng "claim nào cần bằng chứng nào" — trong đó có đúng hai dòng mô tả sự cố của công ty:

- *Bug fixed* → phải chạy lại triệu chứng gốc; **không đủ**: "đã sửa code nên chắc là xong".
- *Agent completed* → phải xem diff của VCS; **không đủ**: agent tự báo "success".

Công ty kiểm chứng ở tầng gate: agent khai → checklist → người ký. Nhưng lời khai của agent không bị buộc phải
kèm bằng chứng máy chạy, nên `status=deployed` của release-engineer và verdict `regression-staging` của QA đi qua
được bốn gate mà không có một tiến trình nào từng khởi động. Đó chính là "deploy là lời khai".

Việc cần làm không phải là cài superpowers, mà là **nâng nguyên tắc `local_checks` của PR lên thành luật chung
cho mọi trạng thái tự khai**: mọi trường `status` mang nghĩa "đã chạy được" chỉ hợp lệ khi payload có
`evidence` do orchestrator tự sinh (lệnh, mã thoát, mã HTTP), không phải do model điền. Trùng đề xuất 3 và 6.

### 2.2 "Rulings, not stalls" — kế hoạch đang chạy thì không đợi người

Nguyên văn cơ chế: khi gặp mâu thuẫn, chỗ mơ hồ, hoặc kế hoạch có khiếm khuyết, agent **tự quyết** và ghi vào sổ
một dòng `Ruling: <quyết định> — <vì sao> — <sai thì mất gì>`. Chỉ bốn thứ được phép dừng lại hỏi người: thao tác
không đảo ngược được, thao tác nhạy cảm về bảo mật, tác động ra ngoài phạm vi làm việc (merge/push/publish), và
kế hoạch hỏng tới mức mọi hướng đều là đoán.

Công ty đang ngược lại: mọi chỗ bí đều thành `pending_human`. REL-019 kẹt ở `production/pending_human` vì
release-engineer tự từ chối deploy mà không gate nào mở ra — không ai quyết, không ai ghi vì sao. Bốn loại
"được phép dừng" ở trên gần trùng với bốn human gate hiện có; phần thiếu là **sổ ruling cho mọi thứ ngoài bốn
loại đó**, để agent tự quyết mà vẫn để lại vết cho người soát.

## 3. `frontend-design` và `hyperframes` có giúp agent thiết kế web không

**Không.** Và đây là chỗ dễ nhầm nhất, nên nói kỹ.

Công ty đã có `ui-ux-design.md` (98 dòng, v6), `frontend.md` (80 dòng, v3), `accessibility.md` (69 dòng). Phần
`sources:` của `ui-ux-design` cho thấy nó đã hấp thụ sẵn bốn skill cùng loại (ui-ux-pro-max, ui-ux-craftsman,
impeccable, hallmark). Nội dung đang có vượt xa một skill thiết kế thông thường:

- vân tay cấu trúc sáu trục, bắt hai màn khác mục đích phải khác ít nhất hai trục — chống rập khuôn
  hero → 3 cột → CTA → footer;
- 5 trạng thái mức màn hình + 8 trạng thái mức component, có trang demo soi bằng mắt;
- khoá token: mọi màu/font phải trỏ về token có tên, đổi nền thì đổi màu chữ trong cùng rule;
- danh mục anti-pattern "mùi máy sinh": cấm `transition: all`, cấm animate `width/height/top/left`, cấm vẽ lại
  khung trình duyệt bằng HTML, cấm emoji làm icon, cấm bịa số liệu để lấp bố cục;
- ngân sách hiệu năng kiểm trong CI, tự chấm 6 trục trước khi giao.

Cài thêm một skill thiết kế nữa chỉ tạo hai nguồn chỉ dẫn cho cùng một việc, và nguồn mới thì mỏng hơn.

`hyperframes` (viết HTML rồi render ra video) là công cụ sản xuất nội dung, không phải công cụ thiết kế sản
phẩm — không nằm trên đường đi của bất kỳ ticket nào trong công ty.

### Lỗ hổng thật của mảng thiết kế web

Không phải thiếu kiến thức, mà là **agent không nhìn thấy thứ nó vừa dựng**. `frontend.md` yêu cầu "kiểm ở 375px,
dark mode, cỡ chữ lớn, reduced-motion" và "trang demo 8 trạng thái để soi bằng mắt" — nhưng không có bước nào
buộc phải thực sự mở trình duyệt, chụp màn hình, đính vào `evidence`. Nên nó rơi vào đúng khuôn lỗi ở mục 2.1:
một lời khai đã kiểm.

Đề xuất (cùng hình dạng với đề xuất 3): **DoD của frontend thêm một dòng — dựng thật, chụp ở 375/768/1440 và
dark mode, đính ảnh vào `evidence` của ticket**; thiếu ảnh thì `reviewer` `request_changes`. Việc này dùng hạ
tầng sẵn có (browser pane), không cần cài gì.

## 4. Các mục còn lại trong danh sách

- `skill-creator` — đã có sẵn trong phiên, hữu ích để viết skill mới cho chính công ty (ví dụ đóng gói
  `gate-brief` cho các gate còn lại). Không cần cài thêm.
- `caveman` (cắt token) — công ty đã có `supervisor` làm cost controller; chỉnh `llm.yaml` rẻ và kiểm soát được
  hơn là để một skill lạ nén ngữ cảnh giữa chừng.
- `claude-seo`, `marketingskills`, `social-media-skills`, `financial-services`, `claude-for-legal`,
  `codex-plugin-cc`, `find-skills`, `humanizer`, `mcp-builder` — không nằm trên đường đi của orchestrator. Agent
  `sc-*` không tự gọi slash command của người dùng.

## 5. Rủi ro nếu cài bừa

Skill được cài sẽ vào ngữ cảnh của mọi phiên và có thể tự kích hoạt sai lúc. Với một hệ chạy nền có gate và ngân
sách token, mỗi skill lạ là thêm một nguồn chỉ dẫn có thể mâu thuẫn với `skills/` của công ty mà không ai khai
báo — đúng khuôn lỗi "chế độ hỏng không tự khai báo".

## 6. Việc nên làm (không cái nào cần cài gì)

1. Nâng `local_checks` thành luật chung: mọi `status` nghĩa "đã chạy" phải kèm `evidence` do orchestrator sinh.
   (= đề xuất 3 + 6, nay có thêm căn cứ từ `verification-before-completion`.)
2. Thêm sổ `Ruling:` cho agent — tự quyết mọi thứ ngoài bốn human gate, ghi rõ "sai thì mất gì".
3. DoD frontend thêm bằng chứng ảnh chụp ở 4 khổ + dark mode.

