"""`python -m company.probe`: CLI thật chạy được chế độ tool nào (ADR-0023/0024), và audit ghi lại chế độ đã dùng.
Không cần `claude` thật: thay tiến trình con bằng hàm giả, nhưng cầu MCP thì chạy thật (socket + ToolBox thật)."""
from __future__ import annotations

import json
from pathlib import Path

from company import probe
from company.bus import InMemoryBus
from company.llm import ClaudeCodeClient, LLMConfig, LLMError
from company.mcp_bridge import SERVER_NAME, ProxyServer
from company.probe import PROBE_TOOL, backends_to_probe, main, probe_backend, probe_toolbox
from company.runner import AgentRunner
from company.tools import WorkspaceTools
from company.workspace import TicketWorkspace
from test_tools_and_agentic import _init_repo, _pr, _task_env


def _cfg(**kw):
    return LLMConfig(provider="claude-code", models={"strong": "m", "standard": "m", "light": "m"}, **kw)


def _ok(body: str = '{"ok": true}') -> str:
    return json.dumps({"result": body, "stop_reason": "end_turn", "usage": {"input_tokens": 3, "output_tokens": 1},
                       "modelUsage": {"claude-haiku-4-5": {}}})


def _cli_calling_tool(args, stdin, cwd=None):
    """CLI giả biết MCP: mở cầu trong args rồi gọi tool qua đó, đúng như `claude -p` thật sẽ làm."""
    cfg = json.loads(Path(args[args.index("--mcp-config") + 1]).read_text(encoding="utf-8"))["mcpServers"][SERVER_NAME]
    px = ProxyServer(int(cfg["args"][cfg["args"].index("--port") + 1]), cfg["args"][cfg["args"].index("--token") + 1])
    names = [t["name"] for t in px.ask({"op": "list"})["tools"]]
    assert PROBE_TOOL in names, names
    px.ask({"op": "call", "name": PROBE_TOOL, "args": {"note": "probe"}})
    return _ok()


# ---------- ba kết luận của probe ----------

def test_probe_reports_mcp_when_cli_reaches_company_tools():
    r = probe_backend(_cfg(), "claude-1", runner=_cli_calling_tool)
    assert r.mode == "mcp" and r.ok and r.tool_called and r.model == "claude-haiku-4-5"
    assert "gọi được tool" in r.detail


def test_probe_reports_cli_when_binary_is_too_old():
    def old(args, stdin, cwd=None):
        raise LLMError("claude -p thoát mã 1: error: unknown option '--mcp-config'")
    r = probe_backend(_cfg(), "claude-1", runner=old)
    assert r.mode == "cli" and not r.ok and "--mcp-config" in r.detail


def test_probe_reports_none_when_cli_cannot_run():
    def dead(args, stdin, cwd=None):
        raise LLMError("claude -p thoát mã 1: Invalid API key · Please run /login")
    r = probe_backend(_cfg(), "claude-1", runner=dead)
    assert r.mode == "none" and "login" in r.detail


def test_probe_bao_none_khi_khoi_tao_client_that_bai(monkeypatch):
    """`ClaudeCodeClient(cfg, ...)` có thể tự ném `LLMError` ngay lúc khởi tạo (vd. binary không tồn tại đường dẫn
    tuyệt đối hỏng) — `probe_backend` phải bắt và báo `mode="none"`, không để lộ traceback."""
    import company.probe as probe_mod

    def boom(cfg, timeout=300.0, **kw):
        raise LLMError("không dựng được client")

    monkeypatch.setattr(probe_mod, "ClaudeCodeClient", boom)
    r = probe_backend(_cfg(), "claude-1", runner=lambda a, s, cwd=None: _ok())
    assert r.mode == "none" and "không dựng được client" in r.detail


def test_probe_reports_cli_when_model_ignores_the_tools():
    """CLI chạy, nhưng không tool nào được gọi: chưa chứng minh được cầu MCP thông — không kết luận `mcp`."""
    r = probe_backend(_cfg(), "claude-1", runner=lambda a, s, cwd=None: _ok())
    assert r.mode == "cli" and not r.tool_called and "KHÔNG gọi tool" in r.detail


def test_probe_does_not_fall_back_to_cli_tools_while_measuring():
    """Đang đo riêng cầu MCP thì không được để nó lùi sang chế độ tool CLI — nếu không, `cli` sẽ bị báo nhầm là `mcp`."""
    seen: list[list[str]] = []

    def old(args, stdin, cwd=None):
        seen.append(args)
        raise LLMError("unknown option '--mcp-config'")

    assert probe_backend(_cfg(cli_tools=True, cli_bash=["pytest:*"]), "x", runner=old).mode == "cli"
    assert len(seen) == 1 and "--mcp-config" in seen[0], "chỉ thử đúng một lượt, không chạy tiếp bằng tool CLI"


def test_probe_toolbox_is_harmless():
    """Bảng tool của probe không chạm file, không chạy lệnh — chỉ một tool ghi nhận mình được gọi."""
    tb, seen = probe_toolbox()
    assert [t.name for t in tb.specs()] == [PROBE_TOOL]
    from company.tools import ToolCall
    assert tb.call(ToolCall(id="p", name=PROBE_TOOL, args={"note": "x"})) == "đã nhận"
    assert seen == ["x"]


# ---------- chọn backend từ llm.yaml ----------

def test_probe_picks_claude_code_backends_from_config(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("COMPANY_LLM_BACKENDS", raising=False); monkeypatch.delenv("COMPANY_LLM_PROVIDER", raising=False)
    from company.llm import load_config
    p = tmp_path / "llm.yaml"
    p.write_text("provider: fake\nbackends:\n"
                 "  - {name: claude-1, provider: claude-code, models: {light: m}}\n"
                 "  - {name: claude-2, provider: claude-code, config_dir: ~/.claude-acc2, models: {light: m}}\n"
                 "  - {name: antigravity, provider: openai, base_url: http://x/v1, models: {light: m}}\n", encoding="utf-8")
    cfg = load_config(p)
    assert [n for n, _ in backends_to_probe(cfg)] == ["claude-1", "claude-2"]
    assert [n for n, _ in backends_to_probe(cfg, "claude-2")] == ["claude-2"]
    assert backends_to_probe(cfg, "antigravity") == []
    # không có `backends:` mà provider là claude-code → chính nó
    assert [n for n, _ in backends_to_probe(_cfg())] == ["default"]


def test_probe_cli_exits_nonzero_when_no_claude_backend(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.delenv("COMPANY_LLM_BACKENDS", raising=False); monkeypatch.delenv("COMPANY_LLM_PROVIDER", raising=False)
    p = tmp_path / "llm.yaml"
    p.write_text("provider: openai\nbase_url: http://x/v1\nmodels: {light: m}\n", encoding="utf-8")
    assert main(["--config", str(p)]) == 1
    assert "Không có backend" in capsys.readouterr().err


def test_probe_cli_ghi_de_model_light_khi_co_tuy_chon_model(tmp_path, monkeypatch, capsys):
    """`--model` phải ghi đè `models["light"]` của MỌI backend được dò (dòng 126)."""
    monkeypatch.delenv("COMPANY_LLM_BACKENDS", raising=False); monkeypatch.delenv("COMPANY_LLM_PROVIDER", raising=False)
    p = tmp_path / "llm.yaml"
    p.write_text("provider: fake\nbackends:\n  - {name: claude-1, provider: claude-code, models: {light: cu}}\n",
                 encoding="utf-8")
    import company.probe as probe_mod

    seen = []
    monkeypatch.setattr(probe_mod, "probe_backend", lambda cfg, name, timeout=300.0: (seen.append(cfg.models["light"]),
                        probe_mod.Result(name, "none"))[1])
    assert main(["--config", str(p), "--model", "moi"]) == 1
    assert seen == ["moi"]


def test_probe_cli_json_output(capsys):
    """`--json` in mảng JSON các Result thay vì bảng chữ, và mã thoát theo `ok` của mọi backend (dòng 133-135)."""
    assert main(["--binary", "claude-khong-ton-tai-xyz", "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list) and data[0]["mode"] == "none"


def test_probe_cli_bao_thanh_cong_khi_moi_backend_deu_ok(monkeypatch, capsys):
    """Mọi backend dùng được `mcp_tools: true` → in dòng tổng kết thành công và thoát 0 (dòng 144-146)."""
    import company.probe as probe_mod
    from company.probe import Result

    monkeypatch.setattr(probe_mod, "probe_backend",
                        lambda cfg, name, timeout=300.0: Result(name, "mcp", "claude", "CLI gọi được tool của công ty", True, "m"))
    assert main(["--binary", "khong-quan-trong"]) == 0
    assert "Mọi backend dùng được" in capsys.readouterr().out


def test_probe_cli_bao_cli_khi_mot_backend_chi_dung_duoc_cli_tools(monkeypatch, capsys):
    """Có backend `mode == "cli"` (không phải `none`) → tổng kết phải nêu tên backend đó (dòng 147-149)."""
    import company.probe as probe_mod
    from company.probe import Result

    monkeypatch.setattr(probe_mod, "probe_backend",
                        lambda cfg, name, timeout=300.0: Result(name, "cli", "claude", "CLI cũ, không hỗ trợ --mcp-config"))
    assert main(["--binary", "khong-quan-trong"]) == 1
    out = capsys.readouterr().out
    assert "chỉ dùng được `cli_tools: true`" in out


def test_probe_cli_bo_qua_backend_da_ok_khi_liet_ke_backend_han_che(tmp_path, monkeypatch, capsys):
    """probe.py 150->147: một backend `mode == "mcp"` (đã OK) đứng cạnh một backend `mode == "cli"` khi tổng
    kết KHÔNG phải mọi backend đều OK — vòng lặp phải BỎ QUA backend đã "mcp" (không rơi vào nhánh cli/none
    nào), chỉ nêu tên backend còn hạn chế."""
    monkeypatch.delenv("COMPANY_LLM_BACKENDS", raising=False); monkeypatch.delenv("COMPANY_LLM_PROVIDER", raising=False)
    p = tmp_path / "llm.yaml"
    p.write_text(
        "provider: fake\nbackends:\n"
        "  - {name: b-ok, provider: claude-code, models: {light: m}}\n"
        "  - {name: b-han-che, provider: claude-code, models: {light: m}}\n",
        encoding="utf-8",
    )
    import company.probe as probe_mod
    from company.probe import Result

    def gia(cfg, name, timeout=300.0):
        if name == "b-ok":
            return Result(name, "mcp", "claude", "CLI gọi được tool của công ty", True, "m")
        return Result(name, "cli", "claude", "CLI cũ, không hỗ trợ --mcp-config")

    monkeypatch.setattr(probe_mod, "probe_backend", gia)
    assert main(["--config", str(p)]) == 1
    out = capsys.readouterr().out
    assert "b-han-che: chỉ dùng được" in out
    assert "b-ok: chỉ dùng được" not in out and "b-ok: không chạy được" not in out


def test_probe_cli_reports_missing_binary(capsys):
    assert main(["--binary", "claude-khong-ton-tai-xyz"]) == 1
    out = capsys.readouterr().out
    assert "none" in out and "không chạy được CLI" in out


# ---------- audit ghi chế độ đã dùng ----------

def test_audit_records_which_mode_ran_the_tool_loop(tmp_path):
    """Người vận hành đọc audit là biết lượt vừa rồi đi hàng rào nào, không phải suy từ llm.yaml."""
    ws = TicketWorkspace(_init_repo(tmp_path / "repo"), "T1", base="main"); ws.create()

    def cli_writes_then_answers(args, stdin, cwd=None):
        i = args.index("--mcp-config")
        cfg = json.loads(Path(args[i + 1]).read_text(encoding="utf-8"))["mcpServers"][SERVER_NAME]
        px = ProxyServer(int(cfg["args"][cfg["args"].index("--port") + 1]), cfg["args"][cfg["args"].index("--token") + 1])
        px.ask({"op": "call", "name": "write_file", "args": {"path": "f.py", "content": "F = 1\n"}})
        return json.dumps({"result": json.dumps(_pr({"ticket_id": "T1"})), "stop_reason": "end_turn", "usage": {}})

    bus = InMemoryBus()
    client = ClaudeCodeClient(_cfg(mcp_tools=True), runner=cli_writes_then_answers)
    AgentRunner(bus, client).generate("builder", _task_env(), "pull-requests", tools=WorkspaceTools(ws).toolbox())
    ev = json.loads(next(iter(bus.replay(topic="audit-log"))).payload["evidence"])
    assert ev["mode"] == "mcp" and ev["calls"] == {"write_file": 1}


def test_audit_mode_is_loop_for_api_providers(tmp_path):
    from company.llm import FakeClient
    from company.tools import ToolCall
    ws = TicketWorkspace(_init_repo(tmp_path / "repo"), "T1", base="main"); ws.create()
    def th(msgs, tools):
        first = not any(x["role"] == "assistant" for x in msgs)
        return [ToolCall(id="c1", name="read_file", args={"path": "mod.py"})] if first else []
    bus = InMemoryBus()
    AgentRunner(bus, FakeClient(handler=lambda s, u: _pr({"ticket_id": "T1"}), tool_handler=th)).generate(
        "builder", _task_env(), "pull-requests", tools=WorkspaceTools(ws).toolbox())
    ev = json.loads(next(iter(bus.replay(topic="audit-log"))).payload["evidence"])
    assert ev["mode"] == "loop" and ev["turns"] == 2


# ---------- ADR-0016: `--explain` nói mỗi khoá đến từ đâu ----------


def test_explain_in_nguon_tung_khoa_va_khong_goi_cli(tmp_path, capsys, monkeypatch):
    """Ràng buộc bắt buộc của ADR-0016: thêm một tầng cấu hình thì phải có lệnh trả lời "giá trị này đến từ
    đâu", nếu không tầng nền thành chỗ cấu hình lặng lẽ khác thứ người đọc thấy trong file package.

    Hai điều kiện, không chỉ một: (1) in ra nguồn của từng khoá; (2) KHÔNG gọi CLI thật — `--explain` là câu
    hỏi về cấu hình, người ta gõ nó đúng lúc cấu hình đang hỏng và CLI có thể chưa chạy được."""
    may = tmp_path / "may.yaml"; may.write_text("provider: anthropic\n", encoding="utf-8")
    goi = tmp_path / "llm.yaml"; goi.write_text("max_tokens: 111\n", encoding="utf-8")
    monkeypatch.setenv("XAGENTS_LLM_CONFIG", str(may))
    monkeypatch.setattr(probe, "probe_backend", _khong_duoc_goi)

    assert probe.main(["--explain", "--config", str(goi)]) == 0
    ra = capsys.readouterr().out
    assert "provider" in ra and str(may) in ra, "khoá lấy từ tầng máy phải chỉ đúng file tầng máy"
    assert str(goi) in ra, "khoá lấy từ llm.yaml phải chỉ đúng file package"


def test_explain_json_doc_duoc_bang_may(tmp_path, capsys, monkeypatch):
    """`--explain --json` để script/CI đọc được: cấu hình là thứ người ta cần so sánh giữa hai máy, mà so bằng
    mắt trên bảng kẻ thì không so được."""
    goi = tmp_path / "llm.yaml"; goi.write_text("max_tokens: 111\n", encoding="utf-8")
    monkeypatch.delenv("XAGENTS_LLM_CONFIG", raising=False)
    monkeypatch.setattr(probe, "probe_backend", _khong_duoc_goi)

    assert probe.main(["--explain", "--json", "--config", str(goi)]) == 0
    nguon = json.loads(capsys.readouterr().out)
    assert nguon["max_tokens"] == f"llm.yaml: {goi}"
    assert nguon["cache_ttl"] == "mặc định"


def _khong_duoc_goi(*args, **kwargs):
    raise AssertionError("`--explain` không được gọi CLI thật")


def test_explain_cau_hinh_hong_thi_noi_tu_te_chu_khong_phun_traceback(tmp_path, capsys, monkeypatch):
    """`--explain` là lệnh người ta gõ ĐÚNG LÚC cấu hình đang hỏng. Ném traceback ra là bắt họ đọc stack của
    mình để tìm một câu tiếng Việt đã viết sẵn ở trong đó — và exit code của traceback là 1 lẫn với mọi lỗi
    khác. Phải in thông điệp ra stderr và trả mã riêng."""
    monkeypatch.setenv("XAGENTS_LLM_CONFIG", str(tmp_path / "khong-co.yaml"))
    monkeypatch.setattr(probe, "probe_backend", _khong_duoc_goi)

    assert probe.main(["--explain"]) == 2
    loi = capsys.readouterr().err
    assert "XAGENTS_LLM_CONFIG" in loi and "không có file đó" in loi
    assert "Traceback" not in loi
