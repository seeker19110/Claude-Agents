"""Quản lý cửa sổ ngữ cảnh (ADR-0012): prompt gửi model không được vượt `max_input_chars` (llm.yaml / COMPANY_MAX_INPUT_CHARS).

Trước đây prompt = system + toàn bộ payload + toàn bộ snapshot blackboard + diff 20k ký tự, không giới hạn: dự án lớn
vượt context hoặc đốt token vô ích. Giờ phân bổ theo ưu tiên, cắt có nhãn để model biết mình đang thiếu gì:

1. System prompt (prompt + skill) là cố định, trừ trước.
2. Payload đầu vào được ưu tiên: nếu vượt phần dành cho nó, chuỗi dài nhất bị cắt dần (diff, log, text...) — cắt giữa,
   giữ đầu và cuối, gắn nhãn `… (cắt N ký tự) …`.
3. Blackboard: mỗi namespace có `content`; phần còn lại của hạn mức chia đều, namespace nào ngắn hơn phần của mình thì
   nhường phần thừa cho namespace khác (water-filling). Bị cắt thì ghi rõ đường dẫn artifact để agent có tool đọc thêm.

Ước lượng token = ký tự / CHARS_PER_TOKEN (thô, đủ để không vượt trần; số token thật vẫn lấy từ `usage`).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

# `__all__` là HỢP ĐỒNG của shim `company.context`: `from xagents_core.context import *` chỉ mang sang
# những tên liệt kê ở đây. Thêm tên public mới mà quên dòng này thì `company.context.<tên>` biến mất
# lặng lẽ — người gọi nhận AttributeError ở chỗ khác hẳn nơi gây lỗi.
__all__ = ["CHARS_PER_TOKEN", "MIN_KEEP", "ContextBudget", "_prune", "cut_middle", "fit", "trim_payload"]

CHARS_PER_TOKEN = 3.2  # tiếng Việt có dấu + JSON: ~3 ký tự/token với tokenizer phổ biến
MIN_KEEP = 400         # không cắt chuỗi xuống dưới mức này (mất nghĩa)


def cut_middle(s: str, limit: int, note: str = "") -> str:
    """Giữ đầu và cuối, cắt giữa có nhãn. `limit` tính cả nhãn."""
    if len(s) <= limit: return s
    tag = f"\n… (cắt {len(s) - limit} ký tự{'; ' + note if note else ''}) …\n"
    keep = max(limit - len(tag), MIN_KEEP // 2)
    head, tail = int(keep * 0.7), keep - int(keep * 0.7)
    return s[:head] + tag + (s[-tail:] if tail > 0 else "")


# Đường đi tới một chuỗi trong payload lồng nhau: khoá dict (str) hoặc chỉ số list (int).
# `strict` của core không nhận `tuple` trần — và ở đây kiểu rõ cũng là tài liệu: nó nói vì sao `_set` đi
# được vào cả list lẫn dict.
Path = tuple[str | int, ...]


def _strings(obj: Any, path: Path = ()) -> list[tuple[Path, str]]:
    out: list[tuple[Path, str]] = []
    if isinstance(obj, str): out.append((path, obj))
    elif isinstance(obj, dict):
        for k, v in obj.items(): out += _strings(v, (*path, k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj): out += _strings(v, (*path, i))
    return out


def _set(obj: Any, path: Path, value: str) -> None:
    cur = obj
    for p in path[:-1]: cur = cur[p]
    cur[path[-1]] = value


def trim_payload(payload: dict[str, Any], limit: int) -> tuple[dict[str, Any], int]:
    """Cắt chuỗi dài nhất trước cho tới khi JSON của payload ≤ limit ký tự. Trả về (payload mới, số ký tự đã cắt)."""
    data = json.loads(json.dumps(payload, ensure_ascii=False))  # bản sao sâu
    removed = 0
    for _ in range(64):
        size = len(json.dumps(data, ensure_ascii=False, indent=2))
        if size <= limit: break
        strs = [(p, s) for p, s in _strings(data) if len(s) > MIN_KEEP]
        if not strs: break
        path, s = max(strs, key=lambda x: len(x[1]))
        target = max(MIN_KEEP, len(s) - (size - limit) - 80)
        cut = cut_middle(s, target, note=f"trường {'.'.join(map(str, path))}")
        removed += len(s) - len(cut); _set(data, path, cut)
    return data, removed


@dataclass
class ContextBudget:
    max_input_chars: int
    system_chars: int
    payload_chars: int = 0
    context_chars: int = 0
    trimmed_payload: int = 0
    trimmed_context: dict[str, int] = field(default_factory=dict)

    @property
    def est_tokens(self) -> int:
        return int((self.system_chars + self.payload_chars + self.context_chars) / CHARS_PER_TOKEN)

    def report(self) -> dict[str, Any]:
        return {"max_input_chars": self.max_input_chars, "system": self.system_chars, "payload": self.payload_chars,
                "context": self.context_chars, "trimmed_payload": self.trimmed_payload,
                "trimmed_context": self.trimmed_context, "est_tokens": self.est_tokens}

    @property
    def trimmed(self) -> bool:
        return bool(self.trimmed_payload or self.trimmed_context)


def fit(system: str, payload: dict[str, Any], context: dict[str, dict[str, Any]], max_input_chars: int,
        payload_share: float = 0.6, paths: dict[str, str] | None = None) -> tuple[dict[str, Any], dict[str, dict[str, Any]], ContextBudget]:
    """Ép payload + blackboard vào hạn mức. `context` = {namespace: {version, content_ref, summary, content?}}.
    `paths` = {namespace: đường dẫn artifact} để nhãn cắt chỉ chỗ đọc thêm."""
    b = ContextBudget(max_input_chars=max_input_chars, system_chars=len(system))
    room = max(max_input_chars - len(system) - 1_500, MIN_KEEP * 4)  # 1 500 cho khung prompt (tiêu đề, yêu cầu)
    ctx_wanted = sum(len(str(v.get("content") or "")) for v in context.values()) + 200 * len(context)
    payload_limit = max(int(room * payload_share), room - ctx_wanted)  # blackboard nhỏ thì payload được rộng hơn
    payload, b.trimmed_payload = trim_payload(payload, min(payload_limit, room))
    b.payload_chars = len(json.dumps(payload, ensure_ascii=False, indent=2))
    ctx_room = room - b.payload_chars
    out: dict[str, dict[str, Any]] = {}
    fixed = sum(len(json.dumps({k: v for k, v in c.items() if k != "content"}, ensure_ascii=False)) + 40 for c in context.values())
    ctx_room -= fixed
    contents = {ns: str(c.get("content") or "") for ns, c in context.items()}
    # water-filling: namespace ngắn lấy đúng phần mình, phần thừa chia cho namespace dài
    remaining, pending = max(ctx_room, 0), dict(contents)
    alloc: dict[str, int] = {}
    while pending:
        share = remaining // len(pending)
        small = {ns: s for ns, s in pending.items() if len(s) <= share}
        if not small:
            for ns in pending: alloc[ns] = share
            break
        for ns, s in small.items():
            alloc[ns] = len(s); remaining -= len(s); pending.pop(ns)
    for ns, c in context.items():
        item = {k: v for k, v in c.items() if k != "content"}
        s = contents[ns]
        if s:
            lim = alloc.get(ns, 0)
            if lim < len(s):
                note = f"đọc đầy đủ ở {paths[ns]}" if paths and paths.get(ns) else "artifact đầy đủ trên blackboard"
                cut = cut_middle(s, max(lim, MIN_KEEP), note=note) if lim >= MIN_KEEP else f"… (bỏ {len(s)} ký tự; {note}) …"
                b.trimmed_context[ns] = len(s) - len(cut); s = cut
            item["content"] = s
        out[ns] = item
    b.context_chars = len(json.dumps(out, ensure_ascii=False, indent=2))
    return payload, out, b


def _prune(msgs: list[dict[str, Any]], keep_turns: int = 3) -> tuple[list[dict[str, Any]], int]:
    """ADR-0007: tỉa `role=tool` cũ hơn `keep_turns` LƯỢT gần nhất của vòng tool — khác `fit()` (cắt một lần
    TRƯỚC vòng); hàm này gọi mỗi lượt BÊN TRONG vòng, vì `msgs` chỉ có hình dạng đầy đủ sau khi vòng đã chạy.

    Một "lượt" = một message `assistant` có `tool_calls`, cộng các `role: tool` phản hồi ngay sau nó. Thuần:
    không đọc `self`, không side effect — nhận `msgs`, trả `msgs` MỚI (không sửa `msgs` gốc) + tổng ký tự đã bỏ.

    Bất biến:
    - `msgs[0]` (yêu cầu gốc, luôn `role=user`) không bao giờ bị tỉa — chống trôi mục tiêu qua nhiều lượt.
    - `role=assistant` và `tool_calls` của nó giữ nguyên mọi lượt — chỉ nội dung tool được thay, không phải
      quyết định model đã đưa ra; xoá `tool_calls` sẽ làm hội thoại sai hình dạng (provider từ chối).
    - `keep_turns` lượt GẦN NHẤT giữ nguyên toàn văn; lượt cũ hơn → mỗi `role=tool` của nó thành
      `[đã cắt: <tool> <chars> ký tự, hash <h>; gọi lại nếu cần]` (`<tool>` tra theo `tool_call_id`, `<h>` là
      hash của nội dung ĐANG bị tỉa — không phải `out_hash` gốc của `ToolBox`, vì `_prune` chỉ thấy `msgs` đã
      qua sanitize/`max_output`, không có `ToolBox`; hai giá trị trùng nhau khi tool không bị sanitize/cắt).
    """
    turn_starts = [i for i, m in enumerate(msgs) if m.get("role") == "assistant" and m.get("tool_calls")]
    if len(turn_starts) <= keep_turns:
        return list(msgs), 0
    # index của lượt gần nhất thứ `keep_turns` — mọi thứ TRƯỚC nó có thể bị tỉa. `keep_turns == 0` là ca biên:
    # `turn_starts[-0]` bằng `turn_starts[0]` trong Python (không có "trừ không"), nên phải xin tường minh
    # "tỉa mọi lượt" (`len(msgs)`) thay vì để `-0` đọc nhầm thành "giữ mọi lượt".
    cutoff = turn_starts[-keep_turns] if keep_turns > 0 else len(msgs)
    tool_name_of: dict[str, str] = {}
    for m in msgs:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                tool_name_of[tc["id"]] = tc["name"]
    out: list[dict[str, Any]] = []
    dropped = 0
    for i, m in enumerate(msgs):
        if i == 0 or i >= cutoff or m.get("role") != "tool":
            out.append(m); continue
        content = str(m.get("content", ""))
        name = tool_name_of.get(str(m.get("tool_call_id")), "?")
        h = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
        placeholder = f"[đã cắt: {name} {len(content)} ký tự, hash {h}; gọi lại nếu cần]"
        dropped += max(0, len(content) - len(placeholder))
        out.append({**m, "content": placeholder})
    return out, dropped
