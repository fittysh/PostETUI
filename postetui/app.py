"""PostETUIApp: top tab bar, five tabs, global keys, and the run lifecycle."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import ContentSwitcher, Footer, Static, Tab, Tabs

from .core.audit import AuditRecord, append_audit, current_host, current_user, new_run_id
from .core.backups import BackupSet
from .core.catalog import Catalog, CatalogError, Integrity, Script, check_integrity, preflight, resolve_script_path
from .core.reports import newest_since
from .core.runner import (
    IS_WINDOWS,
    DRY_MODES,
    Argument,
    ArgumentError,
    Mode,
    ScriptRunner,
    argument_tokens,
    build_argv,
    build_arguments,
    command_line,
    ps_quote,
    run_capture,
    transcript_path,
    validate_values,
)
from .core.state import RecentRun, load_state, save_state
from .theme import APP_LABEL, CSS, THEME
from .widgets.banner import EnvironmentBox
from .widgets.catalog_table import ScriptsPane
from .widgets.console_view import OutputPane, RunArtifacts
from .widgets.param_form import RunPane
from .widgets.report_table import ReportsPane
from .widgets.rollback_list import RollbackPane

MIN_WIDTH, MIN_HEIGHT = 100, 30
TABS = [("scripts", "Scripts"), ("run", "Run"), ("output", "Output"), ("reports", "Reports"), ("rollback", "Rollback")]
FOCUS_TARGET = {"scripts": "#catalog", "run": "#run", "output": "#console", "reports": "#files", "rollback": "#sets"}


def count_list_file(path: Path) -> int | None:
    """Entries in a tools.txt-style file (blank and # lines ignored), or None if unreadable."""
    try:
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return None
    return sum(1 for line in lines if line.strip() and not line.lstrip().startswith("#"))


class MainScreen(Screen[None]):
    """Default screen. Resize events arrive at screens, not the App."""

    def on_resize(self) -> None:
        cast("PostETUIApp", self.app).check_size()


class TooSmallScreen(Screen[None]):
    """Shown instead of a broken layout while the terminal is under 100 x 30."""

    def compose(self) -> ComposeResult:
        yield Static("", id="too-small")

    def on_mount(self) -> None:
        self.show_size(*self.app.size)

    def on_resize(self) -> None:
        cast("PostETUIApp", self.app).check_size()

    def show_size(self, width: int, height: int) -> None:
        self.query_one("#too-small", Static).update(
            f"[b]Please enlarge the terminal.[/b]\n\n"
            f"PostETUI needs at least {MIN_WIDTH} x {MIN_HEIGHT}.\nCurrent size: {width} x {height}.\n\n"
            "Maximise the window or reduce the font size."
        )


class PostETUIApp(App[None]):
    """Launcher + viewer. Never embeds or rewrites the scripts' business logic."""

    CSS = CSS
    TITLE = "PostETUI"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("tab", "next_tab", "Next", priority=True, key_display="Tab"),
        Binding("shift+tab", "prev_tab", "Prev", priority=True, show=False),
        *[Binding(str(i + 1), f"goto('{tab_id}')", title, show=False) for i, (tab_id, title) in enumerate(TABS)],
        Binding("d", "dry_run", "Dry-Run"),
        Binding("o", "open_docs", "Docs"),
        Binding("backspace", "back", "Back", key_display="Bksp"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        root: Path,
        catalog: Catalog,
        catalog_path: Path,
        *,
        unicode: bool = True,
        state_file: Path | None = None,
    ) -> None:
        self.unicode = unicode  # read by get_css_variables() during App.__init__
        super().__init__()
        self.root = root.resolve()
        self.catalog = catalog
        self.catalog_path = catalog_path
        self.state_file = state_file
        self.state = load_state(state_file)
        self.logs_dir = self.root / catalog.settings.logs_dir
        self.current_script: Script | None = catalog.scripts[0] if catalog.scripts else None
        self.overrides: set[str] = set()
        self.rollback_dry_ok: set[Path] = set()
        self.runner: ScriptRunner | None = None
        self.ps_version = "detecting..."
        self._integrity: dict[str, tuple[float | None, Integrity]] = {}
        self._signatures: dict[tuple[str, float], str] = {}
        self._history: list[str] = ["scripts"]
        self._going_back = False
        self._too_small: TooSmallScreen | None = None

    # ------------------------------------------------------------------ layout

    def get_css_variables(self) -> dict[str, str]:
        box = "round" if self.unicode else "ascii"
        strong = "heavy" if self.unicode else "ascii"
        return {**super().get_css_variables(), "box": box, "box-strong": strong}

    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar") as bar:
            bar.border_title = APP_LABEL
            tabs = Tabs(*[Tab(title, id=f"tab-{tab_id}") for tab_id, title in TABS], id="tabs")
            tabs.can_focus = False
            yield tabs
            yield Static(self._short_root(), id="ctx-path")
        with ContentSwitcher(id="main", initial="scripts"):
            yield ScriptsPane(id="scripts")
            yield RunPane(id="run")
            yield OutputPane(id="output")
            yield ReportsPane(id="reports")
            yield RollbackPane(id="rollback")
        yield Footer()

    def on_mount(self) -> None:
        self.register_theme(THEME)
        self.theme = THEME.name
        if not self.unicode:
            self.screen.add_class("ascii")
        self.gather_environment()
        self.query_one("#catalog").focus()
        self.check_size()

    def _short_root(self) -> str:
        text = str(self.root)
        return text if len(text) <= 40 else "..." + text[-37:]

    def get_default_screen(self) -> Screen[Any]:
        return MainScreen(id="_default")

    def check_size(self) -> None:
        """Swap in the 'please enlarge' screen below MIN_WIDTH x MIN_HEIGHT, and back."""
        width, height = self.size
        small = width < MIN_WIDTH or height < MIN_HEIGHT
        if small:
            if self._too_small is None:
                self._too_small = TooSmallScreen()
                self.push_screen(self._too_small)
            elif self._too_small.is_mounted:
                self._too_small.show_size(width, height)
        elif self._too_small is not None:
            if self.screen is self._too_small:
                self.pop_screen()
            self._too_small = None

    # ------------------------------------------------------------ navigation

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if event.tab.id is None:
            return
        tab_id = event.tab.id.removeprefix("tab-")
        self.query_one("#main", ContentSwitcher).current = tab_id
        if not self._going_back and self._history[-1] != tab_id:
            self._history.append(tab_id)
        self._going_back = False
        self.call_after_refresh(lambda: self.query_one(FOCUS_TARGET[tab_id]).focus())
        self.refresh_bindings()

    @property
    def active_tab(self) -> str:
        return (self.query_one(Tabs).active or "tab-scripts").removeprefix("tab-")

    def action_goto(self, tab_id: str) -> None:
        self.query_one(Tabs).active = f"tab-{tab_id}"

    def action_next_tab(self) -> None:
        if len(self.screen_stack) > 1:  # a modal or the too-small screen: normal focus movement
            self.screen.focus_next()
            return
        self.query_one(Tabs).action_next_tab()

    def action_prev_tab(self) -> None:
        if len(self.screen_stack) > 1:
            self.screen.focus_previous()
            return
        self.query_one(Tabs).action_previous_tab()

    def action_back(self) -> None:
        if len(self._history) > 1:
            self._history.pop()
            self._going_back = True
            self.action_goto(self._history[-1])

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "dry_run":
            return self.active_tab == "scripts"
        return True

    # --------------------------------------------------------------- helpers

    def integrity(self, script: Script) -> Integrity:
        """Integrity check, cached until the file's modified time changes."""
        try:
            path = resolve_script_path(self.root, script)
            mtime = path.stat().st_mtime if path.is_file() else None
        except (CatalogError, OSError):
            mtime = None
        cached = self._integrity.get(script.id)
        if cached and cached[0] == mtime and mtime is not None:
            return cached[1]
        result = check_integrity(self.root, script)
        self._integrity[script.id] = (mtime, result)
        return result

    def cached_signature(self, path: Path) -> str | None:
        """Authenticode status if already known; 'n/a' for non-PowerShell files."""
        if path.suffix.lower() != ".ps1" or not path.is_file():
            return "n/a"
        return self._signatures.get((str(path), path.stat().st_mtime))

    async def signature(self, path: Path) -> str:
        """Authenticode status of a .ps1 (Valid, NotSigned, HashMismatch...), cached."""
        known = self.cached_signature(path)
        if known is not None:
            return known
        command = f"(Get-AuthenticodeSignature -LiteralPath {ps_quote(str(path))}).Status"
        out = await run_capture(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command])
        status = out or "unavailable"
        self._signatures[(str(path), path.stat().st_mtime)] = status
        return status

    def tools_count(self) -> int | None:
        """Entries in the site tools.txt."""
        tools_file = self.catalog.settings.tools_file
        return count_list_file(self.root / tools_file) if tools_file else None

    def count_list_file(self, path: Path) -> int | None:
        return count_list_file(path)

    @work(exclusive=True, group="environment")
    async def gather_environment(self) -> None:
        """Fill the Environment box; the PowerShell probe runs in the background."""
        self.refresh_environment()
        out = await run_capture(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "$PSVersionTable.PSVersion.ToString()"])
        self.ps_version = out or "NOT FOUND"
        self.refresh_environment()
        if not out:
            self.notify("powershell.exe not found or blocked. PowerShell scripts cannot run.", severity="error", timeout=15)

    def refresh_environment(self) -> None:
        last = self.state.last_run()
        found = sum(1 for s in self.catalog.scripts if self.integrity(s).state not in ("MISSING", "OUTSIDE_ROOT"))
        tools = self.tools_count()
        # Short keys: at 100 columns the box is 27 wide beside the banner.
        info = {
            "Host": current_host(),
            "User": current_user(),
            "PS": self.ps_version,
            "Root": str(self.root),
            "Scripts": f"{found} of {len(self.catalog.scripts)} found",
            "Tools": f"{tools} listed" if tools is not None else "no tools file",
            "Last run": f"{last.started[5:16].replace('T', ' ')} {last.script_id}" if last else "-",
            "Status": last.status if last else "-",
        }
        self.query_one(EnvironmentBox).show(info)

    def copy_text(self, text: str) -> None:
        """Copy via the terminal (OSC 52) and, on Windows, clip.exe for consoles without OSC 52."""
        self.copy_to_clipboard(text)
        if IS_WINDOWS:
            try:
                subprocess.run(["clip"], input=("\ufeff" + text).encode("utf-16-le"), check=False,
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
            except (OSError, subprocess.SubprocessError):
                pass
        self.notify("Command copied to the clipboard.")

    # --------------------------------------------------------------- actions

    async def open_run(self, script: Script) -> None:
        """Load a script into the Run tab and switch to it."""
        self.current_script = script
        await self.query_one(RunPane).load(script)
        self.action_goto("run")

    async def action_dry_run(self) -> None:
        """Scripts tab 'd': dry-run with last-used values, or open the form if something is missing."""
        script = self.current_script
        if script is None:
            return
        if not script.supports_dry_run:
            self.notify(f"{script.name} has no dry-run mode. Open it with Enter.", severity="warning")
            return
        saved = self.state.last_values.get(script.id, {})
        values = {p.name: saved.get(p.name, p.default) for p in script.parameters}
        _, errors = validate_values(script, self.root, values)
        if errors:
            await self.open_run(script)
            self.notify("Fill in the required parameters, then press d.", severity="warning")
            return
        self.start_run(script, values, "DRY-RUN")

    def action_open_docs(self) -> None:
        local = self.root / "OPERATOR_GUIDE.md"
        if local.is_file() and IS_WINDOWS:
            os.startfile(local)  # noqa: S606 - opens the guide in the default viewer
        elif self.catalog.settings.docs_url:
            self.open_url(self.catalog.settings.docs_url)
        else:
            self.notify("No operator guide found.", severity="warning")

    async def action_quit(self) -> None:
        if self.runner is not None:
            self.notify("A run is in progress. Press k on the Output tab to cancel it first.", severity="warning")
            return
        self.exit()

    def on_unmount(self) -> None:
        if self.runner is not None:
            self.runner.kill_now()

    def cancel_run(self) -> None:
        if self.runner is None:
            self.notify("No run in progress.")
            return
        self.runner.cancel()
        self.notify("Cancelling: stopping the process tree...", severity="warning")

    # ------------------------------------------------------------- run flow

    def start_run(self, script: Script, values: dict[str, Any] | None, mode: Mode, manifest: Path | None = None) -> bool:
        """Validate, then launch a run in the background. Returns False when refused."""
        if self.runner is not None:
            self.notify("A run is already in progress. Press k on the Output tab to cancel it.", severity="warning")
            return False
        try:
            path = preflight(self.root, script, override_mismatch=script.id in self.overrides)
            extra: list[Argument] = []
            if manifest is not None:
                assert script.rollback_flag and script.manifest_flag
                extra = [(script.rollback_flag, None), (script.manifest_flag, str(manifest))]
            args = build_arguments(script, self.root, None if manifest else values, dry_run=mode in DRY_MODES, extra=extra)
        except (CatalogError, ArgumentError) as exc:
            self.notify(str(exc), title="Cannot run", severity="error", timeout=12)
            return False

        if values is not None and manifest is None:
            self.state.last_values[script.id] = {k: v for k, v in values.items()}
            save_state(self.state, self.state_file)

        argv = build_argv(script, path, args)
        started = datetime.now()
        header = (
            f"PostETUI run  script={script.id}  mode={mode}  user={current_user()}  host={current_host()}  "
            f"started={started:%Y-%m-%d %H:%M:%S}"
        )
        output = self.query_one(OutputPane)
        output.begin(script, mode, command_line(argv))
        self.runner = ScriptRunner(
            argv,
            script=script,
            cwd=self.root,
            log_path=transcript_path(self.logs_dir, script.id, started),
            timeout=script.timeout_seconds,
            grace=self.catalog.settings.cancel_grace_seconds,
            header=header,
            on_line=output.write_line,
            on_progress=output.progress,
        )
        self.action_goto("output")
        self._finish_run(self.runner, script, mode, path, args, manifest)
        return True

    def start_rollback(self, backup: BackupSet, *, dry_run: bool) -> bool:
        """Rollback through the script's own -Rollback -ManifestPath entry point."""
        if backup.manifest is None:
            return False
        mode: Mode = "ROLLBACK-DRY-RUN" if dry_run else "ROLLBACK"
        return self.start_run(backup.script, None, mode, manifest=backup.manifest)

    @work(exclusive=True, group="run")
    async def _finish_run(
        self, runner: ScriptRunner, script: Script, mode: Mode, path: Path, args: list[Argument], manifest: Path | None
    ) -> None:
        result = await runner.run()
        try:
            csv_path = newest_since(self.root, script.report_csv_glob, result.started)
            backup = newest_since(self.root, script.backup_glob, result.started)
            manifest_out = backup / script.manifest_name if backup and (backup / script.manifest_name).is_file() else None
            rollback = ""
            if manifest_out and script.rollback_flag and script.manifest_flag:
                rb_args = build_arguments(
                    script, self.root, None, dry_run=script.supports_dry_run,
                    extra=[(script.rollback_flag, None), (script.manifest_flag, str(manifest_out))],
                )
                rollback = command_line(build_argv(script, path, rb_args))

            integrity = self.integrity(script)
            counters = result.counters
            record = AuditRecord(
                run_id=new_run_id(result.started),
                timestamp=result.started.isoformat(timespec="seconds"),
                user=current_user(),
                host=current_host(),
                script=script.id,
                script_hash=integrity.sha256 or "",
                mode=mode,
                args=" ".join(argument_tokens(script, args)),
                exit_code=result.exit_code,
                elapsed=result.elapsed,
                ok=counters.ok,
                failed=counters.failed + counters.timeout,
                skipped=counters.skipped,
                log_path=str(result.log_path or ""),
                csv_path=str(csv_path or ""),
                backup_path=str(backup or ""),
            )
            warnings = append_audit(self.logs_dir, record)
            self.state.record_run(
                RecentRun(
                    run_id=record.run_id, script_id=script.id, mode=mode, status=result.status,
                    started=record.timestamp, elapsed=result.elapsed, log_path=record.log_path,
                    csv_path=record.csv_path, backup_path=record.backup_path,
                )
            )
            state_warning = save_state(self.state, self.state_file)
            if state_warning:
                warnings.append(state_warning)
            if mode == "ROLLBACK-DRY-RUN" and manifest is not None and result.status in ("SUCCESS", "WARN"):
                self.rollback_dry_ok.add(manifest)

            self.query_one(OutputPane).finish(result, RunArtifacts(csv_path, backup, rollback, warnings))
            self.query_one(ScriptsPane).refresh_catalog()
            self.refresh_environment()
            self.query_one(ReportsPane).reload(select=csv_path)
            self.query_one(RollbackPane).reload()
        finally:
            self.runner = None
        severity = "information" if result.status == "SUCCESS" else ("warning" if result.status in ("WARN", "CANCELLED") else "error")
        self.notify(f"{script.name}: {result.status}", title=mode, severity=severity)
