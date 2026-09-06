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

ADR-0027 (`--deliver`): production được duyệt và deploy → tag `v<version>` + fast-forward `company/release` trong repo
khách (`Integration.deliver`); production rolled_back/failed → lùi con trỏ nhánh release về lần giao trước (tag giữ).
`--push-remote` đẩy lên remote của khách; lỗi push chỉ vào audit. `main` của khách vẫn không bị chạm.
"""
from __future__ import annotations

import json
import sys
import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .blackboard import Blackboard
from .bus import InMemoryBus
from .delivery import DONE_STATES, DeliveryLead
from .events import BUDGET_FACTOR, Envelope, Task
from .gate_cli import PersistentGate
from .gates import Decision, GateRequest
from .llm import LLMError, ModelClient, TransientError
from .orch import rehydrate, scheduler, verify, worktree_flow
from .orch.cli import main, source_fingerprint
from .orch.routes import (
    ACTOR,
    PLAN_INPUTS,
    PROD_ROUTE,
    RESEARCH_TOPICS,
    REVIEW_AGENT,
    ROUTES,
    SPEC_RUNTIME_REWORKS,
    STAGING_ROUTE,
    Route,
    _dict_of,
    _with_draft,
    check_routes,
    key_for,
    spec_runtime_gap,
)

# Không dùng trong file này nhưng là hợp đồng công khai của module (gate_brief.py, test) — giữ re-export tường
# minh bằng alias cùng tên để ruff không coi là import thừa.
from .orch.routes import BLIND_STRIP as BLIND_STRIP
from .orch.routes import ENGINEERING as ENGINEERING
from .orch.routes import MAX_CONFLICT_RETRIES as MAX_CONFLICT_RETRIES
from .orch.routes import THREAT_ROUTE as THREAT_ROUTE
from .orch.routes import _can_author_tests as _can_author_tests
from .orch.routes import _has_dispute as _has_dispute
from .orch.routes import _test_scope_ok as _test_scope_ok
from .orch.routes import _with_chan_doan as _with_chan_doan
from .orch.routes import _with_diff as _with_diff
from .orch.state import OrchState, install_aliases
from .registry import AgentSpec, load_agents
from .routing import retry_after_seconds
from .runner import CONTEXT_ONLY, AgentRunner, RunnerError
from .supervisor import Supervisor
from .web import WebTools, research_toolbox
from .workspace import Integration, WorkspaceError


@dataclass
class StepResult:
    event_id: str
    topic: str
    key: str
    actions: list[str] = field(default_factory=list)
    deferred: str | None = None  # lý do hoãn (gate:..., paused:..., transient:...)
    transient: bool = False      # một agent gặp lỗi transport sau khi đã retry → event sẽ được thử lại ở nhịp sau


class ReloadRequested(Exception):
    """Vòng watch xin khởi động lại tiến trình vì mã nguồn đã đổi (xem `Orchestrator.watch`)."""



class Orchestrator:
    if TYPE_CHECKING:
        # Bí danh do `install_aliases` gắn lúc chạy (ADR-0034). mypy không thấy property gắn động nên
        # khai báo lại kiểu ở đây; nguồn sự thật vẫn là `OrchState`, và `test_orch_state_rehydrate`
        # bắt lỗi nếu hai danh sách lệch nhau.
        processed: set[str]
        queue: list[Envelope]
        partial: dict[str, set[str]]
        deferred: dict[str, tuple[Envelope, str]]
        defer_until: dict[str, float]
        once: set[str]
        plans: dict[str, dict[str, Any]]
        integrated: set[str]
        conflict_retries: Counter[str]
        missing_threat_model: set[str]
        spec_runtime_reworks: Counter[str]
        release_sha: dict[str, str]
        delivered: dict[str, dict[str, Any]]
        void_releases: set[str]
        stalled: dict[str, dict[str, Any]]
        stall_count: Counter[str]
        unhandled: dict[str, dict[str, Any]]
        escalation_decided: Counter[str]
        debt_gate: dict[str, dict[str, Any]]
        paused: set[str]
        project_repos: dict[str, Integration]
        bad_repos: set[str]
        stats: Counter[str]
        reload_on_change: bool

    def __init__(self, bus: InMemoryBus, client: ModelClient, agents: dict[str, AgentSpec] | None = None,
                 max_retries: int = 3, repo: Path | None = None, base: str = "HEAD", max_turns: int = 25,
                 batch_releases: bool = False,
                 integration: str = "company/integration", workers: int = 1, web: WebTools | bool = False,
                 artifacts: Path | None = None, project_budget_usd: float | None = None,
                 deliver: bool = False, push_remote: str | None = None, release_branch: str = "company/release",
                 test_author: bool = False):
        self.bus = bus
        # ADR-0028: bật vai viết test độc lập. Mặc định TẮT — nó thêm một lượt model mỗi ticket, nên phải là
        # lựa chọn có ý thức của người vận hành, không phải thứ tự bật lên sau một lần `git pull`.
        self.test_author = bool(test_author)
        self.repo, self.max_turns = (Path(repo) if repo else None), max_turns
        self.workers = max(1, int(workers))
        self.web = web if isinstance(web, WebTools) else (WebTools() if web else None)
        self._lock = threading.RLock()   # trạng thái orchestrator (processed, deferred, once, stats) — KHÔNG publish khi đang giữ
        self._qlock = threading.RLock()  # hàng đợi; _on_event (chạy dưới lock của bus) chỉ chạm lock này
        self._ws_lock = threading.RLock()
        self._merge_lock = threading.RLock()  # merge vào nhánh tích hợp chạy một mình (ADR-0012 §7), kể cả khi --workers>1
        self.state = OrchState()
        if self.repo is not None and not (self.repo / ".git").exists():
            raise ValueError(f"repo không phải git repository: {self.repo}")
        # `--repo` là repo MẶC ĐỊNH của tiến trình. Từng dự án có thể chỉ repo riêng ngay trong `research-requests`
        # (payload.repo, payload.base — ADR-0025): học từ log lúc mở lại và từ event lúc chạy, ticket của dự án nào
        # làm trong worktree của repo đó. Repo sai (không có .git) → audit một lần, dự án rơi về mặc định.
        self.deliver, self.push_remote, self.release_branch = bool(deliver), push_remote, release_branch
        self.integration = Integration(self.repo, integration, base, release_branch) if self.repo is not None else None
        self.base, self.integration_branch = base, integration
        self.source_fp = source_fingerprint()  # mã nguồn lúc khởi động — `watch(reload=True)` so với đây
        self.agents = agents or load_agents()
        bad = check_routes(self.agents)
        if bad: raise ValueError("ROUTES lệch front matter: " + "; ".join(bad))
        self.blackboard = Blackboard(bus, store=artifacts)
        self.gate = PersistentGate(bus)
        self.lead = DeliveryLead(bus, self.gate, max_retries=max_retries, batch_releases=batch_releases)
        self.lead.require_integration = self.integration is not None
        budget_usd = project_budget_usd if project_budget_usd is not None else getattr(client, "budget_usd", None)
        # ADR-0032: ngưỡng "nợ kiến trúc treo" cấu hình cùng chỗ với trần ngân sách (llm.yaml `debt_reviews`).
        self.supervisor = Supervisor(bus, max_retries=max_retries, project_budget_usd=budget_usd,
                                     debt_threshold=int(getattr(client, "debt_reviews", None) or 3))
        self.runner = AgentRunner(bus, client, self.agents, self.blackboard)
        self._rehydrate()
        bus.subscribe("*", self._on_event)

    # ---------- khôi phục từ log ----------

    _rehydrate = rehydrate.rehydrate
    _nap_lai_hen = rehydrate._nap_lai_hen
    _retry_con_can = rehydrate._retry_con_can


    # ---------- worktree, repo theo dự án, gộp nhánh tích hợp (ADR-0034: orch/worktree_flow.py) ----------

    _learn_repo = worktree_flow.learn_repo
    integration_for = worktree_flow.integration_for
    _project_of_ticket = worktree_flow.project_of_ticket
    _integration_of_ticket = worktree_flow.integration_of_ticket
    _has_integration = worktree_flow.has_integration
    workspace = worktree_flow.workspace
    _integrate_approved = worktree_flow.integrate_approved
    _branch_ahead = worktree_flow.branch_ahead
    _merge_ticket = worktree_flow.merge_ticket
    _merge_ticket_locked = worktree_flow.merge_ticket_locked
    _read_only_tools = worktree_flow.read_only_tools
    _author_tests = worktree_flow.author_tests
    _engineer = worktree_flow.engineer
    comment = worktree_flow.comment
    takeover = worktree_flow.takeover





    def _integration_of_release(self, env: Envelope) -> Integration | None:
        """RC / release-event → dự án qua ticket đầu tiên của nó (mọi ticket một RC cùng dự án)."""
        tickets = env.payload.get("tickets") or []
        return self._integration_of_ticket(str(tickets[0])) if tickets else self.integration_for(self.project_for(env))





    def latest(self, topic: str, key: str) -> Envelope | None:
        return self.bus.latest(topic, key)

    # ---------- vòng lặp chính, hoãn/đánh dấu/audit (ADR-0034: orch/scheduler.py) ----------

    _actionable = scheduler._actionable
    _track_pause = scheduler._track_pause
    _on_event = scheduler._on_event
    _target = staticmethod(scheduler.target)
    _parallel_ok = scheduler._parallel_ok
    _take_batch = scheduler._take_batch
    run = scheduler.run
    _integrate_pending = scheduler._integrate_pending
    tick = scheduler.tick
    watch = scheduler.watch
    _maybe_reload = scheduler._maybe_reload
    _defer = scheduler._defer
    _retry_deferred = scheduler._retry_deferred
    _mark = scheduler._mark
    _remember = scheduler._remember
    _audit = scheduler._audit


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
        if env.topic in {"tasks", "pull-requests"} and self._superseded(env, res): return res
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
        if env.topic == "release-events" and env.payload.get("status") == "pending_human":
            self._release_paused(env, res)
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

    def _superseded(self, env: Envelope, res: StepResult) -> bool:
        """Event `tasks`/`pull-requests` còn trong hàng đợi (hoãn vì paused/transient, hoặc mở lại bus) mà ticket đã
        đi tiếp thì là hàng cũ: bỏ, audit `<topic>.superseded`, không giao agent.

        - `tasks` chỉ còn giá trị khi ticket vẫn `dispatched` — trạng thái mà chính event đó đặt. Người tiếp quản
          publish PR (ADR-0012 → `in_review`) hay ticket đã approved/blocked thì task này đã bị vượt. Giao nó cho
          backend là backend chạy trên worktree đã commit → "không sửa file nào" ×3 → `blocked` → review PR của
          người bị bỏ vì ticket không còn `in_review`.
        - `pull-requests` chỉ còn giá trị khi là PR MỚI NHẤT của ticket: `_on_pr` đã đặt lại vòng review theo PR
          sau, review PR trước là chấm commit cũ rồi ghi verdict vào vòng của PR mới.
        Đo được (2026-09-04/05): QLKH-004 mở lại 7 lần, 13 lần review block, 10.7M token; sau khi mở lại bus,
        PR tiếp quản 04:10 (đã có 2/3 verdict, hoãn vì qa transient) vẫn nằm hàng đợi cạnh PR tiếp quản mới."""
        tid = str(env.payload.get("ticket_id") or env.key)
        if tid not in self.lead.tickets: return False  # event ngoài delivery-lead (test/relay): không có trạng thái để so
        st = self.lead.state.get(tid)
        if env.topic == "tasks":
            if st == "dispatched": return False
            why = {"state": st, "retry": env.payload.get("retry", 0)}
        else:
            newest = self.latest("pull-requests", tid)
            if newest is None or newest.event_id == env.event_id: return False
            why = {"state": st, "pr_ref": env.payload.get("pr_ref"), "newest_pr_ref": newest.payload.get("pr_ref")}
        self._audit(f"{env.topic}.superseded", {"ticket_id": tid, "event_id": env.event_id, **why},
                    ticket_id=tid, project_id=self.project_for(env))
        res.actions.append(f"superseded:{tid}:{env.topic}")
        self._mark(env, res)
        return True

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
            elif r.tools == "tests":
                ts = self._author_tests(agent, inp, r)
                res.actions.append(f"{agent}→{r.topic_out}:{ts.key}" if ts is not None else f"{agent}→bỏ:{inp.key}")
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
                run_ev: dict[str, Any] | None = None
                if r.tools == "ro" and env.topic == "release-events" and r.topic_out == "review-results":
                    # ADR-0029 mục "regression-staging": bằng chứng chạy là của ORCHESTRATOR, không phải của model.
                    # Chạy smoke trước lượt QA, đưa vào input để QA dẫn nó; sau lượt, verdict bị đối chiếu với nó.
                    run_ev = self._regression_run(inp)
                    inp = inp.model_copy(update={"payload": {**inp.payload, "evidence": {**_dict_of(inp.payload.get("evidence")), "run": run_ev}}})
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
                p = g.payloads[0]
                if r.topic_out == "review-results" and env.topic in {"release-candidates", "release-events"}                         and (rid := env.payload.get("release_id")) and p.get("ticket_id") != rid:
                    # Review trên RELEASE (release-check của security, QA hồi quy trên staging): subject là release_id
                    # của ROUTE, không phải lời khai của model — cùng nguyên tắc với `env`/`release_id` trong
                    # `_release`. Model hay điền ticket đầu tiên của RC vào `ticket_id`: review rơi vào ticket ĐÃ
                    # approved (vô nghĩa), `release_reviews[rid]` thiếu nguồn → Gate 3 không mở, escalation cũng
                    # không → RC chết im. Đo được 2026-09-06 (QLKH REL-024): security block ghi ticket_id=
                    # TCK-CR-OPS-001-04, không gate nào mở, `status` xanh.
                    self._audit("review.subject_overridden", {"release_id": rid, "claimed_ticket_id": p.get("ticket_id"),
                                                              "source": p.get("source")}, actor=agent, project_id=self.project_for(env))
                    p = {**p, "ticket_id": rid}
                if run_ev is not None:
                    p = self._verdict_with_run(agent, inp, p, run_ev)
                out = self.runner.publish(agent, inp, r.topic_out, p, key=key_for(r.topic_out, p, env.key),
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
        rec = {"agent": agent, "topic": env.topic, "event_id": env.event_id, "subject": subject, "error": str(error)[:300]}
        with self._lock: self.unhandled[subject] = rec
        self._audit("agent_error_unhandled", rec, ticket_id=env.payload.get("ticket_id"), project_id=self.project_for(env))
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

    def _retry_unhandled(self, subject: str, by: str, reason: str) -> bool:
        """Như `_retry_stalled` nhưng cho event bất kỳ mà agent lỗi không nhánh nào nhận (`unhandled`)."""
        rec = self.unhandled.get(subject)
        if rec is None: return False
        env = next((e for e in self.bus.replay(topic=str(rec["topic"])) if e.event_id == rec["event_id"]), None)
        if env is None: return False
        with self._lock:
            self.processed.discard(env.event_id); self.partial.pop(env.event_id, None); self.unhandled.pop(subject, None)
            self.spec_runtime_reworks.pop(subject, None)  # người cho chạy lại → spec-writer được thêm một lượt sửa tự động
        self._audit("event.retried", {**rec, "subject": subject, "by": by, "reason": reason[:300]}, project_id=self.project_for(env))
        with self._qlock: self.queue.insert(0, env)
        return True





    def _integrate(self, rc: Envelope, res: StepResult) -> bool:
        """Mọi ticket của RC phải nằm trên nhánh tích hợp (thường đã merge lúc approved). Trả về False nếu RC bị huỷ."""
        if not self._has_integration(): return True
        rid = rc.payload["release_id"]
        if rid in self.void_releases: return False
        for tid in rc.payload.get("tickets", []):
            if tid in self.integrated and not self._branch_ahead(tid): continue
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





    _release_evidence = verify.release_evidence

    def _release(self, agent: str, rc: Envelope, r: Route) -> Envelope:
        """release-engineer nhận RC kèm `target_env`; đầu ra phải đúng env và release_id, nếu không thì coi là invalid."""
        rid = rc.payload["release_id"]
        integ = self._integration_of_release(rc)
        extra: dict[str, Any] = ({"integration_branch": integ.branch, "integration_sha": integ.sha()}
                                 if integ is not None else {})
        if r.target_env == "production":
            # `gate_release` CHỈ có nghĩa với production: Gate 3 gác cửa production, không gác staging.
            # Trước đây gửi cho cả hai env và staging luôn thấy `false` (Gate 3 chưa thể duyệt vì chưa có qa hồi quy),
            # release-engineer đọc đó là "chưa được phép" nên TỪ CHỐI deploy staging — khoá kín cả dây chuyền:
            # staging không `deployed` → qa hồi quy không chạy → Gate 3 không đủ nguồn để mở → `gate_release` mãi
            # false. Đo được 2026-09-06 (QLKH): 18/18 release-candidate chết ở đây, 0 lần ra production, 0 tag giao
            # hàng, dù 14/14 ticket đã vào nhánh tích hợp. Staging là nơi QA hồi quy TRƯỚC khi xin Gate 3 (ADR-0006).
            extra["gate_release"] = self.gate.is_approved(rid)
            # Lượt production phải THẤY bằng chứng staging/QA/security/gate ngay trong payload: agent không có tool
            # đọc bus; thiếu thì nó "không được tự suy diễn" và dừng chờ người. Đo được 2026-09-06 (REL-025): staging
            # deployed 06:01, QA pass 06:02, Gate 3 ký 06:04 — lượt production 06:04 vẫn trả pending_human với lý do
            # "chưa qua deploy staging thật".
            extra["evidence"] = self._release_evidence(rid)
        inp = rc.model_copy(update={"payload": {**rc.payload, "target_env": r.target_env, **extra}})
        if r.target_env == "staging" and integ is not None and (full := integ.rev(integ.branch)):
            # Sha mà QA sẽ hồi quy — và sha sẽ được giao khi production duyệt (ADR-0027). Ghi audit để bền qua restart.
            with self._lock: self.release_sha[rid] = full
            self._audit("release.staged", {"release_id": rid, "sha": full, "branch": integ.branch}, project_id=self.project_for(rc))
        g = self.runner.generate(agent, inp, r.topic_out)
        p = g.payloads[0]
        if p.get("env") != r.target_env or p.get("release_id") != rid:
            # `env` và `release_id` là của ROUTE và của RC, KHÔNG phải lời khai của model — cùng nguyên tắc với
            # `version` ngay dưới. Trước đây output lệch bị ném RunnerError: agent trả `env=staging` ở lượt
            # production (nhầm lẫn dễ hiểu vì hai lượt nhận payload gần giống nhau) → invalid_output → escalation,
            # và bước CUỐI của dây chuyền giao hàng chết ngay sau khi người đã ký Gate 3. Đo được 2026-09-06
            # (QLKH REL-019): hai lần liên tiếp, không deploy được production dù mọi cổng đã qua.
            self._audit("release.env_overridden", {"release_id": rid, "expected_env": r.target_env,
                                                   "claimed_env": p.get("env"), "claimed_release_id": p.get("release_id")},
                        actor=agent, tokens=g.tokens)
            p = {**p, "env": r.target_env, "release_id": rid}
        if (want := rc.payload.get("version")) and p.get("version") != want:
            # Phiên bản là của RC (delivery-lead suy từ nội dung release), không phải lời khai của model.
            self._audit("release.version_overridden", {"release_id": rid, "claimed": p.get("version"), "version": want}, actor=agent)
            p = {**p, "version": want}
        if r.target_env == "staging" and p.get("status") == "deployed":
            p = self._smoke(agent, rc, rid, p, integ)
        return self.runner.publish(agent, rc, r.topic_out, p, key=rid, tokens=g.tokens, model=g.model, generated=g)


    _smoke = verify.smoke
    _regression_run = verify.regression_run
    _verdict_with_run = verify.verdict_with_run

    # ---------- kế hoạch: gate spec → threat model → delivery-lead sinh ticket → gate plan → dispatch ----------

    def _plan(self, env: Envelope, res: StepResult) -> StepResult:
        project = env.payload.get("project_id") or env.key
        if env.topic == "approved-specs":
            sid = f"SPEC-{project}"
            if not self.gate.is_approved(sid):
                decided = [g for g in self.gate.history if g.subject_id == sid]
                if sid not in self.gate.pending and not decided:
                    if (gap := spec_runtime_gap(env.payload)) is not None:
                        return self._spec_runtime_missing(env, project, gap, res)
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
            # Duyệt escalation này = lập lại kế hoạch: ghi vào `unhandled` để `_retry_unhandled` chạy lại đúng event
            # nguồn (change-request / approved-specs). Trước đây duyệt rơi xuống nhánh ticket → "reopen" một ticket
            # không tồn tại, không gì xảy ra. Đo được 2026-09-06 (CR-STAGE-001, PLAN-QLKH-5 rỗng): duyệt xong hàng
            # đợi rỗng, phải phát lại decide-change bằng tay.
            with self._lock:
                self.unhandled[project] = {"agent": "delivery-lead", "topic": env.topic, "event_id": env.event_id,
                                           "subject": project, "error": f"plan_rejected: {'; '.join(problems)[:200]}"}
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

    def _spec_runtime_missing(self, env: Envelope, project: str, gap: str, res: StepResult) -> StepResult:
        """ADR-0031: spec ứng dụng không có `runtime` hợp lệ thì KHÔNG mở gate spec — người ký Gate 1 không được đặt
        trước một PRD mà câu "chạy cho tôi xem" chưa có câu trả lời. Thay vào đó trả về spec-writer với lý do (`hint`)
        đúng như `request_changes` của người; quá `SPEC_RUNTIME_REWORKS` lần vẫn thiếu → escalation cấp dự án, cùng
        khuôn với kế hoạch bị `_check_plan` từ chối (approve = chạy lại event nguồn, reject = bỏ).
        Khoá theo `event_id` của spec (mỗi lần spec-writer publish là một event mới, không nuốt lần hai — khuôn 3
        `TRAPS.md`); bộ đếm theo dự án dựng lại từ audit (khuôn 2)."""
        with self._lock:
            self.spec_runtime_reworks[project] += 1; n = self.spec_runtime_reworks[project]
        cause = next((e for t in ("clarification-answers", "requirements-draft", "clarification-questions")
                      for e in self.bus.replay(topic=t) if e.event_id == env.causation_id), None) if env.causation_id else None
        if cause is None:
            cause = self.latest("requirements-draft", project)
        self._audit("spec.runtime_missing", {"project_id": project, "event_id": env.event_id, "kind": env.payload.get("kind"),
                                             "runtime": env.payload.get("runtime"), "reason": gap, "attempt": n,
                                             "source_event": cause.event_id if cause else None}, project_id=project)
        if cause is not None and n <= SPEC_RUNTIME_REWORKS:
            hint = f"orchestrator từ chối mở gate spec (lần {n}): {gap}"
            prev = {k: env.payload.get(k) for k in ("kind", "runtime", "artifacts")}
            inp = cause.model_copy(update={"payload": {**cause.payload, "hint": hint, "previous_spec": prev}})
            self._recall("spec-writer", cause)  # `partial` đã ghi spec-writer cho event nguồn: gọi lại là CHỦ Ý
            route = Route(cause.topic, "spec-writer", "approved-specs",
                          enrich=None if cause.topic == "requirements-draft" else _with_draft)
            self._call("spec-writer", inp, route, res)
            res.actions.append(f"spec_runtime_missing:{project}:rework:{n}")
            self._mark(env, res); return res
        why = gap if cause is not None else f"{gap}; không có requirements-draft để spec-writer làm lại"
        self._audit("spec.runtime_escalated", {"project_id": project, "event_id": env.event_id, "attempts": n, "reason": why,
                                               "source_event": cause.event_id if cause else None,
                                               "source_topic": cause.topic if cause else None}, project_id=project)
        res.actions.append(f"spec_runtime_missing:{project}:escalated")
        with self._lock: self.stats["errors"] += 1
        self.supervisor.escalate_gate(project, f"spec thiếu runtime sau {n} lần: {gap[:200]}", once_key=f"spec_runtime:{env.event_id}")
        if cause is not None:
            with self._lock:
                self.unhandled[project] = {"agent": "spec-writer", "topic": cause.topic, "event_id": cause.event_id,
                                           "subject": project, "error": f"spec_runtime_missing: {gap[:200]}"}
        if project not in self.gate.pending:
            self.gate.request(GateRequest(kind="escalation", subject_id=project, created_by="spec-writer",
                                          checklist=["spec_runtime", "decision:retry|close"]))
        self._mark(env, res); return res

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
                if rc is not None:
                    self._recall("release-engineer", rc)  # ký lại Gate 3 phải chạy lại được lượt production
                    self._call("release-engineer", rc, PROD_ROUTE, res)
        self._note_closed()
        self._mark(env, res)
        self._retry_deferred()
        return res

    def _check_escalations(self) -> None:
        """Ticket blocked (retry hết) hoặc bị supervisor escalate → gate `escalation` cho người quyết (checklist gate 'bất thường')."""
        # `self.paused` chứa cả ID DỰ ÁN (supervisor pause khi dự án chạm trần ngân sách), không chỉ ticket. Lọc
        # `t in self.lead.tickets` bỏ sót đúng nhóm đó: dự án bị pause thì mọi event của nó bị hoãn, không cổng
        # nào mở, không ai được hỏi — đo được: `paused=['P1']` mà `gates_pending={}`.
        # Người ĐÃ quyết nhưng `gate.decide` còn nằm trong hàng đợi (mở lại bus: `_rehydrate` đã đếm nó vào
        # `escalation_decided` nhưng `resume` chỉ được phát khi event đó được xử lý) → subject vẫn `paused`, khoá mang số
        # quyết định mới → gate TRÙNG cho một việc người vừa duyệt. Đo được (2026-09-05): REL-004 duyệt 21:19, orchestrator
        # mở lại 21:30, gate thứ hai mở ngay sau event đầu tiên trong hàng đợi, trước khi decide được áp dụng.
        self._check_paused_releases()
        with self._qlock:
            decided_pending = {str(_evidence(e.payload).get("subject_id")) for e in self.queue
                               if e.topic == "audit-log" and e.payload.get("action") == "gate.decide"}
        for tid in {*self.lead.blocked(), *self.paused}:
            if self.lead.state.get(tid) in DONE_STATES: continue  # đã đóng/đã xong: không mở gate nữa
            if tid in decided_pending: continue  # đã có quyết định chờ áp dụng: không hỏi người lần nữa
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
        self._check_debt()

    def _check_debt(self) -> None:
        """ADR-0032: mã nợ kiến trúc chạm ngưỡng (supervisor đếm từ bus, xác định) → gate `escalation` cấp DỰ ÁN với
        danh sách nợ, số lần, ticket nào nhắc, và hint "cần ticket ADR + người ký". Không pause dự án: nợ treo là
        quyết định bị né, không phải sự cố — việc khác vẫn chạy trong lúc người quyết.

        Khoá once mang (dự án, mã nợ, lần thứ mấy): restart không mở trùng (`once` dựng lại từ audit), nhưng nợ tăng
        tiếp tới bội số kế của ngưỡng là lần thứ n+1 → gate mới (khuôn 3, TRAPS.md). Gate của dự án đang bận (stall
        hoặc nợ khác) thì đợi — không `remember`, nhịp sau mở."""
        for due in self.supervisor.debt_due:
            pid = due["project_id"]; key = f"debt:{pid}:{due['debt_id']}:{due['times']}"
            if key in self.once: continue
            if pid in self.gate.pending or pid in self.debt_gate: continue
            self._remember(key)
            rec = {**due, "table": self.supervisor.debt_table(pid)}
            self.debt_gate[pid] = rec
            self._audit("debt.escalated", rec, project_id=pid)
            checklist = [f"debt:{due['debt_id']}×{due['consecutive']} liên tiếp ({due['source']}; {','.join(due['tickets'])})",
                         *[f"debt:{r['debt_id']}×{r['mentions']} ({','.join(r['tickets'])})" for r in rec["table"]
                           if r["debt_id"] != due["debt_id"]],
                         "decision:adr|waive", f"hint:{due['hint']}"]
            self.gate.request(GateRequest(kind="escalation", subject_id=pid, created_by="supervisor", checklist=checklist))

    def _on_escalation_decided(self, tid: str, decision: str, by: str, reason: str, res: StepResult) -> None:
        if tid in self.debt_gate:  # ADR-0032: nợ kiến trúc cấp dự án — người ghi nhận (ADR + người ký) hay chấp nhận treo
            rec = self.debt_gate.pop(tid)
            self._audit("debt.decided", {"project_id": tid, "debt_id": rec.get("debt_id"), "times": rec.get("times"),
                                         "decision": decision, "by": by, "reason": reason[:300]}, project_id=tid)
            res.actions.append(f"debt:{tid}:{rec.get('debt_id')}:{decision}")
            return
        if tid in self.lead.release_tickets:  # escalation của một RELEASE (không phải ticket): xem docstring
            # `Delivery.waive_release_findings`/`rework_release_tickets` — người quyết định chấp nhận rủi ro (finding
            # không có code để sửa: DPIA, license...) hay đúng là lỗi code thật cần các ticket merged làm lại.
            if decision == "approve":
                sources = self.lead.waive_release_findings(tid)
                self.bus.publish(Envelope(topic="supervisor-actions", key=tid, actor=by,
                                          payload={"target": tid, "action": "resume", "reason": f"escalation approve: {reason}"[:300]}))
                res.actions.append(f"release_waived:{tid}:{','.join(sources)}")
                if self._rerun_release(tid, by, reason, res): res.actions.append(f"release_rerun:{tid}")
            elif self._superseded_release(tid):
                # RC cũ mà nội dung đã nằm trong một bản GIAO sau nó (nhánh tích hợp cộng dồn): "đóng" là huỷ RC,
                # KHÔNG trả ticket đã giao về làm lại. Đo được 2026-09-06: sau bản giao v0.15.1, 10 RC cũ
                # pending_human sẽ mở gate; từ chối theo hành vi cũ đá 14 ticket đã giao về changes_requested.
                self._audit("release.void", {"release_id": tid, "reason": f"nội dung đã nằm trong bản giao; {reason}"[:300]})
                self._void(tid); res.actions.append(f"void:{tid}")
            else:
                self.lead.rework_release_tickets(tid, reason or "người từ chối escalation release: cần sửa nội dung thật")
                res.actions.append(f"release_reworked:{tid}")
            return
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
        if tid not in self.lead.tickets and tid in self.unhandled:
            # Event KHÔNG phải ticket (change-request, acceptance...) mà agent lỗi không nhánh nào nhận: trước đây rơi
            # xuống nhánh ticket bên dưới → "reopen" một ticket không tồn tại, event không bao giờ chạy lại. Đo được
            # 2026-09-06: CR-DEV-001, delivery-lead lỗi error_max_structured_output_retries, duyệt escalation xong
            # hàng đợi rỗng, phải phát lại CR bằng tay.
            # `resume` trước: supervisor đã `pause` subject khi escalate — không gỡ thì event chạy lại bị hoãn
            # "paused:<subject>" và `_check_escalations` mở gate mới cho cùng việc.
            self.bus.publish(Envelope(topic="supervisor-actions", key=tid, actor=by,
                                      payload={"target": tid, "action": "resume", "reason": f"escalation {decision}: {reason}"[:300]}))
            if decision == "approve":
                ok = self._retry_unhandled(tid, by, reason)
                res.actions.append(f"retry:{tid}" if ok else f"retry_failed:{tid}")
            else:
                rec = self.unhandled.pop(tid, {})
                self._audit("event.abandoned", {**rec, "subject": tid, "by": by, "reason": reason})
                res.actions.append(f"closed:{tid}")
            return
        if decision == "approve":  # mở lại với hint = lý do người duyệt, cấp thêm một ngân sách ticket
            b = self.supervisor.budgets.get(tid); t = self.lead.tickets.get(tid)
            if b and t:
                b.limit = max(b.limit, b.used) + t.budget_tokens
                self._audit("budget.extended", {"ticket_id": tid, "limit": b.limit, "by": by}, ticket_id=tid)
            if tid in self.integrated and self.lead.state.get(tid) in {"blocked", "escalated", "changes_requested"}:
                # Code của ticket ĐÃ ở trong nhánh tích hợp: giao lại chỉ tổ bắt agent làm lại việc đã merge, nó
                # không sửa gì (đúng) rồi bị tính `invalid_output` → block → escalation → lặp. Xem
                # `DeliveryLead.mark_done_already_integrated`.
                self._audit("ticket.already_integrated", {"ticket_id": tid, "by": by}, ticket_id=tid,
                            project_id=self.lead.tickets[tid].project_id if tid in self.lead.tickets else None)
                self.lead.mark_done_already_integrated(tid)
                res.actions.append(f"already_integrated:{tid}")
            elif self.lead.state.get(tid) in {"blocked", "escalated"}:
                self.lead.reopen(tid, hint=reason or "người duyệt mở lại sau escalation")
            self.bus.publish(Envelope(topic="supervisor-actions", key=tid, actor=by,
                                      payload={"target": tid, "action": "resume", "reason": f"escalation approve: {reason}"[:300]}))
            res.actions.append(f"reopen:{tid}")
            # Escalation vì một REVIEW AGENT lỗi (không phải assignee): ticket vẫn `in_review`, event PR đã bị đánh dấu
            # xử lý, nên duyệt gate xong không có gì chạy lại review còn thiếu — ticket nằm im tới `review_timeout`
            # (2 giờ) mới được `tick` giao lại. Đo được (2026-09-05): QLKH-005/QLKH-013 duyệt xong đứng im, người
            # phải `takeover` nộp lại PR nguyên trạng để vòng review chạy. Ở đây gọi lại đúng nguồn còn thiếu trên PR
            # mới nhất; `partial` giữ cho reviewer/qa đã chấm không chạy lại.
            if self.lead.state.get(tid) == "in_review" and (pr := self.latest("pull-requests", tid)) is not None:
                for src in sorted(self.lead.required_reviews(tid) - set(self.lead.reviews.get(tid, {}))):
                    self._audit("review.rerun", {"ticket_id": tid, "source": src, "by": by}, ticket_id=tid,
                                project_id=self.project_for(pr))
                    self._call(REVIEW_AGENT[src], pr, Route("pull-requests", REVIEW_AGENT[src], "review-results"), res)
        elif decision in {"reject", "rollback"} and tid in self.lead.tickets:
            blocked = self.lead.close_escalated(tid); res.actions.append(f"closed:{tid}")
            self._audit("ticket.abandoned", {"ticket_id": tid, "by": by, "dependents_blocked": blocked}, ticket_id=tid,
                        project_id=self.lead.tickets[tid].project_id)
            if blocked: res.actions.append("blocked:" + ",".join(blocked))
            if self.lead.batch_releases:  # ticket đóng không còn giữ release của các ticket đã approved
                self.lead.flush_releases(self.lead.tickets[tid].project_id)

    # ---------- giao hàng thật (ADR-0027) ----------

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



    def redeploy(self, release_id: str, by: str) -> Envelope:
        """Chạy lại lượt STAGING cho một release-candidate đã có — dùng khi dây chuyền từng kẹt vì lỗi hạ tầng và
        RC nằm lại giữa đường.

        Sự kiện `release-candidates` chỉ được xử lý MỘT lần (`processed`), nên sau khi sửa một lỗi hạ tầng, các RC
        đang kẹt không có đường nào chạy lại: chỉ RC mới mới hưởng bản vá, mà RC mới chỉ sinh ra khi có ticket
        approved chưa nằm trong RC nào. Đo được 2026-09-06 (QLKH): sau khi vá deadlock `gate_release` ở staging,
        18 RC cũ vẫn kẹt vĩnh viễn vì 14/14 ticket đều đã nằm trong một RC hợp lệ — không gì sinh RC mới nữa.

        Người vận hành gọi lệnh này (bus không cho người tự phát `release-candidates`: topic đó của delivery-lead)."""
        if not by.split(":", 1)[0] == "human": raise ValueError("by phải là human:<tên>")
        rc = self.latest("release-candidates", release_id)
        if rc is None: raise ValueError(f"không có release-candidate {release_id}")
        if release_id in self.void_releases: raise ValueError(f"{release_id}: RC đã bị huỷ, không chạy lại")
        self._audit("release.redeploy", {"release_id": release_id, "by": by}, actor=by,
                    project_id=self.project_for(rc))
        res = StepResult(rc.event_id, rc.topic, rc.key)
        self._recall("release-engineer", rc)
        self._call("release-engineer", rc, STAGING_ROUTE, res)  # cùng route như lượt đầu, chỉ khác là do người gọi
        return rc

    def _check_paused_releases(self) -> None:
        """Quét mọi RC mà release-event CUỐI là `pending_human` và không gate nào chờ → mở gate escalation. Cần vì
        `_release_paused` chỉ chạy lúc XỬ LÝ event: RC kẹt từ trước bản vá (event đã `processed`) hay orchestrator
        mở lại sau khi gate đã quyết mà lượt chạy lại vẫn dừng — không có sweep thì chúng nằm im mãi như cũ."""
        for rid in list(self.lead.releases):
            if rid in self.void_releases or rid in self.gate.pending: continue
            last = self.latest("release-events", rid)
            if last is None or last.payload.get("status") != "pending_human": continue
            key = f"release.pending_human:{rid}:{last.event_id}"
            if key in self.once: continue
            self._remember(key)
            self._audit("release.pending_human", {"release_id": rid, "env": last.payload.get("env"),
                                                  "summary": str(last.payload.get("summary") or "")[:300]},
                        actor="release-engineer", project_id=self.project_for(last))
            self.gate.request(GateRequest(kind="escalation", subject_id=rid, created_by="release-engineer",
                                          checklist=["root_cause", "decision:redeploy|close", "hint"]))

    def _superseded_release(self, rid: str) -> bool:
        """RC chưa giao, nhưng mọi ticket của nó đã ở nhánh tích hợp (hoặc đã xong) và đã có một bản giao SAU nó →
        nội dung RC này đã tới tay khách trong bản giao đó; RC chỉ còn là sổ sách."""
        if rid in self.delivered or rid not in self.lead.release_tickets: return False
        if rid not in self.lead.releases: return False
        later = [d for d in self.delivered if d in self.lead.releases and self.lead.releases.index(d) > self.lead.releases.index(rid)]
        if not later: return False
        return all(t in self.integrated or self.lead.state.get(t) in DONE_STATES for t in self.lead.release_tickets[rid])

    def _release_paused(self, env: Envelope, res: StepResult) -> None:
        """release-engineer TỰ DỪNG (`status=pending_human`): xem `_check_paused_releases` — sweep đó chạy ở mọi nhịp
        (kể cả ngay sau lượt vừa phát event này, trước khi event được lấy khỏi hàng đợi), nên ở đây chỉ còn ghi
        hành động để `orchestrated` của event nói rõ gate đã mở."""
        rid = str(env.payload.get("release_id") or env.key)
        self._check_paused_releases()
        if rid in self.gate.pending: res.actions.append(f"gate:escalation:{rid}")

    def _recall(self, agent: str, env: Envelope) -> None:
        """Cho phép gọi LẠI một agent trên cùng event một cách chủ ý. `partial[event_id]` ghi agent đã chạy để event
        bị hoãn transient không chạy lại — nhưng nó cũng nuốt mọi lần gọi lại có chủ đích trên cùng envelope (RC):
        Gate 3 ký lần hai, chạy lại lượt release-engineer vừa tự dừng. Đo được 2026-09-06: lead ký lại Gate 3
        REL-019 lúc 03:06 chỉ chạy được vì orchestrator vừa restart (partial trong RAM trống)."""
        with self._lock:
            if env.event_id in self.partial: self.partial[env.event_id].discard(agent)

    def _rerun_release(self, rid: str, by: str, reason: str, res: StepResult) -> bool:
        """Chạy lại lượt release-engineer mà nó vừa tự dừng: env lấy từ release-event cuối; production chỉ khi Gate 3
        đã ký. Lý do người duyệt đi vào payload làm `human_hint`. Trả False nếu không có gì để chạy lại."""
        last = self.latest("release-events", rid); rc = self.latest("release-candidates", rid)
        if last is None or rc is None or last.payload.get("status") != "pending_human": return False
        env_ = last.payload.get("env")
        route = STAGING_ROUTE if env_ == "staging" else PROD_ROUTE
        if route is PROD_ROUTE and not self.lead._gate_kind_approved(rid, "release"): return False
        self._audit("release.rerun", {"release_id": rid, "env": env_, "by": by}, actor=by, project_id=self.project_for(rc))
        inp = rc.model_copy(update={"payload": {**rc.payload, "human_hint": reason}}) if reason else rc
        self._recall("release-engineer", rc)
        self._call("release-engineer", inp, route, res)
        return True

    # ---------- hoãn / đánh dấu / audit ----------






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

    def rulings(self, project_id: str | None = None, ticket_id: str | None = None) -> list[dict[str, Any]]:
        """Sổ Ruling (ADR-0030): mọi quyết định agent tự đưa ra, đọc từ audit `ruling` — không giữ trong RAM nên không
        có gì để mất khi mở lại bus. Lọc theo dự án hoặc ticket; mỗi mục mang actor, thời điểm, decision/why/cost."""
        out: list[dict[str, Any]] = []
        for e in self.bus.replay(topic="audit-log"):
            a = e.payload
            if a.get("action") != "ruling": continue
            if project_id and a.get("project_id") != project_id: continue
            if ticket_id and a.get("ticket_id") != ticket_id: continue
            d = _evidence(a)
            out.append({"at": e.ts.isoformat(timespec="seconds"), "by": a.get("actor"), "ticket_id": a.get("ticket_id"),
                        "project_id": a.get("project_id"), **d})
        return out

    def status(self) -> dict[str, Any]:
        return {"warnings": self._deadlock_warnings(), "rulings": len(self.rulings()),
                "queue": len(self.queue), "deferred": {k: v[1] for k, v in self.deferred.items()},
                "paused": sorted(self.paused), "tickets": dict(self.lead.state), "waiting": self.lead.waiting(),
                "blocked": self.lead.blocked(), "releases": self.lead.releases,
                "stalled": {pid: f"{st['agent']} lỗi trên {st['topic']}: {st['error'][:120]}" for pid, st in self.stalled.items()},
                "architecture_debt": self.supervisor.debt_table(),  # ADR-0032
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


install_aliases(Orchestrator)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
