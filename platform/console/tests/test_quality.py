"""console.quality: đọc `<db>.quality.sqlite` CHỈ ĐỌC (ADR-0021 §f) — console không bao giờ ghi/tạo journal này.

Journal fake dựng bằng chính `ExecutionJournal`/`RunSpec` của `xagents_core.execution` (như coordinator thật ghi),
không chép SQL tay — console chỉ đọc lại đúng những gì core đã ghi.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from xagents_core.execution import (
    Complexity,
    ExecutionEvent,
    ExecutionEventKind,
    ExecutionJournal,
    RunSpec,
    TaskSpec,
)

from console.quality import contracts

K = ExecutionEventKind


def _spec(run_id: str) -> RunSpec:
    return RunSpec(run_id, "mục tiêu", (
        TaskSpec(task_id="T1", objective="làm T1", complexity=Complexity.C2),
        TaskSpec(task_id="quality:accept", objective="nghiệm thu", dependencies=("T1",),
                 complexity=Complexity.C3, acceptance=("lint", "tests")),
    ))


def _emit(journal: ExecutionJournal, run_id: str, kind: ExecutionEventKind, task_id: str | None,
         payload: dict) -> None:
    events = journal.events(run_id)
    journal.transition(ExecutionEvent(run_id, kind, task_id, payload=payload,
                                      event_id=f"{run_id}:{task_id}:{kind.value}:{len(events)}",
                                      ts=datetime.now(UTC)),
                       expected_count=len(events))


def _run_to_quality_started(journal: ExecutionJournal, run_id: str) -> None:
    journal.register(_spec(run_id))
    _emit(journal, run_id, K.RUN_STARTED, None, {})
    _emit(journal, run_id, K.TASK_STARTED, "T1", {})
    _emit(journal, run_id, K.TASK_SUCCEEDED, "T1", {})
    _emit(journal, run_id, K.TASK_STARTED, "quality:accept", {})


def build_succeeded(path: Path, run_id: str = "RUN-OK") -> None:
    with ExecutionJournal(path) as journal:
        _run_to_quality_started(journal, run_id)
        _emit(journal, run_id, K.TASK_SUCCEEDED, "quality:accept",
              {"result": {"findings": []}, "reason": ""})


def build_failed(path: Path, run_id: str = "RUN-BLOCKED") -> None:
    with ExecutionJournal(path) as journal:
        _run_to_quality_started(journal, run_id)
        _emit(journal, run_id, K.TASK_FAILED, "quality:accept",
              {"result": {"findings": ["tests:missing", "lint:missing"]}, "reason": "tests:missing; lint:missing"})


# ---------- không có profile ----------

def test_khong_co_journal_tra_none_va_khong_tao_file(tmp_path: Path) -> None:
    db = tmp_path / "company.quality.sqlite"
    assert contracts(db) is None
    assert not db.exists(), "console không được tạo journal khi chưa ai ký profile"


# ---------- run succeeded ----------

def test_run_succeeded_hien_dung_trang_thai(tmp_path: Path) -> None:
    db = tmp_path / "company.quality.sqlite"
    build_succeeded(db)
    out = contracts(db)
    assert out == [{"run_id": "RUN-OK", "status": "succeeded",
                    "checks_total": ["lint", "tests"], "checks_passed": ["lint", "tests"], "blocker": ""}]


# ---------- run failed + blocker ----------

def test_run_failed_hien_blocker_va_check_chua_pass(tmp_path: Path) -> None:
    db = tmp_path / "company.quality.sqlite"
    build_failed(db)
    out = contracts(db)
    assert out == [{"run_id": "RUN-BLOCKED", "status": "failed", "checks_total": ["lint", "tests"],
                    "checks_passed": [], "blocker": "tests:missing; lint:missing"}]


# ---------- run đang chạy (chưa có kết quả) ----------

def test_run_dang_chay_chua_co_ket_qua(tmp_path: Path) -> None:
    """`quality:accept` mới `TASK_STARTED`, chưa có event kết quả nào mang `result.findings` — không check nào
    được coi là pass, không blocker (chưa hỏng, chỉ đang chạy)."""
    db = tmp_path / "company.quality.sqlite"
    with ExecutionJournal(db) as journal:
        _run_to_quality_started(journal, "RUN-RUNNING")
    out = contracts(db)
    assert out == [{"run_id": "RUN-RUNNING", "status": "running", "checks_total": ["lint", "tests"],
                    "checks_passed": [], "blocker": ""}]


# ---------- chỉ đọc: không được mở ghi ----------

def test_khong_mo_journal_o_che_do_ghi(tmp_path: Path) -> None:
    """`contracts()` không được đổi mtime/size của FILE JOURNAL CHÍNH, và không thêm/bớt run hay event nào —
    chứng minh nó không `INSERT`/`CREATE TABLE`/`PRAGMA journal_mode` như `ExecutionJournal.__init__` làm.

    (SQLite tự tạo companion `-shm`/`-wal` RỖNG khi mở ĐỌC một DB đã ở WAL mode — đó là cơ chế reader nội bộ
    của SQLite khi mở kết nối, không phải dữ liệu console ghi; file chính và số dòng mới là bằng chứng đúng chỗ.)
    """
    db = tmp_path / "company.quality.sqlite"
    build_succeeded(db)  # `ExecutionJournal` (writer thật) đã bật WAL khi ghi — đó là việc của N1, không phải N3
    before = db.stat()
    out1 = contracts(db)
    after = db.stat()
    assert (before.st_mtime, before.st_size) == (after.st_mtime, after.st_size)
    out2 = contracts(db)  # đọc lại lần hai phải giống hệt: không ghi gì thêm để lần sau khác đi
    assert out1 == out2 == [{"run_id": "RUN-OK", "status": "succeeded",
                             "checks_total": ["lint", "tests"], "checks_passed": ["lint", "tests"], "blocker": ""}]


def test_contracts_mo_bang_uri_ro(tmp_path: Path, monkeypatch) -> None:
    """Nếu ai đó lỡ đổi lại thành `sqlite3.connect(path)` thường (mở ghi), test này bắt được: giả một file KHÔNG
    phải SQLite hợp lệ nhưng named đúng đuôi — mở ghi thường sẽ không lỗi ngay (tự tạo DB mới đè lên); mở `mode=ro`
    trên file rỗng-không-phải-sqlite phải ném lỗi và được `contracts()` nuốt thành `None`, KHÔNG được ghi đè file."""
    db = tmp_path / "company.quality.sqlite"
    db.write_bytes(b"khong phai sqlite")
    before = db.read_bytes()
    assert contracts(db) is None
    assert db.read_bytes() == before
