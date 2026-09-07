"""K5.3/K5.4 kịch bản B: `--jobs N` chạy nhiều agent song song, và bảng điểm vào job summary.

Hai thứ này tồn tại vì cùng một lý do: trước K5, ghi lại bản ghi eval chỉ làm được trên MÁY CÁ NHÂN có API key
(`make eval-record`), nên bước 3 của checklist 7 bước là cửa hẹp một người. Workflow `eval-record.yml` mở cửa đó
ra; `--jobs` làm 21 agent chạy vừa trong `timeout-minutes: 45`; bảng điểm để người merge PR bản ghi đọc được
điểm mà không phải mở log job.

Song song ở đây là chờ MẠNG (mỗi agent một lượt gọi model), không phải CPU — nên `ThreadPoolExecutor` là đúng
công cụ, và điều PHẢI giữ là: mỗi agent một client riêng, một file bản ghi riêng, và thứ tự IN không đổi.
"""
from __future__ import annotations

import threading
from typing import Any

import pytest

from company import evals


def _stub(monkeypatch: pytest.MonkeyPatch, ids: list[str], **over: Any) -> None:
    monkeypatch.setattr(evals, "load_agents", lambda: {i: object() for i in ids})
    monkeypatch.setattr(evals, "load_cases", over.get("load_cases", lambda aid: [object()]))
    monkeypatch.setattr(evals, "outdated_versions", lambda i: {})
    monkeypatch.setattr(evals, "required_agents", lambda: [])
    monkeypatch.setattr(evals, "ReplayClient", over.get("ReplayClient", lambda aid: object()))
    monkeypatch.setattr(evals, "run_eval", over.get("run_eval",
                        lambda aid, *a: [evals.CaseResult(name="c", passed=True, failures=[], tokens=1)]))


def test_jobs_giu_nguyen_thu_tu_in_du_chay_song_song(monkeypatch, capsys) -> None:
    """`--jobs` đổi thứ tự CHẠY, không đổi thứ tự ĐỌC. Nếu in thẳng trong luồng, dòng của bốn agent cài răng
    lược và `FAIL` không biết thuộc về ai — log không so được giữa hai lần chạy."""
    ids = [f"a{i}" for i in range(8)]
    _stub(monkeypatch, ids)
    assert evals.main(["all", "--replay", "--jobs", "4"]) == 0
    out = capsys.readouterr().out
    thu_tu = [ln.split(":")[0] for ln in out.splitlines() if ln.endswith("1/1 pass")]
    assert thu_tu == sorted(ids), f"phải in theo id, nhận được {thu_tu}"


def test_jobs_that_su_chay_nhieu_luong(monkeypatch) -> None:
    """Đo hai chiều cho chính cơ chế: bỏ nhánh `ThreadPoolExecutor` thì test này thấy đúng MỘT luồng."""
    ids = [f"a{i}" for i in range(6)]
    luong: set[int] = set()
    rao = threading.Barrier(3, timeout=10)

    def run_eval(aid: str, *a: Any) -> list[Any]:
        luong.add(threading.get_ident())
        rao.wait()   # sáu agent, ba luồng: rào chỉ mở khi có ĐỦ ba agent chạy CÙNG LÚC
        return [evals.CaseResult(name="c", passed=True, failures=[], tokens=1)]

    _stub(monkeypatch, ids, run_eval=run_eval)
    assert evals.main(["all", "--replay", "--jobs", "3"]) == 0
    assert len(luong) >= 3, f"phải có ít nhất 3 luồng thật, nhận được {len(luong)}"


def test_mot_agent_thi_khong_dung_pool(monkeypatch) -> None:
    """Một agent + `--jobs 8` phải đi đường tuần tự, và dù đi đường nào cũng CHỈ chạy đúng một lượt eval —
    dựng pool cho một việc là tốn không lý do, chạy hai lượt là tốn tiền thật hai lần."""
    _stub(monkeypatch, ["a0"])
    goi = {"n": 0}
    monkeypatch.setattr(evals, "run_eval", lambda *a: (goi.update(n=goi["n"] + 1),
                        [evals.CaseResult(name="c", passed=True, failures=[], tokens=1)])[1])
    assert evals.main(["a0", "--replay", "--jobs", "8"]) == 0 and goi["n"] == 1


def test_jobs_khong_hop_le_bi_chan_truoc_khi_tieu_tien(monkeypatch) -> None:
    """`--jobs 0` treo `ThreadPoolExecutor` (max_workers phải > 0); `--jobs -1` cũng vậy. Chặn ở argparse để
    lỗi hiện ngay khi gõ lệnh, không phải sau khi đã gọi model được một nửa."""
    _stub(monkeypatch, ["a0"])
    for bad in ("0", "-1"):
        with pytest.raises(SystemExit) as e:
            evals.main(["all", "--replay", "--jobs", bad])
        assert e.value.code == 2


def test_agent_hong_khong_keo_do_ca_lo_va_van_giu_dung_hai_loai_ket_qua(monkeypatch, capsys) -> None:
    """Chạy song song không được làm nhoè ranh giới `gate_ok` / `cases_ok` (ADR-0010): agent thiếu bản ghi làm
    ĐỎ (cổng), agent chấm không đạt thì KHÔNG (điểm)."""
    ids = ["a0", "a1"]

    def replay(aid: str) -> Any:
        if aid == "a0": raise evals.LLMError("chưa có bản ghi")
        return object()

    _stub(monkeypatch, ids, ReplayClient=replay,
          run_eval=lambda *a: [evals.CaseResult(name="c", passed=False, failures=["x"], tokens=1)])
    monkeypatch.setattr(evals, "required_agents", lambda: ["a0"])
    assert evals.main(["all", "--replay", "--strict", "--jobs", "2"]) == 1, "thiếu bản ghi = cổng đỏ"
    out = capsys.readouterr().out
    assert "FAIL a0" in out and "a1: 0/1 pass" in out

    monkeypatch.setattr(evals, "required_agents", lambda: [])
    monkeypatch.setattr(evals, "ReplayClient", lambda aid: object())
    assert evals.main(["all", "--replay", "--strict", "--jobs", "2"]) == 0, "chấm không đạt KHÔNG phải cổng"


def test_agent_khong_co_ca_eval_khong_lam_hong_lo_song_song(monkeypatch, capsys) -> None:
    _stub(monkeypatch, ["a0", "a1"], load_cases=lambda aid: [] if aid == "a0" else [object()])
    assert evals.main(["all", "--replay", "--jobs", "2"]) == 0
    out = capsys.readouterr().out
    assert "a0:" not in out and "a1: 1/1 pass" in out


# ---------- K5.4: bảng điểm vào job summary ----------

def test_bang_diem_vao_job_summary_khi_chay_trong_actions(monkeypatch, tmp_path, capsys) -> None:
    """`$GITHUB_STEP_SUMMARY` là cách DUY NHẤT người merge PR bản ghi thấy điểm mà không phải mở log job.
    Bảng phải nói CẢ hai cột — điểm chấm và trạng thái bản ghi — vì chúng là hai loại kết quả khác nhau."""
    f = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(f))
    _stub(monkeypatch, ["a0", "a1"],
          run_eval=lambda aid, *a: [evals.CaseResult(name="c", passed=aid == "a0", failures=[], tokens=1)])
    assert evals.main(["all", "--replay", "--jobs", "2"]) == 0
    body = f.read_text(encoding="utf-8")
    assert "| `a0` | 1/1 |" in body and "| `a1` | 0/1 |" in body
    assert "không phải cổng" in body, "bảng phải nói rõ điểm không làm CI đỏ, kẻo người đọc tưởng đỏ là hỏng"


def test_khong_o_trong_actions_thi_khong_ghi_gi(monkeypatch, capsys) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    _stub(monkeypatch, ["a0"])
    assert evals.main(["all", "--replay"]) == 0   # không ném dù không có biến


def test_summary_khong_ghi_duoc_thi_khong_lam_do_luot_ghi(monkeypatch, tmp_path) -> None:
    """Bảng điểm là THÔNG TIN, không phải kết quả: đĩa đầy hay đường dẫn hỏng không được vứt bỏ một lượt ghi
    eval vừa tốn tiền thật."""
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "khong-co-thu-muc" / "s.md"))
    _stub(monkeypatch, ["a0"])
    assert evals.main(["all", "--replay"]) == 0


def test_summary_bo_qua_agent_khong_chay_ca_nao(monkeypatch, tmp_path) -> None:
    """Agent không có ca eval không phải một dòng `0/0` trong bảng — đọc lên như thể nó trượt hết."""
    f = tmp_path / "s.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(f))
    _stub(monkeypatch, ["a0"], load_cases=lambda aid: [])
    assert evals.main(["all", "--replay"]) == 0
    assert not f.exists(), "không có gì để chấm thì không dựng bảng rỗng"
