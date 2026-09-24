# ADR-0017: phiên chính điều khiển, harness giữ execution state bền

## Bối cảnh

`/thi-hanh` đã giải quyết đúng một vấn đề lớn: người ra lệnh một lần, phiên chính tự chia gói, tạo worktree,
gọi subagent, chạy cổng, review và đi tới PR merge. Nhưng phần quan trọng nhất của orchestration vẫn nằm trong
Markdown + context của phiên chính. `docs/thi-hanh/<mã>.md` vừa là kế hoạch cho người đọc vừa là state machine.
Hệ quả: transition không được type-check như code, worker report vẫn cần phiên chính diễn giải, và một phiên mới
muốn tiếp quản phải dựng lại nhiều ý nghĩa từ văn bản.

Repo đã có các mảnh cần thiết để làm tốt hơn: SQLite/event log, runner, sandbox, routing, trace/span, worktree,
machine-generated evidence và quy tắc "không tin lời khai". Thiếu một lớp chung mô tả **run/task/attempt** bằng
contract máy đọc được và dựng lại state từ log append-only.

## Quyết định

1. **Phiên chính sở hữu intent và quyết định, không sở hữu execution state.** Main session/Claude Code/ChatGPT
   là director: hiểu yêu cầu, quyết kiến trúc, steer/escalate/approve. Harness ở `xagents-core` giữ trạng thái
   thi hành và bằng chứng. Model/provider của director có thể đổi mà run không mất.
2. Thêm kernel `xagents_core.execution` gồm:
   - `RunSpec` + `TaskSpec`: DAG công việc có complexity C1/C2/C3, acceptance, tool/write/context scope;
   - `RunState`: trạng thái thuần dựng lại từ event, không lấy object RAM làm nguồn sự thật;
   - `ExecutionEvent`: event identity bền; transition run/task bị code từ chối khi sai thứ tự;
   - `EvidenceReceipt`: hash output + command/cwd/exit code/git head để "pass" là dữ kiện máy sinh;
   - `ExecutionJournal`: SQLite append-only, mở process mới replay ra cùng state.
3. **DAG phải hợp lệ ngay lúc tạo `RunSpec`**: không task id trùng, không dependency thiếu, không chu trình.
4. Trạng thái vòng đầu:
   `PENDING → RUNNING → SUCCEEDED|BLOCKED|CANCELLED`; task:
   `PENDING/READY → RUNNING → SUCCEEDED|FAILED`, task lỗi có thể `TASK_RETRIED → READY`.
   Dependency chỉ mở READY khi mọi dependency đã SUCCEEDED.
5. Journal và state machine ở core chỉ là **cơ chế**. Nó không biết ticket/company/gate/model/PR. Các package
   miền sẽ map workflow của mình vào contract này ở PR sau.
6. PR này là **H1+H2 foundation**, chưa đổi source of truth của `/thi-hanh`. Cho tới khi bridge H7 được merge,
   `docs/thi-hanh/<mã>.md` vẫn là state vận hành hiện tại. Không giả vờ migration đã xong.
7. Các bước tiếp theo đi tuần tự: scheduler/lease → worker/worktree runtime → exact-head evidence/review →
   main-session bridge → context broker/quality policy/trajectory benchmark. Không thêm swarm trước khi kernel
   state/evidence ổn định.

## Hệ quả

- Process/conversation chết không buộc state machine phải sống trong context; journal replay lại được.
- Transition sai trở thành exception có test thay vì một dòng Markdown bị hiểu khác nhau ở phiên sau.
- Có một contract chung để Claude/ChatGPT/Codex hoặc provider khác làm director mà không đổi execution engine.
- Đổi lại repo có thêm một SQLite journal khi harness thật được bật. Đây là state vận hành, không commit Git,
  cùng lớp dữ liệu runtime như các `*.sqlite*` hiện đã bị cấm commit.
- PR này chưa tạo scheduler, worker pool hay tự mở PR; đó là cố ý để mỗi bước có thể đo, review và rollback độc lập.

## Liên quan

- `docs/KHUON-THI-HANH.md` — orchestration hiện tại, sẽ trở thành thin control client ở H7.
- `platform/xagents-core/src/xagents_core/sqlite_bus.py` — tiền lệ append-only + replay.
- `platform/xagents-core/src/xagents_core/execution.py` — contract/state/journal của quyết định này.
- `platform/xagents-core/tests/test_execution.py` — ca chiều thuận/ngược cho DAG, transition, evidence, restart.
- ADR-0001 — core chỉ giữ cơ chế, không biết nghĩa của từng công ty.
- ADR-0009 — observability theo ranh giới runtime; execution event bổ sung state, không thay span.
