"""Sandbox tiến trình cho lệnh con (ADR-0035).

Trước ADR này, "sandbox" của công ty chỉ là *đường dẫn + env*: lệnh của khách (lint/test theo stack, lệnh khởi
động trong `smoke.py` do model viết ra) chạy bằng quyền người vận hành và thấy cả `HOME`. Module này gói ba điểm
gọi subprocess đó sau một giao diện duy nhất để có thể đổi sang container mà không sửa nơi gọi.

Hai backend: `SubprocessSandbox` (giữ NGUYÊN hành vi hiện có — cùng cách cắt output, cùng timeout, cùng
`clean_env`) và `ContainerSandbox` (docker/podman `run --rm`, mạng tắt mặc định). Chọn backend bằng
`sandbox_from_config`: `COMPANY_SANDBOX` env → `cfg.sandbox` → `"auto"`. **Fail-closed**: khai đích danh
`container` mà không có binary thì `SandboxError`, không bao giờ âm thầm tụt về subprocess.

Git KHÔNG đi qua đây (xem ADR-0035): argv hard-code, hook đã bị vô hiệu, và push cần credential của người vận hành.

PR này chỉ thêm module + cấu hình; nối vào `tools.py`/`workspace.py`/`smoke.py` là PR K2.2.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from .workspace import SECRET_ENV, clean_env

if TYPE_CHECKING:  # pragma: no cover - chỉ để mypy, tránh import vòng lúc chạy
    from .llm import LLMConfig


class SandboxError(Exception):
    """Không dựng được sandbox đã yêu cầu. Cố ý là lỗi, không phải cảnh báo (fail-closed)."""


@dataclass(frozen=True)
class RunSpec:
    """Một lệnh cần chạy. `network=False` là mặc định; smoke bật `network=True` + `port` để probe được 127.0.0.1."""
    argv: list[str]
    cwd: Path
    env: dict[str, str] = field(default_factory=dict)
    timeout: float = 600.0
    network: bool = False
    port: int | None = None
    max_output: int = 6000


@dataclass(frozen=True)
class Result:
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    sandbox: str


@runtime_checkable
class Handle(Protocol):
    """Tiến trình đang chạy (cho `smoke.run_smoke`: poll trong lúc probe HTTP, giết, rồi lấy đuôi stderr)."""
    def poll(self) -> int | None: ...
    def kill(self) -> None: ...
    def stderr_tail(self, n: int) -> str: ...


class Sandbox(Protocol):
    name: str
    def run(self, spec: RunSpec) -> Result: ...
    def spawn(self, spec: RunSpec) -> Handle: ...


def sanitize_env(env: dict[str, str] | None) -> dict[str, str]:
    """Env cuối cùng của lệnh con. Lọc lại lần nữa ngay tại sandbox dù nơi gọi đã `clean_env()`: sandbox là chỗ
    cuối cùng biến môi trường đi qua, không dựa vào kỷ luật của nơi gọi."""
    base = clean_env() if env is None else dict(env)
    return {k: v for k, v in base.items() if not SECRET_ENV.search(k)} | {"PYTHONDONTWRITEBYTECODE": "1"}


class _ProcHandle:
    """Bọc `Popen` đúng vòng đời mà `smoke.py` đang dùng: poll → kill → communicate(timeout=5) → đuôi stderr."""

    def __init__(self, proc: Any):
        self.proc = proc
        self._tail = ""

    def poll(self) -> int | None:
        rc = self.proc.poll()
        return None if rc is None else int(rc)

    def kill(self) -> None:
        self.proc.kill()

    def stderr_tail(self, n: int) -> str:
        if not self._tail:
            try:
                _, err = self.proc.communicate(timeout=5)
            except (subprocess.TimeoutExpired, ValueError):
                err = ""
            self._tail = err or ""
        return self._tail[-n:]


class SubprocessSandbox:
    """Hành vi hiện tại: tiến trình con của chính người vận hành, cô lập bằng cwd + env đã lọc khoá."""

    def __init__(self, runner: Any = subprocess.run, popen: Any = subprocess.Popen):
        self.name = "subprocess"
        self._runner, self._popen = runner, popen

    def run(self, spec: RunSpec) -> Result:
        try:
            r = self._runner(spec.argv, cwd=str(spec.cwd), capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=spec.timeout, env=sanitize_env(spec.env))
        except subprocess.TimeoutExpired:
            return Result(None, "", f"quá {spec.timeout}s", True, self.name)
        return Result(int(r.returncode), (r.stdout or "")[-spec.max_output:], (r.stderr or "")[-spec.max_output:],
                      False, self.name)

    def spawn(self, spec: RunSpec) -> Handle:
        return _ProcHandle(self._popen(spec.argv, cwd=str(spec.cwd), env=sanitize_env(spec.env),
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                                       encoding="utf-8", errors="replace"))


class ContainerSandbox:
    """`docker`/`podman run --rm` với cwd mount vào `/w`, mạng tắt, hạn mức pid/cpu/ram.

    Env đi qua `--env-file -` (stdin) chứ không phải `-e`: giá trị không hiện trong danh sách tiến trình của máy."""

    def __init__(self, runtime: str, image: str, cpus: str = "2", memory: str = "2g",
                 runner: Any = subprocess.run, popen: Any = subprocess.Popen):
        self.runtime, self.image, self.cpus, self.memory = runtime, image, cpus, memory
        self._runner, self._popen = runner, popen
        self.name = f"container:{image}" + ("" if self._uid() else ":no-uid")

    @staticmethod
    def _uid() -> str | None:
        """Windows không có `os.getuid` → bỏ cờ `-u` (container chạy user mặc định của image) và nói thẳng trong
        tên sandbox để audit không tưởng là đã hạ quyền."""
        getuid, getgid = getattr(os, "getuid", None), getattr(os, "getgid", None)
        if getuid is None or getgid is None:
            return None
        return f"{getuid()}:{getgid()}"

    def _argv(self, spec: RunSpec) -> list[str]:
        base = [self.runtime, "run", "--rm", "--pids-limit", "256", "--cpus", self.cpus, "--memory", self.memory]
        uid = self._uid()
        if uid: base += ["-u", uid]
        base += ["-v", f"{spec.cwd}:/w:rw", "-w", "/w", "--env-file", "-"]
        base += (["--network", "bridge", "-p", f"127.0.0.1:{spec.port}:{spec.port}"] if spec.network
                 else ["--network", "none"])
        return [*base, self.image, *spec.argv]

    @staticmethod
    def _env_file(spec: RunSpec) -> str:
        # `--env-file -` đọc từng dòng KEY=VALUE trên stdin; giá trị nhiều dòng không hợp lệ nên bỏ.
        return "\n".join(f"{k}={v}" for k, v in sanitize_env(spec.env).items() if "\n" not in v)

    def run(self, spec: RunSpec) -> Result:
        try:
            r = self._runner(self._argv(spec), input=self._env_file(spec), capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=spec.timeout)
        except subprocess.TimeoutExpired:
            return Result(None, "", f"quá {spec.timeout}s", True, self.name)
        return Result(int(r.returncode), (r.stdout or "")[-spec.max_output:], (r.stderr or "")[-spec.max_output:],
                      False, self.name)

    def spawn(self, spec: RunSpec) -> Handle:
        proc = self._popen(self._argv(spec), stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                           stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        if proc.stdin is not None:
            proc.stdin.write(self._env_file(spec))
            proc.stdin.close()
        return _ProcHandle(proc)


def sandbox_from_config(cfg: LLMConfig, which: Any = shutil.which) -> Sandbox:
    """`COMPANY_SANDBOX` env → `cfg.sandbox` → `auto`. `auto` chọn container nếu có binary, ngược lại subprocess;
    `container` khai đích danh mà thiếu binary → `SandboxError` (fail-closed, ADR-0035)."""
    mode = os.environ.get("COMPANY_SANDBOX") or getattr(cfg, "sandbox", "") or "auto"
    runtime = os.environ.get("COMPANY_SANDBOX_RUNTIME") or getattr(cfg, "sandbox_runtime", "") or "docker"
    image = os.environ.get("COMPANY_SANDBOX_IMAGE") or getattr(cfg, "sandbox_image", "") or "python:3.12-slim"
    if mode == "subprocess":
        return SubprocessSandbox()
    if mode == "container":
        if not which(runtime):
            raise SandboxError(f"COMPANY_SANDBOX=container nhưng không tìm thấy `{runtime}` trên PATH; "
                               f"cài runtime hoặc đặt COMPANY_SANDBOX=subprocess (không tự tụt hạng bảo vệ)")
        return ContainerSandbox(runtime, image)
    if mode != "auto":
        raise SandboxError(f"chế độ sandbox không hợp lệ: {mode!r} (auto | container | subprocess)")
    return ContainerSandbox(runtime, image) if which(runtime) else SubprocessSandbox()
