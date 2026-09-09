"""engine.py: console bật/tắt động cơ của từng xưởng (ADR-0004).

Test chạy tiến trình con THẬT (`sys.executable -c ...`) chứ không mock `subprocess`: thứ đáng sai ở module này
là vòng đời tiến trình — bật hai lần, chết giữa chừng, tắt rồi vẫn khai đang chạy — và mock `Popen` thì đúng
những chỗ đó không được kiểm. Điều duy nhất thay là `SPECS`: không test nào được gọi orchestrator thật.
"""
from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from console import engine as en
from console.engine import COMPANY, KEEPER, STUDIO

SLEEP = "import time,sys; print('song', flush=True); time.sleep(60)"
DIE = "import sys; sys.stderr.write('vo tao roi\\n'); sys.exit(3)"


@dataclass(frozen=True)
class FakeSpec(en.EngineSpec):
    """Spec dùng đúng `EngineSpec` thật, chỉ đổi dòng lệnh sang một python vô hại."""

    code: str = SLEEP

    def argv(self, db: Path, interval: float) -> list[str]:
        return [sys.executable, "-c", self.code]


@pytest.fixture
def mgr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> en.EngineManager:
    monkeypatch.setitem(en.SPECS, COMPANY, FakeSpec("x", tmp_path, "xưởng phần mềm"))
    m = en.EngineManager({COMPANY: tmp_path / "company.sqlite", STUDIO: None, KEEPER: None},
                         log_dir=tmp_path / ".engine")
    yield m
    m.stop_all()


def _wait(mgr: en.EngineManager, xuong: str, state: str, timeout: float = 10.0) -> dict:
    """Chờ tới khi `status()` ĐO ĐƯỢC trạng thái mong đợi. Không `sleep` cố định: máy CI chậm hơn máy dev."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        one = next(e for e in mgr.status()["engines"] if e["xuong"] == xuong)
        if one["state"] == state:
            return one
        time.sleep(0.05)
    raise AssertionError(f"{xuong} không bao giờ tới trạng thái {state}: {mgr.status()}")


# ---------- dòng lệnh: không tham số nào của người đi vào argv ----------

def test_argv_company_chay_run_watch_trong_thu_muc_cong_ty() -> None:
    spec = en.SPECS[COMPANY]
    argv = spec.argv(Path("/tmp/company.sqlite"), 30.0)
    assert argv[:3] == [sys.executable, "-m", "company.orchestrator"]
    assert argv[-3:] == ["run", "--watch", "30.0"] and "--db" in argv
    assert spec.cwd.name == "software-company"   # gốc repo có company.sqlite RỖNG (AGENTS.md)


def test_argv_keeper_dung_lenh_watch_cua_no_kem_repo() -> None:
    argv = en.SPECS[KEEPER].argv(Path("/tmp/keeper.sqlite"), 300.0)
    assert argv[3] == "watch" and "--repo" in argv and argv[-2:] == ["--interval", "300.0"]


def test_argv_studio_giong_company() -> None:
    assert en.SPECS[STUDIO].argv(Path("/tmp/s.sqlite"), 12.0)[-3:] == ["run", "--watch", "12.0"]


# ---------- vòng đời ----------

def test_bat_roi_hoi_lai_thi_thay_dang_chay_kem_pid_va_log(mgr: en.EngineManager) -> None:
    r = mgr.start(COMPANY, interval=10, by="human:truc-ban")
    assert r["ok"] is True and r["state"] == "running" and r["pid"] > 0
    one = _wait(mgr, COMPANY, "running")
    assert one["by"] == "human:truc-ban" and one["interval"] == 10.0 and one["uptime_s"] >= 0
    assert Path(one["log"]).exists() and "console bật bởi human:truc-ban" in Path(one["log"]).read_text(encoding="utf-8")


def test_bat_hai_lan_thi_lan_hai_bi_chan_409(mgr: en.EngineManager) -> None:
    mgr.start(COMPANY, interval=10, by="human:a")
    with pytest.raises(en.EngineError) as e:
        mgr.start(COMPANY, interval=10, by="human:b")
    assert e.value.http_status == 409 and "đang chạy rồi" in str(e.value)


def test_tat_thi_tien_trinh_chet_that_va_ghi_lai_ai_tat(mgr: en.EngineManager) -> None:
    started = mgr.start(COMPANY, interval=10, by="human:a")
    r = mgr.stop(COMPANY, by="human:b")
    assert r["state"] == "exited" and r["stopped_by"] == "human:b"
    # pid không còn: bằng chứng máy, không phải lời khai của sổ
    con = subprocess.run([sys.executable, "-c", f"import os;os.kill({started['pid']},0)"], capture_output=True)
    assert con.returncode != 0 and b"ProcessLookupError" in con.stderr


def test_dong_co_tu_chet_thi_hien_exited_kem_ma_thoat_va_duoi_log(tmp_path: Path,
                                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    """Bẫy 'xanh vì đã bấm Bật': động cơ chết vì thiếu cấu hình phải nhìn khác hẳn động cơ đang chạy."""
    monkeypatch.setitem(en.SPECS, COMPANY, FakeSpec("x", tmp_path, "xưởng phần mềm", code=DIE))
    m = en.EngineManager({COMPANY: tmp_path / "c.sqlite"}, log_dir=tmp_path / ".engine")
    m.start(COMPANY, interval=10, by="human:a")
    one = _wait(m, COMPANY, "exited")
    assert one["exit_code"] == 3 and "vo tao roi" in one["tail"] and "stopped_by" not in one
    assert m.status()["engines"][0]["state"] == "exited"      # hỏi lại vẫn nhớ vì sao


def test_tat_khi_khong_chay_bi_chan_409(mgr: en.EngineManager) -> None:
    with pytest.raises(en.EngineError) as e:
        mgr.stop(COMPANY, by="human:a")
    assert e.value.http_status == 409


def test_tat_dong_co_da_tu_chet_cung_bi_chan_409(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(en.SPECS, COMPANY, FakeSpec("x", tmp_path, "xưởng phần mềm", code=DIE))
    m = en.EngineManager({COMPANY: tmp_path / "c.sqlite"}, log_dir=tmp_path / ".engine")
    m.start(COMPANY, interval=10, by="human:a")
    _wait(m, COMPANY, "exited")
    with pytest.raises(en.EngineError):
        m.stop(COMPANY, by="human:a")


def test_stop_all_giet_moi_dong_co_console_da_bat(mgr: en.EngineManager) -> None:
    mgr.start(COMPANY, interval=10, by="human:a")
    mgr.stop_all()
    assert _wait(mgr, COMPANY, "exited")["state"] == "exited"
    mgr.stop_all()   # gọi lần hai không nổ: đường atexit chạy sau server_close


# ---------- từ chối ----------

@pytest.mark.parametrize("xuong,by,interval,mong", [
    ("xuong-la", "human:a", 30, "xưởng lạ"),
    (COMPANY, "  ", 30, "thiếu người bật"),
    (COMPANY, "human:a", "nhanh", "phải là số giây"),
    (COMPANY, "human:a", 1, "5–3600"),
    (COMPANY, "human:a", 9999, "5–3600"),
])
def test_start_tu_choi_tham_so_sai(mgr: en.EngineManager, xuong: str, by: str, interval, mong: str) -> None:
    with pytest.raises(en.EngineError, match=mong):
        mgr.start(xuong, interval=interval, by=by)


def test_start_tu_choi_khi_console_khong_co_db_cua_xuong(mgr: en.EngineManager) -> None:
    with pytest.raises(en.EngineError, match="không có đường dẫn bus"):
        mgr.start(STUDIO, interval=30, by="human:a")


def test_start_tu_choi_khi_thu_muc_cong_ty_khong_ton_tai(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(en.SPECS, COMPANY, FakeSpec("x", tmp_path / "khong-co", "xưởng phần mềm"))
    m = en.EngineManager({COMPANY: tmp_path / "c.sqlite"}, log_dir=tmp_path / ".engine")
    with pytest.raises(en.EngineError, match="không thấy thư mục"):
        m.start(COMPANY, interval=30, by="human:a")


def test_start_bao_500_khi_khong_chay_duoc_tien_trinh(mgr: en.EngineManager, monkeypatch: pytest.MonkeyPatch) -> None:
    def no(*a, **k):
        raise OSError("hết tiến trình")
    monkeypatch.setattr(en.subprocess, "Popen", no)
    with pytest.raises(en.EngineError) as e:
        mgr.start(COMPANY, interval=30, by="human:a")
    assert e.value.http_status == 500 and "hết tiến trình" in str(e.value)


def test_stop_tu_choi_xuong_la_va_thieu_nguoi(mgr: en.EngineManager) -> None:
    with pytest.raises(en.EngineError, match="xưởng lạ"):
        mgr.stop("xuong-la", by="human:a")
    with pytest.raises(en.EngineError, match="thiếu người tắt"):
        mgr.stop(COMPANY, by="")


# ---------- trạng thái đọc ----------

def test_xuong_khong_cau_hinh_db_hien_configured_false(mgr: en.EngineManager) -> None:
    st = {e["xuong"]: e for e in mgr.status()["engines"]}
    assert set(st) == {COMPANY, STUDIO, KEEPER}
    assert st[STUDIO]["configured"] is False and st[STUDIO]["state"] == "stopped" and st[STUDIO]["tail"] == ""
    assert st[COMPANY]["configured"] is True


def test_fingerprint_doi_khi_bat_va_khi_tat(mgr: en.EngineManager) -> None:
    truoc = mgr.fingerprint()
    mgr.start(COMPANY, interval=10, by="human:a")
    giua = mgr.fingerprint()
    mgr.stop(COMPANY, by="human:a")
    assert truoc != giua != mgr.fingerprint()


def test_tail_tra_chuoi_rong_khi_khong_doc_duoc_log(tmp_path: Path) -> None:
    assert en._tail(tmp_path / "khong-co.log") == ""


def test_tail_chi_lay_may_dong_cuoi(tmp_path: Path) -> None:
    log = tmp_path / "a.log"
    log.write_text("\n".join(f"dong {i}" for i in range(200)), encoding="utf-8")
    duoi = en._tail(log).splitlines()
    assert len(duoi) == en.LOG_TAIL_LINES and duoi[-1] == "dong 199"


def test_ten_xuong_khong_lech_voi_decide() -> None:
    """`engine.py` chép ba hằng tên xưởng (xem chú thích ở đầu file). Chép thì phải có người canh."""
    from console import decide

    assert (en.COMPANY, en.STUDIO, en.KEEPER) == (decide.COMPANY, decide.STUDIO, decide.KEEPER)
    assert en.XUONG == decide.XUONG and set(en.SPECS) == set(decide.XUONG)
