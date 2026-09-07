from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .roles import ROLE, Assignee, BuildPhase, ReviewSource

Topic = Literal[
    "research-requests", "research-findings", "requirements-draft",
    "clarification-questions", "clarification-answers", "approved-specs",
    "tasks", "test-suites", "pull-requests", "review-results", "release-candidates",
    "release-events", "incidents", "shared-context", "audit-log", "supervisor-actions",
    "change-requests", "acceptance-results", "external-feedback",
]
Namespace = Literal[
    "prd", "glossary", "design", "architecture", "api-contract", "schema", "threat-model",
    "infra", "analytics", "docs", "knowledge", "contract",
]

NAMESPACE_OWNERS: dict[str, set[str]] = {
    # ADR-0037 PR-5e: bốn namespace của khối nghiên cứu/kế hoạch về cùng một chủ — `product` (pha `research` ghi
    # glossary/design, pha `spec` ghi prd, pha `plan` ghi architecture/api-contract).
    "prd": {ROLE.PRODUCT}, "glossary": {ROLE.PRODUCT}, "design": {ROLE.PRODUCT},
    "architecture": {ROLE.PRODUCT}, "api-contract": {ROLE.PRODUCT, ROLE.BUILDER},
    "schema": {ROLE.BUILDER}, "threat-model": {ROLE.SECURITY}, "infra": {ROLE.BUILDER},
    "analytics": {ROLE.BUILDER}, "docs": {ROLE.OPS}, "knowledge": {ROLE.SUPERVISOR}, "contract": {ROLE.OPS},
}

# Namespace phạm vi toàn công ty (không thuộc dự án nào): bài học dùng chung cho mọi dự án.
GLOBAL_NAMESPACES = frozenset({"knowledge"})

# Ticket có bất kỳ tag nào dưới đây bắt buộc thêm review của `security` (ADR-0003).
RISK_TAGS = frozenset({"auth", "payment", "pii", "crypto", "upload", "admin", "external-api"})
BUDGET_FACTOR = 1.5  # budget_tokens ≥ estimate_tokens × BUDGET_FACTOR (skill cost-estimation)

# ADR-0037 PR-1: ticket vượt trần này phải chia nhỏ trước khi qua `_check_plan` (dời từ mục "Code gửi kèm" của
# gate plan cũ — mọi khoá gate plan nay là một kiểm ở `_check_plan`, không còn chỗ nào chỉ người mới thấy).
MAX_TICKET_TOKENS = 200_000
# Từ khoá trong title/scope/acceptance (so khớp không phân biệt hoa thường) buộc ticket phải khai `risk_tags`.
RISK_HINTS = frozenset({
    "auth", "login", "password", "payment", "thanh toán", "pii", "cccd", "email",
    "crypto", "upload", "admin", "webhook", "external",
})

SCHEMA_VERSION = 1  # tăng khi envelope hoặc payload của topic đổi không tương thích ngược


class Ruling(BaseModel):
    """ADR-0030 — sổ Ruling: quyết định agent TỰ đưa ra thay vì dừng chờ người. Ba phần bắt buộc, không phần nào
    được bỏ: `decision` (quyết gì), `why` (căn cứ: spec, shared-context, quy ước), `cost_if_wrong` (sai thì mất gì —
    để người soát biết có đáng lật lại không). Chỉ bốn việc được phép dừng chờ người: không đảo ngược được; nhạy cảm
    bảo mật; tác động ra ngoài worktree (merge/push/publish); kế hoạch hỏng tới mức mọi hướng đều là đoán."""
    decision: str
    why: str
    cost_if_wrong: str


class Envelope(BaseModel):
    event_id: str = Field(default_factory=lambda: uuid4().hex)
    topic: Topic
    key: str
    actor: str
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any]
    schema_version: int = SCHEMA_VERSION
    correlation_id: str | None = None  # event gốc của chuỗi nhân quả (mặc định = chính event_id khi không có cha)
    causation_id: str | None = None    # event trực tiếp sinh ra event này

    def model_post_init(self, _ctx: Any) -> None:
        if self.correlation_id is None:
            self.correlation_id = self.event_id

    def child(self, **kw: Any) -> Envelope:
        """Envelope mới trong cùng chuỗi nhân quả: kế thừa correlation_id, causation_id = event này."""
        return Envelope(correlation_id=self.correlation_id, causation_id=self.event_id, **kw)

class Task(BaseModel):
    ticket_id: str
    project_id: str
    requirement_id: str
    assignee: Assignee
    # ADR-0037: mảng kỹ thuật của ticket = PHA của agent làm ticket (`AgentSpec.phases`), thay cho việc chọn một
    # agent riêng cho mỗi stack. Từ PR-5d `assignee` chỉ còn một giá trị (`builder`) nên đây là trường DUY NHẤT
    # nói ticket thuộc mảng nào; thiếu nó thì `routes.phase_for` trả None và builder chạy bằng prompt chung.
    stack: BuildPhase | None = None
    title: str
    acceptance: list[str]
    scope: list[str] = []
    estimate_days: float = 0.5
    depends_on: list[str] = []
    retry: int = 0
    hint: str | None = None
    # Hướng dẫn của NGƯỜI (gate escalation `reopen`, `comment`). Tách khỏi `hint` vì `hint` bị delivery-lead ghi
    # đè bằng thông điệp máy mỗi lần retry ("lần trước lỗi: ..."), nên chẩn đoán của người — thứ giá trị nhất —
    # là thứ mất đầu tiên. Đo được 2026-09-06 (QLKH-012): hint chi tiết sống đúng MỘT lượt rồi bị thay.
    human_hint: str | None = None
    estimate_tokens: int | None = None
    budget_tokens: int = 120_000
    risk_tags: list[str] = []
    budget_usd: float | None = None  # trần chi phí tiền của ticket (tuỳ chọn); supervisor cắt khi chạm, ngoài budget_tokens
    priority: int = 3  # 1 = cao nhất (WSJF/MoSCoW quy về 1..5); delivery-lead dispatch theo priority rồi thứ tự tạo
    rulings: list[Ruling] = []  # ADR-0030

class PullRequest(BaseModel):
    ticket_id: str
    branch: str
    pr_ref: str
    summary: str = ""
    impact: dict[str, Any] = {}
    local_checks: dict[str, Any]
    project_id: str | None = None  # orchestrator điền từ ticket: blackboard và chi phí phân vùng theo dự án (ADR-0018)
    rulings: list[Ruling] = []  # ADR-0030
    # ADR-0033: bằng chứng ngoài `local_checks` — hiện dùng `screenshots[]` cho ticket frontend. Hình mở (dict)
    # vì mỗi loại bằng chứng có hình dạng riêng; ràng buộc từng loại nằm ở JSON Schema, không ở đây.
    evidence: dict[str, Any] = {}
    # Đường hợp lệ để khai "việc đã xong từ lượt trước, không cần sửa thêm" — cùng tinh thần `test_dispute`:
    # agent tự đối chiếu với acceptance criteria rồi giải thích VÌ SAO không sửa gì, thay vì im lặng bị tính
    # invalid_output (TCK-CR-RUNTIME-01, 2026-09-06). Ngưỡng độ dài xác thực ở runner, không ở đây.
    no_changes_reason: str | None = None

class Finding(BaseModel):
    level: Literal["block", "warn", "nit"]
    text: str
    location: str | None = None

class ReviewResult(BaseModel):
    ticket_id: str
    source: ReviewSource
    verdict: Literal["pass", "block", "fail"]
    findings: list[Finding] = []
    root_cause: str | None = None
    bug_reports: list[str] = []
    metrics: dict[str, Any] = {}
    project_id: str | None = None
    # Trường prompt reviewer/qa-debugger vẫn đòi (nay có trong schema, không còn lọt nhờ additionalProperties)
    sbom_ref: str | None = None
    # Model trả câu tóm tắt hoặc object theo từng loại scan/test: nhận cả hai, không ép model đổi hình đầu ra
    scan_summary: str | dict[str, Any] | None = None
    test_summary: str | dict[str, Any] | None = None
    mutation_score: float | None = None
    perf: dict[str, Any] | None = None
    a11y: dict[str, Any] | None = None
    rulings: list[Ruling] = []  # ADR-0030

class SharedContext(BaseModel):
    namespace: Namespace
    version: int
    content_ref: str
    summary: str = ""
    project_id: str | None = None  # None = phạm vi toàn công ty (vd. knowledge); dự án khác nhau không ghi đè nhau
    content: str | None = None  # toàn văn artifact; bus là nguồn sự thật, artifact store chỉ mirror ra file cho người đọc
    rulings: list[Ruling] = []  # ADR-0030

class AuditLog(BaseModel):
    actor: str
    action: str
    ticket_id: str | None = None
    project_id: str | None = None
    evidence: str | None = None
    tokens: int = 0
    # Token ĐẦU RA riêng. `tokens` là tổng (input + output) và phình theo số lượt tool vì mỗi lượt gửi lại cả
    # hội thoại, nên nó không đo được "agent đã làm bao nhiêu việc". Ngân sách ticket dùng trường này.
    output_tokens: int = 0
    cost_usd: float = 0.0  # từ bảng giá `prices` trong llm.yaml; 0 khi model không có giá (supervisor đếm `unpriced`)
    rulings: list[Ruling] = []  # ADR-0030
    phase: str | None = None  # ADR-0037: pha của lượt (`AgentSpec.phases`) — hai lượt cùng actor khác pha phân biệt được ở sổ

class ChangeRequest(BaseModel):
    """Khách yêu cầu đổi phạm vi sau khi spec đã duyệt (account-manager tạo). Không sửa spec trực tiếp."""
    change_id: str
    project_id: str
    requested_by: str
    description: str
    affects_requirements: list[str] = []
    impact: dict[str, Any] = {}
    decision: Literal["pending", "accepted", "rejected", "deferred"] = "pending"
    rulings: list[Ruling] = []  # ADR-0030

class AcceptanceResult(BaseModel):
    """Kết quả nghiệm thu (UAT) của khách trên một release (account-manager ghi nhận)."""
    release_id: str
    project_id: str
    verdict: Literal["accepted", "rejected", "conditional"]
    signed_by: str
    findings: list[Finding] = []
    evidence_ref: str | None = None
    rulings: list[Ruling] = []  # ADR-0030

class SupervisorAction(BaseModel):
    target: str
    action: Literal["pause", "resume", "escalate", "budget_cut", "warn"]
    reason: str
    evidence: str | None = None
    project_id: str | None = None
    rulings: list[Ruling] = []  # ADR-0030

PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "tasks": Task, "pull-requests": PullRequest, "review-results": ReviewResult,
    "shared-context": SharedContext, "audit-log": AuditLog, "supervisor-actions": SupervisorAction,
    "change-requests": ChangeRequest, "acceptance-results": AcceptanceResult,
}

TicketState = Literal["draft", "waiting", "dispatched", "in_progress", "in_review", "changes_requested",
                      "approved", "merged", "released", "closed", "blocked", "escalated"]
TRANSITIONS: dict[str, set[str]] = {
    "draft": {"dispatched", "waiting"}, "waiting": {"dispatched"}, "dispatched": {"in_progress"},
    "in_progress": {"in_review"}, "in_review": {"changes_requested", "approved"}, "changes_requested": {"dispatched"},
    "approved": {"merged", "changes_requested"}, "merged": {"released", "changes_requested"}, "released": {"closed", "changes_requested"},
    "blocked": {"dispatched", "escalated"},
    "escalated": {"dispatched", "closed"}, "closed": set(),
}
def can_transition(src: str, dst: str) -> bool:
    return dst in {"blocked", "escalated"} or dst in TRANSITIONS.get(src, set())
