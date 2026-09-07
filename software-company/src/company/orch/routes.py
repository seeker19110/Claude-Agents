"""Bảng route + guard/enrich thuần: agent nào chạy tiếp theo cho topic nào (tách khỏi orchestrator.py, ADR-0034).

Không giữ trạng thái phiên — mọi hàm ở đây chỉ đọc từ `Orchestrator` (bus, lead, workspace, blackboard) qua tham
số, không có side effect ngoài audit-log của `_audit`. `check_routes` đối chiếu bảng với front matter agent lúc
khởi động (`Orchestrator.__init__`), nên lệch route/schema vỡ ngay, không phải lúc chạy.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..events import Envelope
from ..registry import AgentSpec
from ..roles import ENGINEERING, ROLE, SOURCE
from ..runner import CONTEXT_ONLY
from ..smoke import parse_runtime
from ..workspace import WorkspaceError

if TYPE_CHECKING:
    from ..orchestrator import Orchestrator

ACTOR = "orchestrator"
MAX_CLARIFY_ROUNDS = 2  # khớp `clarification-questions.round` (maximum 2) và prompt clarifier
PAUSING = frozenset({"pause", "budget_cut", "escalate"})

MAX_CONFLICT_RETRIES = 6  # xung đột merge thứ 7 liên tiếp cho một ticket mới tính vào retry nội dung (xem conflict_retries)
# Chuỗi nghiên cứu chạy theo key=project, không có ticket/retry/blocked: một agent lỗi là cả dự án đứng mà không ai
# thấy. Lỗi ở các topic này mở gate `escalation` cấp dự án (approve = chạy lại event, reject = đóng dự án).
RESEARCH_TOPICS = frozenset({"research-requests", "research-findings", "requirements-draft", "clarification-answers"})
CONTROL_TOPICS = frozenset({"audit-log", "shared-context", "supervisor-actions"})
# Nhãn `source` của review-results → agent chấm. ADR-0037: `reviewer` và `qa` là hai GÓC NHÌN của cùng agent `qa`.
REVIEW_AGENT = {SOURCE.REVIEWER: ROLE.QA, SOURCE.QA: ROLE.QA, SOURCE.SECURITY: ROLE.SECURITY}
KEY_FIELD = {"tasks": "ticket_id", "pull-requests": "ticket_id", "test-suites": "ticket_id", "review-results": "ticket_id", "incidents": "incident_id",
             "change-requests": "change_id", "release-candidates": "release_id", "release-events": "release_id",
             "acceptance-results": "release_id"}  # topic khác (project_id) giữ key của event nguồn


def key_for(topic: str, payload: dict[str, Any], default: str) -> str:
    return str(payload.get(KEY_FIELD.get(topic, ""), "") or default)
ACTIVE_STATES = frozenset({"dispatched", "in_progress", "in_review"})
# Trường bị gỡ khỏi payload trước khi đưa cho test-author (ADR-0028: lượt MÙ). `hint` là phản hồi review vòng
# trước — nó nói về CODE, đọc nó là hết mù.
BLIND_STRIP = frozenset({"hint", "retry", "test_suite", "diff", "chan_doan"})

When = Callable[[Envelope, "Orchestrator"], bool]
Enrich = Callable[[Envelope, "Orchestrator"], dict[str, Any]]


@dataclass(frozen=True)
class Route:
    topic_in: str
    agent: str  # id agent, hoặc "$assignee" = lấy từ payload.assignee (khối kỹ thuật)
    topic_out: str  # topic, hoặc CONTEXT_ONLY = chỉ ghi blackboard
    when: When | None = None
    target_env: str | None = None  # route release: đầu ra phải có env đúng như yêu cầu
    many: bool = False  # 0..n payload một lượt (agent được quyền "không có gì để phát")
    enrich: Enrich | None = None  # thêm dữ liệu vào payload đầu vào (vd. bản draft mới nhất cho spec-writer)
    tools: str | None = None  # "rw": sửa code trong worktree (kỹ thuật); "ro": chỉ đọc + chạy test (QA); "research": đọc repo khách + web
    # ADR-0037: pha của lượt — agent nạp thêm skill của pha này (`AgentSpec.phases`). None = chỉ skill cấp agent,
    # trừ route sửa code: pha lấy theo `stack` của ticket lúc chạy, xem `phase_for`.
    phase: str | None = None

    def agents(self) -> tuple[str, ...]:
        return ENGINEERING if self.agent == "$assignee" else (self.agent,)


def phase_for(r: Route, spec: AgentSpec, inp: Envelope) -> str | None:
    """Pha của một lượt (ADR-0037). Route khai sẵn thì dùng; route sửa code lấy theo `stack` của ticket (ADR-0013)
    vì cùng một `builder` làm cả sáu stack.

    `stack` là DỮ LIỆU trong payload chứ không phải bảng route, nên nó chỉ được nhận khi agent thật sự khai pha
    đó — trong lúc chuyển đổi (một số agent đã gộp, một số chưa) `stack=backend` gửi cho agent `backend` cũ,
    vốn không có pha nào, phải chạy như trước chứ không được ném lỗi. Pha do ROUTE khai thì `check_routes` đã
    đối chiếu với front matter lúc khởi động."""
    if r.phase is not None: return r.phase
    if r.tools != "rw": return None
    stack = str(inp.payload.get("stack") or inp.payload.get("assignee") or "")
    return stack if stack in spec.phases else None


def _from(*actors: str) -> When:
    return lambda e, _o: e.actor in actors


def _field(name: str, *values: Any) -> When:
    return lambda e, _o: e.payload.get(name) in values


def _needs_security(e: Envelope, o: Orchestrator) -> bool:
    tid = e.payload.get("ticket_id") or e.key
    return tid in o.lead.tickets and SOURCE.SECURITY in o.lead.required_reviews(tid)


def _release_needs_security(e: Envelope, o: Orchestrator) -> bool:
    return o.lead.release_needs_security(e.payload["release_id"])


def _dict_of(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _deployed(env_name: str) -> When:
    return lambda e, _o: e.payload.get("env") == env_name and e.payload.get("status") == "deployed"


def _answers_complete(e: Envelope, o: Orchestrator) -> bool:
    """Người đã trả lời hết câu hỏi của vòng gần nhất (hoặc clarifier đã hết vòng) → đi thẳng spec-writer.
    Thiếu câu trả lời mà vẫn viết spec thì spec dựa trên giả định người chưa xác nhận.

    Câu trả lời TÍCH LUỸ trong vòng hiện tại, không chỉ tính event này: người trả lời bổ sung một câu ở lượt
    sau (vd. sau khi `security` nêu thêm câu hỏi mở) không phải gửi lại toàn bộ câu cũ. Trước đây chỉ
    đọc `e.payload`, nên lượt bổ sung luôn bị coi là "thiếu hết các câu trước" và spec-writer không bao giờ
    chạy lại — câu trả lời nằm im trong bus, không audit, không báo ai (đo được khi chạy thật 2026-09-04)."""
    pid = str(e.payload.get("project_id") or e.key)
    q = o.latest("clarification-questions", pid)
    if q is None: return True
    asked = {str(x.get("id")) for x in q.payload.get("questions", [])}
    answered = {str(a.get("question_id")) for a in e.payload.get("answers", [])}
    for prev in o.bus.replay(topic="clarification-answers", key=pid):
        # chỉ tính câu trả lời của ĐÚNG vòng này: id có thể trùng giữa các vòng, câu cũ không được
        # vô tình thoả mãn câu hỏi mới.
        if prev.ts >= q.ts:
            answered |= {str(a.get("question_id")) for a in prev.payload.get("answers", [])}
    return not (asked - answered) or int(q.payload.get("round", 1)) >= MAX_CLARIFY_ROUNDS


def _answers_incomplete(e: Envelope, o: Orchestrator) -> bool:
    return not _answers_complete(e, o)


def _spec_ready(e: Envelope, o: Orchestrator) -> bool:
    """Spec-writer chỉ chạy khi đã trả lời hết câu hỏi VÀ dự án có `requirements-draft`. Trước đây câu trả lời gửi cho
    một dự án chưa có bản nháp (chuỗi nghiên cứu chết, hoặc gửi nhầm dự án) vẫn sinh PRD từ đầu vào trống."""
    if not _answers_complete(e, o): return False
    pid = str(e.payload.get("project_id") or e.key)
    if o.latest("requirements-draft", pid) is not None: return True
    o._audit("spec_writer.no_draft", {"project_id": pid, "event_id": e.event_id,
                                      "reason": "clarification-answers nhưng dự án chưa có requirements-draft"},
             once=f"no_draft:{e.event_id}", project_id=pid)
    return False


def _cr_accepted_needs_research(e: Envelope, _o: Orchestrator) -> bool:
    return e.payload.get("decision") == "accepted" and bool(e.payload.get("affects_requirements"))


def _cr_accepted_direct(e: Envelope, _o: Orchestrator) -> bool:
    return e.payload.get("decision") == "accepted" and not e.payload.get("affects_requirements")


SPEC_KINDS = ("application", "library", "docs")   # `approved-specs.payload.kind`; thiếu = application (không khai ≠ được miễn)
SPEC_RUNTIME_REWORKS = 1  # số lần tự trả spec về spec-writer vì thiếu runtime trước khi hỏi người (= max_retries của nó)


def spec_runtime_gap(payload: dict[str, Any]) -> str | None:
    """ADR-0031: Gate 1 chỉ mở khi spec trả lời được "chạy ở đâu". Trả về lý do thiếu (để gửi lại spec-writer), None
    khi đủ. `kind=library|docs` được miễn `runtime` nhưng phải KHAI RÕ — thiếu `kind` tính là ứng dụng, vì im lặng
    chính là cách QLKH đi qua bốn gate mà không có điểm vào nào (báo cáo 2026-09-06-ban-giao-khong-chay-duoc)."""
    kind = payload.get("kind") or "application"
    if kind not in SPEC_KINDS:
        return f"`kind`={kind!r} không hợp lệ; phải là một trong {', '.join(SPEC_KINDS)}"
    if kind != "application":
        return None
    if parse_runtime(payload) is not None:
        return None
    rt = payload.get("runtime")
    what = "thiếu `runtime`" if not isinstance(rt, dict) else "`runtime.command` rỗng hoặc `port`/`timeout_s`/`expect_status` không phải số"
    return (f"spec kind=application {what}: Gate 1 cần lệnh khởi động (`runtime.command`, có thể chứa {{port}}), "
            "`port` (0 = tự chọn), `health` (đường GET trả 200) và phụ thuộc ngoài; nếu sản phẩm là thư viện hay tài liệu "
            "thì khai `kind: library|docs` thay vì bỏ trống")


def _with_draft(e: Envelope, o: Orchestrator) -> dict[str, Any]:
    d = o.latest("requirements-draft", e.payload.get("project_id") or e.key)
    return {"requirements_draft": d.payload} if d else {}


def _with_intake(e: Envelope, o: Orchestrator) -> dict[str, Any]:
    """Synthesizer cần CẢ báo cáo intake lẫn báo cáo 4 mục của researcher (ADR-0006), nhưng nó chỉ được đánh thức bởi
    báo cáo của researcher. Không đính kèm đề bài của intake thì tiêu chí bắt đầu không bao giờ đủ và draft luôn rỗng."""
    key = e.payload.get("project_id") or e.key
    found = [x for x in o.bus.replay("research-findings", key) if x.payload.get("kind") == ROLE.INTAKE]
    return {ROLE.INTAKE: found[-1].payload.get("data")} if found and found[-1].payload.get("data") else {}


def _with_diff(e: Envelope, o: Orchestrator) -> dict[str, Any]:
    """Reviewer/QA/security đọc diff thật của branch ticket (khi có repo) thay vì tin `summary` của PR."""
    ws = o.workspace(e.payload.get("ticket_id") or e.key)
    if ws is None or not ws.path.exists(): return {}
    try: return {"diff": ws.diff(), "changed_files": ws.changed_files()}
    except WorkspaceError as ex: return {"diff_error": str(ex)[:300]}


def _with_chan_doan(e: Envelope, o: Orchestrator) -> dict[str, Any]:
    """qa-debugger nhận thêm LỊCH SỬ HỎNG của chính ticket này, phạm vi hẹp và chỉ-đọc.

    Agent chỉ thấy PR trước mặt nên mỗi vòng lại chẩn đoán từ đầu, không biết mình đang xem lần thứ mấy. Đo
    được ở lần chạy thật 2026-09-04: QLKH-001 quay 8 vòng với `blocked 3× / reopen 8× / review_block 13×`, và
    179/193 lỗi của cả dự án là CÙNG MỘT sự cố hết quota — không agent nào biết điều đó vì chỉ `supervisor`
    đăng ký đọc `audit-log`.

    Cố ý bơm bản LÁT CẮT THEO TICKET chứ không phải toàn cảnh: khuôn lỗi của dự án khác là nhiễu cho việc chấm
    một PR, và `max_input_chars` của qa-debugger chỉ có 50k. Vẫn chỉ-đọc: agent không được cấp thêm tool nào,
    không sửa được mã công ty — đây là bậc thấp nhất có ích, để kiểm xem nó chẩn đoán có đúng không trước khi
    tính chuyện cho nhiều quyền hơn."""
    tid = str(e.payload.get("ticket_id") or e.key)
    try:
        from ..metrics import diagnose
        d = diagnose(o.bus, top=30)
    except Exception as ex:  # chẩn đoán hỏng không được làm hỏng lượt review
        return {"chan_doan_error": str(ex)[:200]}
    vong = d["ticket_quay_vong"].get(tid)
    khuon = [k for k in d["loi_theo_khuon"] if tid in k["tickets"]][:3]
    if not vong and not khuon: return {}
    return {"chan_doan": {"lich_su_ticket": vong, "khuon_loi_cua_ticket": khuon,
                          "gate_dang_cho": d["gate"]["dang_cho"]}}


def _test_scope_ok(o: Orchestrator, tid: str) -> bool:
    """Có worktree cho ticket và stack của repo khách khai được vùng test không (ADR-0028 §3, fail closed)."""
    ws = o.workspace(tid)
    if ws is None: return False
    try:
        ws.create()
    except Exception:  # không dựng được worktree thì cứ đi đường cũ, `_engineer` sẽ báo lỗi thật
        return False
    return bool(ws.stack().test_globs)


def _can_author_tests(e: Envelope, o: Orchestrator) -> bool:
    if not o.test_author: return False
    tid = str(e.payload.get("ticket_id") or e.key)
    if _test_scope_ok(o, tid): return True
    # Khoá mang thế hệ = số lần rework của TICKET (khuôn 3, TRAPS.md §1): thiếu nó, ticket rework lần 2 vẫn
    # không phân vùng được vùng test nhưng audit không ghi lần hai — người đọc `tests_authored_by_assignee`
    # tưởng chỉ xảy ra một lần trong khi nó lặp lại mỗi lần dispatch.
    retry = o.lead.tickets[tid].retry if tid in o.lead.tickets else 0
    o._audit("tests_authored_by_assignee", {"ticket_id": tid, "reason": "không phân vùng được vùng test của stack"},
             ticket_id=tid, project_id=e.payload.get("project_id"), once=f"no-test-author:{tid}:{retry}")
    return False


def _no_test_author(e: Envelope, o: Orchestrator) -> bool:
    return not _can_author_tests(e, o)


def _has_dispute(e: Envelope, _o: Orchestrator) -> bool:
    return bool(str(e.payload.get("test_dispute") or "").strip())


def _with_task(e: Envelope, o: Orchestrator) -> dict[str, Any]:
    """Assignee nhận lại toàn bộ ticket (acceptance, scope, hint...) kèm bộ test vừa được viết."""
    t = o.latest("tasks", str(e.payload.get("ticket_id") or e.key))
    base = dict(t.payload) if t is not None else {}
    return {**base, "test_suite": {k: e.payload.get(k) for k in ("files", "acceptance_covered", "tests_status", "commit", "notes")},
            "tests_authored_by": ROLE.QA}


STAGING_ROUTE = Route("release-candidates", ROLE.OPS, "release-events", target_env="staging", phase="deploy")
ROUTES: tuple[Route, ...] = (
    # khối nghiên cứu: intake → researcher → synthesizer → risk → clarifier → (người trả lời) → spec-writer
    Route("research-requests", ROLE.INTAKE, "research-findings"),
    Route("research-findings", ROLE.RESEARCHER, "research-findings", _from(ROLE.INTAKE), tools="research"),
    Route("research-findings", ROLE.SYNTHESIZER, "requirements-draft", _from(ROLE.RESEARCHER), enrich=_with_intake),
    Route("requirements-draft", ROLE.RISK, "requirements-draft", _from(ROLE.SYNTHESIZER)),
    Route("requirements-draft", ROLE.CLARIFIER, "clarification-questions", _from(ROLE.RISK)),
    Route("clarification-answers", ROLE.CLARIFIER, "clarification-questions", _answers_incomplete, enrich=_with_draft),
    Route("clarification-answers", ROLE.PRODUCT, "approved-specs", _spec_ready, enrich=_with_draft),
    # kỹ thuật + chất lượng
    # ADR-0028: có repo và phân vùng được vùng test → test-author viết test MÙ trước, rồi assignee viết code cho
    # tới khi xanh mà KHÔNG ghi được file test. Không phân vùng được (stack lạ, không repo) → đường cũ, và PR mang
    # `tests_authored_by: "assignee"` để reviewer biết bộ test này không độc lập.
    Route("tasks", ROLE.QA, "test-suites", _can_author_tests, tools="tests", phase="author"),
    Route("tasks", "$assignee", "pull-requests", _no_test_author, tools="rw"),
    Route("test-suites", "$assignee", "pull-requests", enrich=_with_task, tools="rw"),
    # Assignee không sửa được test (tool chặn): nó ghi `test_dispute` và việc quay về pha `author` — lượt DUY NHẤT
    # bộ test được đổi sau khi đã viết, và lượt duy nhất pha `author` được xem diff.
    Route("pull-requests", ROLE.QA, "test-suites", _has_dispute, enrich=_with_diff, tools="tests", phase="author"),
    # ADR-0037: reviewer + qa-debugger thành MỘT lượt pha `review` cho MỌI ticket (không còn guard `_needs_qa`
    # theo `risk_tags`: `RISK_REVIEWS` chỉ còn `security`), nên enrich gộp cả diff lẫn `chan_doan`.
    # Pha `review` và security cũng có tool CHỈ ĐỌC trên worktree: diff dài hơn `max_input_chars` bị cắt giữa,
    # agent "không được suy diễn" nên BLOCK vì "diff không có trong đầu vào" — không phải lỗi code. Đo được
    # 2026-09-06 (TCK-CR-DEV-001-02, PR 877 dòng): security chặn vì thiếu diff `http_adapter.py`, ticket bị trả
    # về làm lại dù reviewer + QA pass. Có tool thì nó đọc đúng file bị cắt rồi mới chấm.
    Route("pull-requests", ROLE.QA, "review-results",
          enrich=lambda e, o: {**_with_diff(e, o), **_with_chan_doan(e, o)}, tools="ro", phase="review"),
    Route("pull-requests", ROLE.SECURITY, "review-results", _needs_security, enrich=_with_diff, tools="ro"),
    # vận hành: RC → staging (+ security DAST/license khi có risk) → QA hồi quy; production đi qua gate 3 (PROD_ROUTE)
    STAGING_ROUTE,
    Route("release-candidates", ROLE.SECURITY, "review-results", _release_needs_security),
    Route("release-events", ROLE.QA, "review-results", _deployed("staging"), tools="ro", phase="review"),  # tool trên worktree tích hợp
    Route("release-events", ROLE.OPS, CONTEXT_ONLY, _deployed("production"), phase="docs"),  # docs, release notes, runbook
    # khách và hậu release
    Route("external-feedback", ROLE.OPS, "change-requests", phase="account"),
    Route("external-feedback", ROLE.OPS, "incidents", many=True, phase="docs"),
    Route("incidents", ROLE.OPS, "research-requests", _field("root_cause_class", "requirement"), many=True, phase="docs"),
    Route("acceptance-results", ROLE.OPS, "change-requests", _field("verdict", "conditional"), many=True, phase="account"),
    Route("change-requests", ROLE.LEAD, "audit-log", _field("decision", "pending")),  # ước lượng impact → người quyết
    Route("change-requests", ROLE.INTAKE, "research-findings", _cr_accepted_needs_research),
)
PROD_ROUTE = Route("release-candidates", ROLE.OPS, "release-events", target_env="production", phase="deploy")


def review_route(agent: str) -> Route:
    """Route chấm PR THẬT của một agent chấm, để chỗ giao lại review (`gates_flow`, `scheduler`) không dựng tay.

    Dựng tay `Route("pull-requests", agent, "review-results")` chạy đúng khi mỗi vai chấm là một agent không
    pha — nhưng ADR-0037 gộp reviewer + qa-debugger vào `qa[review]`, và một Route dựng tay không mang `phase`,
    `enrich`, `tools`: lượt giao lại sẽ chạy bằng prompt pha `author` (không skill code-review, không diff,
    không tool đọc worktree) rồi trả ra `test-suites`. Lấy đúng dòng trong `ROUTES` thì không thể lệch."""
    for r in ROUTES:
        if r.topic_in == "pull-requests" and r.topic_out == "review-results" and r.agent == agent:
            return r
    raise KeyError(f"không có route chấm pull-requests cho {agent}")
THREAT_ROUTE = Route("approved-specs", ROLE.SECURITY, "review-results")  # threat model trước ticket đầu (ADR-0003)

# Đầu vào khiến delivery-lead lập kế hoạch (sinh nhiều ticket một lượt) → `_check_plan` → dispatch (ADR-0037).
PLAN_INPUTS: dict[str, When] = {
    "approved-specs": lambda e, _o: True,
    "incidents": _field("root_cause_class", "code", "ops", "design"),
    "change-requests": _cr_accepted_direct,
}


def check_routes(agents: dict[str, AgentSpec]) -> list[str]:
    """Bảng route phải khớp front matter reads/writes; trả về danh sách vi phạm (rỗng = ổn)."""
    bad = []
    for r in (*ROUTES, PROD_ROUTE, THREAT_ROUTE):
        for a in r.agents():
            spec = agents[a]
            if r.topic_in not in spec.reads and "*" not in spec.reads: bad.append(f"{a} không đọc {r.topic_in}")
            if r.phase is not None and r.phase not in spec.phases:
                bad.append(f"{a} không có pha {r.phase} (front matter khai: {sorted(spec.phases) or 'không pha nào'})")
            if r.topic_out == CONTEXT_ONLY:
                if not spec.namespaces_write: bad.append(f"{a} không có namespace để ghi blackboard")
            elif r.topic_out not in spec.writes: bad.append(f"{a} không ghi {r.topic_out}")
    lead = agents[ROLE.LEAD]
    bad += [f"{ROLE.LEAD} không đọc {t}" for t in PLAN_INPUTS if t not in lead.reads]
    return bad
