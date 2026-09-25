from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest

from postetui.core.catalog import Catalog, Parameter, Script
from postetui.core.runner import (
    ArgumentError,
    ScriptRunner,
    build_argv,
    build_arguments,
    coerce_value,
    command_line,
    sanitize,
)

from .helpers import DEMO_VALUES

PS = Script(id="ps", name="PS", path="x.ps1", supports_dry_run=True, dry_run_flag="-DryRun", base_args=["-NonInteractive"],
            parameters=[Parameter(name="Recipe", type="list", required=True), Parameter(name="Source", type="string"),
                        Parameter(name="Retries", type="int", min=1, max=3), Parameter(name="Force", type="bool")])


@pytest.mark.parametrize("value", ["a;b", "a&b", "a|b", "a`b", 'a"b', "$(calc)", "a\nb"])
def test_sanitize_rejects_injection(value: str) -> None:
    with pytest.raises(ArgumentError):
        sanitize(value, "field")


def test_sanitize_allows_normal_values() -> None:
    assert sanitize("EXAMPLE_PRODUCT_RECIPE.rcp", "Recipe").endswith(".rcp")
    assert sanitize("O'Brien $name", "x") == "O'Brien $name"  # literal inside PowerShell single quotes


def test_list_values_split_trim_and_dedupe(tmp_path: Path) -> None:
    param = Parameter(name="Tools", type="list")
    assert coerce_value(param, "A, B\nC;A  D", tmp_path) == ["A", "B", "C", "D"]
    assert coerce_value(param, "", tmp_path) is None


def test_int_enum_and_path_validation(tmp_path: Path) -> None:
    number = Parameter(name="N", type="int", min=10, max=600)
    assert coerce_value(number, "60", tmp_path) == 60
    for bad in ("5", "601", "x"):
        with pytest.raises(ArgumentError):
            coerce_value(number, bad, tmp_path)
    with pytest.raises(ArgumentError, match="one of"):
        coerce_value(Parameter(name="M", type="enum", choices=["Audit", "Enable"]), "Delete", tmp_path)
    path = Parameter(name="P", type="path", must_exist=True)
    (tmp_path / "tools.txt").write_text("x")
    assert coerce_value(path, "tools.txt", tmp_path) == str(tmp_path / "tools.txt")
    with pytest.raises(ArgumentError, match="does not exist"):
        coerce_value(path, "missing.txt", tmp_path)
    assert coerce_value(path, r"\\server\share\x.txt", tmp_path)  # UNC is not probed


def test_powershell_command_is_exact_and_quoted(tmp_path: Path) -> None:
    args = build_arguments(PS, tmp_path, {"Recipe": "A.rcp, B.rcp", "Source": "O'Brien", "Retries": "2", "Force": True}, dry_run=True)
    argv = build_argv(PS, Path(r"C:\Scripts\x.ps1"), args)
    assert argv[:6] == ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command"]
    assert argv[6] == (
        "& 'C:\\Scripts\\x.ps1' -NonInteractive -Recipe 'A.rcp','B.rcp' -Source 'O''Brien' -Retries 2 -Force -DryRun; "
        "exit $LASTEXITCODE"
    )
    assert command_line(argv).startswith('powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "&')


def test_required_and_one_of_errors(demo_catalog: Catalog, demo_root: Path) -> None:
    script = demo_catalog.get("demo_kla")
    with pytest.raises(ArgumentError, match="required"):
        build_arguments(script, demo_root, {})
    with pytest.raises(ArgumentError, match="at least one of"):
        build_arguments(script, demo_root, {"Recipe": "A.rcp", "SourceTool": "T1"})


def test_rollback_arguments_skip_parameters(demo_catalog: Catalog, demo_root: Path) -> None:
    script = demo_catalog.get("demo_kla")
    args = build_arguments(script, demo_root, None, dry_run=True, extra=[("--rollback", None), ("--manifest-path", "m.csv")])
    assert args == [("--dry-run", None), ("--rollback", None), ("--manifest-path", "m.csv")]


def _runner(catalog: Catalog, root: Path, script_id: str, values: dict | None, **kwargs: object) -> ScriptRunner:
    script = catalog.get(script_id)
    args = build_arguments(script, root, values, dry_run=values is not None and script.supports_dry_run)
    argv = build_argv(script, (root / script.path).resolve(), args)
    options = {"cwd": root, "log_path": root / "Logs" / "t.log", "timeout": 60, "grace": 0.5}
    options.update(kwargs)
    return ScriptRunner(argv, script=script, **options)  # type: ignore[arg-type]


async def test_run_streams_output_and_maps_exit_code(demo_catalog: Catalog, demo_root: Path) -> None:
    lines: list[tuple[str, bool]] = []
    runner = _runner(demo_catalog, demo_root, "demo_kla", DEMO_VALUES, on_line=lambda line, err: lines.append((line, err)))
    result = await runner.run()
    assert result.status == "WARN" and result.exit_code == 1  # one UNREACHABLE tool -> exit 1 -> WARN
    assert (result.counters.processed, result.counters.ok, result.counters.failed) == (3, 2, 1)
    assert ("[WARN ] demo stderr line", True) in lines
    assert any("A tool share is unreachable" in h for h in result.hints)
    transcript = (demo_root / "Logs" / "t.log").read_text(encoding="utf-8")
    assert "TOOL-A09   UNREACHABLE" in transcript and "--- WARN" in transcript


async def test_timeout_kills_the_process(demo_catalog: Catalog, demo_root: Path) -> None:
    runner = _runner(demo_catalog, demo_root, "demo_hang", {}, timeout=1.5)
    started = time.monotonic()
    result = await runner.run()
    assert result.status == "TIMEOUT"
    assert time.monotonic() - started < 15
    assert runner.process is not None and runner.process.returncode is not None


async def test_cancel_marks_run_cancelled(demo_catalog: Catalog, demo_root: Path) -> None:
    holder: list[ScriptRunner] = []
    runner = _runner(demo_catalog, demo_root, "demo_hang", {}, on_line=lambda line, err: holder[0].cancel())
    holder.append(runner)
    result = await runner.run()
    assert result.status == "CANCELLED"
    assert result.counters.processed == 1
    assert result.error == "Cancelled by operator"


async def test_missing_interpreter_is_reported(demo_catalog: Catalog, demo_root: Path) -> None:
    runner = ScriptRunner(["definitely-not-installed-xyz.exe"], script=demo_catalog.get("demo_kla"),
                          cwd=demo_root, log_path=None, timeout=10)
    result = await runner.run()
    assert result.status == "ERROR" and "Python was not found" in (result.error or "")


@pytest.mark.skipif(os.name != "nt" or not shutil.which("powershell.exe"), reason="Windows PowerShell only")
async def test_real_powershell_receives_arrays(tmp_path: Path) -> None:
    script_path = tmp_path / "echo.ps1"
    script_path.write_text(
        "param([string[]] $Recipe, [switch] $DryRun)\n"
        "Write-Host (\"count={0} dry={1}\" -f $Recipe.Count, $DryRun)\n"
        "Write-Host '  [ 1 / 1 ] TOOL-A02   SUCCESS'\nexit 1\n",
        encoding="utf-8",
    )
    script = Script(id="echo", name="Echo", path="echo.ps1", supports_dry_run=True, dry_run_flag="-DryRun",
                    exit_codes={0: "SUCCESS", 1: "WARN"}, parameters=[Parameter(name="Recipe", type="list")])
    argv = build_argv(script, script_path, build_arguments(script, tmp_path, {"Recipe": "A.rcp,B.rcp"}, dry_run=True))
    lines: list[str] = []
    result = await ScriptRunner(argv, script=script, cwd=tmp_path, log_path=None, timeout=60,
                                on_line=lambda line, err: lines.append(line)).run()
    assert "count=2 dry=True" in lines
    assert result.status == "WARN" and result.counters.ok == 1
