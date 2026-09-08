"""Ba adapter hợp nhất ở K3.3c2: `AnthropicClient`, `CodexClient`, `FakeClient` (+ `cli_env`, `check_argv`,
`anthropic_input_tokens`).

Đây là chỗ **studio được nâng**, nên mỗi điểm nâng cần một ca đứng tên nó — và cần đúng ở core, không mượn suite
của company. Đo lúc hợp nhất: đột biến "bỏ `timeout`" và "lỗi mạng về `LLMError`" làm company ĐỎ nhưng studio
XANH, tức studio không có ca nào canh chính thứ nó vừa nhận. Mã nay ở core thì ca cũng phải ở core, nếu không
một PR sau gỡ `TransientError` đi sẽ chỉ đỏ ở một trong hai suite và dễ bị đọc là "lỗi của company".

Bốn điểm nâng, mỗi điểm một ca:
1. `timeout` truyền xuống SDK — không có nó, một request treo giữ luôn orchestrator.
2. Lỗi mạng / 4xx-5xx tạm thời → `TransientError` (hoãn), không phải `LLMError` (dừng).
3. `cache_write_tokens` — Anthropic để token GHI vào cache ngoài `input_tokens`.
4. Prompt của codex đi qua **stdin**, kèm `check_argv` cho phần argv còn lại.
"""
from __future__ import annotations

import json
import sys
import types

import pytest

from xagents_core.llm import (
    ARGV_LIMIT,
    AnthropicClient,
    CodexClient,
    FakeClient,
    LLMConfig,
    LLMError,
    Refused,
    TransientError,
    anthropic_input_tokens,
    check_argv,
    cli_env,
)
from xagents_core.tools import ToolCall, ToolSpec


class _Usage:
    def __init__(self, input_tokens=10, output_tokens=5, **kw):
        self.input_tokens, self.output_tokens = input_tokens, output_tokens
        for k, v in kw.items(): setattr(self, k, v)


class _Block:
    def __init__(self, type, **kw):
        self.type = type
        for k, v in kw.items(): setattr(self, k, v)


class _Msg:
    def __init__(self, content, usage, model="claude-x", stop_reason="end_turn", stop_details=None):
        self.content, self.usage, self.model = content, usage, model
        self.stop_reason, self.stop_details = stop_reason, stop_details


class _Stream:
    def __init__(self, final): self._final = final
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def get_final_message(self): return self._final


class _ConnErr(Exception): ...


class _StatusErr(Exception):
    def __init__(self, message, status_code=500):
        super().__init__(message); self.message, self.status_code = message, status_code


def _fake_sdk(monkeypatch, final=None, raise_error=None):
    mod = types.ModuleType("anthropic")
    seen: dict = {}

    class _Messages:
        def stream(self, **kw):
            seen["kwargs"] = kw
            if raise_error is not None: raise raise_error
            return _Stream(final)

    class Anthropic:
        def __init__(self, timeout=None): seen["timeout"] = timeout; self.messages = _Messages()

    mod.Anthropic, mod.APIConnectionError, mod.APIStatusError = Anthropic, _ConnErr, _StatusErr
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    return seen


def _cfg(**kw):
    return LLMConfig(provider="anthropic", models={"strong": "claude-opus-5", "standard": "claude-sonnet-5"}, **kw)


# ---------- anthropic_input_tokens ----------

def test_anthropic_input_tokens_cong_ca_doc_va_ghi_cache():
    """Anthropic để token cache RA NGOÀI `input_tokens`. Không cộng lại thì `audit-log.tokens` bỏ sót gần hết
    system prompt (phần lặp nằm trong cache) và trần ngân sách của supervisor không bao giờ chạm."""
    assert anthropic_input_tokens(_Usage(input_tokens=10, cache_read_input_tokens=2,
                                         cache_creation_input_tokens=3)) == (15, 2, 3)
    assert anthropic_input_tokens(_Usage(input_tokens=10)) == (10, 0, 0)


# ---------- AnthropicClient ----------

def test_anthropic_timeout_di_xuong_sdk(monkeypatch):
    """Điểm nâng 1. Studio trước không đặt timeout: một request treo giữ luôn cả orchestrator — vòng lặp tuần
    tự, một tiến trình, không ai gỡ được ngoài Ctrl-C."""
    seen = _fake_sdk(monkeypatch, _Msg([_Block("text", text="{}")], _Usage()))
    AnthropicClient(_cfg())
    assert seen["timeout"] == 600.0
    AnthropicClient(_cfg(), timeout=12.0)
    assert seen["timeout"] == 12.0


def test_anthropic_tra_ve_du_token_cache_va_tool_call(monkeypatch):
    """Điểm nâng 3: `cache_write_tokens` phải ra tới `Completion`, không dừng ở helper."""
    usage = _Usage(input_tokens=10, output_tokens=7, cache_read_input_tokens=2, cache_creation_input_tokens=3)
    blocks = [_Block("text", text='{"a": 1}'), _Block("tool_use", id="t1", name="web", input={"q": "x"})]
    _fake_sdk(monkeypatch, _Msg(blocks, usage))
    c = AnthropicClient(_cfg())
    out = c.complete(system="s", user="u", schema={"type": "object"}, model_tier="strong",
                     tools=[ToolSpec("web", "tìm", {"type": "object"})])
    assert (out.input_tokens, out.cached_input_tokens, out.cache_write_tokens) == (15, 2, 3)
    assert out.output_tokens == 7 and out.text == '{"a": 1}'
    assert out.tool_calls == [ToolCall(id="t1", name="web", args={"q": "x"})]


def test_anthropic_loi_mang_va_ma_tam_thoi_la_transient(monkeypatch):
    """Điểm nâng 2, cái đắt nhất. Studio ném `LLMError` cho MỌI lỗi, mà `LLMError` là lỗi NỘI DUNG —
    orchestrator dừng thay vì hoãn event cho nhịp sau, nên một nhịp mạng chập làm hỏng cả lượt."""
    _fake_sdk(monkeypatch, raise_error=_ConnErr("đứt cáp"))
    with pytest.raises(TransientError, match="lỗi mạng"):
        AnthropicClient(_cfg()).complete(system="s", user="u", schema={}, model_tier="strong")

    _fake_sdk(monkeypatch, raise_error=_StatusErr("quá tải", status_code=529))
    with pytest.raises(TransientError) as ei:
        AnthropicClient(_cfg()).complete(system="s", user="u", schema={}, model_tier="strong")
    assert ei.value.status == 529


def test_anthropic_ma_khong_tam_thoi_van_la_llm_error(monkeypatch):
    """Mặt kia của điểm nâng 2: 400 là lỗi của ta, retry vô ích. Nếu ca này biến mất thì `TransientError` nuốt
    luôn lỗi vĩnh viễn và orchestrator quay vòng mãi trong im lặng."""
    _fake_sdk(monkeypatch, raise_error=_StatusErr("schema sai", status_code=400))
    with pytest.raises(LLMError) as ei:
        AnthropicClient(_cfg()).complete(system="s", user="u", schema={}, model_tier="strong")
    assert not isinstance(ei.value, TransientError) and ei.value.status == 400


def test_anthropic_refusal_mang_theo_ly_do(monkeypatch):
    _fake_sdk(monkeypatch, _Msg([], _Usage(), stop_reason="refusal",
                                stop_details=types.SimpleNamespace(category="harmful")))
    with pytest.raises(Refused, match="harmful"):
        AnthropicClient(_cfg()).complete(system="s", user="u", schema={}, model_tier="strong")


def test_anthropic_ghep_tool_result_lien_tiep_vao_mot_luot_user():
    """`_messages`: nhiều `tool_result` của cùng một lượt phải gộp vào MỘT message user — API từ chối nếu tách."""
    msgs = AnthropicClient._messages([
        {"role": "user", "content": "hỏi"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "name": "n", "args": {}}]},
        {"role": "tool", "tool_call_id": "a", "content": "kq1"},
        {"role": "tool", "tool_call_id": "b", "content": "kq2"},
    ])
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert [b["tool_use_id"] for b in msgs[-1]["content"]] == ["a", "b"]
    assert msgs[1]["content"][0]["type"] == "tool_use"   # assistant không có text → chỉ khối tool_use


# ---------- CodexClient ----------

def _codex(out, **kw):
    seen: list = []
    cfg = LLMConfig(provider="codex", models={"strong": "gpt-5.6", "standard": "gpt-5.6"}, **kw)
    return CodexClient(cfg, binary="codex", runner=lambda a, stdin: (seen.append((a, stdin)), out)[1]), seen


OK = json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": '{"answer": "ok"}'}}) + "\n" + \
     json.dumps({"type": "turn.completed",
                 "usage": {"input_tokens": 100, "cached_input_tokens": 40, "cache_write_input_tokens": 7,
                           "output_tokens": 9}})


def test_codex_prompt_di_qua_stdin_khong_qua_argv():
    """Điểm nâng 4. Prompt dài trên argv làm hệ điều hành thoát với `Argument list too long` — một thông điệp
    không nói gì về prompt, đúng khuôn 1 của TRAPS §1 (chế độ hỏng không tự khai báo)."""
    c, seen = _codex(OK)
    out = c.complete(system="SYS", user="USER", schema={"type": "object"}, model_tier="standard")
    args, stdin = seen[0]
    assert "SYS" in stdin and "USER" in stdin and "JSON Schema" in stdin
    assert not any("SYS" in a for a in args), "prompt không được nằm trong argv"
    assert args[1] == "exec" and "--json" in args and args[args.index("-s") + 1] == "read-only"
    assert (out.input_tokens, out.cached_input_tokens, out.cache_write_tokens, out.output_tokens) == (100, 40, 7, 9)


def test_codex_thuc_su_goi_check_argv_chu_khong_chi_co_ham_do():
    """Đo hai chiều lộ ra lỗ: bỏ hẳn `check_argv(args)` khỏi `CodexClient.complete` mà bộ test vẫn XANH, vì ca
    `test_check_argv_*` chỉ gọi hàm đó TRỰC TIẾP — nó chứng minh hàm đúng, không chứng minh ai gọi nó. Ca này đi
    qua đúng `complete()` với argv vượt trần (tên model khổng lồ) nên nối được hai đầu.

    Nhớ vì sao trần này tồn tại: vượt argv làm hệ điều hành thoát với `Argument list too long`, một thông điệp
    không nhắc gì tới prompt — đúng khuôn 1 của TRAPS §1."""
    c, seen = _codex(OK)
    c.cfg.models["strong"] = "m" * (ARGV_LIMIT + 10)
    with pytest.raises(LLMError, match="argv của CLI dài"):
        c.complete(system="s", user="u", schema={}, model_tier="strong")
    assert seen == [], "phải chặn TRƯỚC khi sinh tiến trình con, không phải sau"


def test_codex_loi_han_muc_la_transient_loi_dang_nhap_thi_khong():
    """Hết quota là chờ được; chưa đăng nhập thì chờ bao lâu cũng thế. Studio trước gộp cả hai vào `LLMError`."""
    c, _ = _codex(json.dumps({"type": "error", "message": "429 rate limited"}))
    with pytest.raises(TransientError, match="429"):
        c.complete(system="s", user="u", schema={}, model_tier="strong")

    c, _ = _codex(json.dumps({"type": "error", "message": "not logged in, run codex login"}))
    with pytest.raises(LLMError, match="chưa đăng nhập") as ei:
        c.complete(system="s", user="u", schema={}, model_tier="strong")
    assert not isinstance(ei.value, TransientError)


def test_codex_canh_bao_metadata_khong_phai_loi():
    c, _ = _codex("\n".join([json.dumps({"type": "error", "message": "Defaulting to fallback metadata"}),
                             json.dumps({"type": "item.completed",
                                         "item": {"type": "agent_message", "text": "{}"}})]))
    assert c.complete(system="s", user="u", schema={}, model_tier="strong").text == "{}"


def test_codex_dong_jsonl_hong_bi_bo_qua_khong_lam_sap_ca_luot():
    """`codex exec` in JSONL, và một dòng hỏng giữa chừng không được giết cả lượt: nó có thể chỉ là log lạ,
    trong khi `agent_message` đứng ngay sau. Hai nhánh bỏ qua: dòng không bắt đầu bằng `{`, và dòng bắt đầu
    bằng `{` nhưng không phải JSON hợp lệ."""
    c, _ = _codex("\n".join([
        "log thuong khong phai json",
        '{"type": "item.completed", "item": {"type": "agent_mess',      # bắt đầu bằng { nhưng vỡ
        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": '{"a": 1}'}}),
    ]))
    assert c.complete(system="s", user="u", schema={}, model_tier="strong").text == '{"a": 1}'


def test_codex_error_long_trong_item_completed_cung_la_loi():
    """Codex báo lỗi ở HAI chỗ: sự kiện `error` cấp trên, và `item.completed` mang `item.type == "error"`.
    Bỏ sót chỗ thứ hai là lỗi đi qua im lặng rồi lộ ra dưới dạng "không trả agent_message" — sai nguyên nhân."""
    c, _ = _codex(json.dumps({"type": "item.completed", "item": {"type": "error", "message": "sandbox tu choi"}}))
    with pytest.raises(LLMError, match="sandbox tu choi"):
        c.complete(system="s", user="u", schema={}, model_tier="strong")


def test_codex_khong_co_agent_message_va_loi_la():
    c, _ = _codex("khong phai json\n" + json.dumps({"type": "turn.completed", "usage": {}}))
    with pytest.raises(LLMError, match="không trả agent_message"):
        c.complete(system="s", user="u", schema={}, model_tier="strong")

    c, _ = _codex(json.dumps({"type": "turn.failed", "error": {"message": "loi la"}}))
    with pytest.raises(LLMError, match="loi la"):
        c.complete(system="s", user="u", schema={}, model_tier="strong")


def test_codex_tu_choi_tool_va_gop_nhieu_luot():
    c, seen = _codex(OK)
    with pytest.raises(LLMError, match="không hỗ trợ tool-use"):
        c.complete(system="s", user="u", schema={}, model_tier="strong",
                   tools=[ToolSpec("web", "d", {"type": "object"})])
    c.complete(system="s", user="u", schema={}, model_tier="strong",
               messages=[{"role": "user", "content": "hoi"}, {"role": "assistant", "content": "dap"}])
    assert "[user]" in seen[0][1] and "[assistant]" in seen[0][1]


def test_codex_config_dir_thanh_codex_home(tmp_path):
    c, _ = _codex(OK, config_dir=str(tmp_path / "acc2"))
    assert c.env["CODEX_HOME"].endswith("acc2")


def test_codex_subprocess_that_phan_loai_dung_ba_loai_hong(monkeypatch):
    """`_subprocess` là đường duy nhất chạm hệ điều hành. Timeout là `TransientError` (điểm nâng 2 áp cho codex);
    thiếu binary và thoát mã ≠ 0 là `LLMError` — chờ thêm không làm chúng đúng lên."""
    import subprocess
    c, _ = _codex(OK)

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    with pytest.raises(LLMError, match="không tìm thấy"):
        c._subprocess(["codex"], "p")

    def timeout(*a, **k): raise subprocess.TimeoutExpired(cmd="codex", timeout=1)
    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(TransientError, match="quá"):
        c._subprocess(["codex"], "p")

    class R: returncode, stdout, stderr = 2, "o" * 900, "e"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    with pytest.raises(LLMError, match="thoát mã 2"):
        c._subprocess(["codex"], "p")

    class Ok: returncode, stdout, stderr = 0, "day la stdout", ""
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Ok())
    assert c._subprocess(["codex"], "p") == "day la stdout"


# ---------- FakeClient ----------

def test_fake_client_ghi_ca_luot_gui_di_lan_doi_so_goc():
    """Hai thứ khác nhau khi có `messages`, và cả hai đều có người dùng: `user` là lượt thật sự gửi đi (thứ model
    đọc), `user_arg` là đối số caller truyền vào — và `evals.prompt_key(system, user)` băm ĐỐI SỐ, nên test nào
    đối chiếu khoá eval phải dùng `user_arg`. Bản cũ của mỗi công ty đều mất đúng thứ bên kia dùng."""
    f = FakeClient(responses=[{"ok": 1}])
    f.complete(system="s", user="GOC", schema={}, model_tier="strong",
               messages=[{"role": "user", "content": "GOC + phần tool"}])
    call = f.calls[0]
    assert call["user"] == "GOC + phần tool" and call["user_arg"] == "GOC"

    f2 = FakeClient(responses=[{"ok": 1}])
    f2.complete(system="s", user="GOC", schema={}, model_tier="strong")
    assert f2.calls[0]["user"] == f2.calls[0]["user_arg"] == "GOC"   # không có messages thì hai cái trùng


def test_fake_client_handler_tool_va_het_cau_tra_loi():
    f = FakeClient(handler=lambda s, u: {"tu": "handler"})
    assert json.loads(f.complete(system="s", user="u", schema={}, model_tier="light").text) == {"tu": "handler"}

    f = FakeClient(responses=[{"a": 1}],
                   tool_handler=lambda msgs, tools: [ToolCall("c", "web", {})] if len(msgs) == 1 else [])
    out = f.complete(system="s", user="u", schema={}, model_tier="strong",
                     tools=[ToolSpec("web", "d", {"type": "object"})])
    assert out.stop_reason == "tool_use" and out.tool_calls[0].name == "web" and out.text == ""
    out2 = f.complete(system="s", user="u", schema={}, model_tier="strong",
                      tools=[ToolSpec("web", "d", {"type": "object"})],
                      messages=[{"role": "user", "content": "u"}, {"role": "tool", "tool_call_id": "c", "content": "kq"}])
    assert json.loads(out2.text) == {"a": 1}

    with pytest.raises(LLMError, match="hết câu trả lời"):
        FakeClient().complete(system="s", user="u", schema={}, model_tier="strong")


# ---------- cli_env / check_argv ----------

def test_cli_env_bo_khoa_tru_tien_to_cli_can(monkeypatch):
    """Trước khi có hàm này, adapter truyền nguyên `os.environ` — khoá TTS/ảnh/YouTube của phòng ban đi thẳng vào
    tiến trình con, thứ không lượt gọi model nào cần tới."""
    monkeypatch.setenv("COMPANY_LLM_API_KEY", "x")
    monkeypatch.setenv("STUDIO_LLM_API_KEY", "x")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "giu")
    monkeypatch.setenv("PATH_LIKE_NORMAL", "giu")
    env = cli_env(keep_prefixes=("OPENAI_",))
    assert "COMPANY_LLM_API_KEY" not in env and "STUDIO_LLM_API_KEY" not in env
    assert "ELEVENLABS_API_KEY" not in env
    assert env["OPENAI_API_KEY"] == "giu" and env["PATH_LIKE_NORMAL"] == "giu"


def test_check_argv_bao_ro_thay_vi_de_he_dieu_hanh_bao_kho_hieu():
    check_argv(["codex", "exec"])   # dưới trần: im lặng
    with pytest.raises(LLMError, match="argv của CLI dài"):
        check_argv(["codex", "x" * (ARGV_LIMIT + 1)])
