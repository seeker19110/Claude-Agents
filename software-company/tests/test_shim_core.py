"""Shim `company.X -> xagents_core.X` (K3 kịch bản B) phải giữ ĐÚNG bề mặt cũ.

Bất biến 1 của kịch bản B: mọi tên `company.X` mà console/test/tài liệu đang import vẫn import được suốt
chương trình. File này là chốt cho bất biến đó — thêm module chuyển sang core ở bước sau thì thêm một dòng
vào `SHIM`, đừng viết một file test mới.
"""
from __future__ import annotations

import importlib

import pytest

# (tên module company, tên module core)
SHIM: list[tuple[str, str]] = [("company.context", "xagents_core.context")]


@pytest.mark.parametrize(("cong_ty", "core"), SHIM)
def test_shim_giu_du_ten_public(cong_ty: str, core: str):
    a, b = importlib.import_module(cong_ty), importlib.import_module(core)
    assert b.__all__, f"{core} phải khai `__all__` — nó là HỢP ĐỒNG của shim, `import *` chỉ mang tên trong đó"
    for ten in b.__all__:
        assert hasattr(a, ten), f"{cong_ty} thiếu `{ten}` — shim không mang sang, người gọi vỡ ở chỗ khác"
        assert getattr(a, ten) is getattr(b, ten), f"{cong_ty}.{ten} không phải CÙNG đối tượng với {core}.{ten}"


@pytest.mark.parametrize(("cong_ty", "core"), SHIM)
def test_shim_mong_khong_co_logic(cong_ty: str, core: str):
    """Shim phải là chuyển tiếp thuần. Một dòng logic lọt vào đây là một bản fork thứ hai mọc lại — đúng thứ
    K3 sinh ra để xoá. `wc -l` ≤ 6 (docstring 2 dòng + 2 dòng import + lề)."""
    from pathlib import Path

    import company
    src = (Path(company.__file__).parent / f"{cong_ty.split('.')[-1]}.py").read_text(encoding="utf-8")
    code = [ln for ln in src.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert len(code) <= 6, f"{cong_ty} dày {len(code)} dòng — shim phải mỏng"
    assert all(ln.startswith(('"""', "from ", "import ")) or ln.endswith('"""') for ln in code), \
        f"{cong_ty} có dòng không phải docstring/import — shim không được mang logic"
