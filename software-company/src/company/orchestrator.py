"""Orchestrator: vòng lặp tự động topic → agent → topic (ADR-0007).

Mỗi event trên bus được đối chiếu với bảng ROUTES (rút từ bảng topic trong docs/architecture.md và front matter
`reads`/`writes` của agent): khớp thì gọi `AgentRunner` rồi publish đầu ra; đầu ra lại là event mới → vòng lặp tiếp.
Phần xác định (DeliveryLead, Supervisor, PersistentGate) subscribe bus như trước; orchestrator chỉ điền chỗ trống
"ai chạy tiếp theo" và tôn trọng ba thứ không bao giờ tự đi tiếp:

- Human gate: `approved-specs` chờ gate `spec`; plan của delivery-lead chờ gate `plan`; production chờ gate `release`;
  ticket blocked/escalate chờ gate `escalation`.
- Supervisor: ticket bị pause/budget_cut/escalate thì mọi event của ticket đó bị hoãn đến khi `resume`.
- Khách: `clarification-answers`, `acceptance-results`, quyết định `change-requests` do người publish (CLI).

Nhánh tích hợp (ADR-0011): có `repo` thì ticket rẽ từ `company/integration`; khi release-candidate xuất hiện (mọi review
pass) orchestrator merge --no-ff từng branch ticket vào đó rồi mới cho release-engineer chạy. Xung đột → RC bị huỷ
(`release.void`), ticket về `changes_requested` với hint là danh sách file xung đột, worktree tạo lại từ nền mới.

Khối kỹ thuật (ADR-0010): có `repo` thì mỗi ticket chạy trong worktree `ticket/<id>` với tool đọc/ghi/lint/test; PR mang
bằng chứng do code điền (`local_checks.verified_by=workspace`, diff thật cho reviewer/QA/security; QA còn có tool chỉ đọc
để tự chạy test). Không có `repo` thì PR vẫn đi tiếp nhưng `local_checks` bị thay bằng `{"unverified": true}` — không
bao giờ để lời tự khai của model đóng vai bằng chứng.

Agent ghi blackboard qua `context_writes` trong đầu ra (runner kiểm namespace). Mọi event đã xử lý được đánh dấu
bằng `audit-log` (actor=orchestrator, action=orchestrated) nên mở lại bus SQLite là tiếp tục đúng chỗ; trạng thái
delivery-lead/supervisor/gate dựng lại từ replay. Không retry lời gọi model vì lỗi nội dung: lỗi ghi audit rồi đi tiếp.

Hai trạng thái dừng KHÁC NHAU về độ bền, rất dễ nhầm khi vận hành:
- HOÃN (`deferred`, xem `_defer`): KHÔNG gọi `_mark`, nên event không mang dấu `orchestrated`. Mở lại tiến trình
  là hàng đợi nhận lại nó — an toàn khi restart. Backend hẹn "thử lại sau Ns" thì `defer_until` giữ đúng hẹn.
- KẸT (`stalled`, xem `_stall`): event ĐÃ bị `_mark`. Lệnh chạy lại (`_retry_stalled`) bỏ dấu đó trong RAM, nên
  `_rehydrate` phải đối chiếu `project.retried` với `orchestrated` gần nhất mới nhận lại được sau restart.

ADR-0012:
- Lỗi transport (`TransientError`, sau khi `RetryingClient` đã thử lại) không phải lỗi agent: event được HOÃN
  (`transient:<agent>`) và nhịp `tick` sau thử lại; agent đã chạy xong trên cùng event không chạy lại (`partial`).
- `--workers N`: event của các key khác nhau chạy song song trong thread pool; bus giữ RLock nên phần xác định
  (delivery-lead, supervisor, gate) vẫn tuần tự. Event đặc biệt (gate decide, plan, RC, clarifier) luôn chạy một mình.
- researcher có tool đọc repo khách (chỉ đọc, không chạy lệnh) và web (`--web`); blackboard có artifact store
  (`--artifacts`, mặc định `<db>.artifacts/`) mirror toàn văn PRD/C4/OpenAPI/threat model ra file.
- Người can thiệp giữa vòng: `comment` (hint cho ticket đang chạy, không tính retry) và `takeover` (người sửa tay trong
  worktree, code chạy lint/test và publish PR dưới tên người) — không cần đợi gate escalation.

ADR-0026 (`--deliver`): production được duyệt và deploy → tag `v<version>` + fast-forward `company/release` trong repo
khách (`Integration.deliver`); production rolled_back/failed → lùi con trỏ nhánh release về lần giao trước (tag giữ).
`--push-remote` đẩy lên remote của khách; lỗi push chỉ vào audit. `main` của khách vẫn không bị chạm.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .blackboard import Blackboard
from .bus import InMemoryBus, is_human
from .delivery import DONE_STATES, DeliveryLead
from .events import BUDGET_FACTOR, AuditLog, Envelope, Task
from .gate_cli import PersistentGate, trusted_decision
from .gates import Decision, GateRequest
from .llm import LLMError, ModelClient, TransientError
from .registry import AgentSpec, load_agents
from .routing import retry_after_seconds
from .runner import CONTEXT_ONLY, AgentRunner, RunnerError, artifact_store
from .supervisor import Supervisor
from .tools import ToolBox, WorkspaceTools
from .web import WebTools, research_toolbox
from .workspace import Integration, TicketWorkspace, WorkspaceError, _git

ACTOR = "orchestrator"
MAX_CLARIFY_ROUNDS = 2  # khớp `clarification-questions.round` (maximum 2) và prompt clarifier
ENGINEERING = ("backend", "frontend", "mobile", "database", "platform", "data")
PAUSING = frozenset({"pause", "budget_cut", "escalate"})
# Chuỗi nghiên cứu chạy theo key=project, không có ticket/retry/blocked: một agent lỗi là cả dự án đứng mà không ai
# thấy. Lỗi ở các topic này mở gate `escalation` cấp dự án (approve = chạy lại event, reject = đóng dự án).
RESEARCH_TOPICS = frozenset({"research-requests", "research-findings", "requirements-draft", "clarification-answers"})
CONTROL_TOPICS = frozenset({"audit-log", "shared-context", "supervisor-actions"})
REVIEW_AGENT = {"reviewer": "reviewer", "qa": "qa-debugger", "security": "security-engineer"}
KEY_FIELD = {"tasks": "ticket_id", "pull-requests": "ticket_id", "review-results": "ticket_id", "incidents": "incident_id",
             "change-requests": "change_id", "release-candidates": "release_id", "release-events": "release_id",
             "acceptance-results": "release_id"}  # topic khác (project_id) giữ key của event nguồn


def key_for(topic: str, payload: dict[str, Any], default: str) -> str:
    return str(payload.get(KEY_FIELD.get(topic, ""), "") or default)
ACTIVE_STATES = frozenset({"dispatched", "in_progress", "in_review"})

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

    def agents(self) -> tuple[str, ...]:
        return ENGINEERING if self.agent == "$assignee" else (self.agent,)


def _from(*actors: str) -> When:
    return lambda e, _o: e.actor in actors


def _field(name: str, *values: Any) -> When:
    return lambda e, _o: e.payload.get(name) in values


def _needs_security(e: Envelope, o: Orchestrator) -> bool:
    tid = e.payload.get("ticket_id") or e.key
    return tid in o.lead.tickets and "security" in o.lead.required_reviews(tid)


def _needs_qa(e: Envelope, o: Orchestrator) -> bool:
    """ADR-0021: QA ở lượt PR chỉ cho ticket có risk_tags; ticket thường reviewer kiêm chấm test."""
    tid = e.payload.get("ticket_id") or e.key
    return tid in o.lead.tickets and "qa" in o.lead.required_reviews(tid)


def _release_needs_security(e: Envelope, o: Orchestrator) -> bool:
    return o.lead.release_needs_security(e.payload["release_id"])


def _deployed(env_name: str) -> When:
    return lambda e, _o: e.payload.get("env") == env_name and e.payload.get("status") == "deployed"


def _answers_complete(e: Envelope, o: Orchestrator) -> bool:
    """Người đã trả lời hết câu hỏi của vòng gần nhất (hoặc clarifier đã hết vòng) → đi thẳng spec-writer.
    Thiếu câu trả lời mà vẫn viết spec thì spec dựa trên giả định người chưa xác nhận.

    Câu trả lời TÍCH LUỸ trong vòng hiện tại, không chỉ tính event này: người trả lời bổ sung một câu ở lượt
    sau (vd. sau khi security-engineer nêu thêm câu hỏi mở) không phải gửi lại toàn bộ câu cũ. Trước đây chỉ
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


def _with_draft(e: Envelope, o: Orchestrator) -> dict[str, Any]:
    d = o.latest("requirements-draft", e.payload.get("project_id") or e.key)
    return {"requirements_draft": d.payload} if d else {}


def _with_intake(e: Envelope, o: Orchestrator) -> dict[str, Any]:
    """Synthesizer cần CẢ báo cáo intake lẫn báo cáo 4 mục của researcher (ADR-0006), nhưng nó chỉ được đánh thức bởi
    báo cáo của researcher. Không đính kèm đề bài của intake thì tiêu chí bắt đầu không bao giờ đủ và draft luôn rỗng."""
    key = e.payload.get("project_id") or e.key
    found = [x for x in o.bus.replay("research-findings", key) if x.payload.get("kind") == "intake"]
    return {"intake": found[-1].payload.get("data")} if found and found[-1].payload.get("data") else {}


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
        from .metrics import diagnose
        d = diagnose(o.bus, top=30)
    except Exception as ex:  # chẩn đoán hỏng không được làm hỏng lượt review
        return {"chan_doan_error": str(ex)[:200]}
    vong = d["ticket_quay_vong"].get(tid)
    khuon = [k for k in d["loi_theo_khuon"] if tid in k["tickets"]][:3]
    if not vong and not khuon: return {}
    return {"chan_doan": {"lich_su_ticket": vong, "khuon_loi_cua_ticket": khuon,
                          "gate_dang_cho": d["gate"]["dang_cho"]}}


ROUTES: tuple[Route, ...] = (
    # khối nghiên cứu: intake → researcher → synthesizer → risk → clarifier → (người trả lời) → spec-writer
    Route("research-requests", "intake", "research-findings"),
    Route("research-findings", "researcher", "research-findings", _from("intake"), tools="research"),
    Route("research-findings", "synthesizer", "requirements-draft", _from("researcher"), enrich=_with_intake),
    Route("requirements-draft", "risk", "requirements-draft", _from("synthesizer")),
    Route("requirements-draft", "clarifier", "clarification-questions", _from("risk")),
    Route("clarification-answers", "clarifier", "clarification-questions", _answers_incomplete, enrich=_with_draft),
    Route("clarification-answers", "spec-writer", "approved-specs", _spec_ready, enrich=_with_draft),
    # kỹ thuật + chất lượng
    Route("tasks", "$assignee", "pull-requests", tools="rw"),
    Route("pull-requests", "reviewer", "review-results", enrich=_with_diff),
    Route("pull-requests", "qa-debugger", "review-results", _needs_qa,
          enrich=lambda e, o: {**_with_diff(e, o), **_with_chan_doan(e, o)}, tools="ro"),
    Route("pull-requests", "security-engineer", "review-results", _needs_security, enrich=_with_diff),
    # vận hành: RC → staging (+ security DAST/license khi có risk) → QA hồi quy; production đi qua gate 3 (PROD_ROUTE)
    Route("release-candidates", "release-engineer", "release-events", target_env="staging"),
    Route("release-candidates", "security-engineer", "review-results", _release_needs_security),
    Route("release-events", "qa-debugger", "review-results", _deployed("staging"), tools="ro"),  # tool trên worktree tích hợp
    Route("release-events", "support-docs", CONTEXT_ONLY, _deployed("production")),  # docs, release notes, runbook
    # khách và hậu release
    Route("external-feedback", "account-manager", "change-requests"),
    Route("external-feedback", "support-docs", "incidents", many=True),
    Route("incidents", "support-docs", "research-requests", _field("root_cause_class", "requirement"), many=True),
    Route("acceptance-results", "account-manager", "change-requests", _field("verdict", "conditional"), many=True),
    Route("change-requests", "delivery-lead", "audit-log", _field("decision", "pending")),  # ước lượng impact → người quyết
    Route("change-requests", "intake", "research-findings", _cr_accepted_needs_research),
)
PROD_ROUTE = Route("release-candidates", "release-engineer", "release-events", target_env="production")
THREAT_ROUTE = Route("approved-specs", "security-engineer", "review-results")  # threat model trước ticket đầu (ADR-0003)

# Đầu vào khiến delivery-lead lập kế hoạch (sinh nhiều ticket một lượt) → gate `plan` → dispatch.
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
            if r.topic_out == CONTEXT_ONLY:
                if not spec.namespaces_write: bad.append(f"{a} không có namespace để ghi blackboard")
            elif r.topic_out not in spec.writes: bad.append(f"{a} không ghi {r.topic_out}")
    lead = agents["delivery-lead"]
    bad += [f"delivery-lead không đọc {t}" for t in PLAN_INPUTS if t not in lead.reads]
    return bad


@dataclass
class StepResult:
    event_id: str
    topic: str
    key: str
    actions: list[str] = field(default_factory=list)
    deferred: str | None = None  # lý do hoãn (gate:..., paused:..., transient:...)
    transient: bool = False      # một agent gặp lỗi transport sau khi đã retry → event sẽ được thử lại ở nhịp sau


class Orchestrator:
    def __init__(self, bus: InMemoryBus, client: ModelClient, agents: dict[str, AgentSpec] | None = None,
                 max_retries: int = 3, repo: Path | None = None, base: str = "HEAD", max_turns: int = 25,
                 batch_releases: bool = False,
                 integration: str = "company/integration", workers: int = 1, web: WebTools | bool = False,
                 artifacts: Path | None = None, project_budget_usd: float | None = None,
                 deliver: bool = False, push_remote: str | None = None, release_branch: str = "company/release"):
        self.bus = bus
        self.repo, self.max_turns = (Path(repo) if repo else None), max_turns
        self.workers = max(1, int(workers))
        self.web = web if isinstance(web, WebTools) else (WebTools() if web else None)
        self._lock = threading.RLock()   # trạng thái orchestrator (processed, deferred, once, stats) — KHÔNG publish khi đang giữ
        self._qlock = threading.RLock()  # hàng đợi; _on_event (chạy dưới lock của bus) chỉ chạm lock này
        self._ws_lock = threading.RLock()
        self._merge_lock = threading.RLock()  # merge vào nhánh tích hợp chạy một mình (ADR-0012 §7), kể cả khi --workers>1
        self.partial: dict[str, set[str]] = {}  # event_id → agent đã chạy xong (để không chạy lại khi event bị hoãn transient)
        if self.repo is not None and not (self.repo / ".git").exists():
            raise ValueError(f"repo không phải git repository: {self.repo}")
        # `--repo` là repo MẶC ĐỊNH của tiến trình. Từng dự án có thể chỉ repo riêng ngay trong `research-requests`
        # (payload.repo, payload.base — ADR-0025): học từ log lúc mở lại và từ event lúc chạy, ticket của dự án nào
        # làm trong worktree của repo đó. Repo sai (không có .git) → audit một lần, dự án rơi về mặc định.
        self.deliver, self.push_remote, self.release_branch = bool(deliver), push_remote, release_branch
        self.integration = Integration(self.repo, integration, base, release_branch) if self.repo is not None else None
        self.base, self.integration_branch = base, integration
        self.project_repos: dict[str, Integration] = {}
        # release_id → {version, tag, sha, short, branch, previous}: bản đã giao (ADR-0026), dựng lại từ audit-log
        self.delivered: dict[str, dict[str, Any]] = {}
        # release_id → sha ĐẦY ĐỦ của nhánh tích hợp lúc deploy staging: đúng nội dung QA đã hồi quy, và là sha được
        # giao khi production duyệt — nhánh tích hợp có thể đã đi tiếp (ticket khác merge) trong lúc chờ gate 3.
        self.release_sha: dict[str, str] = {}
        self.bad_repos: set[str] = set()
        self.void_releases: set[str] = set()
        self.integrated: set[str] = set()  # ticket đã merge vào nhánh tích hợp (khi approved, không đợi RC)
        self.missing_threat_model: set[str] = set()  # spec chưa có threat model vì security-engineer lỗi
        self.stalled: dict[str, dict[str, Any]] = {}  # project_id → {event_id, agent, topic, error}: dự án kẹt chờ người
        self.stall_count: Counter[str] = Counter()  # event_id → số lần kẹt (mỗi lần một gate mới, không im lặng lần hai)
        self.agents = agents or load_agents()
        bad = check_routes(self.agents)
        if bad: raise ValueError("ROUTES lệch front matter: " + "; ".join(bad))
        self.blackboard = Blackboard(bus, store=artifacts)
        self.gate = PersistentGate(bus)
        self.lead = DeliveryLead(bus, self.gate, max_retries=max_retries, batch_releases=batch_releases)
        self.lead.require_integration = self.integration is not None
        budget_usd = project_budget_usd if project_budget_usd is not None else getattr(client, "budget_usd", None)
        self.supervisor = Supervisor(bus, max_retries=max_retries, project_budget_usd=budget_usd)
        self.runner = AgentRunner(bus, client, self.agents, self.blackboard)
        self.processed: set[str] = set()
        self.paused: set[str] = set()
        self.plans: dict[str, dict[str, Any]] = {}
        self.queue: list[Envelope] = []
        self.deferred: dict[str, tuple[Envelope, str]] = {}
        # event_id → mốc monotonic sớm nhất được thử lại. Backend nói rõ "thử lại sau Ns" thì phải chờ đúng
        # chừng đó; hỏi lại sớm hơn vừa vô ích vừa làm bẩn audit-log (xem `_retry_deferred`).
        self.defer_until: dict[str, float] = {}
        self.once: set[str] = set()  # nhắc nhở / hành động chỉ làm một lần (gate.remind, review.reassign, lesson...)
        # ticket_id → số quyết định escalation đã áp cho ticket đó. Đối xứng với `stall_count` ở nhánh dự-án-kẹt:
        # nếu không có nó, ticket bị chặn LẦN HAI sinh ra đúng khoá `once` của lần một nên không mở gate nào nữa.
        self.escalation_decided: Counter[str] = Counter()
        self.stats: Counter[str] = Counter()
        self._rehydrate()
        bus.subscribe("*", self._on_event)

    # ---------- khôi phục từ log ----------

    def _rehydrate(self) -> None:
        # Một lần duyệt log, không hai: `replay()` trên bus bền vững parse lại từng envelope, nên quét đôi là nhân đôi
        # thời gian mở lại một dự án đã chạy lâu.
        log = list(self.bus.replay())
        # Thứ tự trong log của lần `orchestrated` / `project.retried` gần nhất cho từng event: dùng ở cuối hàm
        # để nhận lại lệnh thử-lại chưa kịp chạy (xem chú thích ở đó).
        last_done: dict[str, int] = {}
        last_retry: dict[str, tuple[int, dict[str, Any]]] = {}   # event_id → (thứ tự trong log, bản ghi stalled)
        hen: dict[str, tuple[str, str]] = {}                     # event_id → (mốc hẹn ISO, lý do hoãn)
        for i, env in enumerate(log):
            if env.topic == "audit-log":
                a = env.payload; d = _evidence(a)
                if a["action"] == "project.retried" and d.get("event_id"): last_retry[str(d["event_id"])] = (i, d)
                if a["actor"] == ACTOR and a["action"] == "orchestrated":
                    self.processed.add(d["event_id"]); last_done[str(d["event_id"])] = i
                elif a["actor"] == ACTOR and a["action"] == "once": self.once.add(d["key"])
                elif a["action"] == "plan.proposed": self.plans[d["plan_id"]] = d
                elif a["action"] == "release.void": self._void(d["release_id"])
                elif a["action"] == "release.staged": self.release_sha[d["release_id"]] = d["sha"]
                elif a["action"] == "delivery.done": self.delivered[d["release_id"]] = d
                elif a["action"] == "delivery.rolled_back": self.delivered.pop(d["release_id"], None)
                elif a["action"] == "ticket.abandoned": self.lead.abandon(d["ticket_id"])
                elif a["action"] == "defer.until" and d.get("event_id"):
                    hen[str(d["event_id"])] = (str(d.get("until") or ""), str(d.get("reason") or "transient:?"))
                elif a["action"] == "ticket.blocked":
                    # xem chú thích ở `DeliveryLead._retry`: không dựng lại `blocked` thì ticket quay về
                    # `dispatched` và người duyệt escalation bấm approve cũng không mở lại được nó.
                    self.lead.state[str(d["ticket_id"])] = "blocked"
                elif a["action"] == "integration.merged":
                    self.integrated.add(d["ticket_id"])
                    prev_r, self.lead.replaying = self.lead.replaying, True
                    try: self.lead.mark_integrated(d["ticket_id"])
                    finally: self.lead.replaying = prev_r
                elif a["action"] == "threat_model.missing": self.missing_threat_model.add(d["subject_id"])
                elif a["action"] == "project.stalled":
                    self.stalled[d["project_id"]] = d; self.stall_count[d["event_id"]] += 1
                elif a["action"] in {"project.retried", "project.closed"}: self.stalled.pop(d["project_id"], None)
                elif a["action"] == "gate.decide":
                    if d.get("subject_id"): self.escalation_decided[str(d["subject_id"])] += 1
                    if d.get("decision") == "approve" and d.get("subject_id") in self.plans \
                            and trusted_decision(env) is not None:
                        self._dispatch_plan(d["subject_id"], replaying=True)
            elif env.topic == "supervisor-actions": self._track_pause(env)
            elif env.topic == "shared-context": self.blackboard._on(env)
            else:
                if env.topic == "research-requests": self._learn_repo(env, replaying=True)
                self.lead.replay(env)
            if env.actor in self.agents and env.causation_id:
                # Đầu ra agent đã publish cho event chưa được đánh dấu xong (crash giữa hai route): agent đó KHÔNG chạy
                # lại khi mở lại — tốn token và sinh PR/review trùng. `partial` được dựng lại từ causation_id.
                self.partial.setdefault(env.causation_id, set()).add(env.actor)
            self.supervisor.replay(env)
        # Lệnh thử-lại chỉ sống trong RAM: `_retry_stalled` bỏ dấu `processed` rồi đẩy event vào `self.queue`.
        # Restart giữa lúc đó là mất trắng — event vẫn mang dấu `orchestrated` của LẦN LỖI, nên hàng đợi dựng lại
        # loại nó ra và dự án nằm im vĩnh viễn dù người đã bấm duyệt. Đo được khi chạy thật (2026-09-04): duyệt
        # gate escalation lúc 06:51:31, restart lúc 06:51:45, sau đó không một dòng `orchestrated` nào nữa.
        # Ai đã bảo "chạy lại" mà event chưa được xử lý lại thì phải bỏ dấu để hàng đợi nhận lại — TRỪ khi việc
        # đó đã có người khác làm xong trong lúc chờ (xem `_retry_con_can`).
        reopened = {eid for eid, (idx, rec) in last_retry.items()
                    if idx > last_done.get(eid, -1) and self._retry_con_can(log, idx, rec)}
        # KHÔNG audit ở đây: `_rehydrate` chạy trong MỌI tiến trình, kể cả lệnh chỉ-đọc (`status`, `report`,
        # `show`, console). Ghi bus từ đường đọc là mỗi lần xem trạng thái lại thêm một dòng rác — chính tôi
        # đã mắc và thấy nó trong log. Việc mở lại sẽ tự hiện ra ở dòng `orchestrated` khi event thật sự chạy.
        self.processed -= reopened
        self.partial = {k: v for k, v in self.partial.items() if k not in self.processed}
        self.queue = [e for e in log if self._actionable(e) and e.event_id not in self.processed]
        self._nap_lai_hen(hen)

    def _nap_lai_hen(self, hen: dict[str, tuple[str, str]]) -> None:
        """Event còn hẹn chờ thì vào `deferred`, KHÔNG vào hàng đợi chạy ngay.

        Không có bước này thì bản ghi `defer.until` chỉ là một dòng log đẹp: `_rehydrate` vẫn đẩy event vào
        `self.queue` và nhịp chạy đầu tiên gọi thẳng backend đang cạn quota.

        Mốc hẹn lưu theo GIỜ TƯỜNG nên quy được về `monotonic` của tiến trình này; hẹn đã qua thì bỏ, để event
        chạy bình thường. Event đã xong không nằm trong hàng đợi nên hẹn cũ của nó vô hại."""
        if not hen: return
        gio, mono = datetime.now(UTC), time.monotonic()
        giu: list[Envelope] = []
        for e in self.queue:
            moc, ly_do = hen.get(e.event_id, ("", ""))
            con = 0.0
            if moc:
                try: con = (datetime.fromisoformat(moc) - gio).total_seconds()
                except ValueError: con = 0.0          # mốc hỏng: thà chạy còn hơn kẹt vĩnh viễn
            if con > 0:
                self.deferred[e.event_id] = (e, ly_do or "transient:?")
                self.defer_until[e.event_id] = mono + con
            else:
                giu.append(e)
        self.queue = giu

    def _retry_con_can(self, log: list[Envelope], idx: int, rec: dict[str, Any]) -> bool:
        """Lệnh chạy lại còn ý nghĩa không, hay việc đã có người khác làm xong trong lúc chờ?

        Lệnh chạy lại chỉ sống trong RAM nên có thể nằm chờ rất lâu (người duyệt gate xong, tiến trình chết,
        hết hạn mức model...). Trong lúc đó dự án vẫn có thể đi tiếp bằng đường khác. Chạy lại một việc đã xong
        là đốt một lượt model đắt tiền để sinh ra bản trùng. Đo được khi chạy thật (2026-09-04): lệnh chạy lại
        ghi lúc 07:00:48, `spec-writer` sau đó thành công ba lần (08:15, 08:22, 08:28), nhưng lệnh cũ vẫn nổ
        lúc 09:54:42 và tiêu 317 giây `claude-opus-5` chỉ để hệ thống báo `plan.duplicate_spec` ở bước sau.

        Cách nhận biết: tra ROUTES xem event đó lẽ ra sinh ra topic nào; nếu topic đó đã có event mới cho cùng
        khoá SAU thời điểm ra lệnh, thì việc đã xong."""
        outs = {r.topic_out for r in ROUTES
                if r.topic_in == rec.get("topic") and r.agent in {rec.get("agent"), "$assignee"}}
        outs.discard(CONTEXT_ONLY)
        if not outs: return True          # không suy ra được route → giữ nguyên hành vi cũ, thà chạy lại còn hơn kẹt
        key = str(rec.get("project_id") or "")
        return not any(e.topic in outs and e.key == key for e in log[idx + 1:])

    # ---------- repo theo từng dự án (ADR-0025) ----------

    def _learn_repo(self, env: Envelope, replaying: bool = False) -> None:
        """`research-requests` mang `repo` (đường dẫn repo git của khách, tuyệt đối hoặc tương đối với cwd) và tuỳ chọn
        `base` → nhánh tích hợp riêng cho dự án đó. Không có `repo` thì dự án dùng `--repo` mặc định. Repo không phải git
        → không dừng dự án (nó vẫn chạy được không repo, PR ghi `unverified`), chỉ audit `project.repo_invalid` một lần."""
        raw = env.payload.get("repo")
        if not raw or not isinstance(raw, str): return
        pid = str(env.payload.get("project_id") or env.key)
        path = Path(raw).expanduser()
        if not (path / ".git").exists():
            if pid not in self.bad_repos:
                self.bad_repos.add(pid)
                if not replaying:
                    self._audit("project.repo_invalid", {"project_id": pid, "repo": raw, "fallback": str(self.repo) if self.repo else None},
                                project_id=pid)
            return
        base = str(env.payload.get("base") or self.base)
        current = self.project_repos.get(pid)
        if current is not None and current.repo == path.resolve() and current.base == base: return
        self.project_repos[pid] = Integration(path.resolve(), self.integration_branch, base, self.release_branch)
        self.bad_repos.discard(pid)
        self.lead.require_integration = True
        if not replaying: self._audit("project.repo", {"project_id": pid, "repo": str(path.resolve()), "base": base}, project_id=pid)

    def integration_for(self, project_id: str | None) -> Integration | None:
        """Nhánh tích hợp của dự án: repo riêng của dự án nếu có, không thì repo mặc định `--repo` (có thể None)."""
        if project_id and project_id in self.project_repos: return self.project_repos[project_id]
        return self.integration

    def _project_of_ticket(self, ticket_id: str) -> str | None:
        t = self.lead.tickets.get(ticket_id)
        return t.project_id if t is not None else None

    def _integration_of_ticket(self, ticket_id: str) -> Integration | None:
        return self.integration_for(self._project_of_ticket(ticket_id))

    def _integration_of_release(self, env: Envelope) -> Integration | None:
        """RC / release-event → dự án qua ticket đầu tiên của nó (mọi ticket một RC cùng dự án)."""
        tickets = env.payload.get("tickets") or []
        return self._integration_of_ticket(str(tickets[0])) if tickets else self.integration_for(self.project_for(env))

    def _has_integration(self) -> bool:
        return self.integration is not None or bool(self.project_repos)

    def _actionable(self, env: Envelope) -> bool:
        if env.topic == "audit-log": return trusted_decision(env) is not None  # gate.decide giả (actor không phải người) không chạy
        return env.topic not in CONTROL_TOPICS

    def _track_pause(self, env: Envelope) -> None:
        act, target = env.payload["action"], env.payload["target"]
        if act in PAUSING: self.paused.add(target)
        elif act == "resume": self.paused.discard(target)

    def _on_event(self, env: Envelope) -> None:
        if env.topic == "supervisor-actions":
            self._track_pause(env)
            if env.payload["action"] == "resume": self._retry_deferred()
        elif self._actionable(env):
            with self._qlock: self.queue.append(env)

    def latest(self, topic: str, key: str) -> Envelope | None:
        return self.bus.latest(topic, key)

    def workspace(self, ticket_id: str) -> TicketWorkspace | None:
        """Worktree của ticket, rẽ từ nhánh tích hợp của DỰ ÁN chứa ticket (tạo nhánh tích hợp nếu chưa có)."""
        integ = self._integration_of_ticket(ticket_id)
        if integ is None or integ.repo is None: return None
        with self._ws_lock: integ.ensure()  # nhiều worker cùng tạo nhánh tích hợp lần đầu → tuần tự
        return TicketWorkspace(integ.repo, ticket_id, base=integ.branch)

    # ---------- vòng lặp ----------

    @staticmethod
    def _target(env: Envelope) -> str:
        return str(env.payload.get("ticket_id") or env.key)

    def _parallel_ok(self, env: Envelope) -> bool:
        """Event chạy được cùng lúc với event khác key? Gate decide, lập kế hoạch, RC (merge tích hợp), clarifier
        (rẽ nhánh theo trạng thái) luôn chạy một mình vì chúng đổi trạng thái chung."""
        if env.topic in {"audit-log", "release-candidates", "clarification-questions"}: return False
        if env.topic in PLAN_INPUTS and PLAN_INPUTS[env.topic](env, self): return False
        return True

    def _take_batch(self, n: int) -> list[Envelope]:
        """Lấy tối đa n event có target khác nhau từ đầu hàng đợi (giữ thứ tự trong cùng key)."""
        with self._qlock:
            batch = [self.queue.pop(0)]
            if n <= 1 or not self._parallel_ok(batch[0]): return batch
            keys, i = {self._target(batch[0])}, 0
            while i < len(self.queue) and len(batch) < n:
                e = self.queue[i]; k = self._target(e)
                if self._parallel_ok(e) and k not in keys: batch.append(self.queue.pop(i)); keys.add(k)
                else: i += 1
            return batch

    def run(self, max_steps: int | None = None, workers: int | None = None) -> list[StepResult]:
        """Xử lý hàng đợi đến khi rỗng (hoặc đủ max_steps). Event bị hoãn không làm vòng lặp quay mãi.
        `workers` > 1: mỗi vòng lấy một lô event khác key và chạy song song (ADR-0012)."""
        workers = workers or self.workers
        out: list[StepResult] = []
        while self.queue and (max_steps is None or len(out) < max_steps):
            room = workers if max_steps is None else max(1, min(workers, max_steps - len(out)))
            batch = self._take_batch(room)
            if len(batch) == 1:
                results = [self.process(batch[0])]
            else:
                with ThreadPoolExecutor(max_workers=len(batch), thread_name_prefix="orch") as ex:
                    results = list(ex.map(self.process, batch))
            out += [r for r in results if r is not None]
            self._check_escalations()
            self._integrate_pending(out)
        self._check_escalations()  # supervisor escalate ở event cuối hàng đợi: gate vẫn phải mở, không chờ event kế tiếp
        self._integrate_pending(out)
        return out

    def _integrate_pending(self, out: list[StepResult]) -> None:
        """Ticket approved mà chưa lên nhánh tích hợp thì merge ngay, không phụ thuộc vào việc có event nào của nó
        được xử lý: review-results cuối cùng có thể bị hoãn (ticket vừa bị supervisor cắt ngân sách) và từ F15 ticket
        phụ thuộc chỉ bắt đầu sau khi merge — không có bước này dự án đứng im."""
        if not self._has_integration(): return
        res = StepResult("integration", "integration", "-")
        self._integrate_approved(res)
        if res.actions: out.append(res)

    def tick(self, now: datetime | None = None) -> list[StepResult]:
        """Một nhịp của chế độ watch: nạp event từ tiến trình khác, thử lại event hoãn vì lỗi transport, chạy hàng đợi,
        nhắc gate quá hạn, giao lại review quá hạn, escalate ticket im lặng quá lâu."""
        if hasattr(self.bus, "poll"): self.bus.poll()
        self._retry_deferred(only="transient:")
        results = self.run()
        remind, overdue = self.gate.due(now)
        for sid in [*remind, *overdue]:
            # Khoá `once` phải mang cả GIAI ĐOẠN: một gate luôn đi qua `remind` (12h) trước rồi mới tới `overdue`
            # (24h), nên dùng chung `gate:{sid}` là lần nhắc nuốt luôn lần quá hạn — `gate.overdue` không bao giờ
            # vào audit-log. Audit-log là bản ghi bền duy nhất và `metrics` đọc "gate chờ" từ đó, nên một gate bể
            # hạn đọc ra y hệt một gate mới chỉ được nhắc.
            pha = "overdue" if sid in overdue else "remind"
            self._audit(f"gate.{pha}", {"subject_id": sid}, once=f"gate:{sid}:{pha}")
        for sid in overdue:  # quá hạn không tự đi tiếp, nhưng cũng không im lặng: supervisor nhận việc
            self.supervisor.escalate_gate(sid, f"gate quá hạn {self.gate.timeout}", once_key=f"gate.escalate:{sid}")
        for tid, missing in self.lead.overdue_reviews(now).items():
            pr = self.latest("pull-requests", tid)
            since = self.lead.review_since[tid].isoformat()  # đọc trước: _call bên dưới có thể đóng vòng review và xoá nó
            for src in sorted(missing):
                key = f"review:{tid}:{src}:{since}"
                if pr is None or key in self.once: continue
                self._remember(key); self._audit("review.reassign", {"ticket_id": tid, "source": src}, ticket_id=tid)
                res = StepResult(pr.event_id, pr.topic, pr.key)
                self._call(REVIEW_AGENT[src], pr, Route("pull-requests", REVIEW_AGENT[src], "review-results"), res)
                results.append(res)
                # Giao lại chỉ một lần (`once`): lượt thứ hai cũng lỗi/quá hạn thì không ai giao nữa và ticket nằm
                # `in_review` mãi. Đưa cho người: supervisor escalate → ticket hoãn, gate `escalation` mở.
                failed = [a for a in res.actions if a.split(":", 1)[0] in {"error", "handler_error", "transient"}]
                if failed:
                    self._audit("review.reassign_failed", {"ticket_id": tid, "source": src, "error": failed[0][:300]}, ticket_id=tid)
                    self.supervisor.escalate_gate(tid, f"review {src} giao lại vẫn lỗi: {failed[0][:200]}", once_key=f"review.escalate:{key}")
        active = {tid for tid, st in self.lead.state.items() if st in ACTIVE_STATES}
        self.supervisor.check_timeouts(now, active=active)
        results += self.run()
        return results

    def watch(self, interval: float = 5.0, max_ticks: int | None = None) -> None:
        n = 0
        while max_ticks is None or n < max_ticks:
            try:
                for r in self.tick(): print(_fmt(r))
            except Exception as e:  # một nhịp lỗi (bus/git/handler) không được giết vòng watch
                self._audit("tick_error", {"error": f"{type(e).__name__}: {str(e)[:300]}"})
                print(f"tick_error: {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
            n += 1
            if max_ticks is None or n < max_ticks: time.sleep(interval)

    def process(self, env: Envelope) -> StepResult | None:
        if env.event_id in self.processed: return None
        res = StepResult(env.event_id, env.topic, env.key)
        if env.topic == "audit-log":
            return self._on_gate_decide(env, res)
        target = env.payload.get("ticket_id") or env.key
        if target in self.paused:
            return self._defer(env, res, f"paused:{target}")
        pid = env.payload.get("project_id")
        if pid and pid in self.paused:  # supervisor pause cả dự án (vượt ngân sách tiền)
            return self._defer(env, res, f"paused:{pid}")
        if env.topic == "research-requests": self._learn_repo(env)  # repo riêng của dự án (ADR-0025), trước khi intake chạy
        if env.topic in PLAN_INPUTS and PLAN_INPUTS[env.topic](env, self):
            return self._plan(env, res)
        if env.topic == "release-candidates" and not self._integrate(env, res):
            self._mark(env, res); return res  # RC huỷ vì xung đột: ticket đã được giao lại, không deploy
        if env.topic == "clarification-questions" and not env.payload.get("questions"):
            # clarifier không còn câu hỏi (hoặc quá round 2 → assumption): spec-writer đi thẳng từ draft sau risk
            draft = self.latest("requirements-draft", env.key)
            if draft is not None:
                self._call("spec-writer", draft, Route("requirements-draft", "spec-writer", "approved-specs"), res)
        if env.topic in {"tasks", "review-results"}:
            # Ticket approved lên nhánh tích hợp TRƯỚC khi ticket phụ thuộc (đã được delivery-lead dispatch ngay lúc
            # approve, nên đứng trước review-results trong hàng đợi) tạo worktree.
            self._integrate_approved(res)
        for r in ROUTES:
            if r.topic_in != env.topic or (r.when and not r.when(env, self)): continue
            agent = env.payload["assignee"] if r.agent == "$assignee" else r.agent
            self._call(agent, env, r, res)
        if env.topic == "release-events" and env.payload.get("env") == "production":
            if env.payload.get("status") == "deployed":
                self._deliver(env, res)
                self._open_acceptance_gate(env.key, res)
            elif env.payload.get("status") in {"rolled_back", "failed"}:
                self._rollback_delivery(env, res)
        if env.topic == "acceptance-results":
            self._close_acceptance_gate(env, res)
            self._record_lessons(env.payload["release_id"])
        self._note_closed()
        if res.transient:  # một agent chưa chạy được vì transport: giữ event lại, nhịp sau thử tiếp (agent xong rồi không chạy lại)
            stuck = next((a for a in res.actions if a.startswith("transient:")), "transient:?")
            # Backend đã nói rõ phải chờ bao lâu ("mọi backend đều đang nghỉ, thử lại sau 1515s") — tôn trọng nó.
            # Trước đây mọi nhịp tick đều hỏi lại: đo được 60 bản ghi `llm_error`/phút liên tục trong lúc pool
            # hết quota (2026-09-04), và `_rehydrate` replay TOÀN BỘ log nên bus phình làm mọi lần mở lại chậm dần.
            return self._defer(env, res, ":".join(stuck.split(":")[:2]), wait_s=retry_after_seconds(stuck))
        self._mark(env, res)
        return res

    def _note_closed(self) -> None:
        """Ghi `ticket.closed` cho ticket vừa vào trạng thái cuối. `metrics.collect` tính lead time (tasks đầu → closed)
        từ chính action này; không ai phát thì `ticket_lead_seconds` luôn rỗng và gauge Prometheus không bao giờ hiện."""
        for tid, st in list(self.lead.state.items()):
            if st != "closed": continue
            t = self.lead.tickets.get(tid)
            self._audit("ticket.closed", {"ticket_id": tid, "retry": t.retry if t else 0}, once=f"closed:{tid}",
                        ticket_id=tid, project_id=t.project_id if t else None)

    def project_for(self, env: Envelope) -> str | None:
        """Dự án của một event, kể cả khi payload không nói: release và ticket đều truy ngược được về dự án.
        Cần cho blackboard phân vùng (ADR-0018) — không có nó thì release notes của khách A ghi vào phạm vi chung."""
        if pid := env.payload.get("project_id"): return str(pid)
        tid = env.payload.get("ticket_id") or (env.key if env.topic in {"tasks", "pull-requests"} else None)
        rid = env.payload.get("release_id") or (env.key if env.topic in {"release-events", "release-candidates",
                                                                        "acceptance-results"} else None)
        if rid and not tid:
            tid = next(iter(self.lead.release_tickets.get(str(rid), [])), None)
        t = self.lead.tickets.get(str(tid)) if tid else None
        return t.project_id if t else None

    def _call(self, agent: str, env: Envelope, r: Route, res: StepResult) -> None:
        with self._lock:
            if agent in self.partial.get(env.event_id, set()): return  # đã chạy xong ở lần xử lý trước (event bị hoãn transient)
        try:
            extra = dict(r.enrich(env, self)) if r.enrich else {}
            if (pid := self.project_for(env)) and not env.payload.get("project_id"): extra["project_id"] = pid
            inp = env.model_copy(update={"payload": {**env.payload, **extra}}) if extra else env
            if r.target_env:
                out = self._release(agent, inp, r); res.actions.append(f"{agent}→{r.topic_out}:{out.key}")
            elif r.tools == "rw":
                pr = self._engineer(agent, inp, r)
                res.actions.append(f"{agent}→{r.topic_out}:{pr.key}" if pr is not None else f"{agent}→rework:{inp.key}")
            elif r.topic_out == CONTEXT_ONLY:
                g = self.runner.run_context(agent, inp)
                res.actions.append(f"{agent}→blackboard:{','.join(w['namespace'] for w in g.context_writes) or '-'}")
            elif r.many:
                g = self.runner.generate(agent, inp, r.topic_out, many=True)
                if g.context_writes: self.runner.write_context(agent, inp, g.context_writes)  # inp mang project_id (ADR-0018)
                if env.topic == "acceptance-results":  # CR từ nghiệm thu conditional phải truy được release (đóng ticket khi quyết)
                    g.payloads = [{**p, "release_id": env.key} for p in g.payloads]
                for i, p in enumerate(g.payloads):  # token/tiền tính một lần cho cả lượt, không nhân theo số payload
                    self.runner.publish(agent, inp, r.topic_out, p, key=key_for(r.topic_out, p, env.key),
                                        tokens=g.tokens if i == 0 else 0, model=g.model, generated=g if i == 0 else None)
                if not g.payloads:
                    self._audit("produced:nothing", {"agent": agent, "topic": r.topic_out, **json.loads(g.evidence())},
                                actor=agent, tokens=g.tokens, cost=g.cost_usd)
                res.actions.append(f"{agent}→{r.topic_out}×{len(g.payloads)}")
            else:
                tools = None
                if r.tools == "ro":
                    tools = self._read_only_tools(inp)
                elif r.tools == "research":
                    integ = self.integration_for(self.project_for(env))  # researcher đọc đúng codebase của dự án
                    tools = research_toolbox(integ.repo if integ is not None else None, self.web)
                g = self.runner.generate(agent, inp, r.topic_out, tools=tools, max_turns=self.max_turns)
                if r.tools == "ro" and tools is not None and not g.tool_calls:
                    # Có tool mà không chạy gì: verdict chỉ là lời khai. Không chặn (người đọc review vẫn quyết), nhưng phải hiện.
                    self._audit("review.no_tool_evidence", {"agent": agent, "topic": env.topic, "key": env.key},
                                actor=agent, ticket_id=inp.payload.get("ticket_id"), project_id=self.project_for(env))
                out = self.runner.publish(agent, inp, r.topic_out, g.payloads[0], key=key_for(r.topic_out, g.payloads[0], env.key),
                                          tokens=g.tokens, model=g.model, context_writes=g.context_writes, generated=g)
                res.actions.append(f"{agent}→{r.topic_out}:{out.key}")
            with self._lock:
                self.stats["runs"] += 1; self.partial.setdefault(env.event_id, set()).add(agent)
        except TransientError as e:  # hết retry transport: không phải lỗi agent — hoãn event, nhịp sau thử lại
            res.actions.append(f"transient:{agent}:{str(e)[:120]}"); res.transient = True
            with self._lock: self.stats["transient"] += 1
        except (RunnerError, LLMError) as e:  # runner đã ghi audit; không retry lời gọi (ADR-0005)
            res.actions.append(f"error:{agent}:{str(e)[:120]}")
            with self._lock: self.stats["errors"] += 1; self.partial.setdefault(env.event_id, set()).add(agent)
            self._after_error(env, agent, e, r, res)
        except Exception as e:  # handler xác định (delivery-lead) từ chối chuyển trạng thái: event đã ghi đĩa
            self._audit("handler_error", {"agent": agent, "error": str(e)[:300]}, ticket_id=env.payload.get("ticket_id"))
            res.actions.append(f"handler_error:{agent}:{str(e)[:120]}")
            with self._lock: self.stats["errors"] += 1; self.partial.setdefault(env.event_id, set()).add(agent)
            self._after_error(env, agent, e, r, res)

    def _after_error(self, env: Envelope, agent: str, error: Exception, r: Route, res: StepResult) -> None:
        """Mọi lỗi agent phải có người nhận: `_stall` lo chuỗi nghiên cứu, `_rework_after_error` lo agent sửa code.
        KHÔNG đường nào nhận thì đây là đường cuối — trước đây lỗi rơi vào im lặng: event vẫn bị `_mark` là đã xử
        lý, ticket treo nguyên trạng thái cũ, không gate nào mở, và `status` báo mọi chỉ số XANH trong khi dự án
        đã chết. Đo được khi chạy thật (2026-09-04): ba reviewer của `pull-requests:QLKH-001` cùng lỗi
        (`env.topic` không thuộc RESEARCH_TOPICS nên `_stall` bỏ qua, `r.tools != "rw"` nên `_rework_after_error`
        cũng bỏ qua) → 13 ticket phụ thuộc chờ vĩnh viễn mà không có một tín hiệu nào."""
        handled = self._stall(env, agent, error, res)
        handled = self._rework_after_error(env, r, error) or handled
        if handled: return
        subject = str(env.payload.get("ticket_id") or env.key)
        self._audit("agent_error_unhandled",
                    {"agent": agent, "topic": env.topic, "event_id": env.event_id, "error": str(error)[:300]},
                    ticket_id=env.payload.get("ticket_id"), project_id=self.project_for(env))
        self.supervisor.escalate_gate(subject, f"{agent} lỗi trên {env.topic}, không nhánh nào xử lý: {str(error)[:200]}",
                                      once_key=f"unhandled:{env.event_id}:{agent}")
        res.actions.append(f"unhandled:{subject}:{agent}")

    def _rework_after_error(self, env: Envelope, r: Route, error: Exception) -> bool:
        """Agent kỹ thuật lỗi (không sửa file, JSON hỏng, hết ngân sách lượt...) → ticket không được treo `dispatched`
        mãi: delivery-lead phát lại task retry+1 với hint là lỗi, hết retry → blocked → gate escalation.
        Trả True nếu nhánh này đã nhận trách nhiệm xử lý lỗi."""
        if r.tools != "rw": return False
        tid = str(env.payload.get("ticket_id") or env.key)
        if self.lead.state.get(tid) not in {"dispatched", "in_progress"}: return False
        try:
            self.lead.rework(tid, f"lần trước lỗi: {str(error)[:500]}")
        except ValueError as ex:
            self._audit("handler_error", {"agent": "delivery-lead", "error": str(ex)[:300]}, ticket_id=tid)
        return True

    def _stall(self, env: Envelope, agent: str, error: Exception, res: StepResult) -> bool:
        """Agent của chuỗi nghiên cứu lỗi → dự án không có bước kế tiếp. Ghi `project.stalled`, supervisor escalate
        (dự án bị hoãn mọi event), mở gate `escalation` subject=project_id. Ticket có cơ chế retry/blocked riêng.
        Trả True nếu nhánh này đã nhận trách nhiệm xử lý lỗi."""
        if env.topic not in RESEARCH_TOPICS: return False
        pid = str(env.payload.get("project_id") or env.key)
        with self._lock:
            self.stall_count[env.event_id] += 1; n = self.stall_count[env.event_id]
            self.stalled[pid] = {"project_id": pid, "event_id": env.event_id, "topic": env.topic, "agent": agent,
                                 "error": str(error)[:300], "attempt": n}
        self._audit("project.stalled", self.stalled[pid], project_id=pid)
        self.supervisor.escalate_gate(pid, f"{agent} lỗi trên {env.topic} (lần {n}): {str(error)[:200]}",
                                      once_key=f"stall:{env.event_id}:{n}")
        if pid not in self.gate.pending:
            self.gate.request(GateRequest(kind="escalation", subject_id=pid, created_by="supervisor",
                                          checklist=["agent_error", "decision:retry|close"]))
        res.actions.append(f"stalled:{pid}:{agent}")
        return True

    def _retry_stalled(self, pid: str, by: str, reason: str) -> bool:
        """Người duyệt gate escalation của dự án: chạy lại event đã lỗi (bỏ dấu đã xử lý, đưa về đầu hàng đợi)."""
        st = self.stalled.get(pid)
        if st is None: return False
        env = next((e for e in self.bus.replay(topic=st["topic"], key=pid) if e.event_id == st["event_id"]), None)
        if env is None: return False
        with self._lock:
            self.processed.discard(env.event_id); self.partial.pop(env.event_id, None); self.stalled.pop(pid, None)
        self._audit("project.retried", {**st, "by": by, "reason": reason}, project_id=pid)
        with self._qlock: self.queue.insert(0, env)
        return True

    def _integrate_approved(self, res: StepResult) -> None:
        """Ticket vừa approved → merge ngay vào nhánh tích hợp, không đợi RC. Ticket phụ thuộc rẽ nhánh từ nhánh tích hợp,
        nên nếu chỉ merge lúc release (nhất là khi gom release) thì ticket sau không thấy code của ticket trước:
        DHCB-5 import `dhcb.layout` của DHCB-2 và đỏ ngay dù DHCB-2 đã approved."""
        if not self._has_integration(): return
        for tid, st in list(self.lead.state.items()):
            if st != "approved" or tid in self.integrated: continue
            self._merge_ticket(tid, res, release_id=None)

    def _merge_ticket(self, tid: str, res: StepResult, release_id: str | None) -> bool:
        """merge --no-ff branch ticket vào nhánh tích hợp. Xung đột → ticket về changes_requested với hint là file xung
        đột, worktree tạo lại từ nền mới; trả về False."""
        with self._merge_lock:
            return self._merge_ticket_locked(tid, res, release_id)

    def _merge_ticket_locked(self, tid: str, res: StepResult, release_id: str | None) -> bool:
        with self._lock:
            if tid in self.integrated: return True  # thread khác vừa merge xong trong lúc ta chờ khoá
        integration = self._integration_of_ticket(tid)
        ws = self.workspace(tid)
        if integration is None or ws is None or not ws.path.exists():
            self._audit("integration.skipped", {"release_id": release_id, "ticket_id": tid, "reason": "không có worktree"}, ticket_id=tid)
            return True
        t = self.lead.tickets.get(tid)
        before = integration.sha()
        m = integration.merge(ws.branch, f"merge({tid}): {t.title if t else tid}" + (f"\n\nrelease: {release_id}" if release_id else ""))
        if m.ok and m.sha == before:
            # Branch không có gì mới so với nhánh tích hợp (vd. vừa `fresh()` sau xung đột, chưa có PR mới): không phải
            # "đã tích hợp" — đánh dấu thế là mất code của lần làm lại về sau.
            self._audit("integration.noop", {"release_id": release_id, "ticket_id": tid, "sha": before}, ticket_id=tid)
            res.actions.append(f"integration_noop:{tid}"); return True
        if m.ok:
            with self._lock: self.integrated.add(tid)
            self._audit("integration.merged", {"release_id": release_id, "ticket_id": tid, "sha": m.sha, "branch": integration.branch,
                                               "repo": str(integration.repo)}, ticket_id=tid)
            res.actions.append(f"integrated:{tid}@{m.sha}")
            started = self.lead.mark_integrated(tid)  # F15: ticket phụ thuộc bắt đầu trên nền đã có code này
            if started: res.actions.append("dispatch:" + ",".join(started))
            return True
        hint = f"xung đột với nhánh tích hợp {integration.branch} ở: {', '.join(m.conflicts or [])}. Làm lại trên nền mới."
        self._audit("integration.conflict", {"release_id": release_id, "ticket_id": tid, "conflicts": m.conflicts}, ticket_id=tid)
        try:
            ws.fresh()
            self.lead.request_changes(tid, hint)
        except (ValueError, WorkspaceError) as e:
            self._audit("handler_error", {"agent": "delivery-lead", "error": str(e)[:300]}, ticket_id=tid)
        res.actions.append(f"conflict:{tid}")
        with self._lock: self.stats["conflicts"] += 1
        return False

    def _integrate(self, rc: Envelope, res: StepResult) -> bool:
        """Mọi ticket của RC phải nằm trên nhánh tích hợp (thường đã merge lúc approved). Trả về False nếu RC bị huỷ."""
        if not self._has_integration(): return True
        rid = rc.payload["release_id"]
        if rid in self.void_releases: return False
        for tid in rc.payload.get("tickets", []):
            if tid in self.integrated: continue
            if self.lead.state.get(tid) not in {"approved", "merged"}:  # đã bị trả về (xung đột lúc approved): RC vô nghĩa
                self._audit("release.void", {"release_id": rid, "ticket_id": tid, "reason": f"ticket đang {self.lead.state.get(tid)}"}, ticket_id=tid)
                self._void(rid); res.actions.append(f"void:{rid}")
                return False
            if not self._merge_ticket(tid, res, release_id=rid):
                self._audit("release.void", {"release_id": rid, "ticket_id": tid}, ticket_id=tid)
                self._void(rid)
                return False
        return True

    def _void(self, rid: str) -> None:
        self.void_releases.add(rid)
        self.lead.void_release(rid)  # gom release: ticket approved trong RC huỷ phải vào RC kế tiếp

    def _read_only_tools(self, inp: Envelope) -> ToolBox | None:
        """Tool chỉ đọc cho QA: worktree của ticket (review PR) hoặc worktree tích hợp (hồi quy sau khi deploy staging —
        release không có ticket riêng, nhưng code vừa deploy chính là nhánh tích hợp). Không có repo → không tool."""
        if not self._has_integration(): return None
        tid = inp.payload.get("ticket_id") or (inp.key if inp.topic in {"tasks", "pull-requests"} else None)
        if tid and (ws := self.workspace(str(tid))) is not None and ws.path.exists():
            return WorkspaceTools(ws, allow_write=False).toolbox()
        integ = self._integration_of_release(inp) if inp.payload.get("release_id") else None
        if integ is not None and integ.path.exists():
            return WorkspaceTools(integ.path, allow_write=False).toolbox()
        return None

    def _engineer(self, agent: str, task: Envelope, r: Route) -> Envelope | None:
        """Ticket → PR. Có repo: agent làm trong worktree, bằng chứng do code điền. Không repo: PR đi tiếp nhưng
        `local_checks` của model bị thay bằng `{"unverified": true}` và ghi audit — không có bằng chứng giả."""
        tid = task.payload.get("ticket_id") or task.key
        budget = self.lead.tickets[tid].budget_tokens if tid in self.lead.tickets else task.payload.get("budget_tokens")
        if (b := self.supervisor.budgets.get(tid)) is not None:
            # Lần làm lại chỉ còn phần ngân sách chưa đốt (supervisor cộng dồn theo audit, kể cả phần đã cấp thêm).
            # Trừ theo ĐẦU RA cho khớp với guard trong `_turns`: trừ theo tổng token thì ticket dùng tool luôn thấy
            # ngân sách bằng 0 ngay từ lần làm lại đầu tiên (đo được: output 18868 nhưng tổng 734862).
            budget = max(b.limit - b.output_used, 0)
        ws = self.workspace(tid)
        if ws is not None:
            g = self.runner.generate_in_workspace(agent, task, ws, budget=budget, max_turns=self.max_turns)
            p = g.payloads[0]
            lc = p["local_checks"]
            if lc.get("lint") is False or lc.get("tests") is False:
                # Máy đã biết PR đỏ: không đưa qua reviewer/QA/security (tốn ba lượt để nghe lại), trả thẳng về ticket.
                bad = [k for k in ("lint", "tests") if lc.get(k) is False]
                hint = f"{'/'.join(bad)} local fail (retry {task.payload.get('retry', 0)}):\n" + \
                       "\n".join((lc.get({"lint": "lint_output", "tests": "test_output"}[k]) or "")[-1500:] for k in bad)
                self._audit("pr.rejected_local_checks", {"ticket_id": tid, "agent": agent, "failed": bad, "commit": p.get("pr_ref"),
                                                         "files": p.get("impact", {}).get("files", [])},
                            actor=agent, tokens=g.tokens, cost=g.cost_usd, ticket_id=tid, project_id=task.payload.get("project_id"))
                if tid in self.lead.tickets: self.lead.rework(tid, hint)
                return None
        else:
            g = self.runner.generate(agent, task, r.topic_out)
            p = {**g.payloads[0], "local_checks": {"unverified": True}}
            self._audit("local_checks.unverified", {"ticket_id": tid, "agent": agent, "claimed": g.payloads[0].get("local_checks")},
                        actor=agent, ticket_id=tid)
        return self.runner.publish(agent, task, r.topic_out, p, key=key_for(r.topic_out, p, task.key),
                                   tokens=g.tokens, model=g.model, context_writes=g.context_writes, generated=g)

    def _release(self, agent: str, rc: Envelope, r: Route) -> Envelope:
        """release-engineer nhận RC kèm `target_env`; đầu ra phải đúng env và release_id, nếu không thì coi là invalid."""
        rid = rc.payload["release_id"]
        integ = self._integration_of_release(rc)
        extra = {"integration_branch": integ.branch, "integration_sha": integ.sha()} if integ is not None else {}
        inp = rc.model_copy(update={"payload": {**rc.payload, "target_env": r.target_env,
                                                "gate_release": self.gate.is_approved(rid), **extra}})
        if r.target_env == "staging" and integ is not None and (full := integ.rev(integ.branch)):
            # Sha mà QA sẽ hồi quy — và sha sẽ được giao khi production duyệt (ADR-0026). Ghi audit để bền qua restart.
            with self._lock: self.release_sha[rid] = full
            self._audit("release.staged", {"release_id": rid, "sha": full, "branch": integ.branch}, project_id=self.project_for(rc))
        g = self.runner.generate(agent, inp, r.topic_out)
        p = g.payloads[0]
        if p.get("env") != r.target_env or p.get("release_id") != rid:
            self._audit("invalid_output", {"agent": agent, "expected_env": r.target_env, "got": p.get("env")},
                        actor=agent, tokens=g.tokens)
            raise RunnerError(f"{agent}: đầu ra env={p.get('env')} release_id={p.get('release_id')}, cần {r.target_env}/{rid}")
        if (want := rc.payload.get("version")) and p.get("version") != want:
            # Phiên bản là của RC (delivery-lead suy từ nội dung release), không phải lời khai của model.
            self._audit("release.version_overridden", {"release_id": rid, "claimed": p.get("version"), "version": want}, actor=agent)
            p = {**p, "version": want}
        return self.runner.publish(agent, rc, r.topic_out, p, key=rid, tokens=g.tokens, model=g.model, generated=g)

    # ---------- kế hoạch: gate spec → threat model → delivery-lead sinh ticket → gate plan → dispatch ----------

    def _plan(self, env: Envelope, res: StepResult) -> StepResult:
        project = env.payload.get("project_id") or env.key
        if env.topic == "approved-specs":
            sid = f"SPEC-{project}"
            if not self.gate.is_approved(sid):
                decided = [g for g in self.gate.history if g.subject_id == sid]
                if sid not in self.gate.pending and not decided:
                    self.gate.request(GateRequest(kind="spec", subject_id=sid, created_by=env.actor,
                                                  checklist=["prd", "acceptance-criteria", "ux-flow", "risks"]))
                if decided and sid not in self.gate.pending:
                    res.actions.append(f"gate:{sid}:{decided[-1].decision}"); self._mark(env, res); return res
                return self._defer(env, res, f"gate:{sid}")
            if not self._threat_model(env, sid, res):
                self._mark(env, res); return res
            live = [pid for pid, p in self.plans.items() if p["project_id"] == project and p["source_topic"] == "approved-specs"
                    and (pid in self.gate.pending or self.gate.is_approved(pid))]
            if live:
                # Spec publish lặp (spec-writer chạy lại, người publish hai lần) không được sinh plan thứ hai cho cùng
                # dự án: ticket trùng, hai gate plan cho một việc. Muốn lập lại thì reject plan cũ trước.
                self._audit("plan.duplicate_spec", {"project_id": project, "event_id": env.event_id, "existing": live}, project_id=project)
                res.actions.append(f"plan_skipped:{','.join(live)}"); self._mark(env, res); return res
        cal = self.supervisor.calibration()  # vòng học: bài học estimate-vs-actual quay lại người ước lượng
        inp = env.model_copy(update={"payload": {**env.payload, "estimate_calibration": cal}}) if cal else env
        try:
            g = self.runner.generate("delivery-lead", inp, "tasks", many=True)
        except TransientError as e:
            res.actions.append(f"transient:delivery-lead:{str(e)[:120]}")
            with self._lock: self.stats["transient"] += 1
            return self._defer(env, res, "transient:delivery-lead")
        except (RunnerError, LLMError) as e:
            res.actions.append(f"error:delivery-lead:{str(e)[:120]}")
            with self._lock: self.stats["errors"] += 1
            self._mark(env, res); return res
        if g.context_writes:  # C4, API contract lên blackboard TRƯỚC khi xin gate plan để người duyệt đọc được
            self.runner.write_context("delivery-lead", env, g.context_writes)
        tickets = [Task.model_validate(p) for p in g.payloads]
        problems = self._check_plan(tickets)
        n = 1 + sum(1 for p in self.plans.values() if p["project_id"] == project)
        plan_id = f"PLAN-{project}-{n}"
        plan = {"plan_id": plan_id, "project_id": project, "source_event": env.event_id, "source_topic": env.topic,
                "tickets": [t.model_dump() for t in tickets], "problems": problems,
                "threat_model": "missing" if f"SPEC-{project}" in self.missing_threat_model else "ok"}
        if problems:
            self._audit("plan_rejected", plan, actor="delivery-lead", tokens=g.tokens, cost=g.cost_usd, project_id=project)
            res.actions.append(f"plan_rejected:{'; '.join(problems)[:120]}")
            with self._lock: self.stats["errors"] += 1
            # Kế hoạch bị từ chối là ngõ cụt: không ticket nào được tạo, không gate nào mở, và không có cơ chế
            # tự lập lại. Trước đây dự án đứng im ở đây mà `status` vẫn báo mọi chỉ số xanh (đo được với dự án
            # DHCB: `tickets: []` → "kế hoạch rỗng" → im lặng vĩnh viễn). Phải hiện ra cho người quyết.
            self.supervisor.escalate_gate(project, f"kế hoạch {plan_id} bị từ chối: {'; '.join(problems)[:200]}",
                                          once_key=f"plan_rejected:{env.event_id}")
            if project not in self.gate.pending:
                self.gate.request(GateRequest(kind="escalation", subject_id=project, created_by="delivery-lead",
                                              checklist=["plan_problems", "decision:retry|close"]))
        else:
            self.plans[plan_id] = plan
            self._audit("plan.proposed", plan, actor="delivery-lead", tokens=g.tokens, cost=g.cost_usd, project_id=project)
            self.gate.request(GateRequest(kind="plan", subject_id=plan_id, created_by="delivery-lead",
                                          checklist=["tickets", "estimate_tokens", "risk_tags", "depends_on", "threat-model",
                                                     "architecture", "api-contract"]))
            res.actions.append(f"plan:{plan_id}:{len(tickets)} ticket")
            with self._lock: self.stats["plans"] += 1
        self._mark(env, res)
        return res

    def _threat_model(self, env: Envelope, sid: str, res: StepResult) -> bool:
        """Security-engineer đọc spec đã duyệt: threat model v1 lên blackboard + review-results key=SPEC-*.
        Verdict block → không lập kế hoạch (người sửa spec rồi publish lại). Trả về True nếu được đi tiếp."""
        prior = self.latest("review-results", sid)
        if prior is not None and prior.payload.get("verdict") != "block":
            return True
        try:
            g = self.runner.generate("security-engineer", env, "review-results")
            p = {**g.payloads[0], "ticket_id": sid, "source": "security"}
            self.runner.publish("security-engineer", env, "review-results", p, key=sid, tokens=g.tokens, model=g.model,
                                context_writes=g.context_writes, generated=g)
            with self._lock: self.stats["runs"] += 1
        except TransientError as e:
            res.actions.append(f"transient:security-engineer:{str(e)[:120]}")
            with self._lock: self.stats["transient"] += 1
            return True  # threat model không chặn plan; lần lập kế hoạch sau (nếu có) sẽ thử lại
        except (RunnerError, LLMError) as e:
            # Không chặn kế hoạch (người duyệt gate plan vẫn quyết được), nhưng phải hiện ra: audit riêng + đánh dấu
            # vào plan để mục `threat-model` trong checklist gate không bị tick nhầm là đã có.
            self._audit("threat_model.missing", {"subject_id": sid, "error": str(e)[:300]},
                        project_id=env.payload.get("project_id"))
            with self._lock: self.missing_threat_model.add(sid)
            res.actions.append(f"error:security-engineer:{str(e)[:120]}")
            with self._lock: self.stats["errors"] += 1
            return True
        if p["verdict"] == "block":
            self._audit("spec_blocked_by_security", {"subject_id": sid, "findings": p.get("findings", [])}, project_id=env.payload.get("project_id"))
            res.actions.append(f"spec_blocked:{sid}"); return False
        res.actions.append(f"threat-model:{sid}:{p['verdict']}"); return True

    def _check_plan(self, tickets: list[Task]) -> list[str]:
        ids = {t.ticket_id for t in tickets}; known = ids | set(self.lead.tickets)
        problems = ["kế hoạch rỗng"] if not tickets else []
        if len(ids) != len(tickets): problems.append("ticket_id trùng")
        for t in tickets:
            if t.ticket_id in self.lead.tickets: problems.append(f"{t.ticket_id} đã tồn tại")
            if t.estimate_tokens is None: problems.append(f"{t.ticket_id} thiếu estimate_tokens")
            elif t.budget_tokens < t.estimate_tokens * BUDGET_FACTOR: problems.append(f"{t.ticket_id} budget < estimate×{BUDGET_FACTOR}")
            if not t.acceptance: problems.append(f"{t.ticket_id} thiếu acceptance")
            unknown = [d for d in t.depends_on if d not in known]
            if unknown or t.ticket_id in t.depends_on: problems.append(f"{t.ticket_id} depends_on sai {unknown or 'chính nó'}")
        cyc = _cycle({t.ticket_id: [d for d in t.depends_on if d in ids] for t in tickets})
        if cyc: problems.append("depends_on vòng: " + " → ".join(cyc))
        return problems

    def _dispatch_plan(self, plan_id: str, replaying: bool = False) -> list[str]:
        plan = self.plans[plan_id]
        pending = [Task.model_validate(t) for t in plan["tickets"] if t["ticket_id"] not in self.lead.tickets]
        done: list[str] = []
        prev, self.lead.replaying = self.lead.replaying, replaying
        try:
            while pending:
                ready = [t for t in pending if all(d in self.lead.tickets for d in t.depends_on)]
                if not ready: raise ValueError(f"{plan_id}: depends_on vòng hoặc chưa biết: {[t.ticket_id for t in pending]}")
                for t in sorted(ready, key=lambda x: x.priority):
                    self.lead.dispatch(t, plan_id); pending.remove(t); done.append(t.ticket_id)
        finally:
            self.lead.replaying = prev
        return done

    # ---------- gate decide: plan → dispatch; release → production; escalation → mở lại / đóng ----------

    def _on_gate_decide(self, env: Envelope, res: StepResult) -> StepResult:
        d = _evidence(env.payload); sid, decision, by = d["subject_id"], d["decision"], d.get("by", "human")
        kind = next((g.kind for g in reversed(self.gate.history) if g.subject_id == sid), None)
        res.actions.append(f"gate:{kind}:{sid}:{decision}")
        # Đếm ở ĐÂY chứ không ở `_on_escalation_decided`: `_rehydrate` đếm mọi `gate.decide` theo subject, nên đếm
        # sống hẹp hơn (chỉ gate escalation) là hai đường lệch nhau và test bất biến restart đỏ — nó đã bắt đúng
        # lỗi này trong chính bản sửa mở gate cho lần chặn thứ hai.
        self.escalation_decided[sid] += 1
        if kind == "escalation":
            self._on_escalation_decided(sid, decision, by, d.get("reason", ""), res)
        elif decision == "approve":
            if sid in self.plans:
                try:
                    res.actions.append("dispatch:" + ",".join(self._dispatch_plan(sid)))
                except (ValueError, PermissionError) as e:
                    self._audit("plan_dispatch_error", {"plan_id": sid, "error": str(e)[:300]}); res.actions.append(f"error:{e}")
            elif sid in self.lead.release_tickets:
                rc = self.latest("release-candidates", sid)
                if rc is not None: self._call("release-engineer", rc, PROD_ROUTE, res)
        self._note_closed()
        self._mark(env, res)
        self._retry_deferred()
        return res

    def _check_escalations(self) -> None:
        """Ticket blocked (retry hết) hoặc bị supervisor escalate → gate `escalation` cho người quyết (checklist gate 'bất thường')."""
        # `self.paused` chứa cả ID DỰ ÁN (supervisor pause khi dự án chạm trần ngân sách), không chỉ ticket. Lọc
        # `t in self.lead.tickets` bỏ sót đúng nhóm đó: dự án bị pause thì mọi event của nó bị hoãn, không cổng
        # nào mở, không ai được hỏi — đo được: `paused=['P1']` mà `gates_pending={}`.
        for tid in {*self.lead.blocked(), *self.paused}:
            if self.lead.state.get(tid) in DONE_STATES: continue  # đã đóng/đã xong: không mở gate nữa
            # budget_cut cũng là "dừng chờ người" (approve = cấp thêm ngân sách): không có gate thì ticket treo im lặng.
            # `pause` cũng vậy và còn nặng hơn — dự án chạm trần ngân sách bị pause thì MỌI event của nó bị hoãn.
            # Thiếu `pause` ở đây thì `n = 0` cho một dự án bị pause, điều kiện bên dưới sai, và không gate nào mở.
            n = sum(1 for a in self.supervisor.actions
                    if a.target == tid and a.action in {"escalate", "budget_cut", "pause"})
            # Mỗi lần escalate/cắt mới, mỗi lần blocked mới → một gate mới. `escalation_decided` là thành phần bắt
            # buộc: sau khi người duyệt mở lại ticket, ticket có thể bị chặn LẠI mà supervisor không hành động gì
            # thêm (n không đổi, state vẫn `blocked`) — thiếu nó thì khoá trùng lần trước, `once` nuốt, và ticket
            # nằm im mãi không ai được hỏi. Đo được khi chạy thật (2026-09-04): QLKH-001 blocked lúc 13:25 với
            # key `escalation:QLKH-001:5:blocked` đã có trong `once` từ lần chặn trước → `gates_pending` rỗng,
            # `status` không báo gì bất thường, 13 ticket phụ thuộc đứng chờ vô hạn.
            key = f"escalation:{tid}:{n}:{self.lead.state.get(tid)}:{self.escalation_decided[tid]}"
            if tid in self.gate.pending or key in self.once: continue
            if self.lead.state.get(tid) == "blocked" or n:
                self._remember(key)
                self.gate.request(GateRequest(kind="escalation", subject_id=tid, created_by="supervisor",
                                              checklist=["root_cause", "decision:reopen|close", "hint"]))

    def _on_escalation_decided(self, tid: str, decision: str, by: str, reason: str, res: StepResult) -> None:
        if tid in self.stalled:  # escalation cấp dự án (chuỗi nghiên cứu lỗi): retry event hoặc đóng dự án
            if decision == "approve":
                self.bus.publish(Envelope(topic="supervisor-actions", key=tid, actor=by,
                                          payload={"target": tid, "action": "resume", "reason": f"escalation approve: {reason}"[:300]}))
                res.actions.append(f"retry:{tid}" if self._retry_stalled(tid, by, reason) else f"retry_failed:{tid}")
            else:
                st = self.stalled.pop(tid, {})
                self._audit("project.closed", {**st, "project_id": tid, "by": by, "reason": reason}, project_id=tid)
                res.actions.append(f"closed:{tid}")
            return
        if decision == "approve":  # mở lại với hint = lý do người duyệt, cấp thêm một ngân sách ticket
            b = self.supervisor.budgets.get(tid); t = self.lead.tickets.get(tid)
            if b and t:
                b.limit = max(b.limit, b.used) + t.budget_tokens
                self._audit("budget.extended", {"ticket_id": tid, "limit": b.limit, "by": by}, ticket_id=tid)
            if self.lead.state.get(tid) in {"blocked", "escalated"}:
                self.lead.reopen(tid, hint=reason or "người duyệt mở lại sau escalation")
            self.bus.publish(Envelope(topic="supervisor-actions", key=tid, actor=by,
                                      payload={"target": tid, "action": "resume", "reason": f"escalation approve: {reason}"[:300]}))
            res.actions.append(f"reopen:{tid}")
        elif decision in {"reject", "rollback"} and tid in self.lead.tickets:
            blocked = self.lead.close_escalated(tid); res.actions.append(f"closed:{tid}")
            self._audit("ticket.abandoned", {"ticket_id": tid, "by": by, "dependents_blocked": blocked}, ticket_id=tid,
                        project_id=self.lead.tickets[tid].project_id)
            if blocked: res.actions.append("blocked:" + ",".join(blocked))
            if self.lead.batch_releases:  # ticket đóng không còn giữ release của các ticket đã approved
                self.lead.flush_releases(self.lead.tickets[tid].project_id)

    # ---------- giao hàng thật (ADR-0026) ----------

    def _deliver(self, env: Envelope, res: StepResult) -> None:
        """Production đã deploy và gate release đã duyệt → tag `v<version>` + fast-forward `company/release` trong repo của
        dự án. Tắt (`--deliver` không bật) hoặc không có repo thì không làm gì; đã giao rồi thì không giao lại."""
        if not self.deliver: return
        rid = env.key
        if rid in self.delivered: return
        integ = self._integration_of_release(env)
        if integ is None or integ.rev(integ.branch) is None:
            self._audit("delivery.skipped", {"release_id": rid, "reason": "không có nhánh tích hợp (dự án chạy không repo)"},
                        project_id=self.project_for(env), once=f"delivery.skipped:{rid}")
            return
        if not self.gate.is_approved(rid):  # delivery-lead đã chặn trước (PermissionError); đây là lớp sau, không tin lời khai
            self._audit("delivery.skipped", {"release_id": rid, "reason": "gate release chưa duyệt"}, project_id=self.project_for(env))
            return
        version = str(env.payload.get("version") or "")
        tickets = self.lead.release_tickets.get(rid, [])
        message = f"release {rid} v{version}\n\ntickets: {', '.join(tickets) or '-'}\nintegration: {integ.branch}"
        try:
            r = integ.deliver(version, message, sha=self.release_sha.get(rid), push_remote=self.push_remote)
        except WorkspaceError as e:
            self._audit("delivery.error", {"release_id": rid, "version": version, "error": str(e)[:300]}, project_id=self.project_for(env))
            res.actions.append(f"delivery_error:{rid}"); return
        rec = {"release_id": rid, "version": version, "tag": r.tag, "sha": r.sha, "short": r.short, "branch": r.branch,
               "previous": r.previous, "tag_created": r.tag_created, "branch_moved": r.branch_moved, "problems": r.problems,
               "pushed": r.pushed, "push_error": r.push_error, "repo": str(integ.repo)}
        with self._lock: self.delivered[rid] = rec
        self._audit("delivery.done", rec, project_id=self.project_for(env))
        for pr in r.problems:  # mỗi vấn đề một dòng audit riêng để `diagnose`/console thấy ngay, không phải bới evidence
            kind_, _, detail = pr.partition(":")
            self._audit(f"delivery.{kind_}", {"release_id": rid, "tag": r.tag, "detail": detail}, project_id=self.project_for(env))
        if r.pushed is False:
            self._audit("delivery.push_failed", {"release_id": rid, "remote": self.push_remote, "error": r.push_error},
                        project_id=self.project_for(env))
        res.actions.append(f"delivered:{rid}@{r.tag}" + (f"({','.join(r.problems)})" if r.problems else ""))

    def _rollback_delivery(self, env: Envelope, res: StepResult) -> None:
        """Production rolled_back/failed của một release đã giao → `company/release` lùi về lần giao trước; tag giữ nguyên."""
        if not self.deliver: return
        rid = env.key
        d = self.delivered.get(rid)
        if d is None: return
        integ = self._integration_of_release(env)
        if integ is None: return
        try:
            r = integ.rollback_delivery(d.get("previous"), expected=str(d["sha"]), push_remote=self.push_remote)
        except WorkspaceError as e:
            self._audit("delivery.error", {"release_id": rid, "error": str(e)[:300]}, project_id=self.project_for(env))
            res.actions.append(f"rollback_error:{rid}"); return
        with self._lock: self.delivered.pop(rid, None)
        self._audit("delivery.rolled_back", {"release_id": rid, "from": d["sha"], "to": d.get("previous"), "tag": d["tag"],
                                             "branch": r.branch, "problems": r.problems, "pushed": r.pushed,
                                             "push_error": r.push_error, "status": env.payload.get("status")},
                    project_id=self.project_for(env))
        if r.pushed is False:
            self._audit("delivery.push_failed", {"release_id": rid, "remote": self.push_remote, "error": r.push_error},
                        project_id=self.project_for(env))
        res.actions.append(f"rolled_back:{rid}" + (f"({','.join(r.problems)})" if r.problems else ""))

    # ---------- vòng học ----------

    def _open_acceptance_gate(self, rid: str, res: StepResult) -> None:
        """Sau production: mở gate `acceptance` cho khách ký (ADR-0017). Là gate thật nên có hạn 24h, có nhắc ở 12h
        và được escalate khi quá hạn — trước đây chỉ là một dòng audit `uat.pending` không ai theo dõi."""
        sid = f"UAT-{rid}"
        if sid in self.gate.pending or self.gate.is_approved(sid) or f"uat:{rid}" in self.once: return
        self._remember(f"uat:{rid}")
        self.gate.request(GateRequest(kind="acceptance", subject_id=sid, created_by="account-manager",
                                      checklist=["uat-script", "acceptance-criteria", "known-issues", "signed_by"]))
        res.actions.append(f"gate:acceptance:{sid}")

    def _close_acceptance_gate(self, env: Envelope, res: StepResult) -> None:
        """Khách ký `acceptance-results` → đóng gate nghiệm thu bằng chính chữ ký đó. Four-eyes bảo đảm người ký của
        khách khác account-manager. Conditional đóng ở dạng request_changes; phần còn lại đi qua change request."""
        rid = env.payload.get("release_id"); sid = f"UAT-{rid}"
        if sid not in self.gate.pending: return
        verdict = env.payload.get("verdict")
        decision: Decision = {"accepted": "approve", "rejected": "reject"}.get(str(verdict), "request_changes")  # type: ignore[assignment]
        by = str(env.payload.get("signed_by") or env.actor)
        try:
            self.gate.decide(sid, decision, by=by, reason=f"acceptance-results: {verdict}", actor=ACTOR)
            res.actions.append(f"gate:acceptance:{sid}:{decision}")
        except (KeyError, PermissionError) as e:
            self._audit("handler_error", {"agent": "account-manager", "error": str(e)[:300]})

    def _record_lessons(self, rid: str) -> None:
        """Sau nghiệm thu: estimate vs actual mỗi ticket đã closed → supervisor.knowledge + blackboard `knowledge`."""
        for tid in self.lead.release_tickets.get(rid, []):
            if self.lead.state.get(tid) != "closed" or f"lesson:{tid}" in self.once: continue
            self._remember(f"lesson:{tid}")
            t = self.lead.tickets[tid]; b = self.supervisor.budgets.get(tid)
            actual = b.used if b else 0; est = t.estimate_tokens or 0
            lesson = {"ticket_id": tid, "assignee": t.assignee, "estimate_tokens": est, "actual_tokens": actual,
                      "review_tokens": b.review_used if b else 0,
                      "ratio": round(actual / est, 2) if est else None, "retry": t.retry, "risk_tags": t.risk_tags}
            self.supervisor.record_lesson(context=f"{t.project_id}/{tid} {t.title}", problem=f"retry={t.retry}",
                                          solution=t.hint or "", evidence=json.dumps(lesson, ensure_ascii=False))
            self.blackboard.write("supervisor", "knowledge", f"audit-log:lesson:{tid}", json.dumps(lesson, ensure_ascii=False))

    # ---------- người can thiệp giữa vòng (ADR-0012) ----------

    def comment(self, ticket_id: str, by: str, text: str) -> Task:
        """Nhận xét của người cho ticket đang chạy: ghi audit `human.comment` và phát lại task với hint = nhận xét
        (delivery-lead không tính retry). Ticket blocked/escalated dùng gate escalation."""
        if not by.split(":", 1)[0] == "human": raise ValueError("by phải là human:<tên>")
        t = self.lead.tickets.get(ticket_id)
        if t is None: raise ValueError(f"không có ticket {ticket_id}")
        self._audit("human.comment", {"ticket_id": ticket_id, "by": by, "text": text[:2000], "state": self.lead.state.get(ticket_id)},
                    actor=by, ticket_id=ticket_id, project_id=t.project_id)
        return self.lead.human_hint(ticket_id, text)

    def takeover(self, ticket_id: str, by: str, message: str | None = None) -> Envelope:
        """Người sửa tay trong worktree `ticket/<id>` rồi giao lại: CODE chạy lint/test thật, commit (nếu còn thay đổi chưa
        commit), publish `pull-requests` dưới tên người với `local_checks.verified_by=workspace`; reviewer/QA/security review
        như PR của agent. Ticket đang `in_review` thì PR này thay PR của agent (vòng review làm lại)."""
        if not by.split(":", 1)[0] == "human": raise ValueError("by phải là human:<tên>")
        t = self.lead.tickets.get(ticket_id); st = self.lead.state.get(ticket_id)
        if t is None: raise ValueError(f"không có ticket {ticket_id}")
        if st not in {"dispatched", "in_progress", "in_review"}:
            raise ValueError(f"{ticket_id}: chỉ tiếp quản ticket dispatched/in_review (đang {st})")
        ws = self.workspace(ticket_id)
        if ws is None or not ws.path.exists():
            raise ValueError(f"{ticket_id}: không có worktree (cần --repo; worktree ở <repo>/.worktrees/{ticket_id})")
        if not ws.has_changes(): raise ValueError(f"{ticket_id}: worktree không có thay đổi so với nhánh tích hợp")
        checks = ws.run_checks()
        sha = ws.commit_all(message or f"feat({ticket_id}): {by} tiếp quản — {t.title}"[:72]) if _git(ws.path, "status", "--porcelain") \
            else _git(ws.path, "rev-parse", "--short", "HEAD")
        files = ws.changed_files()
        p = {"ticket_id": ticket_id, "branch": ws.branch, "pr_ref": sha, "summary": message or f"{by} tiếp quản ticket",
             "impact": {"files": files}, "local_checks": {**checks, "verified_by": "workspace"}}
        self._audit("human.takeover", {"ticket_id": ticket_id, "by": by, "commit": sha, "files": files,
                                       "lint": checks["lint"], "tests": checks["tests"]}, actor=by, ticket_id=ticket_id, project_id=t.project_id)
        return self.bus.publish(Envelope(topic="pull-requests", key=ticket_id, actor=by, payload=p))

    # ---------- hoãn / đánh dấu / audit ----------

    def _defer(self, env: Envelope, res: StepResult, reason: str, wait_s: float | None = None) -> StepResult:
        """`wait_s`: backend nói rõ phải chờ bao lâu → không thử lại trước mốc đó (xem `_retry_deferred`)."""
        with self._lock:
            self.deferred[env.event_id] = (env, reason); res.deferred = reason; self.stats["deferred"] += 1
            if wait_s and wait_s > 0:
                self.defer_until[env.event_id] = time.monotonic() + float(wait_s)
                res.deferred = f"{reason} (chờ {int(wait_s)}s)"
                ghi_hen = True
            else:
                ghi_hen = False
        if ghi_hen:
            # Mốc hẹn phải BỀN và theo GIỜ TƯỜNG. `defer_until` dùng `time.monotonic()` — vô nghĩa ở tiến trình
            # khác — và cả `deferred` lẫn nó đều chỉ sống trong RAM, trong khi `_rehydrate` đẩy mọi event chưa
            # xử lý thẳng vào `self.queue`. Nên restart giữa lúc chờ quota là mất hẹn và đập ngay vào backend
            # đã cạn: vô ích, bẩn audit-log, và có thể bị phạt nặng hơn.
            #
            # Đo được khi chạy thật (2026-09-04 15:46:30): cả hai backend trả 429, hệ thống hoãn 2010s đúng
            # theo hẹn; nhưng `status` từ tiến trình khác đọc ra `deferred: {}` — mốc hẹn không tồn tại ngoài
            # RAM của tiến trình đang chạy.
            self._audit("defer.until", {"event_id": env.event_id, "reason": reason, "wait_s": int(wait_s or 0),
                                        "until": (datetime.now(UTC) + timedelta(seconds=float(wait_s or 0))).isoformat()},
                        ticket_id=env.payload.get("ticket_id"), project_id=env.payload.get("project_id"))
        return res

    def _retry_deferred(self, only: str | None = None) -> None:
        """Đưa event hoãn về đầu hàng đợi; `only` = tiền tố lý do (vd. "transient:") để chỉ thử lại loại đó.
        Event nào backend đã hẹn giờ (`defer_until`) thì chờ đúng hẹn — hỏi lại sớm hơn chỉ tốn một dòng lỗi."""
        now = time.monotonic()
        with self._lock, self._qlock:
            picked = {k: v for k, v in self.deferred.items()
                      if (only is None or v[1].startswith(only)) and self.defer_until.get(k, 0.0) <= now}
            for k in picked: self.deferred.pop(k); self.defer_until.pop(k, None)
            self.queue[:0] = [e for e, _ in picked.values()]

    def _mark(self, env: Envelope, res: StepResult) -> None:
        with self._lock:
            self.processed.add(env.event_id); self.partial.pop(env.event_id, None)
        self._audit("orchestrated", {"event_id": env.event_id, "topic": env.topic, "actions": res.actions},
                    ticket_id=env.payload.get("ticket_id") or (env.key if env.topic == "tasks" else None),
                    project_id=env.payload.get("project_id"))

    def _remember(self, key: str) -> None:
        """Ghi nhớ bền vững một việc chỉ làm một lần (khôi phục qua replay)."""
        with self._lock: self.once.add(key)
        self._audit("once", {"key": key})

    def _audit(self, action: str, data: dict[str, Any], actor: str = ACTOR, tokens: int = 0, once: str | None = None,
               ticket_id: str | None = None, project_id: str | None = None, cost: float = 0.0) -> None:
        if once:
            with self._lock:
                if once in self.once: return
                self.once.add(once)
            self._audit("once", {"key": once})
        a = AuditLog(actor=actor, action=action, tokens=tokens, ticket_id=ticket_id, project_id=project_id,
                     evidence=json.dumps(data, ensure_ascii=False), cost_usd=cost)
        self.bus.publish(Envelope(topic="audit-log", key=actor, actor=actor, payload=a.model_dump()))

    def _integration_status(self) -> dict[str, Any] | None:
        """Nhánh tích hợp mặc định (`--repo`) + của từng dự án có repo riêng; None khi chưa có worktree tích hợp nào."""
        def one(integ: Integration) -> dict[str, str] | None:
            if not integ.path.exists(): return None
            return {"branch": integ.branch, "sha": integ.sha(), "repo": str(integ.repo)}
        default = one(self.integration) if self.integration is not None else None
        projects = {pid: st for pid, integ in self.project_repos.items() if (st := one(integ)) is not None}
        if default is None and not projects: return None
        out: dict[str, Any] = dict(default or {})
        if projects: out["projects"] = projects
        return out

    def _deadlock_warnings(self) -> list[str]:
        """Còn ticket chưa xong mà KHÔNG đường nào có thể chạy tiếp → nói thẳng ra.

        Mọi trường trong `status()` đều mô tả trạng thái, không trường nào trả lời "có việc gì chạy được không".
        Nên một dự án chết vẫn đọc ra hoàn toàn bình thường: `queue: 0`, `stalled: {}`, `gates_pending: {}` —
        ba chỉ số xanh vì rỗng, mà rỗng ở đây chính là triệu chứng.

        Đo được khi chạy thật (2026-09-04): QLKH-001 `blocked` lúc 13:25 không mở được gate (xem
        `_check_escalations`), 13 ticket phụ thuộc đứng chờ. `status` không có gì bất thường trong 26 phút; chỉ
        vì có người ngồi đọc từng finding mới phát hiện. Đây là lớp phòng thủ cuối: kể cả khi một nhánh cụ thể
        quên mở gate, câu hỏi "còn việc nào chạy được không" vẫn phải được trả lời trung thực.

        `queue` đếm event chưa được đánh dấu `orchestrated`, nên lượt agent đang bay vẫn tính là có việc — cảnh
        báo này không kêu oan khi hệ thống chỉ đang chờ model trả lời."""
        live = {t: st for t, st in self.lead.state.items() if st not in DONE_STATES}
        if not live: return []
        # KHÔNG miễn trừ `self.paused`: pause luôn cần người gỡ, mà người chỉ được hỏi qua gate. Pause mà không
        # có gate nào chính là ca bế tắc cần kêu to nhất — bản đầu của cảnh báo này miễn trừ `paused` nên mù
        # đúng ca đó (`paused=['P1']`, `gates_pending={}`, `warnings=[]`).
        if self.queue or self.deferred or self.gate.pending or self.stalled: return []
        return [f"khong co viec nao chay duoc: {len(live)} ticket chua xong "
                f"({', '.join(f'{t}={st}' for t, st in sorted(live.items())[:5])}"
                f"{', ...' if len(live) > 5 else ''}) ma queue/gate/deferred/stalled deu rong"]

    def status(self) -> dict[str, Any]:
        return {"warnings": self._deadlock_warnings(),
                "queue": len(self.queue), "deferred": {k: v[1] for k, v in self.deferred.items()},
                "paused": sorted(self.paused), "tickets": dict(self.lead.state), "waiting": self.lead.waiting(),
                "blocked": self.lead.blocked(), "releases": self.lead.releases,
                "stalled": {pid: f"{st['agent']} lỗi trên {st['topic']}: {st['error'][:120]}" for pid, st in self.stalled.items()},
                "gates_pending": {sid: g.kind for sid, g in self.gate.pending.items()}, "plans": list(self.plans),
                "blackboard": {key: {"v": sc.version, "ref": sc.content_ref, "chars": len(sc.content or ""),
                                     "file": str(p) if (p := self.blackboard.path(sc.namespace,
                                                                                  project_id=sc.project_id)) else None}
                               for key, sc in self.blackboard.all().items()},
                "workers": self.workers, "web": self.web is not None,
                "cost_usd": self.supervisor.sprint_report()["cost_usd_total"],
                "integration": self._integration_status(), "void_releases": sorted(self.void_releases),
                "delivery": {rid: {k: d.get(k) for k in ("version", "tag", "short", "branch", "problems", "pushed")}
                             for rid, d in sorted(self.delivered.items())},
                "stats": dict(self.stats), "events": len(self.bus)}


def _cycle(graph: dict[str, list[str]]) -> list[str]:
    """Một chu trình trong đồ thị phụ thuộc (rỗng nếu không có) — bắt ở bước lập kế hoạch, trước gate, không để tới dispatch."""
    state: dict[str, int] = {}; stack: list[str] = []
    def visit(n: str) -> list[str]:
        state[n] = 1; stack.append(n)
        for m in graph.get(n, []):
            if state.get(m) == 1: return [*stack[stack.index(m):], m]
            if m not in state and (c := visit(m)): return c
        stack.pop(); state[n] = 2; return []
    for n in graph:
        if n not in state and (c := visit(n)): return c
    return []


def _evidence(a: dict[str, Any]) -> dict[str, Any]:
    try:
        d = json.loads(a.get("evidence") or "{}")
    except json.JSONDecodeError:
        return {}
    return d if isinstance(d, dict) else {}


def _fmt(r: StepResult) -> str:
    tail = f"  hoãn: {r.deferred}" if r.deferred else "  " + "; ".join(r.actions)
    return f"{r.topic:<22} {r.key:<14}{tail}"


def main(argv: list[str] | None = None) -> int:
    """python -m company.orchestrator run [--db] [--max-steps N] [--watch GIÂY] [--workers N] [--web]
       python -m company.orchestrator publish <topic> <file.json> --actor human:po [--key K]
       python -m company.orchestrator decide-change <change_id> accepted|rejected|deferred --by human:po
       python -m company.orchestrator comment <ticket> --by human:x --text "..."   # hint giữa vòng, không tính retry
       python -m company.orchestrator takeover <ticket> --by human:x [--message]   # người sửa tay trong worktree rồi giao lại
       python -m company.orchestrator status | report | metrics [--prometheus] | show <namespace> [--db]"""
    ap = argparse.ArgumentParser(description="Orchestrator: vòng lặp tự động topic → agent → topic")
    ap.add_argument("--db", type=Path, default=Path("company.sqlite"))
    ap.add_argument("--repo", type=Path, help="git repo của khách: khối kỹ thuật sửa code thật trong worktree ticket/<id>")
    ap.add_argument("--base", default="HEAD", help="nhánh/commit gốc để tạo nhánh tích hợp lần đầu (mặc định HEAD)")
    ap.add_argument("--integration", default="company/integration", help="nhánh tích hợp: ticket rẽ từ đây, merge vào đây")
    ap.add_argument("--artifacts", type=Path, help="artifact store của blackboard (mặc định <db>.artifacts/)")
    ap.add_argument("--workers", type=int, default=1, help="số event khác key chạy song song (mặc định 1)")
    ap.add_argument("--web", action="store_true", help="cho researcher tool web_search/fetch_url (mạng ra ngoài)")
    ap.add_argument("--batch-release", action="store_true",
                    help="gom mọi ticket approved của dự án vào một RC khi không còn ticket đang chạy (mặc định: mỗi ticket một RC)")
    ap.add_argument("--deliver", action="store_true",
                    help="ADR-0026: production duyệt + deploy → tag v<version> và fast-forward nhánh release trong repo khách")
    ap.add_argument("--push-remote", help="remote của repo khách để push nhánh release + tag sau khi giao (mặc định: không push)")
    ap.add_argument("--release-branch", default="company/release", help="nhánh 'đang chạy production' trong repo khách")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rn = sub.add_parser("run"); rn.add_argument("--max-steps", type=int); rn.add_argument("--watch", type=float,
        help="chạy liên tục, mỗi N giây nạp event mới (gate CLI, publish) rồi xử lý")
    pb = sub.add_parser("publish"); pb.add_argument("topic"); pb.add_argument("file", type=Path)
    pb.add_argument("--actor", required=True); pb.add_argument("--key")
    dc = sub.add_parser("decide-change", help="khách quyết định change request (sau khi delivery-lead ước lượng impact)")
    dc.add_argument("change_id"); dc.add_argument("decision", choices=["accepted", "rejected", "deferred"])
    dc.add_argument("--by", required=True); dc.add_argument("--reason", default="")
    cm = sub.add_parser("comment", help="người nhận xét ticket đang chạy: phát lại task với hint, không tính retry")
    cm.add_argument("ticket_id"); cm.add_argument("--by", required=True); cm.add_argument("--text", required=True)
    tk = sub.add_parser("takeover", help="người đã sửa tay trong worktree ticket: chạy lint/test, commit, publish PR dưới tên người")
    tk.add_argument("ticket_id"); tk.add_argument("--by", required=True); tk.add_argument("--message")
    sub.add_parser("status"); sub.add_parser("report", help="sprint report: estimate vs actual, chi phí, hành động supervisor")
    dg = sub.add_parser("diagnose", help="chẩn đoán: gom lỗi thô thành khuôn lặp lại, ticket quay vòng, gate chờ quyết")
    dg.add_argument("--top", type=int, default=10, help="số khuôn lỗi in ra (mặc định 10)")
    mt = sub.add_parser("metrics", help="metrics từ audit-log: gọi/token/USD/thời gian theo agent, model, ticket; gate chờ")
    mt.add_argument("--prometheus", action="store_true", help="xuất text exposition format cho Prometheus")
    sh = sub.add_parser("show", help="in toàn văn artifact mới nhất của một namespace blackboard"); sh.add_argument("namespace")
    sh.add_argument("--project", help="dự án của artifact (ADR-0018); bỏ qua nếu chỉ có một dự án dùng namespace đó")
    ns = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # Windows console cp1252
        if hasattr(stream, "reconfigure"): stream.reconfigure(encoding="utf-8")
    from .sqlite_bus import Lease, LeaseError, SQLiteBus
    bus = SQLiteBus(ns.db)
    if ns.cmd == "publish":
        if not is_human(ns.actor):  # CLI là cửa của người; giả danh agent/orchestrator từ đây là vượt quyền producer của bus
            print(f"--actor phải là người (human:<tên>), không phải {ns.actor!r}", file=sys.stderr); return 2
        payload = json.loads(ns.file.read_text(encoding="utf-8"))
        key = ns.key or payload.get("ticket_id") or payload.get("release_id") or payload.get("project_id") or payload.get("change_id")
        if not key: print("cần --key", file=sys.stderr); return 2
        env = bus.publish(Envelope(topic=ns.topic, key=key, actor=ns.actor, payload=payload))
        print(f"published {env.topic} key={env.key} event={env.event_id}"); return 0
    if ns.cmd == "decide-change":
        cr = next(reversed(list(bus.replay(topic="change-requests", key=ns.change_id))), None)
        if cr is None: print(f"không có change-request {ns.change_id}", file=sys.stderr); return 2
        impact = next((_evidence(e.payload) for e in reversed(list(bus.replay(topic="audit-log")))
                       if e.payload.get("action") == "change.impact" and _evidence(e.payload).get("change_id") == ns.change_id), {})
        payload = {**cr.payload, "decision": ns.decision, "impact": {**cr.payload.get("impact", {}), **impact.get("impact", {}),
                                                                       "decided_by": ns.by, "reason": ns.reason}}
        env = bus.publish(Envelope(topic="change-requests", key=ns.change_id, actor=ns.by, payload=payload))
        print(f"{ns.change_id}: {ns.decision} by {ns.by} event={env.event_id}"); return 0
    if ns.cmd == "metrics":
        from .metrics import collect, prometheus
        m = collect(bus)
        print(prometheus(m) if ns.prometheus else json.dumps(m, ensure_ascii=False, indent=2)); return 0
    if ns.cmd == "diagnose":
        from .metrics import diagnose
        print(json.dumps(diagnose(bus, top=ns.top), ensure_ascii=False, indent=2)); return 0
    from .llm import FakeClient, make_client
    # Chỉ `run` gọi model; status/report/show/comment/takeover là việc của người và của code, không được đòi SDK/API key.
    orch = Orchestrator(bus, make_client() if ns.cmd == "run" else FakeClient(), repo=ns.repo, base=ns.base, integration=ns.integration, workers=ns.workers,
                        web=ns.web, batch_releases=ns.batch_release, artifacts=ns.artifacts or artifact_store(ns.db),
                        deliver=ns.deliver, push_remote=ns.push_remote, release_branch=ns.release_branch)
    if ns.cmd == "status":
        print(json.dumps(orch.status(), ensure_ascii=False, indent=2)); return 0
    if ns.cmd == "report":
        print(json.dumps(orch.supervisor.sprint_report(), ensure_ascii=False, indent=2)); return 0
    if ns.cmd == "show":
        sc = orch.blackboard.read(ns.namespace, ns.project)
        if sc is None and ns.project is None:
            # Blackboard phân vùng theo dự án: không nêu --project thì chỉ đoán được khi đúng một dự án có namespace này.
            found = [c for (pid, nsp), c in orch.blackboard._latest.items() if nsp == ns.namespace]
            if len(found) == 1: sc = found[0]
            elif len(found) > 1:
                projects = ", ".join(sorted(str(c.project_id) for c in found))
                print(f"{ns.namespace} có ở nhiều dự án ({projects}); nêu --project", file=sys.stderr); return 2
        if sc is None: print(f"chưa có namespace {ns.namespace}", file=sys.stderr); return 2
        scope = f" [{sc.project_id}]" if sc.project_id else ""
        print(f"# {ns.namespace} v{sc.version}{scope} — {sc.content_ref}\n# {sc.summary}\n")
        print(sc.content if sc.content is not None else "(chỉ có con trỏ, không có toàn văn)"); return 0
    if ns.cmd in {"comment", "takeover"}:
        try:
            if ns.cmd == "comment":
                t = orch.comment(ns.ticket_id, ns.by, ns.text); print(f"{t.ticket_id}: phát lại với hint (retry={t.retry})")
            else:
                env = orch.takeover(ns.ticket_id, ns.by, ns.message)
                print(f"{env.key}: PR {env.payload['pr_ref']} của {ns.by}, lint={env.payload['local_checks']['lint']} "
                      f"tests={env.payload['local_checks']['tests']} event={env.event_id}")
        except (ValueError, WorkspaceError) as e:
            print(str(e), file=sys.stderr); return 2
        return 0
    try:
        lease = Lease(ns.db); lease.acquire()
    except LeaseError as e:
        print(str(e), file=sys.stderr); return 3
    try:
        if ns.watch:
            try: orch.watch(interval=ns.watch)
            except KeyboardInterrupt: pass
        else:
            for r in orch.tick() if ns.max_steps is None else orch.run(ns.max_steps): print(_fmt(r))
    finally:
        lease.release()
    print(json.dumps(orch.status(), ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
