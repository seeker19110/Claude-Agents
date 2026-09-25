"""Real SQLite concurrency, rollback and lost-ACK checks for the quality adapter."""
from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from xagents_core.execution import (
    ExecutionEvent,
    ExecutionEventKind,
    ExecutionJournal,
    ExecutionJournalError,
    ExecutionTransitionError,
    RunSpec,
    RunStatus,
    TaskSpec,
    TaskStatus,
)


def spec() -> RunSpec:
    return RunSpec("run", "Test durable decisions", (TaskSpec("A", "Build"), TaskSpec("B", "Review", ("A",))))


def event(kind: ExecutionEventKind, task: str | None = None) -> ExecutionEvent:
    return ExecutionEvent("run", kind, task)


def test_transition_validates_and_commits_then_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "journal.sqlite"
    with ExecutionJournal(path) as journal:
        journal.register(spec())
        journal.transition(event(ExecutionEventKind.RUN_STARTED), expected_count=0)
        journal.transition(event(ExecutionEventKind.TASK_STARTED, "A"), expected_count=1)
        state = journal.transition(event(ExecutionEventKind.TASK_SUCCEEDED, "A"), expected_count=2)
        assert state.tasks == {"A": TaskStatus.SUCCEEDED, "B": TaskStatus.READY}
    with ExecutionJournal(path) as journal:
        assert journal.resume("run") == state
        assert len(journal.events("run")) == 3


def test_unknown_run_or_invalid_order_cannot_poison_journal(tmp_path: Path) -> None:
    with ExecutionJournal(tmp_path / "journal.sqlite") as journal:
        with pytest.raises(ExecutionJournalError, match="chưa đăng ký"):
            journal.transition(event(ExecutionEventKind.RUN_STARTED), expected_count=0)
        assert journal.events("run") == ()
        journal.register(spec())
        with pytest.raises(ExecutionTransitionError):
            journal.transition(event(ExecutionEventKind.TASK_SUCCEEDED, "A"), expected_count=0)
        assert journal.events("run") == ()
        assert journal.resume("run").status is RunStatus.PENDING


def test_stale_count_rejected_without_partial_write(tmp_path: Path) -> None:
    with ExecutionJournal(tmp_path / "journal.sqlite") as journal:
        journal.register(spec())
        journal.transition(event(ExecutionEventKind.RUN_STARTED), expected_count=0)
        with pytest.raises(ExecutionJournalError, match="stale"):
            journal.transition(event(ExecutionEventKind.TASK_STARTED, "A"), expected_count=0)
        assert len(journal.events("run")) == 1
        assert journal.resume("run").attempts["A"] == 0


@pytest.mark.parametrize("count", [-1, True, 1.5])
def test_count_is_a_nonnegative_integer(tmp_path: Path, count: object) -> None:
    with ExecutionJournal(tmp_path / "journal.sqlite") as journal:
        with pytest.raises(ValueError, match="expected_count"):
            journal.transition(event(ExecutionEventKind.RUN_STARTED), expected_count=count)  # type: ignore[arg-type]


def test_lost_ack_replays_identical_id_not_work_and_preserves_original_timestamp(tmp_path: Path) -> None:
    start = event(ExecutionEventKind.RUN_STARTED)
    path = tmp_path / "journal.sqlite"
    with ExecutionJournal(path) as journal:
        journal.register(spec())
        journal.transition(start, expected_count=0)
        state = journal.transition(event(ExecutionEventKind.TASK_STARTED, "A"), expected_count=1)
    with ExecutionJournal(path) as journal:
        assert journal.transition(replace(start, ts=start.ts + timedelta(hours=1)), expected_count=0) == state
        assert len(journal.events("run")) == 2
        assert journal.events("run")[0].ts == start.ts


@pytest.mark.parametrize("change", ["payload", "kind", "run", "task"])
def test_reused_event_id_with_different_content_is_not_ack(tmp_path: Path, change: str) -> None:
    start = event(ExecutionEventKind.RUN_STARTED)
    with ExecutionJournal(tmp_path / "journal.sqlite") as journal:
        journal.register(spec())
        journal.register(replace(spec(), run_id="other"))
        journal.transition(start, expected_count=0)
        changes: dict[str, object] = {"payload": {"reason": "different"}, "kind": ExecutionEventKind.RUN_CANCELLED,
                                     "run_id": "other", "task_id": "A"}
        key = {"payload": "payload", "kind": "kind", "run": "run_id", "task": "task_id"}[change]
        conflicting = replace(start, **{key: changes[key]})
        if change == "task":
            conflicting = replace(conflicting, kind=ExecutionEventKind.TASK_STARTED)
        with pytest.raises(ExecutionJournalError, match="collision"):
            journal.transition(conflicting, expected_count=1)
        assert journal.resume("run").status is RunStatus.RUNNING
        assert journal.events("other") == ()


def test_run_count_is_not_global_sequence(tmp_path: Path) -> None:
    with ExecutionJournal(tmp_path / "journal.sqlite") as journal:
        journal.register(spec())
        journal.register(replace(spec(), run_id="other"))
        journal.transition(event(ExecutionEventKind.RUN_STARTED), expected_count=0)
        journal.transition(replace(event(ExecutionEventKind.RUN_STARTED), run_id="other"), expected_count=0)
        journal.transition(event(ExecutionEventKind.TASK_STARTED, "A"), expected_count=1)
        assert len(journal.events("run")) == 2


def test_two_connections_compete_for_one_transition(tmp_path: Path) -> None:
    path = tmp_path / "journal.sqlite"
    with ExecutionJournal(path) as first, ExecutionJournal(path) as second:
        first.register(spec())
        ready = threading.Barrier(2)

        def write(journal: ExecutionJournal) -> str:
            ready.wait(timeout=10)
            try:
                journal.transition(event(ExecutionEventKind.RUN_STARTED), expected_count=0)
            except ExecutionJournalError:
                return "rejected"
            return "accepted"

        with ThreadPoolExecutor(2) as pool:
            assert sorted(pool.map(write, (first, second))) == ["accepted", "rejected"]
        assert len(first.events("run")) == 1
        assert first.resume("run").status is RunStatus.RUNNING


def test_two_connections_register_identical_spec_idempotently(tmp_path: Path) -> None:
    path = tmp_path / "journal.sqlite"
    with ExecutionJournal(path) as first, ExecutionJournal(path) as second:
        ready = threading.Barrier(2)

        def register(journal: ExecutionJournal) -> None:
            ready.wait(timeout=10)
            journal.register(spec())

        with ThreadPoolExecutor(2) as pool:
            list(pool.map(register, (first, second)))
        assert first.load_spec("run") == spec()


def test_failed_insert_rolls_back_and_releases_write_lock(tmp_path: Path) -> None:
    path = tmp_path / "journal.sqlite"
    with ExecutionJournal(path) as first, ExecutionJournal(path) as second:
        first.register(spec())
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TRIGGER reject_event BEFORE INSERT ON execution_events "
                               "BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
        connection.close()
        with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
            first.transition(event(ExecutionEventKind.RUN_STARTED), expected_count=0)
        assert first.events("run") == ()
        with sqlite3.connect(path) as connection:
            connection.execute("DROP TRIGGER reject_event")
        connection.close()
        state = second.transition(event(ExecutionEventKind.RUN_STARTED), expected_count=0)
        assert state.status is RunStatus.RUNNING


def test_equal_python_values_with_different_json_types_are_collision(tmp_path: Path) -> None:
    start = replace(event(ExecutionEventKind.RUN_STARTED), payload={"flag": True})
    with ExecutionJournal(tmp_path / "journal.sqlite") as journal:
        journal.register(spec())
        journal.transition(start, expected_count=0)
        with pytest.raises(ExecutionJournalError, match="collision"):
            journal.transition(replace(start, payload={"flag": 1}), expected_count=0)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_payload_is_not_persisted(tmp_path: Path, value: float) -> None:
    with ExecutionJournal(tmp_path / "journal.sqlite") as journal:
        journal.register(spec())
        with pytest.raises(ValueError):
            journal.transition(replace(event(ExecutionEventKind.RUN_STARTED), payload={"cost": value}), expected_count=0)
        assert journal.events("run") == ()


@pytest.mark.parametrize("field", ["event_id", "run_id"])
def test_blank_event_identity_is_not_persisted(tmp_path: Path, field: str) -> None:
    with ExecutionJournal(tmp_path / "journal.sqlite") as journal:
        journal.register(spec())
        with pytest.raises(ValueError, match="identity"):
            journal.transition(replace(event(ExecutionEventKind.RUN_STARTED), **{field: " "}), expected_count=0)


def test_naive_event_timestamp_rejected(tmp_path: Path) -> None:
    start = event(ExecutionEventKind.RUN_STARTED)
    with ExecutionJournal(tmp_path / "journal.sqlite") as journal:
        journal.register(spec())
        with pytest.raises(ValueError, match="timezone"):
            journal.transition(replace(start, ts=start.ts.replace(tzinfo=None)), expected_count=0)


def test_run_event_cannot_carry_ignored_task_id(tmp_path: Path) -> None:
    with ExecutionJournal(tmp_path / "journal.sqlite") as journal:
        journal.register(spec())
        with pytest.raises(ValueError, match="run event"):
            journal.transition(event(ExecutionEventKind.RUN_STARTED, "A"), expected_count=0)
        assert journal.events("run") == ()
