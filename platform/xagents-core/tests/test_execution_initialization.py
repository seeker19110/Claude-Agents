"""A rejected journal must not leave a live SQLite connection behind."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from xagents_core.execution import ExecutionJournal


@pytest.mark.parametrize("corrupt", [True, False])
def test_initialization_failure_closes_connection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corrupt: bool) -> None:
    path = tmp_path / "broken.sqlite"
    if corrupt:
        path.write_bytes(b"not a sqlite database")
    else:
        db = sqlite3.connect(path)
        db.execute("CREATE TABLE execution_events (wrong_column TEXT)")
        db.close()
    connect = sqlite3.connect
    connections: list[sqlite3.Connection] = []

    def capture(*args: object, **kwargs: object) -> sqlite3.Connection:
        # The journal always opens the tested path; keep production connection options.
        conn = connect(path, check_same_thread=False, timeout=30.0)
        connections.append(conn)
        return conn

    monkeypatch.setattr("xagents_core.execution.sqlite3.connect", capture)
    try:
        with pytest.raises(sqlite3.DatabaseError):
            ExecutionJournal(path)
        assert len(connections) == 1
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connections[0].execute("SELECT 1")
    finally:
        for connection in connections:
            connection.close()
