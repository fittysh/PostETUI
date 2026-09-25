"""Run-report analysis with pandas: load, summarise, trend, repeat offenders, export."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Font, PatternFill

from .catalog import Catalog
from .parser import normalize_status

TOOL_COLUMNS = ("targettool", "tool", "toolid", "toolname", "host")
STATUS_COLUMNS = ("status", "result", "comparison")
DURATION_COLUMNS = ("durationseconds", "duration", "elapsedseconds", "elapsed")
STAMP_RE = re.compile(r"_\d{8}_\d{6}$")
FILTERS: dict[str, tuple[str, ...] | None] = {
    "all": None,
    "failed": ("FAILED",),
    "skipped": ("SKIPPED",),
    "timeout": ("TIMEOUT",),
}
XLSX_FILLS = {
    "SUCCESS": "C6EFCE", "DRY-RUN": "DDEBF7", "SKIPPED": "E7E6E6",
    "WARN": "FFEB9C", "FAILED": "FFC7CE", "TIMEOUT": "E4C1F9",
}


class ReportError(Exception):
    """A report CSV cannot be read or has no status column."""


@dataclass(frozen=True)
class ReportFile:
    """A CSV written by a catalog script."""

    path: Path
    script_id: str
    modified: float

    @property
    def family(self) -> str:
        """File name without its _yyyyMMdd_HHmmss stamp, e.g. KLA_Recipe_Transfer."""
        return STAMP_RE.sub("", self.path.stem)


@dataclass(frozen=True)
class ReportSummary:
    """Summary cards for one report."""

    rows: int
    tools: int
    success_rate: float
    failed: int
    skipped: int
    timeouts: int
    avg_duration: float | None


def list_report_files(root: Path, catalog: Catalog) -> list[ReportFile]:
    """Every CSV matching a script's report_csv_glob, newest first."""
    found: dict[Path, ReportFile] = {}
    for script in catalog.scripts:
        if not script.report_csv_glob:
            continue
        for path in root.glob(script.report_csv_glob):
            if path.is_file():
                found[path] = ReportFile(path, script.id, path.stat().st_mtime)
    # Name breaks mtime ties: the _yyyyMMdd_HHmmss stamp sorts chronologically.
    return sorted(found.values(), key=lambda f: (f.modified, f.path.name), reverse=True)


def newest_since(root: Path, pattern: str | None, since: datetime) -> Path | None:
    """Newest path matching the glob that changed at or after `since` (for run summaries)."""
    if not pattern:
        return None
    cutoff = since.timestamp() - 1
    hits = [p for p in root.glob(pattern) if p.stat().st_mtime >= cutoff]
    return max(hits, key=lambda p: p.stat().st_mtime, default=None)


def _pick(columns: list[str], wanted: tuple[str, ...]) -> str | None:
    lower = {c.lower(): c for c in columns}
    return next((lower[w] for w in wanted if w in lower), None)


def load_report(path: Path) -> pd.DataFrame:
    """Read a report CSV and add _Tool, _Status (normalised) and _Duration columns."""
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError, OSError) as exc:
        raise ReportError(f"{path.name}: cannot read CSV ({exc}).") from None
    columns = list(df.columns)
    status_col = _pick(columns, STATUS_COLUMNS)
    if status_col is None:
        raise ReportError(f"{path.name}: no Status column (expected one of Status, Result, Comparison).")
    tool_col = _pick(columns, TOOL_COLUMNS)
    duration_col = _pick(columns, DURATION_COLUMNS)

    df["_Tool"] = df[tool_col] if tool_col else ""
    df["_Status"] = [normalize_status(v) or "UNKNOWN" for v in df[status_col]]
    df["_Duration"] = pd.to_numeric(df[duration_col], errors="coerce") if duration_col else float("nan")
    return df


def summarize(df: pd.DataFrame) -> ReportSummary:
    """Success rate counts every row that is not FAILED or TIMEOUT."""
    rows = len(df)
    status = df["_Status"] if rows else pd.Series(dtype=str)
    failed = int((status == "FAILED").sum())
    timeouts = int((status == "TIMEOUT").sum())
    skipped = int((status == "SKIPPED").sum())
    tools = len({t for t in df["_Tool"] if t}) if rows else 0
    durations = df["_Duration"].dropna() if rows else pd.Series(dtype=float)
    return ReportSummary(
        rows=rows,
        tools=tools,
        success_rate=100.0 * (rows - failed - timeouts) / rows if rows else 0.0,
        failed=failed,
        skipped=skipped,
        timeouts=timeouts,
        avg_duration=float(durations.mean()) if len(durations) else None,
    )


def filter_status(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """Filter by one of FILTERS: all, failed, skipped, timeout."""
    wanted = FILTERS[key]
    return df if wanted is None else df[df["_Status"].isin(wanted)]


def family_files(files: list[ReportFile], family: str) -> list[ReportFile]:
    """Files of the same family, newest first."""
    return [f for f in files if f.family == family]


def trend(files: list[ReportFile], count: int = 10) -> list[tuple[str, float]]:
    """(file name, success rate) for the last `count` runs, oldest first. Unreadable files are skipped."""
    points: list[tuple[str, float]] = []
    for report in reversed(files[:count]):
        try:
            points.append((report.path.name, summarize(load_report(report.path)).success_rate))
        except ReportError:
            continue
    return points


def repeat_offenders(files: list[ReportFile], runs: int = 5, min_failures: int = 2) -> pd.DataFrame:
    """Tools that FAILED or TIMED OUT in at least `min_failures` of the last `runs` reports."""
    counts: Counter[str] = Counter()
    read = 0
    for report in files[:runs]:
        try:
            df = load_report(report.path)
        except ReportError:
            continue
        read += 1
        bad = set(df.loc[df["_Status"].isin(["FAILED", "TIMEOUT"]), "_Tool"]) - {""}
        counts.update(bad)
    rows = [(tool, n, read) for tool, n in counts.most_common() if n >= min_failures]
    return pd.DataFrame(rows, columns=["Tool", "FailedRuns", "Runs"])


def export_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Original columns with the normalised status first as 'Result'."""
    original = [c for c in df.columns if not c.startswith("_")]
    out = df[original].copy()
    out.insert(0, "Result", df["_Status"].values)
    return out


def export_csv(df: pd.DataFrame, out_dir: Path, now: datetime | None = None) -> Path:
    """Write the current view to <out_dir>/PostETUI_export_<timestamp>.csv."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"PostETUI_export_{(now or datetime.now()):%Y%m%d_%H%M%S}.csv"
    export_frame(df).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def export_xlsx(
    df: pd.DataFrame, summary: ReportSummary, source: str, out_dir: Path, now: datetime | None = None
) -> Path:
    """Management summary workbook: a Summary sheet and a Rows sheet with a colour-coded Result column."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = now or datetime.now()
    path = out_dir / f"PostETUI_summary_{stamp:%Y%m%d_%H%M%S}.xlsx"
    cards = pd.DataFrame(
        [
            ("Source report", source),
            ("Generated", f"{stamp:%Y-%m-%d %H:%M}"),
            ("Rows", summary.rows),
            ("Tools", summary.tools),
            ("Success rate %", round(summary.success_rate, 1)),
            ("Failed", summary.failed),
            ("Skipped", summary.skipped),
            ("Timeouts", summary.timeouts),
            ("Avg duration (s)", "" if summary.avg_duration is None else round(summary.avg_duration, 1)),
        ],
        columns=["Metric", "Value"],
    )
    rows = export_frame(df)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        cards.to_excel(writer, sheet_name="Summary", index=False)
        rows.to_excel(writer, sheet_name="Rows", index=False)
        sheet = writer.sheets["Rows"]
        last = max(len(rows) + 1, 2)
        for status, colour in XLSX_FILLS.items():
            sheet.conditional_formatting.add(
                f"A2:A{last}",
                CellIsRule(operator="equal", formula=[f'"{status}"'], fill=PatternFill("solid", start_color=colour, end_color=colour)),
            )
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for column in sheet.columns:
            width = max(len(str(c.value or "")) for c in column)
            sheet.column_dimensions[column[0].column_letter].width = min(max(width + 2, 10), 60)
        writer.sheets["Summary"].column_dimensions["A"].width = 20
        writer.sheets["Summary"].column_dimensions["B"].width = 50
    return path
