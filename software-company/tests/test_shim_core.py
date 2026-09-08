"""Shim `company.X -> xagents_core.X` (K3 kịch bản B) phải giữ ĐÚNG bề mặt cũ.

Bất biến 1 của kịch bản B: mọi tên `company.X` mà console/test/tài liệu đang import vẫn import được suốt
chương trình. File này là chốt cho bất biến đó — thêm module chuyển sang core ở bước sau thì thêm một dòng
vào `SHIM`, đừng viết một file test mới.
"""
from __future__ import annotations

import importlib

import pytest

# (tên module company, tên module core)
SHIM: list[tuple[str, str]] = [("company.context", "xagents_core.context"),
                               ("company.routing", "xagents_core.routing")]   # K3.3d

# K3.2: shim CÓ một phần cấu hình. `company.sandbox` giữ `sandbox_from_config` vì đó là chỗ duy nhất biết mình
# phục vụ công ty nào (biến `COMPANY_SANDBOX*`, `cfg.sandbox`, mặc định `auto`) — đưa vào core là đưa một câu
# `if prefix == …` vào lõi, đúng thứ ADR gốc 0001 cấm. Chúng vẫn phải mang đủ tên core sang, và vẫn KHÔNG được
# mọc lại khung: một `class`/`@dataclass` ở đây nghĩa là bản fork thứ hai đã quay lại.
SHIM_CO_CAU_HINH: list[tuple[str, str]] = [("company.sandbox", "xagents_core.sandbox")]


@pytest.mark.parametrize(("cong_ty", "core"), SHIM + SHIM_CO_CAU_HINH)
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


@pytest.mark.parametrize(("cong_ty", "core"), SHIM_CO_CAU_HINH)
def test_shim_co_cau_hinh_khong_moc_lai_khung(cong_ty: str, core: str):
    """Được phép có hàm đọc cấu hình; KHÔNG được phép có lại kiểu dữ liệu hay backend. Ranh giới đo bằng
    `class`/`@dataclass`: đó là hình dạng mà bản sao cũ của `sandbox.py` từng có."""
    from pathlib import Path

    import company
    src = (Path(company.__file__).parent / f"{cong_ty.split('.')[-1]}.py").read_text(encoding="utf-8")
    cam = [ln for ln in src.splitlines() if ln.startswith(("class ", "@dataclass"))]
    assert not cam, f"{cong_ty} định nghĩa lại {cam} — khung phải ở core"


# ---------- K3.3b: `LLMConfig` là LỚP CON của core, không phải bản fork thứ hai ----------

def test_llmconfig_ke_thua_khung_core_va_chi_them_truong_cua_company():
    """`company.llm` chưa phải shim (bốn adapter còn ở lại tới K3.3c), nhưng cấu hình thì đã là khung của core.
    Ca này canh hai chiều: kế thừa thật, và phần thêm vào ĐÚNG là những gì studio không có. Một trường chung mọc
    lại ở đây (`base_url`, `max_tokens`, `backends`…) nghĩa là bản fork đang quay lại từ dưới lên."""
    from dataclasses import fields

    from xagents_core.llm import LLMConfig as CoreLLMConfig

    from company.llm import LLMConfig

    assert issubclass(LLMConfig, CoreLLMConfig)
    them = {f.name for f in fields(LLMConfig)} - {f.name for f in fields(CoreLLMConfig)}
    assert them == {"cli_tools", "cli_max_turns", "cli_bash", "mcp_tools", "mcp_max_turns", "retries", "retry_base",
                    "prices", "budget_usd", "debt_reviews", "cli_max_budget_usd", "sandbox", "sandbox_image",
                    "sandbox_runtime"}


def test_thong_diep_thieu_model_goi_dung_bien_cua_company():
    """`PREFIX` của lớp con là thứ duy nhất giữ cho thông điệp lỗi gọi đúng biến người vận hành phải đặt. Đo ở đây
    vì core không biết tên công ty nào — nó chỉ đo được chuỗi `DEMO_`."""
    import pytest

    from company.llm import LLMConfig, LLMError

    with pytest.raises(LLMError, match=r"COMPANY_MODEL_STANDARD hoặc llm\.yaml"):
        LLMConfig().model_for("standard")


def test_core_config_cua_company_dung_mot_nguon():
    """`CORE` là chỗ duy nhất biết company tên gì và nằm ở đâu; `company.llm.ROOT/CONFIG_FILE` phải đọc từ đó chứ
    không dựng lại từ `__file__` của mình — hai nguồn cho một sự thật thì sớm muộn chúng lệch."""
    from company import llm
    from company.core import CORE

    assert CORE.prefix == "COMPANY" and CORE.db_name == "company.sqlite"
    assert (CORE.root / "llm.yaml").name == "llm.yaml" and (CORE.root / "agents").is_dir()
    assert llm.ROOT is CORE.root and llm.CONFIG_FILE == CORE.config_file
