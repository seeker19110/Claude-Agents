"""Deploy thật bằng `docker compose` — `deployed` là container đang chạy, không phải lời khai (ADR-0039).

`run_smoke` (ADR-0029) khởi động sản phẩm, probe, rồi **giết** nó: đúng để chấm "chạy được", sai để nói "đang
chạy". Module này chạy compose file **của khách** (công ty chạy nó chứ không sinh nó) rồi kết luận ba phần —
`up -d` thoát 0 **và** `ps` cho mọi service `running` **và** smoke probe vào cổng đã map trả đúng
`expect_status`. Thiếu bất kỳ phần nào → `ok=False` + `down`, để không bỏ lại container nửa sống trên máy trực.

Ranh giới (ADR-0039 §6):

- Chỉ **bốn** lệnh con: `up -d`, `ps`, `logs --tail`, `down`. argv do code ghép, không nội suy chuỗi từ payload
  của model — thứ duy nhất model chạm được là đường dẫn compose file (`runtime.deploy`), và nó phải tồn tại
  trong repo khách mới được dùng.
- `--project-name company-<project_id>-<env>` do **code** đặt: model không đổi được nó để giẫm sang môi trường
  khác. `env` là của ROUTE (`staging` | `production`), không phải lời khai.
- env lọc qua `clean_env` (bỏ `SECRET_ENV`, `GH_*`/`GITHUB_*`) như mọi lệnh con khác.
- Cổng **đọc** từ `ps` chứ orchestrator không tự chọn và không sửa compose của khách (ADR-0039 §2).

`docker compose` KHÔNG đi qua `Sandbox` (ADR-0039 §7): nhốt một client gọi `/var/run/docker.sock` vào container
là vô nghĩa — nó vẫn có quyền cao nhất của máy. Đây là ngoại lệ subprocess thứ hai sau `github_pr.py` (ADR-0038),
khai kèm lý do trong `tests/test_sandbox_noi_vao_cong_ty.py`.

Fail-closed theo đúng khuôn `sandbox_from_settings` (ADR-0035): `COMPANY_DEPLOY=compose` khai đích danh mà thiếu
binary là **lỗi**, không phải "coi như xong"; `auto` thiếu binary thì nói thiếu kèm tên biến người vận hành phải
đặt, và "chưa deploy" không bao giờ được đọc thành "đã deploy".
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from xagents_core.sandbox import clean_env

from .smoke import VERIFIED_BY, Runtime
from .smoke import _probe as http_probe  # cùng probe với smoke: "đang chạy" và "chạy được" phải đo bằng một thước

ENV_MODE = "COMPANY_DEPLOY"
ENV_RUNTIME = "COMPANY_DEPLOY_RUNTIME"
DEFAULT_RUNTIME = "docker"
MODES = ("auto", "compose", "off")
# Dò mặc định khi spec không khai `runtime.deploy` (ADR-0039 §1). Cố ý ngắn: đoán thêm tên file là đoán thay khách.
COMPOSE_NAMES = ("docker-compose.yml", "compose.yaml")
ENVS = ("staging", "production")
CMD_SUB = ("up", "ps", "logs", "down")   # ADR-0039 §6: bốn lệnh con, không hơn
UP_TIMEOUT_S = 300
CMD_TIMEOUT_S = 60
LOGS_TAIL = 50
LOGS_MAX = 2000

# Runner mặc định của `docker compose` — ngoại lệ Sandbox thứ hai (ADR-0039 §7). Giữ ở đây, không gọi thẳng trong
# thân hàm, để mọi test tiêm được runner giả: CI không có docker daemon (ADR-0039 §"Cách đo").
_RUN: Any = subprocess.run   # chỉ chạy `<binary> compose …` — xem `_argv`


class DeployError(Exception):
    """Không dựng được deploy đã yêu cầu. Cố ý là lỗi, không phải cảnh báo (fail-closed như `SandboxError`)."""


@dataclass(frozen=True)
class DeployRecord:
    """Bằng chứng của một lần deploy — `record()` là dạng ghi vào `release-events.evidence.deploy` (D1b).

    Ba hình, phân biệt được bằng máy: đang chạy (`ok=True`), không chạy được (`ok=False` + `error`), và **không
    thử** (`skipped`) — hình thứ ba KHÔNG phải thành công, đó là cả lý do module này tồn tại.
    """
    project: str
    env: str
    ok: bool = False
    services: tuple[str, ...] = ()
    container_ids: tuple[str, ...] = ()
    port: int | None = None
    started_at: str = ""
    smoke: dict[str, Any] = field(default_factory=dict)
    compose_file: str = ""
    skipped: str = ""
    error: str = ""
    logs_tail: str = ""

    def record(self) -> dict[str, Any]:
        out: dict[str, Any] = {"project": self.project, "env": self.env, "ok": self.ok,
                               "verified_by": VERIFIED_BY}
        for k in ("services", "container_ids", "port", "started_at", "smoke", "compose_file", "skipped",
                  "error", "logs_tail"):
            v = getattr(self, k)
            if v:
                out[k] = list(v) if isinstance(v, tuple) else v
        return out


def project_name(project_id: str, env: str) -> str:
    """Tên compose project do CODE đặt. Hai môi trường là hai project tách hẳn (ADR-0039 §2)."""
    return f"company-{project_id}-{env}"


def deploy_settings() -> tuple[str, str]:
    """`(mode, binary)` từ môi trường. Company đọc env, core thì không — cùng lý do với `sandbox_from_config`:
    tên biến là của công ty, không phải của lõi."""
    return (os.environ.get(ENV_MODE, "auto").strip().lower() or "auto",
            os.environ.get(ENV_RUNTIME, DEFAULT_RUNTIME).strip() or DEFAULT_RUNTIME)


def compose_file(repo_root: Path, rt: Runtime) -> str:
    """Đường dẫn compose file tương đối trong repo khách, "" nếu không có. Khai trong spec thì phải tồn tại —
    khai một file không có KHÔNG được lặng lẽ rơi về file dò được (người ký spec sẽ tưởng đã chạy file của mình)."""
    named = rt.deploy.strip()
    if named:
        return named if (repo_root / named).is_file() else ""
    return next((n for n in COMPOSE_NAMES if (repo_root / n).is_file()), "")


def _argv(binary: str, project: str, cfile: str, *args: str) -> list[str]:
    """argv do CODE ghép, không nội suy chuỗi từ payload của model (ADR-0039 §6): chỉ `cfile` đến từ spec, và
    `compose_file` đã xác nhận nó là file có thật trong repo khách. Lệnh con ngoài bốn lệnh cho phép là lỗi lập
    trình, không phải cấu hình — nên ném ngay chứ không trả bản ghi hỏng."""
    if not args or args[0] not in CMD_SUB:
        raise DeployError(f"lệnh con không được phép: {args[:1]} (chỉ {' | '.join(CMD_SUB)})")
    return [binary, "compose", "--project-name", project, "-f", cfile, *args]


def _compose(run: Any, binary: str, repo: Path, project: str, cfile: str, *args: str,
             timeout: int = CMD_TIMEOUT_S) -> tuple[bool, str]:
    """Một lệnh con compose; không ném — (ok, stdout) hoặc (False, lý do rút gọn)."""
    argv = _argv(binary, project, cfile, *args)
    try:
        r = run(argv, cwd=str(repo), capture_output=True, text=True, encoding="utf-8", env=clean_env(),
                timeout=timeout)
    except FileNotFoundError:
        return False, f"{binary}: không có trên máy (đặt {ENV_RUNTIME} hoặc {ENV_MODE}=off)"
    except subprocess.TimeoutExpired:
        return False, f"{binary} compose {args[0]}: quá {timeout}s"
    return (True, (r.stdout or "").strip()) if r.returncode == 0 else (False, ((r.stderr or "") or (r.stdout or "")).strip()[-600:])


def _services(out: str) -> list[dict[str, Any]]:
    """`compose ps --format json` trả một mảng JSON (compose v2 mới) HOẶC mỗi container một dòng JSON (bản cũ).
    Đọc cả hai: bản compose trên máy trực không phải thứ công ty chọn được."""
    text = out.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        rows = []
        for line in text.splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                return []
        return [r for r in rows if isinstance(r, dict)]
    if isinstance(data, dict):
        return [data]
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def _published_port(rows: list[dict[str, Any]]) -> int | None:
    """Cổng đã map ra máy chủ, đọc từ `ps` — orchestrator KHÔNG tự chọn cổng và không sửa compose (ADR-0039 §2)."""
    for row in rows:
        pubs = row.get("Publishers") or []
        for p in pubs if isinstance(pubs, list) else []:
            try:
                port = int((p or {}).get("PublishedPort") or 0)
            except (TypeError, ValueError):
                continue
            if port:
                return port
    return None


def _smoke_running(rt: Runtime, port: int) -> dict[str, Any]:
    """Probe cổng ĐÃ MAP của container đang chạy — dùng lại `smoke._probe`, khác `run_smoke` ở chỗ không khởi
    động và không giết gì: tiến trình ở đây phải sống tiếp sau khi đo xong."""
    url = f"http://127.0.0.1:{port}{rt.path}"
    out: dict[str, Any] = {"verified_by": VERIFIED_BY, "url": url, "port": port, "ok": False,
                           "http_status": None, "expect_status": rt.expect_status, "elapsed_s": 0.0}
    t0 = time.monotonic()
    while time.monotonic() - t0 < rt.timeout_s:
        st = http_probe(url)
        if st is not None:
            out["http_status"] = st
            out["ok"] = st == rt.expect_status
            break
        time.sleep(0.25)
    else:
        out["error"] = f"không trả lời {url} trong {rt.timeout_s}s"
    out["elapsed_s"] = round(time.monotonic() - t0, 2)
    return out


def deploy(repo_root: Path, project_id: str, env: str, rt: Runtime, *,
           mode: str | None = None, binary: str | None = None,
           run: Any = _RUN, which: Any = shutil.which) -> DeployRecord:
    """Dựng `runtime.deploy` của spec trong `repo_root` (worktree tích hợp — KHÔNG chạm `main` của khách).

    `run`/`which` tiêm được vì CI không có docker daemon và ma trận còn `windows-latest` (ADR-0039 §"Cách đo"):
    bốn nhánh của quyết định 3 và fail-closed của quyết định 4 đo được mà không cần container thật.
    """
    mode_, binary_ = deploy_settings()
    mode, binary = (mode if mode is not None else mode_), (binary if binary is not None else binary_)
    project = project_name(project_id, env)
    def rec(**kw: Any) -> DeployRecord:
        return DeployRecord(project=project, env=env, **kw)

    if env not in ENVS:
        raise DeployError(f"env không hợp lệ: {env!r} ({' | '.join(ENVS)}) — env là của ROUTE, không phải lời khai")
    if mode not in MODES:
        raise DeployError(f"{ENV_MODE} không hợp lệ: {mode!r} ({' | '.join(MODES)})")
    if mode == "off":
        return rec(skipped=f"{ENV_MODE}=off")
    if not which(binary):
        if mode == "compose":
            raise DeployError(f"{ENV_MODE}=compose nhưng không tìm thấy `{binary}` trên PATH; cài runtime, đặt "
                              f"{ENV_RUNTIME}=<binary> hoặc {ENV_MODE}=off (không tự tụt hạng bảo vệ)")
        return rec(skipped=f"không có `{binary}` trên PATH; đặt {ENV_RUNTIME} nếu runtime tên khác, hoặc "
                           f"{ENV_MODE}=off để tắt hẳn")
    cfile = compose_file(repo_root, rt)
    if not cfile:
        return rec(skipped=f"không khai `runtime.deploy` và không dò ra {' / '.join(COMPOSE_NAMES)} trong repo")

    started_at = datetime.now(UTC).isoformat()
    def teardown(**kw: Any) -> DeployRecord:
        """Nhánh hỏng: lấy đuôi log làm bằng chứng RỒI `down` — không bỏ lại container nửa sống (ADR-0039 §3)."""
        ok_logs, logs = _compose(run, binary, repo_root, project, cfile, "logs", "--tail", str(LOGS_TAIL))
        _compose(run, binary, repo_root, project, cfile, "down")
        return rec(started_at=started_at, compose_file=cfile, logs_tail=logs[-LOGS_MAX:] if ok_logs else "", **kw)

    ok, out = _compose(run, binary, repo_root, project, cfile, "up", "-d", timeout=UP_TIMEOUT_S)
    if not ok:
        return teardown(error=f"up -d: {out}")

    ok, out = _compose(run, binary, repo_root, project, cfile, "ps", "--format", "json")
    if not ok:
        return teardown(error=f"ps: {out}")
    rows = _services(out)
    if not rows:
        return teardown(error="ps: không có service nào đang chạy sau `up -d`")
    services = tuple(str(r.get("Service") or r.get("Name") or "?") for r in rows)
    ids = tuple(str(r.get("ID") or r.get("Name") or "")[:12] for r in rows)
    chet = [f"{s}={r.get('State') or '?'}" for s, r in zip(services, rows, strict=True)
            if str(r.get("State") or "").lower() != "running"]
    if chet:
        return teardown(services=services, container_ids=ids, error=f"ps: service không `running`: {', '.join(chet)}")

    port = _published_port(rows)
    if port is None:
        return teardown(services=services, container_ids=ids,
                        error="ps: compose không map cổng nào ra máy chủ — không có gì để probe")
    smoke = _smoke_running(rt, port)
    if not smoke["ok"]:
        return teardown(services=services, container_ids=ids, port=port, smoke=smoke,
                        error="smoke: cổng đã map không trả đúng `expect_status`")
    return rec(ok=True, services=services, container_ids=ids, port=port, started_at=started_at,
               smoke=smoke, compose_file=cfile)
