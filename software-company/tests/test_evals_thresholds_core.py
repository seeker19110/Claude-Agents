"""p3.3: cơ chế ngưỡng eval chuyển lên `xagents_core.evals`; company DÙNG LẠI chứ không giữ bản riêng.

Ca ở đây là ca chống hồi quy cho việc chuyển: nếu ai đó chép lại một bản `Threshold`/`check_thresholds` riêng
vào `company.evals` thì hai công ty lại trôi khỏi nhau (đúng thứ ADR-0001 muốn chặn), và ca đầu sẽ đỏ.
"""
from __future__ import annotations

from pathlib import Path

from xagents_core import evals as core_evals

from company import evals


def test_company_dung_lai_co_che_cua_core() -> None:
    assert evals.Threshold is core_evals.Threshold
    assert evals.check_thresholds is core_evals.check_thresholds


def test_thresholds_yaml_cua_company_khong_doi() -> None:
    """Số của company giữ nguyên sau khi chuyển cơ chế lên core: 6 agent, sàn 0.95."""
    th = evals.load_thresholds()
    assert len(th) == 6
    assert all(t.min_pass_ratio == 0.95 for t in th.values())
    assert th["builder"].cases == 13 and th["supervisor"].cases == 3


def test_makefile_eval_replay_co_strict() -> None:
    """`make eval-replay` phải chạy đúng thứ CI chạy — thiếu `--strict` là cổng chỉ tồn tại trên CI,
    người sửa prompt ở máy không thấy đỏ cho tới khi đẩy lên."""
    mk = (Path(__file__).resolve().parents[1] / "Makefile").read_text(encoding="utf-8")
    body = mk.split("eval-replay:")[1].split("\neval-thresholds:")[0]
    assert "--strict" in body, body
