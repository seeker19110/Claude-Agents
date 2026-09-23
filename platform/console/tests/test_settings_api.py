"""/api/settings: xem luôn được, ghi phải có --allow-config (tách khỏi --allow-decide)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from test_server import Console, make_console, static_dir  # noqa: F401  (dùng lại fixture của test_server)

LLM = """backends:
  - {name: claude-sub, provider: claude-code, models: {strong: claude-opus-5}}
  - name: antigravity
    provider: openai
    base_url: http://127.0.0.1:1123/v1
    models: {strong: claude-sonnet-4-6, standard: gemini-3.8-flash-medium}
routing:
  prefer: {standard: antigravity}
"""


@pytest.fixture
def llm_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    from console import settings

    monkeypatch.setattr(settings, "gateway_catalog", lambda *a, **k: [])
    path = tmp_path / "llm.yaml"
    path.write_text(LLM, encoding="utf-8")
    return {"software-company": path}


def test_get_settings_works_even_in_readonly(make_console, llm_yaml):  # noqa: F811
    c = make_console(readonly=True, llm_yaml=llm_yaml)
    status, body = c.request("GET", "/api/settings")
    assert status == 200
    assert body["can_edit"] is False
    entry = body["companies"]["software-company"]
    assert [b["name"] for b in entry["backends"]] == ["claude-sub", "antigravity"]


def test_get_settings_still_needs_the_token(make_console, llm_yaml):  # noqa: F811
    c = make_console(llm_yaml=llm_yaml)
    assert c.request("GET", "/api/settings", token="sai")[0] == 401


def test_write_is_blocked_without_allow_config(make_console, llm_yaml):  # noqa: F811
    """--allow-decide KHÔNG mở khoá sửa cấu hình: hai rủi ro khác nhau, hai cờ khác nhau."""
    c = make_console(readonly=False, llm_yaml=llm_yaml)
    status, body = c.request("POST", "/api/settings", body={"company": "software-company",
                                                            "models": {"antigravity": {"standard": "gemini-3.7-flash-low"}}})
    assert status == 403 and "--allow-config" in body["error"]
    assert "gemini-3.8-flash-medium" in llm_yaml["software-company"].read_text(encoding="utf-8")


def test_write_applies_and_reports_changes(make_console, llm_yaml):  # noqa: F811
    c = make_console(allow_config=True, llm_yaml=llm_yaml)
    status, body = c.request("POST", "/api/settings", body={"company": "software-company",
                                                            "models": {"antigravity": {"standard": "gemini-3.7-flash-low"}},
                                                            "disable": ["claude-sub"]})
    assert status == 200, body
    assert "tắt backend claude-sub" in body["changes"]
    data = yaml.safe_load(llm_yaml["software-company"].read_text(encoding="utf-8"))
    assert data["backends"][0]["models"]["standard"] == "gemini-3.7-flash-low"
    assert [b["name"] for b in data["disabled_backends"]] == ["claude-sub"]


def test_bad_company_and_bad_model_are_400(make_console, llm_yaml):  # noqa: F811
    c = make_console(allow_config=True, llm_yaml=llm_yaml)
    assert c.request("POST", "/api/settings", body={"company": "khong-co"})[0] == 400
    status, body = c.request("POST", "/api/settings",
                             body={"company": "software-company", "models": {"khong-co": {"strong": "x"}}})
    assert status == 400 and "không có backend" in body["error"]


@pytest.mark.parametrize("extra", [
    {"models": {"antigravity": "gemini-3.7-flash-low"}},   # tier phải là ánh xạ → trước đây AttributeError
    {"models": ["antigravity"]},
    {"disable": [["claude-sub"]]},                          # phần tử không phải chuỗi → trước đây TypeError
    {"disable": "claude-sub"},
    {"enable": {"claude-sub": True}},
    {"prefer": ["standard"]},
    {"prefer": {"standard": ["antigravity"]}},
])
def test_sai_kieu_truong_la_400_khong_rot_ket_noi(make_console, llm_yaml, extra):  # noqa: F811
    """Audit 2026-09-23: thân POST không kiểm kiểu → ngoại lệ không bắt → kết nối bị cắt thay vì 400."""
    c = make_console(allow_config=True, llm_yaml=llm_yaml)
    before = llm_yaml["software-company"].read_text(encoding="utf-8")
    status, body = c.request("POST", "/api/settings", body={"company": "software-company", **extra})
    assert status == 400, body
    assert llm_yaml["software-company"].read_text(encoding="utf-8") == before
