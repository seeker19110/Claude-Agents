"""Vòng lặp `watch → triage → patch → verify → gate? → release` của `keeper` (BT7, `DAC-TA-KEEPER.md` §9).

Khuôn lấy từ `software-company/src/company/orch/scheduler.py` (`run`/`tick`/`watch`, `_audit`, một nhịp lỗi
không giết vòng watch). **Sao khuôn, không import chéo công ty** — `keeper` không phụ thuộc `company`.

## Trạng thái KHÔNG sống trong RAM

Mọi thứ orchestrator biết đều dựng lại được từ `keeper.sqlite` bằng `bus.replay()` lúc mở: ticket đã tạo
(`maintenance-tickets`), khoá chống-trùng của `triager` (suy từ `ticket_id`, xem `_apply`), bằng chứng đã đo
(`verification-reports`), dòng release đã soạn (`release-notes`), và sổ gate (`PersistentGate` tự replay
`audit-log`). Đó là điều kiện để `--watch` chết giữa chừng rồi chạy lại mà không làm lại việc đã làm — và là
một trong bốn khuôn lỗi lặp lại của X-Agents (`TRAPS.md`).

## Bốn cổng, không đi vòng

`pr_blockers()` là NƠI DUY NHẤT quyết định "được mở PR chưa", và nó gọi thẳng bốn cổng đã dựng ở BT4–BT6:

| Khoá | Cổng | Bất biến |
|---|---|---|
| `human-only` | `patcher.HUMAN_ONLY_SEGMENTS` — chạm `agents/`/`skills/` thì mở ticket `high` cho NGƯỜI | bảy bước `CONTRIBUTING.md` §3 |
| `evidence` | `evidence.require_two_way()` (qua `record_verification`) | I2 |
| `gate` | gate `keeper` approved cho ticket `risk_tier == "high"` | §9 |
| `budget` | `budget.can_open_pr()` — hỏi `gh` thật mỗi lần | I3 |

`human-only` là khoá VĨNH VIỄN: một người duyệt gate cũng không biến nó thành việc `keeper` tự làm — gate ở
đó để người biết mà làm, không phải để uỷ quyền ngược lại cho máy.

## "Mở PR" ở BT7 nghĩa là gì

Nghĩa là soạn và phát `release-notes` + ghi `pr.open` vào `audit-log`. Thao tác `gh pr create` THẬT không nằm
ở đây: `github.py` chỉ đọc (bất biến I1) và một chu kỳ thật là việc của canary BT8. Nói "mở PR" cho một hàm
gọi `gh` sẽ là lời khai, và `AGENTS.md` cấm §8 áp cho chính `keeper` trước tiên.
"""
from __future__ import annotations

import json
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .budget import GitHubLike, can_open_pr
from .bus import KeeperBus
from .core import CORE
from .events import AuditLog, Envelope, ReleaseNote, Signal, Ticket, VerificationReport
from .evidence import TwoWayEvidence, verification_report
from .gates import GATE_ACTOR, PersistentGate, gate_approvers, request_gate
from .patcher import HUMAN_ONLY_SEGMENTS
from .release import compose
from .signals import dedupe
from .triage import TriageState, triager

__all__ = ["HUMAN_ONLY", "KeeperOrchestrator", "TickResult", "touches_human_only"]

#: Khoá chặn "việc này của người" — hằng số chứ không chuỗi rời, vì cả `pr_blockers` lẫn test đều nêu tên nó.
HUMAN_ONLY = "human-only"

SCOUT_ACTOR = "dependency-scout"
TRIAGER_ACTOR = "triager"
VERIFIER_ACTOR = "regression-guard"
RELEASE_ACTOR = "release-clerk"

TICKET_PREFIX = "KEEP:"


def touches_human_only(subject: str) -> bool:
    """`agents/`/`skills/` là THÀNH PHẦN đường dẫn, không phải substring — cùng phép so `patcher.check_path`
    dùng, nhắc lại ở lớp quyết định để `pr_blockers` không phải chạm đĩa mới biết."""
    parts = subject.replace("\\", "/").split("/")
    return any(seg in parts for seg in HUMAN_ONLY_SEGMENTS)


@dataclass
class TickResult:
    """Kết quả một nhịp: ticket mới sinh, dòng release mới soạn, và các việc đã làm (để in ra `--watch`)."""
    tickets: list[Ticket] = field(default_factory=list)
    notes: list[ReleaseNote] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


class KeeperOrchestrator:
    """Một tiến trình vòng lặp trên một `keeper.sqlite`. Nhiều tiến trình cùng file thì `bus.poll()` mỗi nhịp
    nạp event của nhau (gate CLI của người là tiến trình khác)."""

    def __init__(self, db: Path, repo: Path, gh: GitHubLike, *, approvers: frozenset[str] | None = None,
                 env: Mapping[str, str] | None = None) -> None:
        self.repo = Path(repo)
        self.gh = gh
        self.env = env
        self.bus: KeeperBus = KeeperBus(CORE, db)
        self.signals: list[Signal] = []
        self.tickets: dict[str, Ticket] = {}
        self.reports: dict[str, VerificationReport] = {}
        self.verified: set[str] = set()
        self.notes: dict[str, ReleaseNote] = {}
        self.triage = TriageState()
        self.ticks = 0
        for env_ in self.bus.replay():
            self._apply(env_)
        for topic in ("maintenance-signals", "maintenance-tickets", "verification-reports", "release-notes"):
            self.bus.subscribe(topic, self._apply)
        # Gate mở SAU replay của mình nhưng tự replay `audit-log` lấy sổ gate — hai nguồn không giẫm nhau vì
        # `_apply` ở đây bỏ qua `audit-log` (xem dưới).
        self.gate = PersistentGate(self.bus, approvers=approvers if approvers is not None else gate_approvers())

    # ---------- dựng lại trạng thái ----------

    def _apply(self, env: Envelope) -> None:
        """Một event → trạng thái. Chạy cho cả replay lúc mở lẫn event mới (subscribe), nên phải idempotent."""
        if env.topic == "maintenance-signals":
            self.signals.append(Signal.model_validate(env.payload))
        elif env.topic == "maintenance-tickets":
            t = Ticket.model_validate(env.payload)
            self.tickets[t.ticket_id] = t
            # Khoá chống-trùng của `triager` KHÔNG được lưu riêng: `ticket_id` LÀ `KEEP:<khoá>` (`triage.py`),
            # nên sổ khoá suy được từ chính ticket. Lưu thêm một bản là hai nguồn cho một sự thật.
            self.triage.seen.add(t.ticket_id.removeprefix(TICKET_PREFIX))
        elif env.topic == "verification-reports":
            r = VerificationReport.model_validate(env.payload)
            self.reports[r.ticket_id] = r
            self.verified.add(r.ticket_id)
        elif env.topic == "release-notes":
            n = ReleaseNote.model_validate(env.payload)
            self.notes[n.ticket_id] = n

    def _publish(self, topic: str, key: str, actor: str, payload: dict[str, Any]) -> Envelope:
        return self.bus.publish(Envelope(topic=topic, key=key, actor=actor, payload=payload))  # type: ignore[arg-type]

    def _audit(self, action: str, data: dict[str, Any], *, ticket_id: str | None = None) -> None:
        a = AuditLog(actor=GATE_ACTOR, action=action, ticket_id=ticket_id,
                     evidence=json.dumps(data, ensure_ascii=False))
        self._publish("audit-log", GATE_ACTOR, GATE_ACTOR, a.model_dump())

    # ---------- watch: nạp việc ----------

    def submit_signal(self, signal: Signal, *, actor: str = SCOUT_ACTOR) -> Envelope:
        """Một quan sát thô lên bus. `scout`/`health`/`drift` (BT3) gọi hàm này; người nạp tay cũng được
        (`maintenance-signals` là topic người ghi được, `core.py:HUMAN_TOPICS`)."""
        return self._publish("maintenance-signals", signal.subject, actor, signal.model_dump())

    # ---------- triage ----------

    def _generation(self, subject: str) -> int:
        """Thế hệ = số vòng đời ticket đã ĐÓNG của chủ thể đó (`triage.py`). Đếm từ ticket đã dựng lại từ bus,
        không phải từ một biến đếm trong RAM."""
        return sum(1 for t in self.tickets.values() if t.subject == subject and t.status == "closed")

    def _triage(self, now: datetime) -> list[Ticket]:
        """Gộp trùng rồi xếp bậc TỪNG signal với thế hệ CỦA CHÍNH chủ thể đó.

        Gọi `triager()` một signal mỗi lần chứ không cả lô: `generation` là tham số chung cho cả lời gọi, nên
        đưa cả lô vào là mọi chủ thể phải dùng chung một thế hệ — một ticket đóng lại ở chủ thể A sẽ đổi khoá
        chống-trùng của B và làm B ra ticket lần hai."""
        out: list[Ticket] = []
        for s in dedupe(self.signals):
            for t in triager([s], generation=self._generation(s.subject), state=self.triage, now=now):
                self._publish("maintenance-tickets", t.ticket_id, TRIAGER_ACTOR, t.model_dump())
                out.append(self.tickets[t.ticket_id])
        return out

    # ---------- verify (I2) ----------

    def record_verification(self, ticket_id: str, payload: Mapping[str, Any],
                            evidence: TwoWayEvidence) -> VerificationReport:
        """`payload` (phần model KỂ) + `evidence` (phần code ĐO) → `VerificationReport` đã qua
        `require_two_way`. Ném `EvidenceError` nếu bằng chứng không đủ — ticket ở lại pha quality (I2)."""
        report = verification_report(payload, evidence=evidence)
        self._publish("verification-reports", report.ticket_id, VERIFIER_ACTOR, report.model_dump())
        return self.reports[ticket_id]

    # ---------- gate? ----------

    def _gate_seen(self, ticket_id: str) -> bool:
        return ticket_id in self.gate.pending or any(r.subject_id == ticket_id for r in self.gate.history)

    def ensure_gate(self, ticket: Ticket) -> None:
        """Ticket `requires_gate` mà chưa có gate nào trong đời nó → xin một gate `patch`. Đúng một lần: gate
        đã đóng (`history`) thì KHÔNG xin lại — mở lại là quyết định riêng, phải phát `supervisor-actions`
        `resume` một cách tường minh (xem `gates.py`, mục 3)."""
        if not ticket.requires_gate or self._gate_seen(ticket.ticket_id):
            return
        request_gate(self.gate, "patch", ticket.ticket_id)
        self._audit("gate.requested", {"subject_id": ticket.ticket_id, "risk_tier": ticket.risk_tier},
                    ticket_id=ticket.ticket_id)

    # ---------- release ----------

    def pr_blockers(self, ticket: Ticket) -> list[str]:
        """Những cổng CHƯA qua, theo thứ tự từ "không bao giờ qua được" tới "hỏi lại sau là qua"."""
        blockers: list[str] = []
        if touches_human_only(ticket.subject):
            blockers.append(HUMAN_ONLY)
        if ticket.ticket_id not in self.verified:
            blockers.append("evidence")
        if ticket.risk_tier == "high" and not self.gate.is_approved(ticket.ticket_id):
            blockers.append("gate")
        if not can_open_pr(self.gh, env=self.env):
            blockers.append("budget")
        return blockers

    def open_pr(self, ticket: Ticket) -> ReleaseNote | None:
        """Soạn dòng release và ghi ý định mở PR, hoặc `None` kèm audit nêu ĐÍCH DANH cổng chặn.

        Ghi lý do chặn vào `audit-log` chứ không im lặng trả `None`: một ticket đứng yên mà không ai biết vì
        sao là đúng khuôn "chế độ hỏng không tự khai báo" (`TRAPS.md`)."""
        blockers = self.pr_blockers(ticket)
        if blockers:
            self._audit("pr.blocked", {"ticket_id": ticket.ticket_id, "blockers": blockers},
                        ticket_id=ticket.ticket_id)
            return None
        note = compose(ticket)
        self._publish("release-notes", note.ticket_id, RELEASE_ACTOR, note.model_dump())
        self._audit("pr.open", {"ticket_id": ticket.ticket_id, "changelog_line": note.changelog_line},
                    ticket_id=ticket.ticket_id)
        return self.notes[ticket.ticket_id]

    # ---------- vòng lặp ----------

    def tick(self, now: datetime | None = None) -> TickResult:
        """Một nhịp: nạp event tiến trình khác → triage → xin gate cho tier cao → thử mở PR cho ticket đủ cổng."""
        moc = now or datetime.now(UTC)
        self.bus.poll()
        res = TickResult(tickets=self._triage(moc))
        res.actions += [f"ticket:{t.ticket_id}" for t in res.tickets]
        for ticket in list(self.tickets.values()):
            if ticket.status == "closed" or ticket.ticket_id in self.notes:
                continue
            self.ensure_gate(ticket)
            note = self.open_pr(ticket)
            if note is not None:
                res.notes.append(note)
                res.actions.append(f"pr:{ticket.ticket_id}")
        return res

    def watch(self, interval: float = 5.0, max_ticks: int | None = None) -> None:
        """`--watch` như hai công ty kia. Một nhịp lỗi (bus/git/`gh`) KHÔNG được giết vòng lặp: ghi
        `tick_error` vào `audit-log` rồi đi tiếp — nhưng ghi, không nuốt."""
        n = 0
        while max_ticks is None or n < max_ticks:
            try:
                for a in self.tick().actions:
                    print(a)
            except Exception as e:  # mọi lỗi của một nhịp, có ghi lại rồi đi tiếp — xem docstring
                self._audit("tick_error", {"error": f"{type(e).__name__}: {str(e)[:300]}"})
                print(f"tick_error: {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
            n += 1
            self.ticks = n
            if max_ticks is None or n < max_ticks:
                time.sleep(interval)
