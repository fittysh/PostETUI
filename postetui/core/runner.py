"""Build safe argument lists and run catalog scripts as child processes.

PowerShell scripts run through -Command, not -File: -File passes "A,B" to a
[string[]] parameter as one string, which breaks tool lists. Every value is
single-quoted (a literal in PowerShell) and screened for ; & | ` " $( first,
so user input can never become code. No shell is involved at any point.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TextIO

from .catalog import Parameter, Script
from .parser import ProgressEvent, RunCounters, hint_for, parse_progress

log = logging.getLogger(__name__)

IS_WINDOWS = os.name == "nt"
FORBIDDEN_RE = re.compile(r"[;&|`\"\r\n\x00]|\$\(")

RunStatus = Literal["SUCCESS", "WARN", "FAILED", "CANCELLED", "TIMEOUT", "ERROR"]
Mode = Literal["DRY-RUN", "APPLY", "ROLLBACK-DRY-RUN", "ROLLBACK"]
ArgValue = str | int | list[str] | None
Argument = tuple[str, ArgValue]
LineCallback = Callable[[str, bool], None]
ProgressCallback = Callable[[ProgressEvent, RunCounters], None]

DRY_MODES: tuple[Mode, ...] = ("DRY-RUN", "ROLLBACK-DRY-RUN")


class ArgumentError(ValueError):
    """A parameter value failed validation or sanitisation."""


def sanitize(value: str, field_name: str) -> str:
    """Reject characters that could chain or inject commands."""
    if FORBIDDEN_RE.search(value):
        raise ArgumentError(f"{field_name}: characters ; & | ` \" $( and line breaks are not allowed")
    return value


def is_unc(value: str) -> bool:
    """True for \\\\server\\share style paths."""
    return value.startswith(("\\\\", "//"))


def coerce_value(param: Parameter, raw: Any, root: Path) -> ArgValue | bool:
    """Validate one raw form value against its schema.

    Returns the typed value, False for an off switch, or None when the
    parameter is left out. Raises ArgumentError with a message for the form.
    """
    name = param.title
    if param.type == "bool":
        if isinstance(raw, bool):
            return raw
        return str(raw or "").strip().lower() in ("1", "true", "yes", "on")

    if param.type == "list":
        items = raw if isinstance(raw, list) else re.split(r"[,;\s]+", str(raw or ""))
        values: list[str] = []
        for item in items:
            text = str(item).strip()
            if text and text not in values:
                values.append(sanitize(text, name))
        if not values:
            if param.required:
                raise ArgumentError(f"{name} is required")
            return None
        return values

    text = "" if raw is None else str(raw).strip()
    if not text:
        if param.required:
            raise ArgumentError(f"{name} is required")
        return None
    sanitize(text, name)

    if param.type == "int":
        try:
            number = int(text)
        except ValueError:
            raise ArgumentError(f"{name} must be a whole number") from None
        if param.min is not None and number < param.min:
            raise ArgumentError(f"{name} must be at least {param.min}")
        if param.max is not None and number > param.max:
            raise ArgumentError(f"{name} must be at most {param.max}")
        return number

    if param.type == "enum":
        if text not in param.choices:
            raise ArgumentError(f"{name} must be one of: {', '.join(param.choices)}")
        return text

    if param.type == "path":
        path = Path(text)
        if not path.is_absolute():
            path = root / path
        # ponytail: UNC paths are not probed here, an unreachable share would freeze
        # the form for ~20 s. The script checks them; add an async probe if needed.
        if param.must_exist and not is_unc(text) and not path.exists():
            raise ArgumentError(f"{name}: {path} does not exist")
        return str(path)

    return text


def is_set(value: ArgValue | bool) -> bool:
    """True when a coerced value produces an argument (0 counts as set)."""
    return value is not None and value is not False


def validate_values(script: Script, root: Path, values: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Coerce every parameter. Returns (coerced, errors); errors['_form'] holds cross-field problems."""
    coerced: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for param in script.parameters:
        try:
            coerced[param.name] = coerce_value(param, values.get(param.name, param.default), root)
        except ArgumentError as exc:
            errors[param.name] = str(exc)
    for group in script.one_of_required:
        if not any(is_set(coerced.get(name)) for name in group):
            errors["_form"] = "Set at least one of: " + ", ".join(group)
    return coerced, errors


def default_flag(script: Script, name: str) -> str:
    """-Name for PowerShell, --name for Python."""
    if script.interpreter == "python":
        return "--" + name.replace("_", "-")
    return "-" + name


def build_arguments(
    script: Script,
    root: Path,
    values: Mapping[str, Any] | None,
    *,
    dry_run: bool = False,
    extra: Sequence[Argument] = (),
) -> list[Argument]:
    """Validate values and return (flag, value) pairs. value None means a bare switch.

    values=None skips the script parameters (used for rollback runs, which only
    need the rollback and manifest flags).
    """
    args: list[Argument] = [(flag, None) for flag in script.base_args]
    if values is not None:
        coerced, errors = validate_values(script, root, values)
        if errors:
            raise ArgumentError("\n".join(errors.values()))
        for param in script.parameters:
            value = coerced[param.name]
            if not is_set(value):
                continue
            args.append((param.flag or default_flag(script, param.name), None if value is True else value))
    if dry_run:
        if not script.supports_dry_run or not script.dry_run_flag:
            raise ArgumentError(f"{script.name} has no dry-run mode")
        args.append((script.dry_run_flag, None))
    for flag, value in extra:
        args.append((flag, sanitize(value, flag) if isinstance(value, str) else value))
    return args


def ps_quote(text: str) -> str:
    """PowerShell single-quoted literal."""
    return "'" + text.replace("'", "''") + "'"


def argument_tokens(script: Script, args: Sequence[Argument]) -> list[str]:
    """Render arguments as tokens for the script's interpreter."""
    tokens: list[str] = []
    for flag, value in args:
        tokens.append(flag)
        if value is None:
            continue
        if script.interpreter == "python":
            tokens.append(",".join(value) if isinstance(value, list) else str(value))
        elif isinstance(value, list):
            tokens.append(",".join(ps_quote(v) for v in value))
        elif isinstance(value, int) and not isinstance(value, bool):
            tokens.append(str(value))
        else:
            tokens.append(ps_quote(str(value)))
    return tokens


def interpreter_executable(script: Script) -> str:
    """Executable for the script's interpreter."""
    if script.interpreter == "powershell":
        return "powershell.exe"
    if script.interpreter == "pwsh":
        return "pwsh.exe" if IS_WINDOWS else "pwsh"
    if not getattr(sys, "frozen", False):
        return sys.executable
    return shutil.which("python") or shutil.which("py") or "python"


def build_argv(script: Script, script_path: Path, args: Sequence[Argument]) -> list[str]:
    """Full argument vector, passed to the OS as a list (no shell)."""
    tokens = argument_tokens(script, args)
    exe = interpreter_executable(script)
    if script.interpreter == "python":
        return [exe, "-u", str(script_path), *tokens]
    command = " ".join(["&", ps_quote(str(script_path)), *tokens]) + "; exit $LASTEXITCODE"
    return [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command]


def command_line(argv: Sequence[str]) -> str:
    """The exact command line Windows receives for this argv."""
    return subprocess.list2cmdline(list(argv))


def transcript_path(logs_dir: Path, script_id: str, started: datetime) -> Path:
    """<logs>/PostETUI_<script>_<yyyyMMdd_HHmmss>.log"""
    return logs_dir / f"PostETUI_{script_id}_{started:%Y%m%d_%H%M%S}.log"


def console_encoding() -> str:
    """PowerShell writes redirected output in the OEM code page on Windows."""
    return "oem" if IS_WINDOWS else "utf-8"


async def run_capture(argv: Sequence[str], timeout: float = 20) -> str | None:
    """Run a short probe command and return its stdout, or None on any failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
        )
    except OSError:
        return None
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        proc.kill()
        return None
    return out.decode(console_encoding(), errors="replace").strip() if proc.returncode == 0 else None


_NOT_FOUND = {
    "powershell": "powershell.exe was not found. Windows PowerShell 5.1 ships with Windows 10/11; check PATH.",
    "pwsh": "pwsh.exe was not found. Install PowerShell 7 or set interpreter: powershell in catalog.yaml.",
    "python": "Python was not found. Install Python 3.11+ (winget install Python.Python.3.12) for Python scripts.",
}


@dataclass
class RunResult:
    """Outcome of one run."""

    status: RunStatus
    exit_code: int | None
    elapsed: float
    counters: RunCounters
    log_path: Path | None
    started: datetime
    hints: list[str] = field(default_factory=list)
    error: str | None = None


class ScriptRunner:
    """Runs one child process, streams its output, and handles cancel and timeout.

    run() never raises: every failure becomes a RunResult with status ERROR.
    """

    def __init__(
        self,
        argv: Sequence[str],
        *,
        script: Script,
        cwd: Path,
        log_path: Path | None,
        timeout: float,
        grace: float = 5.0,
        header: str = "",
        on_line: LineCallback | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self.argv = list(argv)
        self.script = script
        self.cwd = cwd
        self.log_path = log_path
        self.timeout = timeout
        self.grace = grace
        self.header = header
        self.on_line = on_line
        self.on_progress = on_progress
        self.counters = RunCounters()
        self.hints: list[str] = []
        self._cancel = asyncio.Event()
        self._log: TextIO | None = None
        self._pattern = script.progress_pattern
        self.process: asyncio.subprocess.Process | None = None

    def cancel(self) -> None:
        """Request cancellation. The process tree is stopped by run()."""
        self._cancel.set()

    def kill_now(self) -> None:
        """Synchronous hard kill of the process tree, for when the app exits mid-run."""
        proc = self.process
        if proc is None or proc.returncode is not None:
            return
        if IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            proc.kill()

    async def run(self) -> RunResult:
        """Start the process and wait for exit, cancel or timeout."""
        started = datetime.now()
        t0 = time.monotonic()
        try:
            status, code, error = await self._run()
        except Exception as exc:  # the TUI must survive anything a script does
            log.exception("runner crashed")
            status, code, error = "ERROR", None, f"Internal runner error: {exc}"
        elapsed = time.monotonic() - t0
        self._write(f"--- {status}  exit={code}  elapsed={elapsed:.1f}s")
        if error:
            self._write(f"--- {error}")
        if self._log:
            self._log.close()
        return RunResult(status, code, elapsed, self.counters, self.log_path, started, self.hints, error)

    async def _run(self) -> tuple[RunStatus, int | None, str | None]:
        self._open_log()
        self._write(self.header + "\n--- " + command_line(self.argv))
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        flags = 0
        if IS_WINDOWS:
            # No console for the child: it cannot draw over the TUI or wait on a prompt.
            flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            proc = await asyncio.create_subprocess_exec(
                *self.argv,
                cwd=str(self.cwd),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                creationflags=flags,
                limit=1 << 20,
            )
        except FileNotFoundError:
            return "ERROR", None, _NOT_FOUND[self.script.interpreter]
        except OSError as exc:
            return "ERROR", None, f"Cannot start {self.argv[0]}: {exc}"
        self.process = proc

        encoding = console_encoding() if self.script.interpreter != "python" else "utf-8"
        pump = asyncio.create_task(self._pump(proc, encoding))
        cancel = asyncio.create_task(self._cancel.wait())
        done, _ = await asyncio.wait({pump, cancel}, timeout=self.timeout, return_when=asyncio.FIRST_COMPLETED)
        cancel.cancel()

        if pump in done:
            code = proc.returncode
            return self.script.exit_status(code), code, None

        status: RunStatus = "CANCELLED" if cancel in done else "TIMEOUT"
        await self._stop(proc)
        try:
            await asyncio.wait_for(pump, 10)
        except TimeoutError:
            pump.cancel()
        reason = "Cancelled by operator" if status == "CANCELLED" else f"Timed out after {self.timeout:.0f}s"
        return status, proc.returncode, reason

    async def _pump(self, proc: asyncio.subprocess.Process, encoding: str) -> None:
        async def read(stream: asyncio.StreamReader, is_err: bool) -> None:
            while True:
                try:
                    raw = await stream.readline()
                except ValueError:  # line longer than the buffer limit
                    raw = await stream.read(1 << 20)
                if not raw:
                    return
                self._handle(raw.decode(encoding, errors="replace").rstrip("\r\n"), is_err)

        assert proc.stdout and proc.stderr
        await asyncio.gather(read(proc.stdout, False), read(proc.stderr, True))
        await proc.wait()

    def _handle(self, line: str, is_err: bool) -> None:
        self._write(("[stderr] " if is_err else "") + line)
        hint = hint_for(line)
        if hint and hint not in self.hints:
            self.hints.append(hint)
        event = parse_progress(line, self._pattern)
        try:
            if self.on_line:
                self.on_line(line, is_err)
            if event:
                self.counters.add(event.status)
                if self.on_progress:
                    self.on_progress(event, self.counters)
        except Exception:
            log.exception("output callback failed")

    async def _stop(self, proc: asyncio.subprocess.Process) -> None:
        """Ask the process tree to stop, then hard-kill it after the grace period."""
        if proc.returncode is not None:
            return
        await self._kill(proc, force=False)
        try:
            await asyncio.wait_for(proc.wait(), self.grace)
            return
        except TimeoutError:
            pass
        await self._kill(proc, force=True)
        try:
            await asyncio.wait_for(proc.wait(), 10)
        except TimeoutError:
            log.error("process %s did not exit after kill", proc.pid)

    @staticmethod
    async def _kill(proc: asyncio.subprocess.Process, *, force: bool) -> None:
        if not IS_WINDOWS:
            proc.kill() if force else proc.terminate()
            return
        # /T takes the whole tree (e.g. robocopy started by the script).
        args = ["taskkill", "/PID", str(proc.pid), "/T"] + (["/F"] if force else [])
        try:
            killer = await asyncio.create_subprocess_exec(
                *args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            await killer.wait()
        except OSError:
            proc.kill()

    def _open_log(self) -> None:
        if not self.log_path:
            return
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log = self.log_path.open("w", encoding="utf-8")
        except OSError as exc:
            self.hints.append(f"Transcript not saved ({exc}).")
            self.log_path = None

    def _write(self, text: str) -> None:
        if not self._log:
            return
        try:
            self._log.write(text + "\n")
        except OSError as exc:
            self.hints.append(f"Transcript stopped: {exc} (disk full?).")
            self._log.close()
            self._log = None
