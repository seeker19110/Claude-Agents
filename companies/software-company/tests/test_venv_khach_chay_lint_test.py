"""ADR-0044: lint/test của repo khách phải chạy bằng MÔI TRƯỜNG CỦA KHÁCH, không phải venv của công ty.

Lỗi đo được 2026-09-23 trên CAMPUS-UNI/TCK-001: `stacks.PY` ghép argv bằng `sys.executable` — tức Python của
orchestrator — rồi chạy trong worktree khách. Django khai trong `pyproject.toml` của khách không có ở đó, nên
`pytest` chết ngay khâu collect (`ModuleNotFoundError: No module named 'django'`) với MỌI code builder viết ra:
ticket quay đủ 3 vòng rồi `ticket.blocked`. Đây là lỗi hạ tầng đội lốt lỗi builder.
"""

from __future__ import annotations

import sys

from company.stacks import detect

KHACH_DAY_DU = """\
[project]
name = "khach"
version = "1.0.0"
dependencies = ["django>=5.2,<6.0"]

[dependency-groups]
dev = ["pytest>=8.3", "pytest-django>=4.9", "coverage[toml]>=7.6", "ruff>=0.6"]
"""


def test_khach_khai_pytest_va_ruff_thi_chay_bang_moi_truong_cua_khach(tmp_path):
    """Đây là hình dáng thật của `campus-company`: `uv run` để Django của khách có mặt lúc collect."""
    (tmp_path / "pyproject.toml").write_text(KHACH_DAY_DU, encoding="utf-8")

    st = detect(tmp_path)

    assert st.name == "python"
    for argv in (st.lint, st.test):
        assert argv is not None
        assert argv[:2] == ["uv", "run"], argv
        assert sys.executable not in argv, f"vẫn dùng Python của công ty: {argv}"
    assert st.test_globs, "phân vùng ghi test/code (ADR-0028) không được mất theo"


def test_khach_khong_khai_pytest_thi_giu_duong_cu_chu_khong_bia_ra_mau_do(tmp_path):
    """Khách không mang bộ test riêng: `uv run` chỉ dựng venv rỗng rồi trả `No module named pytest` — một màu đỏ
    do hạ tầng, không do code. Giữ `sys.executable` thay vì đổi lỗi hạ tầng này lấy lỗi hạ tầng khác."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "k"\nversion = "1"\ndependencies = ["django"]\n', encoding="utf-8"
    )

    st = detect(tmp_path)

    assert st.test is not None and st.test[0] == sys.executable
    assert st.lint is not None and st.lint[0] == sys.executable


def test_khai_ruff_ma_khong_khai_pytest_thi_moi_lenh_quyet_dinh_rieng(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "k"\nversion = "1"\ndependencies = ["ruff>=0.6"]\n', encoding="utf-8"
    )

    st = detect(tmp_path)

    assert st.lint is not None and st.lint[:2] == ["uv", "run"]
    assert st.test is not None and st.test[0] == sys.executable


def test_khach_khai_cong_cu_o_optional_dependencies_van_tinh(tmp_path):
    """`[project.optional-dependencies]` là cách khai extras kiểu cũ — `uv sync --extra` vẫn cài, nên vẫn tính."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "k"\nversion = "1"\ndependencies = []\n'
        '\n[project.optional-dependencies]\ndev = ["pytest>=8.3", "ruff>=0.6"]\n',
        encoding="utf-8",
    )

    st = detect(tmp_path)

    assert st.lint is not None and st.lint[:2] == ["uv", "run"]
    assert st.test is not None and st.test[:2] == ["uv", "run"]


def test_pyproject_khong_co_bang_project_thi_giu_python_cua_cong_ty(tmp_path):
    """Chỉ có `[tool.*]` thì không phải dự án uv — `uv run` không chạy được trên nó."""
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 120\n", encoding="utf-8")

    st = detect(tmp_path)

    assert st.test is not None and st.test[0] == sys.executable


def test_pyproject_hong_thi_roi_ve_duong_cu_chu_khong_no(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project\nname =", encoding="utf-8")

    st = detect(tmp_path)

    assert st.test is not None and st.test[0] == sys.executable


def test_ten_goi_doc_tu_bang_toml_chu_khong_grep(tmp_path):
    """`pytest` nằm trong chuỗi mô tả KHÔNG phải là dependency — grep sẽ nhận nhầm, `tomllib` thì không."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "k"\nversion = "1"\ndescription = "chạy pytest và ruff bằng tay"\ndependencies = []\n',
        encoding="utf-8",
    )

    st = detect(tmp_path)

    assert st.test is not None and st.test[0] == sys.executable


def test_requirements_txt_khong_co_pyproject_thi_giu_python_cua_cong_ty(tmp_path):
    (tmp_path / "requirements.txt").write_text("django\npytest\n", encoding="utf-8")

    st = detect(tmp_path)

    assert st.test is not None and st.test[0] == sys.executable
