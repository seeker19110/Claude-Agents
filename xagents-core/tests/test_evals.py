"""`xagents_core.evals` — ghi / phát lại eval prompt (K3.6c).

Công ty GIẢ ở đây là một `EvalSuite` con dựng trên `tmp_path`: một agent bịa, một ca bịa, một "runner" hai
dòng. Core không được biết `AgentRunner` của ai, nên ca của core cũng không được mượn nó — và một ca đọc
`evals/` thật sẽ đỏ theo mỗi lần ai đó sửa prompt.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest
import yaml

from xagents_core.evals import (
    CaseResult,
    EvalSuite,
    RecordingClient,
    ReplayClient,
    _get,
    _Probe,
    check,
    prompt_key,
)
from xagents_core.llm import Completion, LLMError


@dataclass
class FakeSpec:
    version: int = 3


@dataclass
class FakeEnv:
    payload: dict[str, Any]


@dataclass
class FakeRun:
    output: FakeEnv
    tokens: int = 7


class CaseError(Exception):
    """Đứng thay `RunnerError` của công ty: core không biết lớp ấy, nó đến qua `case_errors`."""


class FakeClient:
    def __init__(self, text: str = '{"ok": 1}', tool_calls: list[Any] | None = None):
        self.text, self.tool_calls, self.calls = text, tool_calls or [], 0

    def complete(self, *, system: str, user: str, schema: Any = None, model_tier: str = "light",
                 cache_key: Any = None, tools: Any = None, messages: Any = None, workdir: Any = None) -> Completion:
        self.calls += 1
        return Completion(text=self.text, input_tokens=1, output_tokens=2, model="fake-1",
                          tool_calls=list(self.tool_calls))


class Suite(EvalSuite):
    case_errors = (CaseError, LLMError)

    def __init__(self, root, ket_qua=None, no=None):
        super().__init__(root)
        self.ket_qua = ket_qua if ket_qua is not None else {"tieu_de": "xin chao"}
        self.no = no          # lỗi mà `run_case` sẽ ném, nếu có

    def load_agents(self) -> dict[str, Any]:
        return {"bien-tap": FakeSpec()}

    def new_bus(self) -> Any:
        return object()

    def new_blackboard(self, bus: Any) -> Any:
        return _BB()

    def run_case(self, agent_id, case, client, agents, bb, bus):
        if self.no is not None: raise self.no
        client.complete(system=f"sys:{agent_id}", user=json.dumps(case["input"], ensure_ascii=False),
                        schema={}, model_tier="light")
        return FakeRun(FakeEnv({**self.ket_qua, "_ctx": bb.da_ghi}))


class _BB:
    def __init__(self): self.da_ghi: list[str] = []
    def write(self, actor, namespace, content_ref, summary="", content=None):
        self.da_ghi.append(f"{namespace}:{content_ref}:{content}")


CASE = {"name": "c1", "topic_out": "ban-tin", "input": {"topic": "t", "key": "K1", "payload": {}},
        "context": [{"actor": "bien-tap", "namespace": "giong", "content_ref": "g.md", "content": "toàn văn"}],
        "expect": {"equals": {"tieu_de": "xin chao"}}}


def _suite(tmp_path, cases=(CASE,), **kw) -> Suite:
    (tmp_path / "evals").mkdir(exist_ok=True)
    (tmp_path / "evals" / "bien-tap.yaml").write_text(yaml.safe_dump({"cases": list(cases)}), encoding="utf-8")
    return Suite(tmp_path, **kw)


# ---------- chấm ----------

def test_get_di_theo_duong_dan_cham_va_tra_none_khi_khong_toi_duoc():
    d = {"a": {"b": [{"c": 1}]}}
    assert _get(d, "a.b.0.c") == 1
    assert _get(d, "a.b.9.c") is None and _get(d, "a.x") is None and _get(d, "a.b.0.c.d") is None


@pytest.mark.parametrize(("expect", "so_loi"), [
    ({"equals": {"x": 1}}, 0), ({"equals": {"x": 2}}, 1),
    ({"contains": {"s": "AI"}}, 0), ({"contains": {"s": "zz"}}, 1),
    ({"min_len": {"l": 2}}, 0), ({"min_len": {"l": 9}}, 1),
    ({"max_len": {"l": 2}}, 0), ({"max_len": {"l": 1}}, 1),
    ({"one_of": {"x": [1, 2]}}, 0), ({"one_of": {"x": [7]}}, 1),
])
def test_check_tung_tieu_chi(expect, so_loi):
    assert len(check({"x": 1, "s": "xin chao ai", "l": [1, 2]}, expect)) == so_loi


def test_any_of_dat_khi_mot_nhanh_dat_va_bao_ly_do_cua_MOI_nhanh_khi_hong():
    p = {"x": 1}
    assert check(p, {"any_of": [[{"equals": {"x": 9}}, {"equals": {"x": 1}}]]}) == []
    (loi,) = check(p, {"any_of": [[{"equals": {"x": 8}}, {"equals": {"x": 9}}]]})
    assert "8" in loi and "9" in loi, "hỏng cả hai nhánh thì phải nói cả hai, không chỉ nhánh đầu"


# ---------- đường dẫn, ca, REQUIRED ----------

def test_duong_dan_suy_tu_root(tmp_path):
    s = _suite(tmp_path)
    assert s.evals_dir == tmp_path / "evals"
    assert s.recordings_dir == tmp_path / "evals" / "recordings"
    assert s.recording_path("bien-tap").name == "bien-tap.json"
    assert s.load_recording("bien-tap") is None, "chưa có file thì None, không phải lỗi"
    assert Suite(tmp_path / "trong").load_cases("bien-tap") == [], "không có file ca thì rỗng"


def test_required_agents_bo_dong_trong_va_dong_chu_thich(tmp_path):
    s = _suite(tmp_path)
    assert s.required_agents() == [], "chưa có REQUIRED.txt thì rỗng"
    s.recordings_dir.mkdir(parents=True)
    (s.recordings_dir / "REQUIRED.txt").write_text("# chú thích\n\nbien-tap\n  qa  \n", encoding="utf-8")
    assert s.required_agents() == ["bien-tap", "qa"]


# ---------- ghi và phát lại ----------

def test_ghi_roi_phat_lai_khong_can_model(tmp_path):
    s = _suite(tmp_path)
    rec = RecordingClient(FakeClient('{"tieu_de": "xin chao"}'), "bien-tap", s)
    s.run_eval("bien-tap", rec)
    p = rec.save()
    assert json.loads(p.read_text(encoding="utf-8"))["prompt_version"] == 3

    lai = ReplayClient("bien-tap", s)
    res = s.run_eval("bien-tap", lai)
    assert [r.passed for r in res] == [True] and lai.data["agent"] == "bien-tap"


def test_phat_lai_khi_chua_co_ban_ghi_va_khi_ban_ghi_lech_prompt(tmp_path):
    s = _suite(tmp_path)
    with pytest.raises(LLMError, match="chưa có bản ghi eval"):
        ReplayClient("bien-tap", s)

    s.recordings_dir.mkdir(parents=True)
    s.recording_path("bien-tap").write_text(json.dumps({"agent": "bien-tap", "prompt_version": 3, "cases": {}}),
                                            encoding="utf-8")
    res = s.run_eval("bien-tap", ReplayClient("bien-tap", s))
    assert res[0].broken_recording and res[0].errored and not res[0].passed


def test_prompt_version_chot_luc_BAT_DAU_khong_doc_lai_luc_save(tmp_path):
    """Bài học 2026-09-05: prompt đổi giữa lượt ghi (người sửa tiếp, hay `git stash` ở nhánh khác) thì bản ghi
    mang một phiên bản nó KHÔNG được ghi bằng, và `outdated_versions` đỏ mà không ai hiểu vì sao."""
    s = _suite(tmp_path)
    rec = RecordingClient(FakeClient(), "bien-tap", s)
    s.load_agents = lambda: {"bien-tap": FakeSpec(version=99)}   # type: ignore[method-assign]  prompt đổi giữa chừng
    assert json.loads(rec.save().read_text(encoding="utf-8"))["prompt_version"] == 3


def test_save_GOP_vao_ban_ghi_cu_khong_ghi_de(tmp_path):
    """Bài học 2026-09-05: một ca lỗi giữa chừng (mạng đứt, hết hạn mức) mà ghi đè là xoá luôn ca đang tốt."""
    s = _suite(tmp_path)
    s.recordings_dir.mkdir(parents=True)
    s.recording_path("bien-tap").write_text(json.dumps(
        {"agent": "bien-tap", "prompt_version": 3, "cases": {"cu": {"text": "x", "model": "m"}}}), encoding="utf-8")

    rec = RecordingClient(FakeClient(), "bien-tap", s)
    rec.complete(system="s", user="u", schema={}, model_tier="light")
    got = json.loads(rec.save().read_text(encoding="utf-8"))
    assert "cu" in got["cases"] and len(got["cases"]) == 2


def test_luot_goi_TOOL_khong_duoc_ghi_chi_ghi_cau_tra_loi_cuoi(tmp_path):
    """Của studio (ADR-0007): phát lại không gọi tool, nên lượt tool không có chỗ trong bản ghi."""
    s = _suite(tmp_path)
    rec = RecordingClient(FakeClient(tool_calls=[{"name": "web"}]), "bien-tap", s)
    rec.complete(system="s", user="u", schema={}, model_tier="light")
    assert rec.entries == {}

    rec.inner = FakeClient()   # lượt cuối, không gọi tool
    rec.complete(system="s", user="u", schema={}, model_tier="light")
    assert list(rec.entries) == [prompt_key("s", "u")]


# ---------- cổng bản ghi ----------

def test_outdated_versions_bat_ban_ghi_o_prompt_cu(tmp_path):
    s = _suite(tmp_path)
    s.recordings_dir.mkdir(parents=True)
    s.recording_path("bien-tap").write_text(json.dumps({"agent": "bien-tap", "prompt_version": 1, "cases": {}}),
                                            encoding="utf-8")
    assert s.outdated_versions() == {"bien-tap": "bản ghi ở prompt v1, agent hiện v3"}
    s.recording_path("bien-tap").write_text(json.dumps({"agent": "bien-tap", "prompt_version": 3, "cases": {}}),
                                            encoding="utf-8")
    assert s.outdated_versions() == {}
    assert Suite(tmp_path / "trong").outdated_versions() == {}, "không có bản ghi thì không phải là lệch"


def test_stale_recordings_bao_ca_thieu_khoa(tmp_path):
    s = _suite(tmp_path)
    s.recordings_dir.mkdir(parents=True)
    s.recording_path("bien-tap").write_text(json.dumps({"agent": "bien-tap", "prompt_version": 3, "cases": {}}),
                                            encoding="utf-8")
    assert s.stale_recordings(["bien-tap"]) == {"bien-tap": ["c1"]}

    rec = RecordingClient(FakeClient(), "bien-tap", s)
    s.run_eval("bien-tap", rec); rec.save()
    assert s.stale_recordings(["bien-tap"]) == {}, "ghi xong thì không còn thiếu"
    assert Suite(tmp_path / "trong").stale_recordings(["bien-tap"]) == {}


def test_probe_lay_khoa_roi_nem(tmp_path):
    p = _Probe()
    with pytest.raises(LLMError, match="probe"):
        p.complete(system="s", user="u", schema={}, model_tier="light")
    assert p.key == prompt_key("s", "u")


# ---------- run_eval ----------

def test_context_cua_ca_duoc_ghi_vao_blackboard_TRUOC_khi_chay(tmp_path):
    s = _suite(tmp_path)
    res = s.run_eval("bien-tap", FakeClient())
    assert res[0].passed and res[0].tokens == 7


def test_ca_cham_khong_dat_khong_phai_la_ca_hong(tmp_path):
    """Phân biệt hai thứ có hệ quả khác nhau ở mã thoát: điểm chấm ≠ bản ghi hỏng ≠ không chạy được."""
    s = _suite(tmp_path, ket_qua={"tieu_de": "sai"})
    (r,) = s.run_eval("bien-tap", FakeClient())
    assert not r.passed and not r.broken_recording and not r.errored and r.failures


def test_loi_khong_phai_ban_ghi_van_la_errored_nhung_khong_phai_broken_recording(tmp_path):
    """Hai trường, hai chính sách cổng: company gác bằng `broken_recording`, studio bằng `errored`."""
    s = _suite(tmp_path, no=CaseError("đầu ra sai schema"))
    (r,) = s.run_eval("bien-tap", FakeClient())
    assert r.errored and not r.broken_recording and not r.passed


def test_loi_NGOAI_case_errors_khong_bi_nuot(tmp_path):
    """`case_errors` hẹp có chủ ý: một `KeyError` trong `run_case` là lỗi CODE, không được hiện ra như
    'model trả sai'. Để `except Exception` ở core là ca eval báo FAIL cho một nguyên nhân nằm ở lập trình."""
    s = _suite(tmp_path, no=KeyError("bug trong run_case"))
    with pytest.raises(KeyError):
        s.run_eval("bien-tap", FakeClient())


def test_lines_in_pass_fail_va_dong_tong_ket():
    out = EvalSuite.lines("bien-tap", [CaseResult("c1", True, tokens=5),
                                       CaseResult("c2", False, ["x sai"], tokens=1)])
    assert out[0].startswith("PASS bien-tap/c1") and "- x sai" in out[1]
    assert out[-1] == "bien-tap: 1/2 pass"


def test_lop_con_phai_khai_bon_hook(tmp_path):
    """`EvalSuite` trần không chạy được: bốn hook là hợp đồng, không phải tuỳ chọn."""
    s = EvalSuite(tmp_path)
    for goi in (lambda: s.load_agents(), lambda: s.new_bus(), lambda: s.new_blackboard(None),
                lambda: s.run_case("a", {}, None, None, None, None)):
        with pytest.raises(NotImplementedError):
            goi()
