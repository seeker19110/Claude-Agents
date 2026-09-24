"""Kernel thi hành bền cho X-Agents (ADR-0017).

Module này cố ý chỉ giữ CƠ CHẾ: contract, DAG state machine, evidence receipt và journal SQLite append-only.
Nó không biết company, ticket, gate hay model nào. Phiên chính quyết intent/kiến trúc; harness giữ state thi hành
có thể replay sau khi process hoặc conversation chết.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import Any, cast
from uuid import uuid4

__all__ = [
    "ArtifactRef",
    "Complexity",
    "DecisionRequest",
    "EvidenceReceipt",
    "ExecutionEvent",
    "ExecutionEventKind",
    "ExecutionJournal",
    "ExecutionJournalError",
    "ExecutionTransitionError",
    "RunSpec",
    "RunState",
    "RunStatus",
    "TaskResult",
    "TaskSpec",
    "TaskStatus",
    "apply_event",
]


class Complexity(StrEnum):
    C1 = "c1"
    C2 = "c2"
    C3 = "c3"


class TaskStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    BLOCKED = "blocked"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"


class ExecutionEventKind(StrEnum):
    RUN_STARTED = "run.started"
    RUN_CANCELLED = "run.cancelled"
    TASK_STARTED = "task.started"
    TASK_SUCCEEDED = "task.succeeded"
    TASK_FAILED = "task.failed"
    TASK_RETRIED = "task.retried"


@dataclass(frozen=True)
class ArtifactRef:
    uri: str
    sha256: str


@dataclass(frozen=True)
class DecisionRequest:
    decision_id: str
    question: str
    reason: str
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceReceipt:
    """Bằng chứng máy sinh, gắn với đúng git head thay vì lời khai text của worker."""

    command: str
    cwd: str
    exit_code: int
    head_sha: str
    output_sha256: str
    started_at: datetime
    duration_ms: float

    @classmethod
    def from_output(
        cls,
        *,
        command: str,
        cwd: str,
        exit_code: int,
        head_sha: str,
        output: bytes,
        duration_ms: float,
    ) -> EvidenceReceipt:
        return cls(
            command=command,
            cwd=cwd,
            exit_code=exit_code,
            head_sha=head_sha,
            output_sha256=hashlib.sha256(output).hexdigest(),
            started_at=datetime.now(UTC),
            duration_ms=duration_ms,
        )

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True)
class TaskResult:
    task_id: str
    attempt_id: str
    status: TaskStatus
    base_sha: str
    head_sha: str
    diff_hash: str
    artifacts: tuple[ArtifactRef, ...] = ()
    evidence: tuple[EvidenceReceipt, ...] = ()
    findings: tuple[str, ...] = ()
    unresolved: tuple[DecisionRequest, ...] = ()


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    objective: str
    dependencies: tuple[str, ...] = ()
    complexity: Complexity = Complexity.C2
    acceptance: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    write_scope: tuple[str, ...] = ()
    context_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.task_id in self.dependencies:
            raise ValueError(f"task {self.task_id!r} phụ thuộc chính nó")


@dataclass(frozen=True)
class RunSpec:
    run_id: str
    objective: str
    tasks: tuple[TaskSpec, ...]

    def __post_init__(self) -> None:
        ids = [task.task_id for task in self.tasks]
        known = set(ids)
        if len(ids) != len(known):
            raise ValueError("task_id trùng trong RunSpec")
        for task in self.tasks:
            missing = set(task.dependencies) - known
            if missing:
                raise ValueError(f"dependency không tồn tại của {task.task_id}: {sorted(missing)}")
        _validate_acyclic(self.tasks)


def _validate_acyclic(tasks: tuple[TaskSpec, ...]) -> None:
    remaining = {task.task_id: set(task.dependencies) for task in tasks}
    while remaining:
        ready = [task_id for task_id, deps in remaining.items() if deps.isdisjoint(remaining)]
        if not ready:
            raise ValueError("dependency graph có chu trình")
        for task_id in ready:
            remaining.pop(task_id)


@dataclass(frozen=True)
class ExecutionEvent:
    run_id: str
    kind: ExecutionEventKind
    task_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid4().hex)
    ts: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_json(self) -> str:
        return json.dumps(
            {
                "event_id": self.event_id,
                "run_id": self.run_id,
                "kind": self.kind.value,
                "task_id": self.task_id,
                "payload": self.payload,
                "ts": self.ts.isoformat(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, data: str) -> ExecutionEvent:
        raw = cast(dict[str, Any], json.loads(data))
        return cls(
            event_id=str(raw["event_id"]),
            run_id=str(raw["run_id"]),
            kind=ExecutionEventKind(str(raw["kind"])),
            task_id=None if raw["task_id"] is None else str(raw["task_id"]),
            payload=cast(dict[str, Any], raw["payload"]),
            ts=datetime.fromisoformat(str(raw["ts"])),
        )


class ExecutionTransitionError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunState:
    run_id: str
    status: RunStatus
    tasks: dict[str, TaskStatus]
    attempts: dict[str, int]
    failures: dict[str, str] = field(default_factory=dict)

    @property
    def blocked_reason(self) -> str:
        if len(self.failures) == 1:
            return next(iter(self.failures.values()))
        return "; ".join(f"{task_id}: {reason}" for task_id, reason in sorted(self.failures.items()))

    @classmethod
    def initial(cls, spec: RunSpec) -> RunState:
        tasks = {
            task.task_id: TaskStatus.PENDING if task.dependencies else TaskStatus.READY
            for task in spec.tasks
        }
        return cls(
            run_id=spec.run_id,
            status=RunStatus.PENDING,
            tasks=tasks,
            attempts={task.task_id: 0 for task in spec.tasks},
        )

    @classmethod
    def replay(cls, spec: RunSpec, events: tuple[ExecutionEvent, ...]) -> RunState:
        state = cls.initial(spec)
        for event in events:
            state = apply_event(spec, state, event)
        return state


def _task_status(state: RunState, event: ExecutionEvent) -> tuple[str, TaskStatus]:
    if event.task_id is None:
        raise ExecutionTransitionError(f"{event.kind.value}: thiếu task_id")
    if event.task_id not in state.tasks:
        raise ExecutionTransitionError(f"{event.kind.value}: task không tồn tại: {event.task_id}")
    return event.task_id, state.tasks[event.task_id]


def _run_started(_spec: RunSpec, state: RunState, _event: ExecutionEvent) -> RunState:
    if state.status is not RunStatus.PENDING:
        raise ExecutionTransitionError(f"run_started chỉ hợp lệ từ PENDING, hiện là {state.status.value}")
    return replace(state, status=RunStatus.RUNNING)


def _run_cancelled(_spec: RunSpec, state: RunState, _event: ExecutionEvent) -> RunState:
    if state.status in {RunStatus.SUCCEEDED, RunStatus.CANCELLED}:
        raise ExecutionTransitionError(f"không cancel run terminal: {state.status.value}")
    tasks = {
        task_id: status if status is TaskStatus.SUCCEEDED else TaskStatus.CANCELLED
        for task_id, status in state.tasks.items()
    }
    return replace(state, status=RunStatus.CANCELLED, tasks=tasks, failures={})


def _task_started(_spec: RunSpec, state: RunState, event: ExecutionEvent) -> RunState:
    task_id, status = _task_status(state, event)
    if state.status is not RunStatus.RUNNING:
        raise ExecutionTransitionError(f"task_started: run phải RUNNING, hiện là {state.status.value}")
    if status is not TaskStatus.READY:
        raise ExecutionTransitionError(f"task_started: task phải READY, hiện là {status.value}")
    tasks = dict(state.tasks)
    attempts = dict(state.attempts)
    tasks[task_id] = TaskStatus.RUNNING
    attempts[task_id] += 1
    return replace(state, tasks=tasks, attempts=attempts)


def _unlock_ready(spec: RunSpec, tasks: dict[str, TaskStatus]) -> dict[str, TaskStatus]:
    out = dict(tasks)
    for task in spec.tasks:
        if out[task.task_id] is not TaskStatus.PENDING:
            continue
        if all(out[dependency] is TaskStatus.SUCCEEDED for dependency in task.dependencies):
            out[task.task_id] = TaskStatus.READY
    return out


def _task_succeeded(spec: RunSpec, state: RunState, event: ExecutionEvent) -> RunState:
    task_id, status = _task_status(state, event)
    if status is not TaskStatus.RUNNING:
        raise ExecutionTransitionError(f"task_succeeded: task phải RUNNING, hiện là {status.value}")
    tasks = dict(state.tasks)
    tasks[task_id] = TaskStatus.SUCCEEDED
    tasks = _unlock_ready(spec, tasks)
    complete = all(status is TaskStatus.SUCCEEDED for status in tasks.values())
    run_status = RunStatus.SUCCEEDED if complete else state.status
    return replace(state, status=run_status, tasks=tasks)


def _task_failed(_spec: RunSpec, state: RunState, event: ExecutionEvent) -> RunState:
    task_id, status = _task_status(state, event)
    if status is not TaskStatus.RUNNING:
        raise ExecutionTransitionError(f"task_failed: task phải RUNNING, hiện là {status.value}")
    tasks = dict(state.tasks)
    tasks[task_id] = TaskStatus.FAILED
    reason = str(event.payload.get("reason") or "task thất bại")
    failures = dict(state.failures)
    failures[task_id] = reason
    return replace(state, status=RunStatus.BLOCKED, tasks=tasks, failures=failures)


def _task_retried(_spec: RunSpec, state: RunState, event: ExecutionEvent) -> RunState:
    task_id, status = _task_status(state, event)
    if state.status is not RunStatus.BLOCKED:
        raise ExecutionTransitionError(f"task_retried: run phải BLOCKED, hiện là {state.status.value}")
    if status is not TaskStatus.FAILED:
        raise ExecutionTransitionError(f"task_retried: task phải FAILED, hiện là {status.value}")
    tasks = dict(state.tasks)
    tasks[task_id] = TaskStatus.READY
    failures = dict(state.failures)
    failures.pop(task_id)
    run_status = RunStatus.BLOCKED if failures else RunStatus.RUNNING
    return replace(state, status=run_status, tasks=tasks, failures=failures)


_HANDLER = {
    ExecutionEventKind.RUN_STARTED: _run_started,
    ExecutionEventKind.RUN_CANCELLED: _run_cancelled,
    ExecutionEventKind.TASK_STARTED: _task_started,
    ExecutionEventKind.TASK_SUCCEEDED: _task_succeeded,
    ExecutionEventKind.TASK_FAILED: _task_failed,
    ExecutionEventKind.TASK_RETRIED: _task_retried,
}


def apply_event(spec: RunSpec, state: RunState, event: ExecutionEvent) -> RunState:
    """Áp đúng một event. Hàm thuần: không ghi đĩa; journal chỉ append event, state luôn dựng lại được."""
    if event.run_id != state.run_id or event.run_id != spec.run_id:
        raise ExecutionTransitionError(
            f"event {event.event_id} thuộc run khác: event={event.run_id}, state={state.run_id}, spec={spec.run_id}"
        )
    return _HANDLER[event.kind](spec, state, event)


class ExecutionJournalError(RuntimeError):
    pass


_JOURNAL_DDL = """
CREATE TABLE IF NOT EXISTS execution_events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    run_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_execution_events_run_seq ON execution_events(run_id, seq);
"""


class ExecutionJournal:
    """Append-only journal cho execution state; mở lại process chỉ replay event, không tin state trong RAM."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._db = sqlite3.connect(self.path)
        self._db.executescript(_JOURNAL_DDL)

    def append(self, event: ExecutionEvent) -> None:
        try:
            with self._db:
                self._db.execute(
                    "INSERT INTO execution_events(event_id, run_id, ts, body) VALUES (?,?,?,?)",
                    (event.event_id, event.run_id, event.ts.isoformat(), event.to_json()),
                )
        except sqlite3.IntegrityError as exc:
            raise ExecutionJournalError(f"event_id trùng: {event.event_id}") from exc

    def events(self, run_id: str) -> tuple[ExecutionEvent, ...]:
        rows = self._db.execute(
            "SELECT body FROM execution_events WHERE run_id = ? ORDER BY seq",
            (run_id,),
        ).fetchall()
        return tuple(ExecutionEvent.from_json(body) for (body,) in rows)

    def replay(self, spec: RunSpec) -> RunState:
        return RunState.replay(spec, self.events(spec.run_id))

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> ExecutionJournal:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
