"""Reports tab: summary cards, per-tool rows, trend sparkline, repeat offenders, exports."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Sparkline, Static

from ..core.reports import (
    ReportError,
    ReportFile,
    export_csv,
    export_xlsx,
    family_files,
    filter_status,
    list_report_files,
    load_report,
    repeat_offenders,
    summarize,
    trend,
)
from ..theme import MUTED, status_text

if TYPE_CHECKING:
    from ..app import PostETUIApp

CARDS = [
    ("tools", "Total tools"),
    ("rate", "Success rate"),
    ("failed", "Failures"),
    ("duration", "Avg duration"),
    ("timeouts", "Timeouts"),
]


class FilesTable(DataTable[object]):
    """Report file list; the footer reads "Enter Load"."""

    BINDINGS = [Binding("enter", "select_cursor", "Load")]


class ReportsPane(Vertical):
    """Data analyst view of the CSV reports written by the scripts."""

    BINDINGS = [
        # 1-4 and s are listed in the Rows panel subtitle to keep the footer short.
        Binding("1", "filter('all')", "All", show=False),
        Binding("2", "filter('failed')", "Failed", show=False),
        Binding("3", "filter('skipped')", "Skipped", show=False),
        Binding("4", "filter('timeout')", "Timeout", show=False),
        Binding("s", "sort", "Sort", show=False),
        Binding("e", "export_csv", "Export CSV"),
        Binding("x", "export_xlsx", "Export XLSX"),
        Binding("r", "reload", "Reload", show=False),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.files: list[ReportFile] = []
        self.current: ReportFile | None = None
        self.df: pd.DataFrame | None = None
        self.view: pd.DataFrame | None = None
        self.filter_key = "all"
        self.sort_column: str | None = None

    @property
    def tui(self) -> PostETUIApp:
        return cast("PostETUIApp", self.app)

    def compose(self) -> ComposeResult:
        with Horizontal(id="cards"):
            for key, title in CARDS:
                card = Static("-", id=f"card-{key}", classes="card")
                card.border_title = title
                yield card
        with Horizontal(id="rep-body"):
            with Vertical(id="rep-left"):
                files = FilesTable(id="files", cursor_type="row", classes="panel")
                files.border_title = "|Report Files|"
                yield files
                with Vertical(id="trend", classes="panel") as box:
                    box.border_title = "|Trend - success %|"
                    yield Sparkline([], id="spark")
                    yield Static("", id="trend-label")
            with Vertical(id="rep-right"):
                rows = DataTable(id="rows", cursor_type="row", zebra_stripes=True, classes="panel")
                rows.border_title = "|Rows - all|"
                yield rows
                offenders = DataTable(id="offenders", cursor_type="row", classes="panel")
                offenders.border_title = "|Repeat Offenders - last 5 runs|"
                yield offenders

    def on_mount(self) -> None:
        self.query_one("#files", DataTable).add_columns("Report", "Script", "Modified")
        self.query_one("#offenders", DataTable).add_columns("Tool", "Failed runs", "Runs")
        self.reload()

    def reload(self, select: Path | None = None) -> None:
        """Rescan report files; load `select`, else keep the current file, else the newest."""
        self.files = list_report_files(self.tui.root, self.tui.catalog)
        table = self.query_one("#files", DataTable)
        table.clear()
        for report in self.files:
            table.add_row(
                report.path.name,
                report.script_id,
                datetime.fromtimestamp(report.modified).strftime("%m-%d %H:%M"),
                key=str(report.path),
            )
        wanted = select or (self.current.path if self.current else None)
        target = next((f for f in self.files if f.path == wanted), self.files[0] if self.files else None)
        if target is None:
            self.clear_report("No report CSVs yet. They appear here after a script writes one.")
            return
        table.move_cursor(row=self.files.index(target))
        self.load(target)

    def clear_report(self, message: str) -> None:
        self.current, self.df, self.view = None, None, None
        for key, _ in CARDS:
            self.query_one(f"#card-{key}", Static).update("-")
        rows = self.query_one("#rows", DataTable)
        rows.clear(columns=True)
        rows.border_title = "|Rows|"
        rows.border_subtitle = message
        self.query_one("#offenders", DataTable).clear()
        self.query_one("#spark", Sparkline).data = []
        self.query_one("#trend-label", Static).update("")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id != "files" or event.row_key.value is None:
            return
        event.stop()
        path = Path(str(event.row_key.value))
        report = next((f for f in self.files if f.path == path), None)
        if report:
            self.load(report)

    def load(self, report: ReportFile) -> None:
        """Load one CSV and refresh cards, rows, trend and offenders."""
        try:
            df = load_report(report.path)
        except ReportError as exc:
            self.clear_report(str(exc))
            self.notify(str(exc), title="Report not loaded", severity="error")
            return
        self.current, self.df = report, df

        summary = summarize(df)
        cards = {
            "tools": str(summary.tools),
            "rate": f"{summary.success_rate:.1f} %",
            "failed": str(summary.failed),
            "duration": "-" if summary.avg_duration is None else f"{summary.avg_duration:.1f} s",
            "timeouts": str(summary.timeouts),
        }
        for key, value in cards.items():
            self.query_one(f"#card-{key}", Static).update(value)

        family = family_files(self.files, report.family)
        points = trend(family, 10)
        self.query_one("#spark", Sparkline).data = [rate for _, rate in points]
        label = f"{len(points)} run(s) of {report.family}"
        if points:
            label += f"\nlatest {points[-1][1]:.0f} %  |  min {min(p[1] for p in points):.0f} %"
        self.query_one("#trend-label", Static).update(Text(label, style=MUTED))

        offenders = self.query_one("#offenders", DataTable)
        offenders.clear()
        for row in repeat_offenders(family).itertuples(index=False):
            offenders.add_row(row.Tool, str(row.FailedRuns), str(row.Runs))
        self.apply_view()

    def apply_view(self) -> None:
        """Filter + sort the loaded report into the Rows table."""
        if self.df is None:
            return
        view = filter_status(self.df, self.filter_key)
        if self.sort_column:
            view = view.sort_values(self.sort_column, kind="stable")
        self.view = view
        columns = ["_Status"] + [c for c in view.columns if not c.startswith("_")]
        table = self.query_one("#rows", DataTable)
        table.clear(columns=True)
        for column in columns:
            table.add_column("Result" if column == "_Status" else column, key=column)
        for values in view[columns].itertuples(index=False):
            table.add_row(status_text(values[0]), *[str(v) for v in values[1:]])
        sort = f", sorted by {self.sort_column}" if self.sort_column else ""
        table.border_title = f"|Rows - {self.filter_key} ({len(view)} of {len(self.df)}){sort}|"
        table.border_subtitle = "1 all  2 failed  3 skipped  4 timeout  s sort  r reload"

    def action_filter(self, key: str) -> None:
        self.filter_key = key
        self.apply_view()

    def action_sort(self) -> None:
        """Cycle the sort column through Result and the CSV columns."""
        if self.df is None:
            return
        columns = ["_Status"] + [c for c in self.df.columns if not c.startswith("_")]
        index = columns.index(self.sort_column) + 1 if self.sort_column in columns else 0
        self.sort_column = columns[index] if index < len(columns) else None
        self.apply_view()

    def action_reload(self) -> None:
        self.reload()

    def action_export_csv(self) -> None:
        if self.view is None:
            self.notify("Load a report first.", severity="warning")
            return
        try:
            path = export_csv(self.view, self.tui.root / "Reports")
        except OSError as exc:
            self.notify(f"Export failed: {exc}", severity="error")
            return
        self.notify(str(path), title="Filtered view exported")

    def action_export_xlsx(self) -> None:
        if self.df is None or self.current is None:
            self.notify("Load a report first.", severity="warning")
            return
        try:
            path = export_xlsx(self.df, summarize(self.df), self.current.path.name, self.tui.root / "Reports")
        except OSError as exc:
            self.notify(f"Export failed: {exc} (file open in Excel?)", severity="error")
            return
        self.notify(str(path), title="Management summary exported")
