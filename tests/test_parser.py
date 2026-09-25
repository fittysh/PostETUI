from __future__ import annotations

import re

import pytest

from postetui.core.parser import RunCounters, hint_for, normalize_status, parse_progress


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("SUCCESS", "SUCCESS"),
        ("RESTORED", "SUCCESS"),
        ("REACHABLE", "SUCCESS"),
        ("UNREACHABLE", "FAILED"),
        ("ACCESS DENIED", "FAILED"),
        ("VERIFY FAILED", "FAILED"),
        ("NOT EXIST", "WARN"),
        ("RECIPE MISSING", "WARN"),
        ("IDENTICAL", "SKIPPED"),
        ("NO-ROLLBACK", "SKIPPED"),
        ("WOULD RESTORE", "DRY-RUN"),
        ("TIMEOUT", "TIMEOUT"),
        ("2026-09-25 10:00:00 [ERROR] Failed to stage", "FAILED"),
        ("Source path : \\\\TOOL-A01\\C\\recipes", ""),
    ],
)
def test_normalize_status(text: str, expected: str) -> None:
    assert normalize_status(text) == expected


def test_parses_kla_progress_line() -> None:
    event = parse_progress("  [ 3 / 10 ] TOOL-A02   REACHABLE")
    assert event is not None
    assert (event.index, event.total, event.tool, event.status) == (3, 10, "TOOL-A02", "SUCCESS")


def test_parses_spec_progress_line() -> None:
    event = parse_progress("14/34  TOOL-A03  SUCCESS")
    assert event is not None and (event.index, event.total, event.status) == (14, 34, "SUCCESS")


@pytest.mark.parametrize(
    "line",
    ["2026-09-25 14:02:11 [INFO ] Tools file : C:\\x", "Loaded 2/3 entries", "09/25/2026 14:02 start", ""],
)
def test_ignores_non_progress_lines(line: str) -> None:
    assert parse_progress(line) is None


def test_custom_regex_with_named_groups() -> None:
    pattern = re.compile(r"^TOOL (?P<tool>\S+) (?P<idx>\d+) of (?P<total>\d+): (?P<status>\w+)$")
    event = parse_progress("TOOL KLAT-1 2 of 5: FAILED", pattern)
    assert event is not None and (event.index, event.total, event.status) == (2, 5, "FAILED")


def test_counters() -> None:
    counters = RunCounters()
    for status in ["SUCCESS", "DRY-RUN", "WARN", "SKIPPED", "FAILED", "TIMEOUT", ""]:
        counters.add(status)
    assert (counters.processed, counters.ok, counters.warn, counters.skipped, counters.failed, counters.timeout) == (6, 2, 1, 1, 1, 1)


def test_hints_are_actionable() -> None:
    hint = hint_for("File C:\\x.ps1 cannot be loaded because running scripts is disabled on this system.")
    assert hint is not None and "Execution policy" in hint
    assert "locked" in (hint_for("The process cannot access the file because it is being used by another process.") or "")
    assert hint_for("all good") is None
