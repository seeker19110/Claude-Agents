"""`xagents_core.runner` — khung runner chung (K3.6d1).

Ca ở đây cố ý KHÔNG có `AgentRunner`: bước d1 chỉ đưa lên core ba lớp kết quả và hai hàm schema. Lý do đầy đủ
ở docstring module — tóm tắt: mọi CHỮ trong prompt (`build_user_message`, `context_writes_schema`,
`tools_prompt`) ở lại từng công ty, vì đổi một dấu cách trong đó là mọi bản ghi eval lệch.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from xagents_core.runner import Generated, RunnerError, RunResult, output_schema, payload_schema

WRITES = {"type": "array", "items": {"type": "object",
                                     "properties": {"namespace": {"type": "string"}, "content_ref": {"type": "string"}},
                                     "required": ["namespace", "content_ref"]}}
TOPIC = {"type": "object", "properties": {"tieu_de": {"type": "string"}}, "required": ["tieu_de"]}


# ---------- payload_schema ----------

def test_payload_schema_lay_dung_phan_payload(tmp_path):
    (tmp_path / "ban-tin.json").write_text(json.dumps({"properties": {"payload": TOPIC}}), encoding="utf-8")
    assert payload_schema(tmp_path, "ban-tin") == TOPIC


def test_payload_schema_topic_khong_co_schema_thi_bao_loi_chu_khong_lot_qua(tmp_path):
    with pytest.raises(RunnerError, match="không có schema cho topic khong-co"):
        payload_schema(tmp_path, "khong-co")


# ---------- output_schema ----------

def test_khong_namespace_va_mot_payload_thi_giu_nguyen_schema_topic():
    """Đường phổ biến nhất: không bọc gì cả, model trả thẳng payload của topic."""
    assert output_schema(TOPIC, [], many=False, writes_schema=WRITES) is TOPIC


def test_co_namespace_thi_boc_payload_va_context_writes():
    got = output_schema(TOPIC, ["giong"], many=False, writes_schema=WRITES)
    assert got["required"] == ["payload"]
    assert got["properties"]["payload"] is TOPIC and got["properties"]["context_writes"] is WRITES


def test_many_thi_boc_thanh_items_mang():
    got = output_schema(TOPIC, [], many=True, writes_schema=WRITES)
    assert got["required"] == ["items"] and got["properties"]["items"] == {"type": "array", "items": TOPIC}
    assert "context_writes" not in got["properties"], "không sở hữu namespace thì không hỏi context_writes"


def test_many_va_co_namespace_thi_co_ca_hai():
    got = output_schema(TOPIC, ["giong"], many=True, writes_schema=WRITES)
    assert set(got["properties"]) == {"items", "context_writes"} and got["required"] == ["items"]


def test_context_only_chi_hoi_context_writes():
    """`schema=None` = agent chỉ ghi blackboard, không publish topic nào."""
    got = output_schema(None, ["giong"], many=False, writes_schema=WRITES)
    assert got == {"type": "object", "properties": {"context_writes": WRITES}, "required": ["context_writes"]}


def test_writes_schema_la_THAM_SO_chu_khong_dung_tai_cho():
    """Hình dạng `context_writes` là hợp đồng đầu ra của agent — tức prompt, tức của từng công ty. Company đòi
    `content` (ADR-0012), studio không. Core không được dựng nó, nếu không một trong hai bên đổi prompt."""
    khac = {"type": "array", "items": {"type": "object", "required": ["namespace", "content_ref", "content"]}}
    got = output_schema(TOPIC, ["giong"], many=False, writes_schema=khac)
    assert got["properties"]["context_writes"] is khac


# ---------- lớp kết quả ----------

def test_generated_mang_dung_phan_chung_hai_cong_ty():
    """Năm trường company có thêm (`output_tokens`, `cost_usd`, `priced`, `duration_ms`, `phase`) KHÔNG được ở
    đây: đưa `phase` (ADR-0037) lên core là bắt studio mang một trường nó không bao giờ ghi (bài học K3.5a)."""
    from dataclasses import fields
    ten = {f.name for f in fields(Generated)}
    assert ten == {"payloads", "tokens", "model", "context_writes", "cache_hit_ratio", "turns", "tool_calls"}
    assert not (ten & {"output_tokens", "cost_usd", "priced", "duration_ms", "phase"})


def test_generated_default_khong_dung_chung_giua_hai_the_hien():
    a, b = Generated([], 0, "m"), Generated([], 0, "m")
    a.context_writes.append({"namespace": "x"}); a.tool_calls["web"] = 1
    assert b.context_writes == [] and b.tool_calls == {}


def test_lop_con_thu_hep_output_va_them_truong_cua_minh():
    """Tiền lệ K3.5a: core để `output: Any`, lớp con thu hẹp về `Envelope` của mình và thêm trường của miền."""
    @dataclass
    class ConRunResult(RunResult):
        cost_usd: float = 0.0

    @dataclass
    class ConGenerated(Generated):
        phase: str | None = None

    r = ConRunResult(output="env", tokens=5, model="m", cost_usd=1.5)
    assert (r.output, r.tokens, r.cost_usd) == ("env", 5, 1.5)
    g = ConGenerated([], 0, "m", phase="review")
    assert g.phase == "review" and g.turns == 1


def test_runner_error_la_exception_thuong():
    with pytest.raises(RunnerError):
        raise RunnerError("x")
