"""4L-3: cắt vòng tool khi model gọi lặp cùng một tool mà không tiến bộ.

Đo được khi chạy thật (2026-09-04): 956.637 token đầu ra cho MỘT ticket, phần lớn là cùng một lời gọi tool lặp
lại với y nguyên tham số và y nguyên kết quả. `_turns` trước đây chỉ dừng khi hết lượt / vượt ngân sách / model
tự dừng — không có gì nhìn vào NỘI DUNG vòng lặp.

Bẫy đã mắc (TRAPS.md khuôn 3 — "reset đếm theo tiến bộ, không theo lượt"): nếu reset bộ đếm theo lượt hội thoại
hay theo "có tool nào khác chen vào", model chỉ cần chen `list_files` giữa hai lần `read_file` giống hệt là thoát
được hàng rào. Chỉ tool GHI chạy THÀNH CÔNG mới là tiến bộ.
"""
from __future__ import annotations

import json
from typing import Any

from company.bus import InMemoryBus
from company.llm import FakeClient
from company.runner import NO_PROGRESS_STOP, NO_PROGRESS_WARN, AgentRunner, _stagnant
from company.tools import WorkspaceTools
from company.workspace import TicketWorkspace
from test_tools_and_agentic import _init_repo, _pr, _task_env, _tc


def _c(name: str, ah: str = "a1", oh: str = "o1", ok: bool = True) -> dict[str, Any]:
    """Một phần tử của `ToolBox.calls` (hình dạng 4L-2: có `args_hash`, `out_hash`, `ms`)."""
    return {"name": name, "args": {}, "ok": ok, "chars": 10, "args_hash": ah, "out_hash": oh, "ms": 0.5}


def _ws(tmp_path):
    ws = TicketWorkspace(_init_repo(tmp_path / "repo"), "T1", base="main"); ws.create()
    return ws


def _run(tmp_path, th, **kw):
    bus = InMemoryBus()
    client = FakeClient(handler=lambda s, u: _pr({"ticket_id": "T1"}), tool_handler=th)
    g = AgentRunner(bus, client).generate("builder", _task_env(), "pull-requests",
                                          tools=WorkspaceTools(_ws(tmp_path)).toolbox(), **kw)
    acts = [e.payload["action"] for e in bus.replay(topic="audit-log")]
    return g, acts, bus, client


# ---------- hàm thuần `_stagnant` ----------

def test_stagnant_dem_dung():
    assert _stagnant([]) == (0, None)
    n, last = _stagnant([_c("read_file"), _c("read_file"), _c("read_file")])
    assert n == 3 and last is not None and last["name"] == "read_file"


def test_reset_khi_ghi_ok():
    """`write_file` chạy OK LÀ tiến bộ → dừng đếm ngay tại đó (không nhìn ngược quá nó)."""
    calls = [_c("read_file"), _c("read_file"), _c("read_file"), _c("write_file", ah="w", oh="ok")]
    assert _stagnant(calls) == (0, None)
    # ghi HỎNG thì không phải tiến bộ: nó là một call như mọi call khác
    n, _ = _stagnant([_c("write_file", ah="w", oh="e", ok=False)] * 3)
    assert n == 3


def test_khong_reset_khi_doc_chen():
    """Bẫy đã biết: model chen một tool ĐỌC khác vào giữa để phá chuỗi lặp — không được tính là tiến bộ."""
    calls = [_c("read_file"), _c("read_file"), _c("list_files", ah="l"), _c("read_file")]
    assert _stagnant(calls)[0] == 3


def test_output_khac_khong_lap():
    """Cùng tool cùng tham số nhưng KẾT QUẢ khác → có tiến bộ (file đã đổi), không tính là lặp."""
    calls = [_c("read_file", oh="o1"), _c("read_file", oh="o2"), _c("read_file", oh="o3")]
    assert calls[-1]["out_hash"] == "o3"
    assert _stagnant(calls)[0] == 1


# ---------- vòng tool thật trong `_turns` ----------

def test_lap_5_lan_thi_cat(tmp_path):
    """`read_file` cùng path lặp mãi: dừng đúng ở lần thứ NO_PROGRESS_STOP, audit `no_progress`."""
    g, acts, bus, _ = _run(tmp_path, lambda m, t: [_tc("read_file", path="mod.py")], max_turns=25)
    assert g.tool_calls == {"read_file": NO_PROGRESS_STOP}, "phải cắt ở lần thứ 5, không chạy hết 25 lượt"
    assert "no_progress" in acts
    ev = json.loads(next(e.payload["evidence"] for e in bus.replay(topic="audit-log")
                         if e.payload["action"] == "no_progress"))
    assert ev["tool"] == "read_file" and ev["n"] == NO_PROGRESS_STOP and ev["turn"] == NO_PROGRESS_STOP
    assert isinstance(ev["args_hash"], str) and len(ev["args_hash"]) == 12


def test_no_progress_van_co_json_cuoi(tmp_path):
    """Cắt KHÔNG ném exception: vòng lặp kết thúc êm và vẫn đi vào nhánh ép chốt JSON như case hết lượt."""
    g, acts, _, client = _run(tmp_path, lambda m, t: [_tc("read_file", path="mod.py")])
    assert g.payloads[0]["ticket_id"] == "T1" and g.payloads[0]["pr_ref"] == "#999"
    assert acts[-2:] == ["tools_used", "tools_trace"]
    assert "JSON cuối cùng" in client.calls[-1]["messages"][-1]["content"]


def test_canh_bao_o_lan_3(tmp_path):
    """Ngưỡng cảnh báo trước ngưỡng cắt: một lượt user nói thẳng model đang lặp, cộng audit `no_progress_warn`."""
    _, acts, _, client = _run(tmp_path, lambda m, t: [_tc("read_file", path="mod.py")])
    assert acts.index("no_progress_warn") < acts.index("no_progress")
    warn = [m for c in client.calls for m in c["messages"]
            if m["role"] == "user" and "cùng tham số cùng kết quả" in m["content"]]
    assert warn and f"read_file {NO_PROGRESS_WARN} lần" in warn[0]["content"]


def test_ghi_file_xen_giua_khong_cat(tmp_path):
    """3 lần đọc lặp → ghi file THÀNH CÔNG → 3 lần đọc lặp: tổng 6 call lặp mà KHÔNG cắt, vì có tiến bộ ở giữa."""
    dem = {"n": 0}

    def th(msgs, tools):
        dem["n"] += 1
        if dem["n"] == 4: return [_tc("write_file", path="feature.py", content="F = 1\n")]
        if dem["n"] > 7: return []
        return [_tc("read_file", path="mod.py")]

    g, acts, _, _ = _run(tmp_path, th, max_turns=25)
    assert g.tool_calls == {"read_file": 6, "write_file": 1}
    assert "no_progress" not in acts


def test_stop_99_thi_chay_du(tmp_path, monkeypatch):
    """Chiều ngược (đo hai chiều): ngưỡng cao không đạt → vòng tool chạy đủ `max_turns` như trước 4L-3."""
    monkeypatch.setattr("company.runner.NO_PROGRESS_WARN", 99)
    monkeypatch.setattr("company.runner.NO_PROGRESS_STOP", 99)
    g, acts, _, _ = _run(tmp_path, lambda m, t: [_tc("read_file", path="mod.py")], max_turns=4)
    assert g.tool_calls == {"read_file": 4} and g.turns == 5
    assert "no_progress" not in acts and "no_progress_warn" not in acts
