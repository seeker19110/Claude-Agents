"""4L-1a: ngưỡng eval theo agent (`evals/thresholds.yaml`) là CỔNG CI, không chỉ dòng "CHÚ Ý".

Trước bản vá này `evals.py:311-356` chỉ đỏ khi bản ghi thiếu/lệch (`gate_ok`, ADR-0010); điểm chấm (`cases_ok`)
không bao giờ đổi mã thoát trừ khi bật tay `--fail-on-score`. Một agent tụt từ 90% xuống 60% qua nhiều lần ghi lại
(mỗi lần một PR riêng, không ai so trực tiếp với lần trước) thì CI vẫn xanh suốt. `thresholds.yaml` chốt điểm đo
HÔM NAY (làm tròn xuống 0.05) làm sàn: bản ghi mới thấp hơn sàn thì đỏ, không cần ai nhớ so sánh bằng mắt.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from company import evals


def _stub(monkeypatch: pytest.MonkeyPatch, ids: list[str], **over: Any) -> None:
    monkeypatch.setattr(evals, "load_agents", lambda: {i: object() for i in ids})
    monkeypatch.setattr(evals, "load_cases", over.get("load_cases", lambda aid: [object()]))
    monkeypatch.setattr(evals, "outdated_versions", lambda i: {})
    monkeypatch.setattr(evals, "required_agents", lambda: [])
    monkeypatch.setattr(evals, "ReplayClient", over.get("ReplayClient", lambda aid: object()))
    monkeypatch.setattr(evals, "run_eval", over.get("run_eval",
                        lambda aid, *a: [evals.CaseResult(name="c", passed=True, failures=[], tokens=1)]))


def _outcome(agent_id: str, passed: int, total: int) -> evals._AgentOutcome:
    res = [evals.CaseResult(name=f"c{i}", passed=i < passed, failures=[]) for i in range(total)]
    return evals._AgentOutcome(agent_id, [], True, passed == total, res)


# ---------- check_thresholds ----------

def test_diem_duoi_nguong_thi_do() -> None:
    th = {"qa": evals.Threshold(min_pass_ratio=0.9, cases=8)}
    fails = evals.check_thresholds([_outcome("qa", 6, 8)], th)  # 0.75 < 0.9
    assert fails and "dưới ngưỡng" in fails[0]


def test_diem_bang_nguong_thi_xanh() -> None:
    th = {"qa": evals.Threshold(min_pass_ratio=0.75, cases=8)}
    assert evals.check_thresholds([_outcome("qa", 6, 8)], th) == []  # 0.75 == 0.75


def test_thu_nho_bo_ca_thi_do() -> None:
    """Xoá bớt ca eval để né ngưỡng điểm cũng phải đỏ — `cases` chống thu nhỏ bộ."""
    th = {"qa": evals.Threshold(min_pass_ratio=0.5, cases=8)}
    fails = evals.check_thresholds([_outcome("qa", 4, 4)], th)  # 4/4 = 1.0 nhưng chỉ còn 4 ca, cần 8
    assert fails and "dưới ngưỡng" in fails[0]


def test_agent_khong_trong_file_khong_bi_chan() -> None:
    th = {"qa": evals.Threshold(min_pass_ratio=0.9, cases=8)}
    assert evals.check_thresholds([_outcome("builder", 0, 8)], th) == []


def test_khong_co_ca_khong_ap() -> None:
    th = {"qa": evals.Threshold(min_pass_ratio=0.9, cases=8)}
    assert evals.check_thresholds([_outcome("qa", 0, 0)], th) == []


# ---------- thresholds.yaml thật khớp REQUIRED.txt ----------

def test_thresholds_yaml_that_khop_required() -> None:
    required = set(evals.required_agents())
    th = evals.load_thresholds()
    assert required, "REQUIRED.txt rỗng — cập nhật ca test này nếu đúng là chủ ý"
    assert set(th) == required, f"thresholds.yaml phải khớp đúng REQUIRED.txt: {set(th)} != {required}"
    for t in th.values():
        assert 0 < t.min_pass_ratio <= 1
        assert t.cases > 0


# ---------- main: cổng thật ----------

def test_main_exit_1_khi_duoi_nguong(monkeypatch, tmp_path, capsys) -> None:
    th_path = tmp_path / "thresholds.yaml"
    th_path.write_text(yaml.safe_dump({"a0": {"min_pass_ratio": 0.9, "cases": 1}}), encoding="utf-8")
    _stub(monkeypatch, ["a0"],
          run_eval=lambda aid, *a: [evals.CaseResult(name="c", passed=False, failures=["x"], tokens=1)])
    rc = evals.main(["all", "--replay", "--thresholds", str(th_path)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "dưới ngưỡng" in out


def test_main_no_thresholds_tat_cong(monkeypatch, tmp_path, capsys) -> None:
    """Chiều ngược: `--no-thresholds` phải trả về hành vi CŨ — điểm thấp không làm CI đỏ."""
    th_path = tmp_path / "thresholds.yaml"
    th_path.write_text(yaml.safe_dump({"a0": {"min_pass_ratio": 0.9, "cases": 1}}), encoding="utf-8")
    _stub(monkeypatch, ["a0"],
          run_eval=lambda aid, *a: [evals.CaseResult(name="c", passed=False, failures=["x"], tokens=1)])
    rc = evals.main(["all", "--replay", "--thresholds", str(th_path), "--no-thresholds"])
    assert rc == 0


def test_load_thresholds_khong_co_file_tra_rong(tmp_path: Path) -> None:
    assert evals.load_thresholds(tmp_path / "khong-ton-tai.yaml") == {}


def test_main_khong_truyen_thresholds_va_file_mac_dinh_khong_ton_tai(monkeypatch, tmp_path, capsys) -> None:
    """Không `--thresholds`, không `--no-thresholds`, và `DEFAULT_THRESHOLDS_PATH` không tồn tại (repo khách
    chưa có `evals/thresholds.yaml`) → bỏ qua cổng ngưỡng êm, không đọc file, không lỗi."""
    monkeypatch.setattr(evals, "DEFAULT_THRESHOLDS_PATH", tmp_path / "khong-ton-tai.yaml")
    _stub(monkeypatch, ["a0"],
          run_eval=lambda aid, *a: [evals.CaseResult(name="c", passed=True, failures=[], tokens=1)])
    rc = evals.main(["all", "--replay"])
    assert rc == 0


def test_load_thresholds_sai_hinh_nem_llmerror(tmp_path: Path) -> None:
    p = tmp_path / "thresholds.yaml"
    p.write_text(yaml.safe_dump({"a0": {"min_pass_ratio": 0.9}}), encoding="utf-8")  # thiếu `cases`
    with pytest.raises(evals.LLMError):
        evals.load_thresholds(p)


def test_load_thresholds_sai_cu_phap_yaml_nem_llmerror(tmp_path: Path) -> None:
    p = tmp_path / "thresholds.yaml"
    p.write_text("a0: [không đóng ngoặc\n", encoding="utf-8")
    with pytest.raises(evals.LLMError):
        evals.load_thresholds(p)


def test_load_thresholds_khong_phai_mapping_nem_llmerror(tmp_path: Path) -> None:
    p = tmp_path / "thresholds.yaml"
    p.write_text(yaml.safe_dump(["a0", "a1"]), encoding="utf-8")
    with pytest.raises(evals.LLMError):
        evals.load_thresholds(p)


def test_load_thresholds_gia_tri_khong_phai_so_nem_llmerror(tmp_path: Path) -> None:
    p = tmp_path / "thresholds.yaml"
    p.write_text(yaml.safe_dump({"a0": {"min_pass_ratio": "cao", "cases": 8}}), encoding="utf-8")
    with pytest.raises(evals.LLMError):
        evals.load_thresholds(p)
