"""Eval prompt của `keeper`: mỗi agent có bộ ca `evals/<agent>.yaml` (đầu vào + tiêu chí chấm XÁC ĐỊNH).

Chạy: `python -m keeper.evals triager` (model đã cấu hình) · `--record` (model thật, ghi
`evals/recordings/<agent>.json`) · `--replay --strict` (CI, không gọi model, không chạm mạng).

Cơ chế ghi/phát lại ở `xagents_core.evals`; ở đây chỉ bốn móc core không được biết (`load_agents`, `new_bus`,
`new_blackboard`, `run_case`) và **chính sách cổng** trong `main` — core cố ý không mang `main` lên
(`xagents_core/evals.py` §3: lấy `main` của company là âm thầm nới cổng của studio).

## Cổng của `keeper`: chính sách của STUDIO, không của company

`keeper` đỏ khi **bất kỳ ca nào không chạy được** (`errored`), không tách `gate_ok`/`cases_ok` như company. Lý
do là hình dạng bộ ca: `keeper` có 5-6 ca mỗi agent, đo những phán xét mà một ca hỏng là một luật rủi ro sai —
không có ca "mềm" nào để tách ra khỏi cổng. Cộng thêm `evals/thresholds.yaml` gác ĐIỂM CHẤM (p3.3) để một bản
ghi mới tụt điểm cũng đỏ, chứ không chỉ bản ghi lệch prompt.

## Vì sao chỉ 4/10 agent có bộ ca

Ca eval chỉ đáng viết cho agent mà **đầu ra là phán xét có thể sai**. Bốn agent có bộ ca: `triager`
(`risk_tier`), `security-auditor` (phân loại phát hiện), `release-clerk` (dòng CHANGELOG + nhật ký phiên),
`keeper-supervisor` (phản ứng của watchdog — và cả phía ngược: KHÔNG phản ứng thừa).

Sáu agent còn lại không có, mỗi cái một lý do:

- `dependency-scout`, `health-monitor`, `drift-detector` phát `Signal` thô do CODE đo (`scout.py`, `health.py`,
  `drift.py`) — không có chỗ cho model quyết, ca eval sẽ chấm một hằng đúng.
- `patcher`/`refactorer` sinh diff; cổng của diff là bằng chứng đo hai chiều (`evidence.py`), không phải một
  `expect` trong YAML.
- `regression-guard` — **đo được, không suy ra.** Bộ ca đầu tiên của gói này viết cho vai đó và bị BỎ sau khi
  chạy model thật (2026-09-09, `claude-sonnet-5`): 1/5 ca đạt, và bốn ca trượt vì agent **làm đúng** — nó từ
  chối chép `before/after` từ `summary` của `patcher`, trả `exit_code: -1` kèm "không có công cụ chạy lệnh
  trong phiên này, đây là lời khai của patcher chứ không phải output tôi vừa chạy". Đúng luật `AGENTS.md` §6 và
  §8. Nghĩa là mọi ca đòi vai này điền số đo đều đang đòi **một lời khai**; bằng chứng thật do
  `evidence.collect_two_way()` sinh, và cổng của nó là `require_two_way()` — cả hai là mã, đã có test riêng.
  Đây là một giới hạn của vai, không phải một khoản nợ eval.

Ngày một trong sáu vai đó thật sự phán xét thì thêm bộ ca cùng lúc với việc ấy, và thêm tên vào
`evals/recordings/REQUIRED.txt`.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from xagents_core.evals import CaseResult as CaseResult
from xagents_core.evals import EvalSuite
from xagents_core.evals import RecordingClient as CoreRecordingClient
from xagents_core.evals import ReplayClient as CoreReplayClient
from xagents_core.evals import Threshold as Threshold
from xagents_core.evals import check as check
from xagents_core.evals import check_thresholds as check_thresholds
from xagents_core.evals import load_thresholds as _core_load_thresholds
from xagents_core.evals import prompt_key as prompt_key

from .blackboard import Blackboard
from .bus import KeeperMemoryBus
from .core import CORE
from .events import Envelope
from .llm import LLMError, ModelClient
from .registry import load_agents
from .runner import AgentRunner, RunnerError

__all__ = ["EVALS_DIR", "RECORDINGS_DIR", "RecordingClient", "ReplayClient", "Suite", "main", "run_eval"]

EVALS_DIR = CORE.root / "evals"
RECORDINGS_DIR = EVALS_DIR / "recordings"
DEFAULT_THRESHOLDS_PATH = EVALS_DIR / "thresholds.yaml"  # sàn ĐIỂM CHẤM, khác REQUIRED.txt gác BẢN GHI


class Suite(EvalSuite):
    """Bộ eval của `keeper`. Chỉ khai thứ core không được biết."""

    case_errors = (RunnerError, LLMError)

    # Đọc từ BIẾN MODULE, không tính từ `self.root`: `monkeypatch.setattr(ev, "RECORDINGS_DIR", …)` là seam của
    # test (cùng lý do đã ghi ở company và studio) — tính từ `self.root` là seam ấy im lặng hết tác dụng.
    @property
    def evals_dir(self) -> Path: return EVALS_DIR

    @property
    def recordings_dir(self) -> Path: return RECORDINGS_DIR

    def load_agents(self) -> dict[str, Any]:
        return load_agents()

    def new_bus(self) -> KeeperMemoryBus:
        return KeeperMemoryBus(CORE)

    def new_blackboard(self, bus: KeeperMemoryBus) -> Blackboard:
        return Blackboard(bus)

    def run_case(self, agent_id: str, case: dict[str, Any], client: ModelClient,
                 agents: dict[str, Any] | None, bb: Blackboard, bus: KeeperMemoryBus) -> Any:
        runner = AgentRunner(bus, client, agents, blackboard=bb)
        i = case["input"]
        inp = Envelope(topic=i["topic"], key=i["key"], actor=i.get("actor", "human"), payload=i["payload"])
        return runner.run(agent_id, inp, case["topic_out"])


SUITE = Suite(CORE.root)


def run_eval(agent_id: str, client: ModelClient, agents: dict[str, Any] | None = None) -> list[CaseResult]:
    return SUITE.run_eval(agent_id, client, agents)


class RecordingClient(CoreRecordingClient):
    def __init__(self, inner: ModelClient, agent_id: str):
        super().__init__(inner, agent_id, SUITE)


class ReplayClient(CoreReplayClient):
    def __init__(self, agent_id: str):
        super().__init__(agent_id, SUITE)


def load_thresholds(path: Path | None = None) -> dict[str, Threshold]:
    return _core_load_thresholds(path or DEFAULT_THRESHOLDS_PATH)


@dataclass(frozen=True)
class _AgentOutcome:
    """Ba trường `check_thresholds` cần (`ScoredOutcome` của core)."""
    agent_id: str
    res: list[CaseResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.res)

    @property
    def passed(self) -> int:
        return sum(r.passed for r in self.res)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Chạy eval prompt của agent keeper: model thật, ghi lại (--record) hoặc phát lại (--replay)")
    ap.add_argument("agent", help="id agent, hoặc `all`")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--record", action="store_true")
    mode.add_argument("--replay", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="với --replay: agent trong evals/recordings/REQUIRED.txt mà thiếu bản ghi hoặc bản ghi "
                         "lệch phiên bản prompt thì tính là fail")
    ap.add_argument("--thresholds", type=Path, default=None, metavar="PATH",
                    help="sàn điểm eval theo agent, mặc định evals/thresholds.yaml nếu tồn tại")
    ap.add_argument("--no-thresholds", action="store_true", help="tắt cổng ngưỡng điểm eval")
    ns = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    agents = SUITE.load_agents()
    ids = sorted(agents) if ns.agent == "all" else [ns.agent]
    ok = True
    required = set(SUITE.required_agents()) if ns.strict else set()
    th: dict[str, Threshold] = {}
    if not ns.no_thresholds:
        th_path = ns.thresholds if ns.thresholds is not None else DEFAULT_THRESHOLDS_PATH
        if ns.thresholds is not None or th_path.exists():
            th = load_thresholds(th_path)
    if ns.strict:
        for aid, why in SUITE.outdated_versions(ids).items():
            print(f"FAIL {aid}: {why} — chạy `make eval-record AGENT={aid}` rồi commit lại"); ok = False
    outcomes: list[_AgentOutcome] = []
    for aid in ids:
        if not SUITE.load_cases(aid):
            continue
        if ns.replay:
            try:
                client: ModelClient = ReplayClient(aid)
            except LLMError as e:
                print(f"{'FAIL' if aid in required else 'SKIP'} {aid}: {e}")
                ok = ok and aid not in required
                continue
        else:
            from .llm import make_client
            client = RecordingClient(make_client(), aid) if ns.record else make_client()
        res = run_eval(aid, client, agents)
        outcomes.append(_AgentOutcome(aid, res))
        for ln in SUITE.lines(aid, res): print(ln)
        if isinstance(client, RecordingClient):
            print(f"đã ghi {client.save()}")
        # `--replay` (CI): cổng là "bản ghi còn khớp prompt và ca chạy được"; điểm chấm gác riêng bằng
        # `thresholds.yaml`. Model thật: mọi ca phải đạt.
        ok = ok and (not any(r.errored for r in res) if ns.replay else all(r.passed for r in res))
    for line in check_thresholds(outcomes, th):
        print(line); ok = False
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
