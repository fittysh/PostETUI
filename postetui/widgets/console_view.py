"""Output tab: live console, progress bar, counters, and the Run Summary box."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.timer import Timer
from textual.widgets import ProgressBar, RichLog, Static

from ..core.catalog import Script
from ..core.parser import ProgressEvent, RunCounters, normalize_status
from ..core.runner import RunResult
from ..theme import MUTED, RED, TEAL, status_color, status_text

if TYPE_CHECKING:
    from ..app import PostETUIApp


@dataclass
class RunArtifacts:
    """Files a finished run left behind, for the summary box."""

    csv: Path | None
    backup: Path | None
    rollback_command: str
    warnings: list[str]


def _clock(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def counters_text(counters: RunCounters) -> Text:
    """Processed / OK / Warn / Skipped / Failed / Timeout strip."""
    text = Text()
    parts = [
        ("Processed", counters.processed, "white"),
        ("OK", counters.ok, status_color("SUCCESS")),
        ("Warn", counters.warn, status_color("WARN")),
        ("Skipped", counters.skipped, status_color("SKIPPED")),
        ("Failed", counters.failed, status_color("FAILED")),
        ("Timeout", counters.timeout, status_color("TIMEOUT")),
    ]
    for i, (label, value, colour) in enumerate(parts):
        if i:
            text.append("   ")
        text.append(f"{label} ", style=MUTED)
        text.append(str(value), style=f"bold {colour}")
    return text


class OutputPane(Vertical):
    """Streams the running script. k cancels, a toggles auto-scroll."""

    BINDINGS = [
        Binding("k", "cancel", "Cancel run"),
        Binding("a", "autoscroll", "Auto-scroll"),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.script: Script | None = None
        self.mode = ""
        self.status = "IDLE"
        self.started = 0.0
        self.elapsed = 0.0
        self._timer: Timer | None = None

    @property
    def tui(self) -> PostETUIApp:
        return cast("PostETUIApp", self.app)

    def compose(self) -> ComposeResult:
        yield Static("No run yet. Pick a script and press d for a dry-run.", id="out-head")
        with Horizontal(id="out-bar"):
            yield ProgressBar(total=None, show_eta=False, id="progress")
        yield Static(counters_text(RunCounters()), id="out-counters")
        console = RichLog(id="console", max_lines=20000, wrap=False, markup=False, highlight=False, classes="panel")
        console.border_title = "|Console|"
        yield console
        summary = Static("", id="summary", classes="panel")
        summary.border_title = "|Run Summary|"
        yield summary

    @property
    def console(self) -> RichLog:
        return self.query_one("#console", RichLog)

    def begin(self, script: Script, mode: str, command: str) -> None:
        """Reset everything for a new run."""
        self.script, self.mode, self.status = script, mode, "RUNNING"
        self.started, self.elapsed = time.monotonic(), 0.0
        self.console.clear()
        self.console.auto_scroll = True
        self.console.write(Text("> " + command, style=MUTED))
        self.query_one("#progress", ProgressBar).update(total=None, progress=0)
        self.query_one("#out-counters", Static).update(counters_text(RunCounters()))
        self.query_one("#summary", Static).remove_class("-shown")
        if self._timer:
            self._timer.stop()
        self._timer = self.set_interval(1, self.tick)
        self.render_head()

    def tick(self) -> None:
        """Advance the elapsed clock while running."""
        self.elapsed = time.monotonic() - self.started
        self.render_head()

    def render_head(self) -> None:
        """Script, mode, status, elapsed and the follow-tail indicator."""
        if self.script is None:
            return
        following = self.console.auto_scroll
        on, off = ("\u25cf following", "\u25cb paused") if self.tui.unicode else ("[following]", "[paused]")
        text = Text(self.script.name, style="bold white")
        text.append("   ")
        text.append(self.mode, style=f"bold {status_color(self.mode)}")
        text.append("   ")
        text.append(self.status, style=f"bold {status_color(self.status)}")
        text.append(f"   {_clock(self.elapsed)}   ", style=MUTED)
        text.append(on if following else off, style=TEAL if following else MUTED)
        self.query_one("#out-head", Static).update(text)

    def write_line(self, line: str, is_err: bool) -> None:
        """Append one output line, coloured by the status word it contains."""
        status = normalize_status(line)
        style = RED if is_err else (status_color(status) if status else "")
        self.console.write(Text(line, style=style))

    def progress(self, event: ProgressEvent, counters: RunCounters) -> None:
        """Move the bar and refresh the counters."""
        self.query_one("#progress", ProgressBar).update(total=max(event.total, 1), progress=min(event.index, event.total))
        self.query_one("#out-counters", Static).update(counters_text(counters))

    def finish(self, result: RunResult, artifacts: RunArtifacts) -> None:
        """Stop the clock and show the Run Summary box."""
        if self._timer:
            self._timer.stop()
            self._timer = None
        self.status, self.elapsed = result.status, result.elapsed
        self.render_head()
        self.query_one("#out-counters", Static).update(counters_text(result.counters))
        bar = self.query_one("#progress", ProgressBar)
        if bar.total is None:
            bar.update(total=1, progress=1 if result.status in ("SUCCESS", "WARN") else 0)

        grid = Table.grid(padding=(0, 2))
        grid.add_column(style=f"bold {MUTED}", no_wrap=True)
        grid.add_column(overflow="fold")
        headline = status_text(result.status)
        headline.append(f"   exit code {result.exit_code if result.exit_code is not None else '-'}", style="white")
        headline.append(f"   elapsed {_clock(result.elapsed)}", style="white")
        grid.add_row("Result", headline)
        grid.add_row("Counters", counters_text(result.counters))
        grid.add_row("Log file", str(result.log_path or "not saved"))
        grid.add_row("CSV report", str(artifacts.csv or "-"))
        grid.add_row("Backup set", str(artifacts.backup or "-"))
        if artifacts.rollback_command:
            grid.add_row("Rollback", Text(artifacts.rollback_command, style=TEAL))
        if result.error:
            grid.add_row("Error", Text(result.error, style=f"bold {RED}"))
        for hint in result.hints:
            grid.add_row("Hint", Text(hint, style=status_color("WARN")))
        for warning in artifacts.warnings:
            grid.add_row("Warning", Text(warning, style=status_color("WARN")))
        summary = self.query_one("#summary", Static)
        summary.update(grid)
        summary.add_class("-shown")

    def action_cancel(self) -> None:
        self.tui.cancel_run()

    def action_autoscroll(self) -> None:
        console = self.console
        console.auto_scroll = not console.auto_scroll
        if console.auto_scroll:
            console.scroll_end(animate=False)
        self.render_head()
