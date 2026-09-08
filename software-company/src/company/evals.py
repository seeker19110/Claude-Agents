"""Eval prompt (ADR-0004): mỗi agent có `evals/<agent>.yaml` gồm các ca đầu vào + tiêu chí chấm xác định.
Chạy với model đã cấu hình (`python -m company.evals reviewer`) hoặc client giả trong test. Không gắn provider nào.

Tiêu chí (`expect`):
  equals:   {field: value}         trường bằng đúng
  contains: {field: substring}     chuỗi chứa (không phân biệt hoa thường)
  min_len:  {field: n}             list/chuỗi có độ dài ≥ n
  max_len:  {field: n}             list/chuỗi có độ dài ≤ n (n=0 nghĩa là phải rỗng)
  one_of:   {field: [v1, v2]}      giá trị nằm trong tập
  any_of:   [expect1, expect2]     ĐẠT nếu ít nhất một nhánh đạt (mỗi nhánh là một khối `expect` đầy đủ)

`any_of` có vì hệ thống nhiều chỗ chấp nhận NHIỀU CÁCH DIỄN ĐẠT cho cùng một yêu cầu; ép đúng một cách là
chấm khác biệt mà hệ không định nghĩa, và ca eval sẽ đỏ vì model chọn cách kia chứ không vì nó làm sai.

Ghi / phát lại (ADR-0010): `--record` chạy model thật và lưu phản hồi vào `evals/recordings/<agent>.json`, khoá bằng
hash(system prompt + user message). `--replay` chạy lại từ bản ghi, không cần model — CI dùng chế độ này. Sửa prompt
hay skill → hash đổi → bản ghi lệch → CI đỏ cho tới khi ghi lại bằng model thật: đó chính là cổng "đổi prompt phải chạy
eval" của ADR-0004, được máy cưỡng chế.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .blackboard import Blackboard
from .bus import InMemoryBus
from .events import Envelope
from .llm import Completion, LLMError, ModelClient
from .registry import load_agents
from .runner import AgentRunner, RunnerError
from .tools import ToolSpec

EVALS_DIR = Path(__file__).resolve().parents[2] / "evals"
RECORDINGS_DIR = EVALS_DIR / "recordings"
REQUIRED_NAME = "REQUIRED.txt"  # agent BẮT BUỘC có bản ghi tươi; thiếu hoặc lệch phiên bản prompt → CI đỏ


def prompt_key(system: str, user: str) -> str:
    return hashlib.sha256(json.dumps([system, user], ensure_ascii=False).encode("utf-8")).hexdigest()[:24]


def recording_path(agent_id: str) -> Path:
    return RECORDINGS_DIR / f"{agent_id}.json"


def load_recording(agent_id: str) -> dict[str, Any] | None:
    p = recording_path(agent_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


class RecordingClient:
    """Bọc client thật; mỗi phản hồi được lưu theo khoá prompt để phát lại sau."""

    def __init__(self, inner: ModelClient, agent_id: str):
        self.inner, self.agent_id = inner, agent_id
        self.entries: dict[str, dict[str, Any]] = {}
        # Chốt phiên bản NGAY LÚC BẮT ĐẦU, không đọc lại lúc `save()`. Một lượt ghi kéo dài nhiều phút; file
        # prompt đổi giữa chừng (người sửa tiếp, hay `git stash`/`checkout` ở nhánh khác) thì bản ghi mang một
        # phiên bản mà nó KHÔNG được ghi bằng — `outdated_versions` đỏ mà không ai hiểu vì sao. Đo được
        # 2026-09-05: stash file prompt trong lúc `make eval-record` chạy, bản ghi ra v11 trong khi prompt v12.
        self.prompt_version = load_agents()[agent_id].version

    def complete(self, *, system: str, user: str, schema: dict[str, Any], model_tier: str,
                 cache_key: str | None = None, tools: list[ToolSpec] | None = None,
                 messages: list[dict[str, Any]] | None = None, workdir: str | None = None) -> Completion:
        c = self.inner.complete(system=system, user=user, schema=schema, model_tier=model_tier, cache_key=cache_key,
                                tools=tools, messages=messages, workdir=workdir)
        self.entries[prompt_key(system, user)] = {"text": c.text, "model": c.model, "input_tokens": c.input_tokens,
                                                  "output_tokens": c.output_tokens}
        return c

    def save(self) -> Path:
        """Gộp vào bản ghi cũ, KHÔNG ghi đè cả file.

        Một ca lỗi giữa chừng (model từ chối, mạng đứt, hết hạn mức) thì lượt ghi chỉ có phần ca chạy được.
        Ghi đè lúc đó xoá luôn những ca đang tốt, và lần replay sau báo "bản ghi lệch prompt" cho một ca mà
        chẳng ai đụng tới — mất bằng chứng vì một sự cố không liên quan. Đo được 2026-09-05 trên qa-debugger.

        Khoá cũ không còn khớp prompt hiện tại thì nằm lại vô hại: `stale_recordings` chấm theo việc khoá
        HIỆN TẠI có mặt hay không, nên rác cũ không che được tín hiệu "phải ghi lại"."""
        cu = load_recording(self.agent_id) or {}
        cases = {**(cu.get("cases") or {}), **self.entries}
        data = {"agent": self.agent_id, "prompt_version": self.prompt_version, "recorded_at": datetime.now(UTC).isoformat(),
                "models": sorted({e["model"] for e in cases.values()}), "cases": cases}
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        p = recording_path(self.agent_id)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        return p


class ReplayClient:
    """Trả phản hồi đã ghi; prompt không có trong bản ghi (prompt/skill/ca eval đã đổi) → LLMError nói rõ phải ghi lại."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        data = load_recording(agent_id)
        if data is None:
            raise LLMError(f"chưa có bản ghi eval cho {agent_id}: chạy `make eval-record AGENT={agent_id}` với model thật")
        self.data: dict[str, Any] = data

    def complete(self, *, system: str, user: str, schema: dict[str, Any], model_tier: str,
                 cache_key: str | None = None, tools: list[ToolSpec] | None = None,
                 messages: list[dict[str, Any]] | None = None, workdir: str | None = None) -> Completion:
        e = self.data["cases"].get(prompt_key(system, user))
        if e is None:
            raise LLMError(f"bản ghi eval của {self.agent_id} lệch prompt hiện tại (prompt/skill/ca eval đã đổi): "
                           f"chạy `make eval-record AGENT={self.agent_id}` với model thật rồi commit bản ghi")
        return Completion(text=e["text"], input_tokens=int(e.get("input_tokens", 0)),
                          output_tokens=int(e.get("output_tokens", 0)), model=f"replay:{e.get('model', '?')}")


def required_agents() -> list[str]:
    """Agent phải có bản ghi eval tươi. Thêm id vào `evals/recordings/REQUIRED.txt` ngay khi commit bản ghi đầu tiên
    của agent đó; từ lúc ấy CI đỏ nếu bản ghi biến mất hoặc lệch prompt (ADR-0004, ADR-0010)."""
    p = RECORDINGS_DIR / REQUIRED_NAME
    if not p.exists(): return []
    return [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


def outdated_versions(agent_ids: list[str] | None = None) -> dict[str, str]:
    """Bản ghi ghi bằng phiên bản prompt cũ hơn phiên bản hiện tại → {agent: "ghi v3, hiện v5"}.
    Kiểm được offline, không cần gọi model: đây là răng của "đổi prompt phải chạy lại eval"."""
    agents = load_agents(); out: dict[str, str] = {}
    for aid in agent_ids or sorted(agents):
        rec = load_recording(aid)
        if rec is None: continue
        got, want = int(rec.get("prompt_version", 0)), agents[aid].version
        if got != want: out[aid] = f"bản ghi ở prompt v{got}, agent hiện v{want}"
    return out


def stale_recordings(agent_ids: list[str] | None = None) -> dict[str, list[str]]:
    """Bản ghi hiện có mà thiếu khoá cho ca eval hiện tại → {agent: [tên ca]} (rỗng = mọi bản ghi còn khớp).
    Test dùng hàm này để CI đỏ ngay khi prompt đổi mà chưa chạy lại eval bằng model thật."""
    agents = load_agents(); out: dict[str, list[str]] = {}
    for aid in agent_ids or sorted(agents):
        rec = load_recording(aid)
        if rec is None: continue
        missing = []
        for case in load_cases(aid):
            bus = InMemoryBus(); bb = Blackboard(bus)
            for ctx in case.get("context", []):
                bb.write(ctx["actor"], ctx["namespace"], ctx["content_ref"], ctx.get("summary", ""), content=ctx.get("content"))
            probe = _Probe(); AgentRunner(bus, probe, agents, blackboard=bb)
            try: _run_case(aid, case, probe, agents, bb, bus)
            except (RunnerError, LLMError): pass
            if probe.key is not None and probe.key not in rec["cases"]: missing.append(case["name"])
        if missing: out[aid] = missing
    return out


class _Probe:
    """Client giả chỉ để lấy khoá prompt của một ca, không trả lời."""
    key: str | None = None

    def complete(self, *, system: str, user: str, schema: dict[str, Any], model_tier: str,
                 cache_key: str | None = None, tools: list[ToolSpec] | None = None,
                 messages: list[dict[str, Any]] | None = None, workdir: str | None = None) -> Completion:
        self.key = prompt_key(system, user)
        raise LLMError("probe")


@dataclass
class CaseResult:
    name: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    tokens: int = 0
    # True khi ca hỏng vì bản ghi (thiếu hoặc lệch prompt), không phải vì model trả sai.
    # Hai loại này có hệ quả khác nhau ở mã thoát: bản ghi hỏng là cổng, điểm chấm thì không.
    broken_recording: bool = False


def _get(d: Any, dotted: str) -> Any:
    cur = d
    for part in dotted.split("."):
        if isinstance(cur, list) and part.isdigit(): cur = cur[int(part)] if int(part) < len(cur) else None
        elif isinstance(cur, dict): cur = cur.get(part)
        else: return None
        if cur is None: return None
    return cur


def check(payload: dict[str, Any], expect: dict[str, Any]) -> list[str]:
    fails: list[str] = []
    for f, v in (expect.get("equals") or {}).items():
        if _get(payload, f) != v: fails.append(f"{f} == {v!r}, thực tế {_get(payload, f)!r}")
    for f, v in (expect.get("contains") or {}).items():
        if str(v).lower() not in str(_get(payload, f) or "").lower(): fails.append(f"{f} phải chứa {v!r}")
    for f, n in (expect.get("min_len") or {}).items():
        if len(_get(payload, f) or []) < n: fails.append(f"len({f}) ≥ {n}")
    for f, n in (expect.get("max_len") or {}).items():
        if len(_get(payload, f) or []) > n: fails.append(f"len({f}) ≤ {n}, thực tế {len(_get(payload, f) or [])}")
    for f, vs in (expect.get("one_of") or {}).items():
        if _get(payload, f) not in vs: fails.append(f"{f} ∈ {vs}")
    for nhanh in (expect.get("any_of") or []):
        con = [check(payload, alt) for alt in nhanh]
        if all(c for c in con):  # mọi nhánh đều hỏng → báo lý do của TỪNG nhánh, không chỉ nhánh đầu
            fails.append("không nhánh nào của any_of đạt: " + " | ".join("; ".join(c) for c in con))
    return fails


def load_cases(agent_id: str) -> list[dict[str, Any]]:
    p = EVALS_DIR / f"{agent_id}.yaml"
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("cases", []) if p.exists() else []


def _run_case(agent_id: str, case: dict[str, Any], client: ModelClient, agents: dict | None, bb: Blackboard, bus: InMemoryBus):
    agents_ = agents or load_agents()
    spec = agents_[agent_id]
    phase = case.get("phase")
    # ADR-0037 §11: agent có `phases` bắt buộc mỗi ca khai `phase:`, và pha đó phải có trong front matter — thiếu
    # hoặc sai tên là lỗi cấu hình ca eval, không phải model trả sai, nên báo rõ thay vì lặng lẽ chạy pha `None`
    # (prompt chung, thiếu skill của pha) và chấm sai nguyên nhân.
    if spec.phases and phase is None:
        raise RunnerError(f"{agent_id}: ca {case.get('name', '?')} thiếu `phase` (agent có phases: {sorted(spec.phases)})")
    if phase is not None and phase not in spec.phases:
        raise RunnerError(f"{agent_id}: ca {case.get('name', '?')} khai phase={phase!r}, front matter chỉ có {sorted(spec.phases)}")
    runner = AgentRunner(bus, client, agents, blackboard=bb)
    i = case["input"]
    inp = Envelope(topic=i["topic"], key=i["key"], actor=i.get("actor", "human"), payload=i["payload"])
    return runner.run(agent_id, inp, case["topic_out"], phase=phase)


def run_eval(agent_id: str, client: ModelClient, agents: dict | None = None) -> list[CaseResult]:
    results = []
    for case in load_cases(agent_id):
        bus = InMemoryBus(); bb = Blackboard(bus)
        for ctx in case.get("context", []):
            bb.write(ctx["actor"], ctx["namespace"], ctx["content_ref"], ctx.get("summary", ""), content=ctx.get("content"))
        try:
            r = _run_case(agent_id, case, client, agents, bb, bus)
        except (RunnerError, LLMError) as e:
            broken = isinstance(e, LLMError) and "bản ghi" in str(e)
            results.append(CaseResult(case["name"], False, [str(e)], broken_recording=broken)); continue
        fails = check(r.output.payload, case.get("expect", {}))
        results.append(CaseResult(case["name"], not fails, fails, r.tokens))
    return results


def _lines(agent_id: str, res: list[CaseResult]) -> list[str]:
    out = [f"{'PASS' if r.passed else 'FAIL'} {agent_id}/{r.name} ({r.tokens} tok)"
           + "".join(f"\n   - {f}" for f in r.failures) for r in res]
    return [*out, f"{agent_id}: {sum(r.passed for r in res)}/{len(res)} pass"]


@dataclass
class _AgentOutcome:
    """Kết quả một agent, tách hai loại đúng như `main`: `gate_ok` (bản ghi đủ và khớp prompt — thứ DUY NHẤT
    làm CI đỏ, ADR-0010) và `cases_ok` (điểm chấm — tín hiệu chất lượng, không phải cổng)."""
    agent_id: str
    lines: list[str]
    gate_ok: bool
    cases_ok: bool
    res: list[CaseResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.res)

    @property
    def passed(self) -> int:
        return sum(r.passed for r in self.res)


@dataclass(frozen=True)
class Threshold:
    """Sàn điểm của một agent (4L-1a). `cases` chống thu nhỏ bộ ca để né `min_pass_ratio`: xoá bớt ca xấu
    làm ratio đẹp lên nhưng `total` tụt dưới `cases` thì vẫn đỏ."""
    min_pass_ratio: float
    cases: int


DEFAULT_THRESHOLDS_PATH = EVALS_DIR / "thresholds.yaml"


def load_thresholds(path: Path | None = None) -> dict[str, Threshold]:
    """Không có file → `{}` (tính năng không áp, không phải lỗi — agent mới chưa kịp có ngưỡng).
    Có file nhưng sai hình (không phải mapping, thiếu trường) → `LLMError` rõ ràng thay vì KeyError mù mờ."""
    p = path or DEFAULT_THRESHOLDS_PATH
    if not p.exists():
        return {}
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise LLMError(f"{p}: sai cú pháp YAML: {e}") from e
    if not isinstance(raw, dict):
        raise LLMError(f"{p}: phải là mapping agent -> {{min_pass_ratio, cases}}")
    out: dict[str, Threshold] = {}
    for aid, v in raw.items():
        if not isinstance(v, dict) or "min_pass_ratio" not in v or "cases" not in v:
            raise LLMError(f"{p}: {aid} thiếu `min_pass_ratio` hoặc `cases`")
        try:
            out[aid] = Threshold(min_pass_ratio=float(v["min_pass_ratio"]), cases=int(v["cases"]))
        except (TypeError, ValueError) as e:
            raise LLMError(f"{p}: {aid} có `min_pass_ratio`/`cases` không phải số: {e}") from e
    return out


def check_thresholds(outcomes: list[_AgentOutcome], th: dict[str, Threshold]) -> list[str]:
    """Dòng FAIL cho agent tụt dưới sàn (4L-1a). Tính SAU khi mọi outcome đã gom xong (dùng được với `--jobs`).
    Agent không có trong `th` → không áp (agent mới, hoặc cố ý chưa đặt ngưỡng); `total == 0` → không áp
    (không có ca eval thì không có gì để chấm, tránh chia 0 và tránh đỏ oan agent chưa có bộ ca)."""
    fails: list[str] = []
    for o in outcomes:
        t = th.get(o.agent_id)
        if t is None or o.total == 0:
            continue
        ratio = o.passed / o.total
        if ratio < t.min_pass_ratio:
            fails.append(f"FAIL {o.agent_id}: điểm {ratio:.2f} dưới ngưỡng {t.min_pass_ratio:.2f} "
                        f"({o.passed}/{o.total} ca) — evals/thresholds.yaml")
        if o.total < t.cases:
            fails.append(f"FAIL {o.agent_id}: bộ ca còn {o.total} dưới ngưỡng {t.cases} ca — "
                        f"bộ ca bị thu nhỏ, evals/thresholds.yaml")
    return fails


def _summary(outcomes: list[_AgentOutcome], th: dict[str, Threshold] | None = None) -> None:
    """Bảng điểm vào `$GITHUB_STEP_SUMMARY` khi chạy trong Actions (K5.4). Điểm KHÔNG phải cổng — nhưng "CI xanh"
    cũng không được đọc thành "eval đạt", nên phải có chỗ nhìn thấy điểm mà không phải mở log job."""
    th = th or {}
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    rows = [o for o in outcomes if o.res]
    if not path or not rows: return
    body = ["| agent | ca đạt | bản ghi | ngưỡng |", "|---|---|---|---|"]
    for o in rows:
        t = th.get(o.agent_id)
        ng = f"≥{t.min_pass_ratio:.2f}, ≥{t.cases} ca" if t else "-"
        body.append(f"| `{o.agent_id}` | {sum(r.passed for r in o.res)}/{len(o.res)} | "
                    f"{'ok' if o.gate_ok else '**lệch/thiếu**'} | {ng} |")
    body.append("")
    body.append("Điểm chấm không phải cổng riêng lẻ (CONTRIBUTING §3): bản ghi thiếu/lệch phiên bản prompt hoặc "
                "tụt dưới `evals/thresholds.yaml` (4L-1a) mới làm CI đỏ.")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(body) + "\n")
    except OSError:   # summary không ghi được thì thôi — nó là thông tin, không phải kết quả
        pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Chạy eval prompt của agent: model thật, ghi lại (--record) hoặc phát lại (--replay)")
    ap.add_argument("agent", help="id agent, hoặc `all`")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--record", action="store_true", help="chạy model thật và lưu evals/recordings/<agent>.json")
    mode.add_argument("--replay", action="store_true", help="chạy từ bản ghi, không gọi model (CI)")
    ap.add_argument("--fail-on-score", action="store_true",
                    help="đỏ cả khi ca eval không đạt (mặc định chỉ bản ghi thiếu/lệch mới đỏ — CONTRIBUTING §3)")
    ap.add_argument("--strict", action="store_true",
                    help="với --replay: agent trong evals/recordings/REQUIRED.txt mà thiếu bản ghi hoặc bản ghi lệch "
                         "phiên bản prompt thì tính là fail")
    ap.add_argument("--jobs", type=int, default=1, metavar="N",
                    help="chạy N agent song song (K5.3). Mỗi agent một client và một file bản ghi riêng nên "
                         "không tranh nhau; thứ tự IN vẫn theo id. Song song ở đây là chờ MẠNG, không phải CPU")
    ap.add_argument("--thresholds", type=Path, default=None, metavar="PATH",
                    help="ngưỡng eval theo agent (4L-1a), mặc định evals/thresholds.yaml nếu tồn tại; "
                         "agent tụt dưới sàn làm CI đỏ")
    ap.add_argument("--no-thresholds", action="store_true", help="tắt cổng ngưỡng eval, giữ hành vi cũ")
    ns = ap.parse_args(argv)
    if ns.jobs < 1: ap.error("--jobs phải >= 1")
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")  # Windows console cp1252
    agents = load_agents()
    ids = sorted(agents) if ns.agent == "all" else [ns.agent]
    # Hai loại kết quả, cố ý tách: `gate_ok` là bản ghi có đủ và đúng phiên bản prompt hay không —
    # đó là thứ duy nhất làm CI đỏ (ADR-0010). `cases_ok` là điểm chấm, một tín hiệu chất lượng cho
    # vòng sau; nó chỉ đổi mã thoát khi chạy với model thật ở máy, không đổi khi CI phát lại.
    gate_ok = True; cases_ok = True
    required = set(required_agents()) if ns.strict else set()
    th: dict[str, Threshold] = {}
    if not ns.no_thresholds:
        th_path = ns.thresholds if ns.thresholds is not None else DEFAULT_THRESHOLDS_PATH
        if ns.thresholds is not None or th_path.exists():
            th = load_thresholds(th_path)
    if ns.strict:
        for aid, why in outdated_versions(ids).items():
            print(f"FAIL {aid}: {why} — chạy `make eval-record AGENT={aid}` rồi commit lại"); gate_ok = False
    def _one(aid: str) -> _AgentOutcome:
        """Một agent, chạy độc lập được: mỗi agent có `RecordingClient` riêng ghi file riêng của nó, và
        `save()` GỘP vào bản ghi cũ chứ không ghi đè — nên chạy song song theo agent không tranh nhau file.
        In ra được GOM lại (`lines`) thay vì `print` thẳng: với `--jobs > 1`, in thẳng là dòng của bốn agent
        cài răng lược, đọc log không biết `FAIL` thuộc về ai."""
        lines: list[str] = []
        if not load_cases(aid): return _AgentOutcome(aid, lines, True, True)
        if ns.replay:
            try: client: ModelClient = ReplayClient(aid)
            except LLMError as e:
                lines.append(f"{'FAIL' if aid in required else 'SKIP'} {aid}: {e}")
                return _AgentOutcome(aid, lines, aid not in required, True)
        else:
            from .llm import make_client
            client = RecordingClient(make_client(), aid) if ns.record else make_client()
        res = run_eval(aid, client, agents)
        lines += _lines(aid, res)
        if ns.record and isinstance(client, RecordingClient):
            lines.append(f"đã ghi {client.save()}")
        return _AgentOutcome(aid, lines, not any(r.broken_recording for r in res),
                             all(r.passed for r in res), res)

    # Thứ tự IN luôn theo id, kể cả khi chạy song song: log so được giữa hai lần chạy. `--jobs` chỉ đổi thứ tự
    # CHẠY, không đổi thứ tự đọc.
    if ns.jobs > 1 and len(ids) > 1:
        with ThreadPoolExecutor(max_workers=ns.jobs) as pool:
            outcomes = list(pool.map(_one, ids))
    else:
        outcomes = [_one(aid) for aid in ids]
    for o in outcomes:
        for ln in o.lines: print(ln)
        gate_ok = gate_ok and o.gate_ok
        cases_ok = cases_ok and o.cases_ok
    _summary(outcomes, th)
    if th:
        for line in check_thresholds(outcomes, th):
            print(line); gate_ok = False
    # Điểm chấm KHÔNG phải cổng (CONTRIBUTING §3): bản ghi thật vừa commit mà đỏ ngay thì không ai dám ghi lại.
    # Nhưng "CI xanh" cũng không được hiểu là "eval đạt": in một dòng tổng kết để đọc log là thấy, và
    # `--fail-on-score` cho người vận hành bật cổng khi muốn.
    if not cases_ok:
        print(f"CHÚ Ý: có ca eval không đạt (xem FAIL ở trên). Mã thoát {'1' if ns.fail_on_score else '0'}: "
              f"điểm chấm {'là cổng vì --fail-on-score' if ns.fail_on_score else 'không phải cổng, chỉ cổng bản ghi mới đỏ'}.")
    return 0 if gate_ok and (cases_ok or not ns.fail_on_score) else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
