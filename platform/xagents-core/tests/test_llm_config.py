"""`LLMConfig` + `load_config` chung (K3.3b).

Đo phần KHUNG: khoá `llm.yaml` hai công ty cùng đọc, bốn biến môi trường chung, bộ lọc `backends`, và việc
`backend_config` sinh ra ĐÚNG lớp con của công ty. Trường riêng của company (giá, ngân sách, sandbox, CLI/MCP) và
tiền tố thật (`COMPANY_*`, `STUDIO_*`) vẫn được đo ở test của chính công ty đó — core không biết tên công ty nào.

Ba chỗ dễ hỏng mà mỗi ca dưới đây canh đúng một chỗ:

1. `type(self)` trong `backend_config` — trả `LLMConfig` trần thì mọi trường riêng của công ty biến mất **ngay khi**
   cấu hình có `backends:`, và không có lỗi nào nổi lên: cấu hình một backend vẫn chạy, cấu hình hai backend thì
   lặng lẽ mất ngân sách.
2. `max_input_chars` phải ở `apply_yaml` chứ không `apply_backend_yaml`: trần prompt là của cả hệ, mỗi backend một
   trần thì cùng một agent bị cắt khác nhau tuỳ tài khoản nào còn hạn mức.
3. `select_backends` chạy SAU `apply_env`: nó đọc `self.backends` mà `apply_env` còn ghi vào (biến `LLM_PROVIDER`
   xoá sạch `backends`).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

import pytest

from xagents_core import CoreConfig
from xagents_core.llm import MAY_CONFIG_ENV, LLMConfig, LLMError, explain_config, load_config, may_config_file


def _core(root: Path) -> CoreConfig:
    return CoreConfig(prefix="DEMO", root=root, db_name="demo.sqlite")


@dataclass
class ConCty(LLMConfig):
    """Lớp con tối giản, đóng vai `company.LLMConfig`: một trường riêng + một khoá yaml riêng."""
    PREFIX: ClassVar[str] = "DEMO"
    budget_usd: float | None = None
    ghi_chu: list[str] = field(default_factory=list)

    def apply_yaml(self, data: Mapping[str, Any]) -> None:
        super().apply_yaml(data)
        if data.get("budget_usd") is not None: self.budget_usd = float(data["budget_usd"])

    def apply_env(self, env: Mapping[str, str], core: CoreConfig) -> None:
        super().apply_env(env, core)
        if env.get(core.env_name("BUDGET_USD")): self.budget_usd = float(env[core.env_name("BUDGET_USD")])


def _yaml(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "llm.yaml"; p.write_text(text, encoding="utf-8"); return p


# ---------- model theo tier ----------

def test_model_for_lui_dan_light_standard_strong():
    cfg = LLMConfig(models={"strong": "S", "standard": "", "light": ""})
    assert cfg.model_for("light") == cfg.model_for("standard") == cfg.model_for("strong") == "S"
    assert LLMConfig(models={"strong": "S", "standard": "M", "light": ""}).model_for("light") == "M"


def test_model_for_khong_co_model_nao_thi_bao_dung_ten_bien_cua_cong_ty():
    """Thông điệp phải gọi ĐÚNG biến người vận hành cần đặt. `PREFIX` là ClassVar nên một `LLMConfig()` dựng tay
    trong test cũng báo đúng tên, không phải chuỗi rỗng vì người dựng quên truyền tiền tố."""
    with pytest.raises(LLMError, match=r"DEMO_MODEL_STRONG hoặc llm\.yaml"):
        ConCty().model_for("strong")


def test_tiers_configured_chi_dem_tier_co_model():
    assert LLMConfig(models={"strong": "S", "standard": "", "light": "L"}).tiers_configured() == {"strong", "light"}


# ---------- llm.yaml ----------

def test_apply_yaml_doc_khoa_chung(tmp_path: Path):
    p = _yaml(tmp_path, "provider: openai\nmodels: {strong: A, light: C}\nbase_url: http://x/v1\n"
                        "max_tokens: 99\neffort: {light: low}\nextra: {top_p: 0.5}\nmax_input_chars: 42\n")
    cfg = load_config(_core(tmp_path), p, cls=LLMConfig)
    assert (cfg.provider, cfg.base_url, cfg.max_tokens, cfg.max_input_chars) == ("openai", "http://x/v1", 99, 42)
    assert cfg.models == {"strong": "A", "standard": "", "light": "C"} and cfg.extra == {"top_p": 0.5}
    assert cfg.effort["light"] == "low" and cfg.effort["strong"] == "high"   # `effort` là update, không thay bảng


def test_khong_co_file_thi_van_ra_cau_hinh_mac_dinh(tmp_path: Path):
    cfg = load_config(_core(tmp_path), tmp_path / "khong-co.yaml", cls=LLMConfig)
    assert cfg.provider == "fake" and cfg.max_input_chars == 120_000 and cfg.backends == []


def test_load_config_khong_truyen_path_thi_lay_llm_yaml_cua_cong_ty(tmp_path: Path):
    _yaml(tmp_path, "provider: openai\n")
    assert load_config(_core(tmp_path), cls=LLMConfig).provider == "openai"


def test_load_config_giu_lop_con_va_khoa_rieng(tmp_path: Path):
    p = _yaml(tmp_path, "provider: openai\nbudget_usd: 12\n")
    cfg = load_config(_core(tmp_path), p, cls=ConCty)
    assert isinstance(cfg, ConCty) and cfg.budget_usd == 12.0


# ---------- biến môi trường ----------

def test_env_thang_file_va_provider_dich_danh_xoa_backends(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    p = _yaml(tmp_path, "provider: openai\nbackends: [{name: a, provider: fake}]\n")
    monkeypatch.setenv("DEMO_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("DEMO_MODEL_STRONG", "opus")
    monkeypatch.setenv("DEMO_LLM_BASE_URL", "http://env/v1")
    monkeypatch.setenv("DEMO_LLM_API_KEY", "k")
    monkeypatch.setenv("DEMO_MAX_INPUT_CHARS", "7")
    cfg = load_config(_core(tmp_path), p, cls=LLMConfig)
    assert cfg.provider == "anthropic" and cfg.backends == []
    assert (cfg.models["strong"], cfg.base_url, cfg.api_key, cfg.max_input_chars) == ("opus", "http://env/v1", "k", 7)


def test_env_cua_lop_con_doc_sau_env_chung(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEMO_BUDGET_USD", "3.5")
    assert load_config(_core(tmp_path), cls=ConCty).budget_usd == 3.5


# ---------- backends ----------

def test_select_backends_loc_va_sap_thu_tu_va_cat_prefer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    p = _yaml(tmp_path, "backends: [{name: a, provider: fake}, {name: b, provider: fake}]\n"
                        "routing: {prefer: {strong: a, light: b}}\n")
    monkeypatch.setenv("DEMO_LLM_BACKENDS", "b")
    cfg = load_config(_core(tmp_path), p, cls=LLMConfig)
    assert [b["name"] for b in cfg.backends] == ["b"] and cfg.routing["prefer"] == {"light": "b"}


def test_select_backends_nhac_ten_khong_co_thi_hong_to(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    p = _yaml(tmp_path, "backends: [{name: a, provider: fake}]\n")
    monkeypatch.setenv("DEMO_LLM_BACKENDS", "a, khong-co")
    with pytest.raises(LLMError, match=r"DEMO_LLM_BACKENDS nhắc backend không có trong llm\.yaml: \['khong-co'\]"):
        load_config(_core(tmp_path), p, cls=LLMConfig)


def test_select_backends_chay_sau_apply_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """`DEMO_LLM_PROVIDER` xoá `backends`, nên bộ lọc phải thấy danh sách RỖNG và báo thiếu — nếu nó chạy trên
    danh sách đọc từ file thì hai biến cùng đặt sẽ cho một cấu hình không tồn tại ở đâu cả."""
    p = _yaml(tmp_path, "backends: [{name: a, provider: fake}]\n")
    monkeypatch.setenv("DEMO_LLM_PROVIDER", "anthropic"); monkeypatch.setenv("DEMO_LLM_BACKENDS", "a")
    with pytest.raises(LLMError, match=r"\['a'\]"):
        load_config(_core(tmp_path), p, cls=LLMConfig)


def test_backend_config_thua_ke_khoa_chung_va_ghi_de_theo_phan_tu():
    goc = ConCty(provider="openai", max_tokens=50, max_input_chars=9, budget_usd=8.0,
                 models={"strong": "S", "standard": "", "light": ""}, extra={"top_p": 0.1})
    b = goc.backend_config({"provider": "codex", "models": {"strong": "X"}, "max_tokens": 70,
                            "config_dir": "/c", "binary": "/b", "api_key": "kk"})
    assert isinstance(b, ConCty), "lớp con phải sinh ra lớp con — nếu không, trường riêng biến mất khi có backends"
    assert b.budget_usd == 8.0 and b.max_input_chars == 9      # thừa kế
    assert (b.provider, b.max_tokens, b.name) == ("codex", 70, "codex")
    assert (b.config_dir, b.binary, b.api_key) == ("/c", "/b", "kk")
    assert b.models == {"strong": "X", "standard": "", "light": ""}, "không `inherit_models` thì KHÔNG mượn model"
    assert goc.models["strong"] == "S" and goc.extra == {"top_p": 0.1}, "không được sửa cấu hình cấp trên"


def test_backend_config_inherit_models_va_ten_mac_dinh_va_api_key_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KEY_O_ENV", "bimat")
    goc = LLMConfig(models={"strong": "S", "standard": "M", "light": ""})
    b = goc.backend_config({"name": "sub", "inherit_models": True, "api_key_env": "KEY_O_ENV"})
    assert b.name == "sub" and b.models["standard"] == "M" and b.api_key == "bimat"
    b.models["standard"] = "khac"
    assert goc.models["standard"] == "M", "`inherit_models` phải là BẢN SAO, không phải cùng một dict"


def test_max_input_chars_khong_doc_o_cap_backend():
    """Trần prompt là thuộc tính của cả hệ. Đọc được ở cấp backend thì cùng một agent bị cắt khác nhau tuỳ tài
    khoản nào còn hạn mức — một lỗi chỉ lộ ra khi backend đầu hết quota."""
    b = LLMConfig(max_input_chars=100).backend_config({"max_input_chars": 5})
    assert b.max_input_chars == 100


def test_select_backends_khong_co_prefer_thi_khong_dung_toi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """`routing:` không khai `prefer` → lọc backend xong là hết việc, không dựng dict rỗng.

    Cấu hình tối thiểu (chỉ `backends:`) là cấu hình MẶC ĐỊNH của một công ty mới, nên nhánh này chạy nhiều
    hơn nhánh có `prefer`; đọc `self.routing["prefer"]` vô điều kiện sẽ là `KeyError` ngay lần nạp đầu."""
    p = _yaml(tmp_path, "backends: [{name: a, provider: fake}, {name: b, provider: fake}]\n")
    monkeypatch.setenv("DEMO_LLM_BACKENDS", "b")

    cfg = load_config(_core(tmp_path), p, cls=LLMConfig)

    assert [b["name"] for b in cfg.backends] == ["b"]
    assert "prefer" not in cfg.routing
# ---------- p3.2c: TTL cache dài, mặc định TẮT ----------

def test_cache_ttl_mac_dinh_tat_va_doc_duoc_o_ca_hai_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """TTL là tính năng của PROVIDER (chỉ Anthropic hiểu), nên khác `max_input_chars`: đọc được ở cấp backend
    để một tài khoản bật TTL dài mà tài khoản kia không phải theo."""
    assert LLMConfig().cache_ttl is None, "mặc định TẮT: body y hệt hôm nay"
    p = _yaml(tmp_path, "provider: anthropic\ncache_ttl: 1h\nbackends:\n  - name: a\n  - name: b\n    cache_ttl: 5m\n")
    cfg = load_config(_core(tmp_path), p, cls=LLMConfig)
    assert cfg.cache_ttl == "1h"
    assert cfg.backend_config(cfg.backends[0]).cache_ttl == "1h", "backend thừa kế cấp trên"
    assert cfg.backend_config(cfg.backends[1]).cache_ttl == "5m", "backend ghi đè được"
    monkeypatch.setenv("DEMO_CACHE_TTL", "5m")
    assert load_config(_core(tmp_path), p, cls=LLMConfig).cache_ttl == "5m", "biến môi trường thắng file"


def test_cache_ttl_sai_gia_tri_hong_to(tmp_path: Path):
    """Bảng ĐÓNG như `CLAUDE_EFFORT`: `1 hour` viết sai thì phải báo, không được lặng lẽ rơi về 5 phút."""
    p = _yaml(tmp_path, "provider: anthropic\ncache_ttl: 1 hour\n")
    with pytest.raises(LLMError, match="cache_ttl"):
        load_config(_core(tmp_path), p, cls=LLMConfig)


# ---------- ADR-0016: tầng máy làm nền cho `llm.yaml` của package ----------



def test_may_config_file_mac_dinh_va_de_bang_bien_moi_truong(tmp_path: Path) -> None:
    """Tầng máy nằm NGOÀI repo — đó là cả điểm của nó: `llm.yaml` gitignored + luật mỗi phiên một worktree
    (`AGENTS.md` cấm §2) cộng lại làm cấu hình model bốc hơi đúng chỗ agent làm việc (đo 2026-09-14: 0/4
    worktree có file nào). Mặc định `~/.config/xagents/llm.yaml`, đè được để test và để máy khác cắm chỗ khác."""
    assert may_config_file({}) == Path.home() / ".config" / "xagents" / "llm.yaml"
    assert may_config_file({MAY_CONFIG_ENV: str(tmp_path / "may.yaml")}) == tmp_path / "may.yaml"


def test_tang_may_lam_nen_package_de_len_tren(tmp_path: Path) -> None:
    """Thứ tự ba tầng: máy → package → biến môi trường. Tầng máy giữ thứ phụ thuộc MÁY NÀY đang đăng nhập tài
    khoản nào (`backends`); package giữ thứ khác nhau giữa các công ty (`routing`, trần, ngân sách)."""
    may = tmp_path / "may.yaml"
    may.write_text("provider: anthropic\nmax_tokens: 999\nbackends:\n  - name: tk1\n    provider: claude-code\n",
                   encoding="utf-8")
    goi = tmp_path / "llm.yaml"
    goi.write_text("max_tokens: 111\nrouting:\n  cooldown_s: 7\n", encoding="utf-8")

    cfg = load_config(_core(tmp_path), goi, cls=ConCty, env={MAY_CONFIG_ENV: str(may)})
    assert [b["name"] for b in cfg.backends] == ["tk1"], "backends của tầng máy phải sống sót qua tầng package"
    assert cfg.provider == "anthropic", "khoá package không khai thì giữ giá trị tầng máy"
    assert cfg.max_tokens == 111, "package khai thì package thắng"
    assert cfg.routing == {"cooldown_s": 7}


def test_tro_file_nen_khong_co_thi_fail_closed_chu_khong_im(tmp_path: Path) -> None:
    """Chỉ đích danh một file nền rồi file đó không có = cấu hình sai, không phải "chạy tạm".

    Nếu bỏ qua, `provider` rơi về mặc định `fake` và mọi lượt gọi model thành giả mà không ai biết — đúng khuôn
    "chế độ hỏng không tự khai báo" mà ADR-0016 lấy làm lý do tồn tại. Lỗi phải NÓI RÕ THIẾU GÌ."""
    thieu = tmp_path / "khong-co" / "may.yaml"
    with pytest.raises(LLMError) as e:
        load_config(_core(tmp_path), None, cls=ConCty, env={MAY_CONFIG_ENV: str(thieu)})
    assert str(thieu) in str(e.value) and MAY_CONFIG_ENV in str(e.value)


def test_thieu_file_nen_mac_dinh_thi_khong_phai_loi(tmp_path: Path) -> None:
    """Vế còn lại của cùng một quyết định: KHÔNG chỉ đích danh thì vắng tầng máy là bình thường — test và
    `evals --replay` chạy offline với `provider: fake`, không được bắt chúng dựng file ngoài repo."""
    cfg = load_config(_core(tmp_path), None, cls=ConCty, env={})
    assert cfg.provider == "fake"


def test_explain_noi_tung_khoa_den_tu_dau(tmp_path: Path) -> None:
    """Thêm một tầng là thêm câu hỏi "giá trị này đến từ đâu" — ADR-0016 bắt buộc kèm lệnh trả lời được nó,
    nếu không tầng nền thành chỗ cấu hình lặng lẽ khác với thứ người đọc thấy trong file package."""
    may = tmp_path / "may.yaml"; may.write_text("provider: anthropic\nmax_tokens: 999\n", encoding="utf-8")
    goi = tmp_path / "llm.yaml"; goi.write_text("max_tokens: 111\n", encoding="utf-8")
    env = {MAY_CONFIG_ENV: str(may), "DEMO_MAX_INPUT_CHARS": "5000"}

    nguon = explain_config(_core(tmp_path), goi, cls=ConCty, env=env)
    assert nguon["provider"] == f"tầng máy: {may}"
    assert nguon["max_tokens"] == f"llm.yaml: {goi}"
    assert nguon["max_input_chars"] == "biến môi trường: DEMO_MAX_INPUT_CHARS"
    assert nguon["cache_ttl"] == "mặc định"


def test_explain_khong_co_tang_nao_thi_moi_khoa_la_mac_dinh(tmp_path: Path) -> None:
    """Không tầng máy, không `llm.yaml`, không biến nào — lệnh vẫn phải trả lời được, và trả lời "mặc định".
    Đây là trạng thái của một worktree vừa tạo: người đọc cần thấy NGAY là chưa có cấu hình nào, thay vì một
    bảng rỗng để họ tự đoán."""
    nguon = explain_config(_core(tmp_path), tmp_path / "khong-co.yaml", cls=ConCty, env={})
    assert set(nguon.values()) == {"mặc định"}
    assert nguon["backends"] == "mặc định"


def test_explain_goi_dung_ten_bien_moi_truong_cho_models(tmp_path: Path) -> None:
    """`models` đọc từ NHIỀU biến (một biến mỗi tier) nên không tra được bằng bảng một-một. Người sửa cấu hình
    cần biết gõ `unset` cái gì, nên phải kể đúng biến nào đang đặt — nói chung chung "biến môi trường" thì họ
    phải đi dò ba tên."""
    nguon = explain_config(_core(tmp_path), tmp_path / "khong-co.yaml", cls=ConCty,
                           env={"DEMO_MODEL_STRONG": "m-a", "DEMO_MODEL_LIGHT": "m-b"})
    assert nguon["models"] == "biến môi trường: DEMO_MODEL_STRONG, DEMO_MODEL_LIGHT"


def test_explain_khoa_doi_gian_tiep_vi_bien_khac_thi_noi_chung(tmp_path: Path) -> None:
    """`DEMO_LLM_PROVIDER` xoá sạch `backends` (một provider chỉ đích danh thì bỏ danh sách). Khoá `backends`
    đổi vì biến ấy chứ không vì `DEMO_LLM_BACKENDS`, nên không được gọi tên một biến KHÔNG hề được đặt — nói
    "biến môi trường" là đúng mức chắc chắn đang có."""
    goi = tmp_path / "llm.yaml"
    goi.write_text("backends:\n  - name: tk1\n    provider: claude-code\n", encoding="utf-8")
    nguon = explain_config(_core(tmp_path), goi, cls=ConCty, env={"DEMO_LLM_PROVIDER": "anthropic"})
    assert nguon["provider"] == "biến môi trường: DEMO_LLM_PROVIDER"
    assert nguon["backends"] == "biến môi trường"
