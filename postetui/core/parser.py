"""Turn raw script output into statuses, progress events and operator hints."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Order matters: "UNREACHABLE" must hit FAILED before "REACHABLE" hits SUCCESS,
# "NOT EXIST" must hit WARN before "EXIST" hits SUCCESS.
_STATUS_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"TIME\s?OUT|TIMED OUT", re.I), "TIMEOUT"),
    (re.compile(r"CANCEL", re.I), "CANCELLED"),
    (re.compile(r"FAIL|ERROR|UNREACHABLE|DENIED|MISMATCH|BLOCKED|ABORT", re.I), "FAILED"),
    (re.compile(r"WOULD|DRY.?RUN|SIMULAT", re.I), "DRY-RUN"),
    (re.compile(r"SKIP|IDENTICAL|NO-ROLLBACK|UNCHANGED|\bN/A\b", re.I), "SKIPPED"),
    (re.compile(r"WARN|MISSING|NOT EXIST|PARTIAL", re.I), "WARN"),
    (re.compile(r"SUCCESS|\bOK\b|RESTORED|PRESENT|REACHABLE|COPIED|VERIFIED|\bEXISTS?\b|\bDONE\b|\bPASS", re.I), "SUCCESS"),
]

# Matches "14/34  TOOL-A03  SUCCESS" and KLA_Recipe_Proliferate's "[ 3 / 10 ] TOOL-A02   REACHABLE".
DEFAULT_PROGRESS_RE = re.compile(
    r"^\s*\[?\s*(?P<idx>\d+)\s*/\s*(?P<total>\d+)\s*\]?\s+(?P<tool>[A-Za-z0-9._-]+)(?:\s+(?P<status>.*?))?\s*$"
)

_HINTS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"running scripts is disabled|cannot be loaded because|is not digitally signed", re.I),
        "Execution policy blocked the script. Ask IT to allow RemoteSigned on this PC, or have the script signed.",
    ),
    (
        re.compile(r"network path was not found|network name cannot be found|Path not accessible|UNREACHABLE", re.I),
        "A tool share is unreachable. Check the tool is on and \\\\<tool>\\C opens in Explorer.",
    ),
    (
        re.compile(r"access (is )?denied|unauthorized", re.I),
        "Access denied. Your Windows account needs write access to the tool share.",
    ),
    (
        re.compile(r"being used by another process|file is locked", re.I),
        "A file is locked by another program (often Excel). Close it and run again.",
    ),
    (
        re.compile(r"not enough space|disk (is )?full", re.I),
        "Disk full. Free space on the drive named in the log and run again.",
    ),
]


def normalize_status(text: str) -> str:
    """Map any status word or log line to SUCCESS/WARN/SKIPPED/FAILED/TIMEOUT/DRY-RUN/CANCELLED, or ''."""
    for pattern, status in _STATUS_RULES:
        if pattern.search(text):
            return status
    return ""


def hint_for(line: str) -> str | None:
    """Actionable advice for a recognised error line, else None."""
    for pattern, hint in _HINTS:
        if pattern.search(line):
            return hint
    return None


@dataclass(frozen=True)
class ProgressEvent:
    """One recognised progress line."""

    index: int
    total: int
    tool: str
    status: str
    raw_status: str


def parse_progress(line: str, pattern: re.Pattern[str] | None = None) -> ProgressEvent | None:
    """Parse a progress line. Needs named groups idx and total; tool and status are optional."""
    match = (pattern or DEFAULT_PROGRESS_RE).search(line)
    if not match:
        return None
    groups = match.groupdict()
    try:
        index, total = int(groups["idx"]), int(groups["total"])
    except (KeyError, TypeError, ValueError):
        return None
    raw_status = (groups.get("status") or "").strip()
    return ProgressEvent(index, total, groups.get("tool") or "", normalize_status(raw_status), raw_status)


@dataclass
class RunCounters:
    """Live Processed / OK / Warn / Skipped / Failed / Timeout counters."""

    processed: int = 0
    ok: int = 0
    warn: int = 0
    skipped: int = 0
    failed: int = 0
    timeout: int = 0

    def add(self, status: str) -> None:
        """Count one progress event. Events without a status are ignored."""
        if not status:
            return
        self.processed += 1
        if status in ("SUCCESS", "DRY-RUN"):
            self.ok += 1
        elif status == "WARN":
            self.warn += 1
        elif status == "SKIPPED":
            self.skipped += 1
        elif status == "TIMEOUT":
            self.timeout += 1
        else:
            self.failed += 1
