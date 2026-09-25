"""Scripts tab: splash banner, Environment box, catalog table and detail panel."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, cast

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, Input, Static

from ..core.catalog import Script
from ..core.state import RecentRun
from ..theme import MUTED, SOFT_GREEN, SOFT_YELLOW, status_color, status_text
from .banner import Banner, EnvironmentBox

if TYPE_CHECKING:
    from ..app import PostETUIApp

TYPE_LABELS = {"powershell": "PowerShell", "pwsh": "pwsh", "python": "Python"}


def fuzzy_match(query: str, text: str) -> bool:
    """True when the query's letters appear in order in the text (spaces ignored)."""
    chars = iter(text.lower())
    return all(ch in chars for ch in query.lower() if not ch.isspace())


class CatalogTable(DataTable[object]):
    """Catalog table; relabels Enter so the footer reads "Enter Run"."""

    BINDINGS = [Binding("enter", "select_cursor", "Run")]


class ScriptsPane(Vertical):
    """Home tab. Enter opens the Run tab, d dry-runs, / filters."""

    BINDINGS = [
        Binding("slash", "filter", "Filter"),
        Binding("escape", "clear_filter", "Clear filter", show=False),
    ]

    @property
    def tui(self) -> PostETUIApp:
        return cast("PostETUIApp", self.app)

    def compose(self) -> ComposeResult:
        with Horizontal(id="home-top"):
            yield Banner(unicode=self.tui.unicode, id="banner")
            env = EnvironmentBox(id="env", classes="panel")
            env.border_title = "|Environment|"
            yield env
        yield Input(placeholder="Filter by name or tag. Enter keeps the filter, Esc clears it.", id="filter")
        with Horizontal(id="home-main"):
            table = CatalogTable(id="catalog", cursor_type="row", zebra_stripes=True, classes="panel")
            table.border_title = "|Available Scripts|"
            yield table
            detail = VerticalScroll(Static(id="detail-body"), id="detail", classes="panel")
            detail.border_title = "|Details|"
            detail.can_focus = False
            yield detail

    def on_mount(self) -> None:
        table = self.query_one("#catalog", DataTable)
        table.add_column("Name", key="name", width=26)
        table.add_column("Type", key="type")
        table.add_column("Last Run", key="last")
        table.add_column("Status", key="status")
        self.refresh_catalog()

    def row_status(self, script: Script, last: RecentRun | None) -> str:
        """Blocking integrity problems first, then the last run, then READY/DRAFT."""
        state = self.tui.integrity(script).state
        if state in ("MISSING", "OUTSIDE_ROOT", "MISMATCH"):
            return state
        if last:
            return last.status
        return "DRAFT" if script.status == "draft" else "READY"

    def refresh_catalog(self) -> None:
        """Rebuild the table, keeping the cursor on the same script."""
        table = self.query_one("#catalog", DataTable)
        keep = self.tui.current_script.id if self.tui.current_script else None
        query = self.query_one("#filter", Input).value.strip()
        table.clear()
        for script in self.tui.catalog.scripts:
            haystack = " ".join([script.name, script.id, *script.tags])
            if query and not fuzzy_match(query, haystack):
                continue
            last = self.tui.state.last_run(script.id)
            when = datetime.fromisoformat(last.started).strftime("%m-%d %H:%M") if last else "-"
            table.add_row(
                Text(script.name, style=SOFT_GREEN),
                TYPE_LABELS[script.interpreter],
                when,
                status_text(self.row_status(script, last)),
                key=script.id,
            )
        if table.row_count == 0:
            self.query_one("#detail-body", Static).update("No script matches the filter.")
            return
        if keep and keep in {str(k.value) for k in table.rows}:
            table.move_cursor(row=table.get_row_index(keep))
        self.show_detail(self.tui.catalog.get(str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)))

    def highlighted(self) -> Script | None:
        """Script under the cursor."""
        table = self.query_one("#catalog", DataTable)
        if table.row_count == 0:
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        return self.tui.catalog.get(str(key))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id != "catalog" or event.row_key.value is None:
            return
        script = self.tui.catalog.get(str(event.row_key.value))
        self.tui.current_script = script
        self.show_detail(script)

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "catalog" and event.row_key.value is not None:
            event.stop()
            await self.tui.open_run(self.tui.catalog.get(str(event.row_key.value)))

    def show_detail(self, script: Script) -> None:
        """Synopsis, safety model, required parameters, path, hash, signature."""
        tui = self.tui
        bullet = "\u2022" if tui.unicode else "-"
        integrity = tui.integrity(script)
        text = Text()
        text.append(script.name + "\n", style="bold white")
        text.append(f"{script.id}  |  {TYPE_LABELS[script.interpreter]}  |  {script.status}\n\n", style=MUTED)
        if script.synopsis:
            text.append(script.synopsis + "\n\n")
        if script.description:
            text.append(" ".join(script.description.split()) + "\n\n", style=MUTED)
        if script.safety:
            text.append("Safety model\n", style=f"bold {SOFT_YELLOW}")
            for line in script.safety:
                text.append(f" {bullet} {line}\n")
            text.append("\n")
        required = [p for p in script.parameters if p.required]
        text.append("Required parameters\n", style=f"bold {SOFT_YELLOW}")
        for param in required:
            text.append(f" {bullet} {param.title} ({param.type})\n")
        if not required:
            text.append(" none\n", style=MUTED)
        if not script.supports_dry_run:
            text.append("\nNo dry-run mode: every run writes.\n", style=f"bold {SOFT_YELLOW}")

        rows = [
            ("Path", str(integrity.path), None),
            ("SHA-256", integrity.sha256 or "-", None),
            ("Pin", integrity.state, status_color(integrity.state)),
            ("Modified", datetime.fromtimestamp(integrity.modified).strftime("%Y-%m-%d %H:%M") if integrity.modified else "-", None),
            ("Signature", tui.cached_signature(integrity.path) or "checking...", None),
            ("Tags", ", ".join(script.tags) or "-", None),
        ]
        text.append("\n")
        for label, value, colour in rows:
            text.append(f"{label:<10}", style=f"bold {MUTED}")
            text.append(value + "\n", style=colour or "")
        self.query_one("#detail-body", Static).update(text)
        if tui.cached_signature(integrity.path) is None:
            self.load_signature(script)

    @work(exclusive=True, group="signature")
    async def load_signature(self, script: Script) -> None:
        """Check the Authenticode signature in the background, then redraw."""
        await self.tui.signature(self.tui.integrity(script).path)
        if self.tui.current_script is script:
            self.show_detail(script)

    def action_filter(self) -> None:
        box = self.query_one("#filter", Input)
        box.add_class("-shown")
        box.focus()

    def action_clear_filter(self) -> None:
        box = self.query_one("#filter", Input)
        box.value = ""
        box.remove_class("-shown")
        self.refresh_catalog()
        self.query_one("#catalog").focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter":
            event.stop()
            self.refresh_catalog()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "filter":
            event.stop()
            self.query_one("#catalog").focus()
