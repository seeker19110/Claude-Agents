"""Ngữ cảnh có hạn mức (ADR-0012 của software-company, chuyển sang core ở K3.1).

Module này trung lập tuyệt đối — không đọc cấu hình, không biết tên công ty — nên nó là bước ĐẦU của K3: nếu
một bước chuyển mã có thể hỏng thì hỏng ở đây là rẻ nhất. Test chuyển sang cùng PR với mã (bất biến 2 của
kịch bản B: dòng nào chuyển package thì test phủ dòng đó chuyển theo).
"""
from __future__ import annotations

from xagents_core.context import CHARS_PER_TOKEN, ContextBudget, _prune, cut_middle, fit, trim_payload


def _turn(idx: int, tool_content: str = "ket qua") -> list[dict]:
    """Một 'lượt' vòng tool: một assistant gọi một tool, kèm phản hồi role=tool tương ứng."""
    return [{"role": "assistant", "content": "", "tool_calls": [{"id": f"c{idx}", "name": "read_file", "args": {"path": f"f{idx}.py"}}]},
            {"role": "tool", "tool_call_id": f"c{idx}", "content": tool_content}]


def _msgs(n_turns: int, tool_content: str = "ket qua") -> list[dict]:
    msgs = [{"role": "user", "content": "yeu cau goc"}]
    for i in range(1, n_turns + 1):
        msgs += _turn(i, tool_content)
    return msgs


def test_prune_giu_k_luot():
    """5 lượt, keep_turns=3: 2 lượt đầu (1, 2) bị tỉa, 3 lượt cuối (3, 4, 5) còn nguyên."""
    msgs = _msgs(5, "x" * 100)
    out, dropped = _prune(msgs, keep_turns=3)
    assert dropped > 0
    tool_msgs = [m for m in out if m["role"] == "tool"]
    assert tool_msgs[0]["content"].startswith("[đã cắt:") and tool_msgs[1]["content"].startswith("[đã cắt:")
    assert tool_msgs[2]["content"] == "x" * 100 and tool_msgs[3]["content"] == "x" * 100 and tool_msgs[4]["content"] == "x" * 100


def test_khong_cat_duoi_k():
    """Đúng hoặc ít hơn keep_turns lượt: không có gì để tỉa, msgs không đổi."""
    msgs = _msgs(3, "x" * 100)
    out, dropped = _prune(msgs, keep_turns=3)
    assert dropped == 0 and out == msgs


def test_giu_user_dau_va_tool_calls():
    """msgs[0] (yêu cầu gốc) không bao giờ bị tỉa; `tool_calls` của assistant vẫn nguyên vẹn dù tool cũ bị tỉa."""
    msgs = _msgs(6, "y" * 200)
    out, _dropped = _prune(msgs, keep_turns=3)
    assert out[0] == {"role": "user", "content": "yeu cau goc"}
    assistants = [m for m in out if m["role"] == "assistant"]
    assert all(m.get("tool_calls") for m in assistants), "tool_calls không bị đụng, kể cả ở lượt bị tỉa"
    assert len(assistants) == 6


def test_fit_cat_payload_truoc_roi_toi_context_va_gan_nhan():
    system = "x" * 1_000
    payload = {"ticket_id": "T1", "diff": "a" * 50_000, "summary": "s"}
    ctx = {"prd": {"version": 1, "content_ref": "docs/prd.md", "summary": "PRD", "content": "p" * 30_000},
           "glossary": {"version": 1, "content_ref": "g.md", "summary": "g", "content": "g" * 500}}
    p, c, b = fit(system, payload, ctx, max_input_chars=20_000, paths={"prd": "store/prd/latest.md"})
    assert b.trimmed_payload > 0 and "cắt" in p["diff"] and p["summary"] == "s" and p["diff"].startswith("aaa")
    assert c["glossary"]["content"] == "g" * 500, "namespace ngắn giữ nguyên, phần thừa nhường cho namespace dài"
    assert "store/prd/latest.md" in c["prd"]["content"] and b.trimmed_context["prd"] > 0
    assert b.system_chars + b.payload_chars + b.context_chars <= 20_000 and b.est_tokens > 0
    _, c2, b2 = fit(system, {"a": "b"}, ctx, max_input_chars=200_000)
    assert not b2.trimmed and c2["prd"]["content"] == "p" * 30_000, "đủ chỗ thì không cắt gì"
    assert cut_middle("abcdef", 100) == "abcdef" and trim_payload({"x": "y"}, 5)[1] == 0


def test_trim_payload_di_sau_vao_list():
    """`_strings` phải đệ quy cả vào phần tử của list, không chỉ dict — payload có list chuỗi dài."""
    payload = {"logs": ["a" * 1000, "b" * 1000]}
    trimmed, cut = trim_payload(payload, 500)
    assert cut > 0
    assert any("cắt" in s for s in trimmed["logs"]), trimmed["logs"]


def test_khong_du_cho_giu_nghia_thi_bo_han_noi_dung_nhung_giu_duong_dan():
    """Hạn mức chia cho NHIỀU namespace tới mức mỗi phần < `MIN_KEEP`: giữ một khúc cụt vài trăm ký tự là vô
    nghĩa, nên bỏ hẳn nội dung — nhưng nhãn phải chỉ đúng chỗ đọc đầy đủ. Agent có tool đọc artifact; thứ nó cần
    là ĐƯỜNG DẪN, không phải một mẩu vụn.

    Một namespace duy nhất thì `alloc` luôn ≥ `MIN_KEEP` nên không vào được nhánh này — ngưỡng ở đây đo bằng
    `fit` thật, không suy từ công thức."""
    ctx = {f"ns{i}": {"version": 1, "content_ref": f"{i}.md", "summary": "s", "content": "p" * 5_000}
           for i in range(10)}
    _, c, b = fit("s" * 100, {"a": "b"}, ctx, max_input_chars=2_000, paths={"ns0": "store/ns0.md"})
    assert c["ns0"]["content"] == "… (bỏ 5000 ký tự; đọc đầy đủ ở store/ns0.md) …"
    assert len(b.trimmed_context) == 10 and b.trimmed


def test_khong_co_paths_thi_nhan_noi_artifact_nam_tren_blackboard():
    """Nhãn mặc định khi nơi gọi không truyền `paths`: vẫn phải nói được đọc thêm ở đâu."""
    ctx = {f"ns{i}": {"version": 1, "content_ref": f"{i}.md", "summary": "s", "content": "p" * 5_000}
           for i in range(10)}
    _, c, _ = fit("s" * 100, {"a": "b"}, ctx, max_input_chars=2_000)
    assert "artifact đầy đủ trên blackboard" in c["ns0"]["content"]


def test_namespace_khong_co_content_giu_nguyen_phan_con_lai():
    """Blackboard có thể chỉ có `summary` + `content_ref` (bản ghi chưa nạp toàn văn) — không được vỡ, và không
    được bịa ra khoá `content`."""
    ctx = {"prd": {"version": 3, "content_ref": "docs/prd.md", "summary": "PRD"}}
    _, c, b = fit("s", {"a": "b"}, ctx, max_input_chars=50_000)
    assert c["prd"] == {"version": 3, "content_ref": "docs/prd.md", "summary": "PRD"}
    assert "content" not in c["prd"] and not b.trimmed


def test_bao_cao_ngan_sach_du_truong_cho_audit():
    """`report()` là thứ đi vào audit `context_trimmed`; thiếu trường là người đọc audit mất manh mối."""
    b = ContextBudget(max_input_chars=10_000, system_chars=100, payload_chars=200, context_chars=300)
    r = b.report()
    assert set(r) == {"max_input_chars", "system", "payload", "context", "trimmed_payload", "trimmed_context",
                      "est_tokens"}
    assert r["est_tokens"] == int(600 / CHARS_PER_TOKEN) and r["trimmed_context"] == {}
    assert not b.trimmed, "chưa cắt gì thì `trimmed` phải False"


def test_cut_middle_giu_dau_va_cuoi():
    s = "A" * 500 + "Z" * 500
    out = cut_middle(s, 400)
    assert out.startswith("A") and out.endswith("Z") and "cắt" in out and len(out) < len(s)
