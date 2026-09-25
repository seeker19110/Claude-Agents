"""Đọc journal chất lượng `<db>.quality.sqlite` (ADR-0021 §f: N3 đọc journal CHỈ ĐỌC, như cách đọc bus).

`ExecutionJournal.__init__` (`xagents_core.execution`) làm `sqlite3.connect(path)` (mở/tạo, GHI được) rồi
`PRAGMA journal_mode=WAL` + `CREATE TABLE IF NOT EXISTS` — dùng nó ở đây sẽ tạo file/bảng khi coordinator chưa từng
ký profile, giống hệt lý do `collect.py` không dùng `SQLiteBus` để đọc bus của công ty (xem đầu `collect.py`).
Module này mở bằng URI `mode=ro` như `collect._bodies`, rồi replay bằng đúng `RunSpec`/`ExecutionEvent`/`RunState`
của core — không chép lại state machine, chỉ chép lại CÁCH ĐỌC.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from xagents_core.execution import ExecutionEvent, RunSpec, RunState, TaskStatus

QUALITY_TASK_ID = "quality:accept"
_DECIDED = {TaskStatus.SUCCEEDED, TaskStatus.FAILED}
_TIMEOUT_S = 1.0


def _connect_ro(db: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=_TIMEOUT_S)


def _runs(db: Path) -> list[tuple[str, str]]:
    con = _connect_ro(db)
    try:
        return [(str(r), str(b)) for r, b in con.execute("SELECT run_id, body FROM execution_runs ORDER BY run_id")]
    finally:
        con.close()


def _events(db: Path, run_id: str) -> tuple[ExecutionEvent, ...]:
    con = _connect_ro(db)
    try:
        rows = con.execute("SELECT body FROM execution_events WHERE run_id = ? ORDER BY seq", (run_id,)).fetchall()
    finally:
        con.close()
    return tuple(ExecutionEvent.from_json(str(body)) for (body,) in rows)


def _findings(events: tuple[ExecutionEvent, ...]) -> tuple[str, ...]:
    """Blockers của lần chấm `quality:accept` gần nhất — payload `result.findings`
    (`company.quality_execution.commit_quality_result`: mỗi blocker là `<check_id>:<lý do>` hoặc `execution:*`)."""
    result = next((e.payload.get("result") for e in reversed(events)
                  if e.task_id == QUALITY_TASK_ID and isinstance(e.payload.get("result"), dict)), None)
    return tuple(str(f) for f in (result or {}).get("findings") or ())


def contracts(journal_path: Path) -> list[dict[str, Any]] | None:
    """Một dòng cho mỗi run đã đăng ký: `run_id`, trạng thái `quality:accept`, check đã pass/chưa, blocker.

    `None` khi journal chưa tồn tại — trang hiện "không có profile"; console KHÔNG được tạo file để trả lời câu hỏi
    này (bất biến N3, ADR-0021 §f). Đọc hỏng (file rác, không phải SQLite) cũng trả `None` thay vì ném — cùng
    nguyên tắc `_View`: nguồn hỏng là trạng thái bình thường, không phải lỗi 500 của cả trang.
    """
    if not journal_path.is_file(): return None
    try:
        runs = _runs(journal_path)
        out: list[dict[str, Any]] = []
        for run_id, body in runs:
            spec = RunSpec.from_json(body)
            events = _events(journal_path, run_id)
            state = RunState.replay(spec, events)
            status = state.tasks.get(QUALITY_TASK_ID)
            required = next((t.acceptance for t in spec.tasks if t.task_id == QUALITY_TASK_ID), ())
            # Chỉ "pass" khi ĐÃ có lượt chấm (SUCCEEDED/FAILED); đang RUNNING/READY thì chưa check nào được xác
            # nhận — không được coi "không có trong findings" là "đã pass" khi chưa hề chạy.
            failed = {f.split(":", 1)[0] for f in _findings(events)} if status in _DECIDED else set(required)
            out.append({
                "run_id": run_id,
                "status": status.value if status is not None else "unknown",
                "checks_total": list(required),
                "checks_passed": [c for c in required if c not in failed],
                "blocker": state.blocked_reason,
            })
        return out
    except (sqlite3.Error, ValueError, KeyError):
        return None
