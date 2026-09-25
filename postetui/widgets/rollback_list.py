"""Rollback tab: backup sets, restore preview, dry-run-first rollback through the script."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from ..core.backups import BackupSet, list_backup_sets
from ..theme import MUTED, RED, status_color
from .confirm import TypedConfirm

if TYPE_CHECKING:
    from ..app import PostETUIApp


def human_size(size: int) -> str:
    """1536 -> '1.5 KB'."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


class SetsTable(DataTable[object]):
    """Backup set list; the footer reads "Enter Apply rollback"."""

    BINDINGS = [Binding("enter", "select_cursor", "Apply rollback")]


class RollbackPane(Vertical):
    """Always dry-run first; apply re-uses the script's own rollback flag."""

    BINDINGS = [
        Binding("r", "dry_run", "Dry-run rollback"),
        Binding("f5", "reload", "Refresh"),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.sets: list[BackupSet] = []

    @property
    def tui(self) -> PostETUIApp:
        return cast("PostETUIApp", self.app)

    def compose(self) -> ComposeResult:
        sets = SetsTable(id="sets", cursor_type="row", zebra_stripes=True, classes="panel")
        sets.border_title = "|Backup Sets|"
        yield sets
        verdict = Static("", id="verdict", classes="panel")
        verdict.border_title = "|Selected Set|"
        yield verdict
        restore = DataTable(id="restore", cursor_type="row", classes="panel")
        restore.border_title = "|Restore Preview|"
        yield restore
        yield Static("r: dry-run rollback   Enter: apply rollback (only after its dry-run)   F5: refresh", id="rb-hint")

    def on_mount(self) -> None:
        self.query_one("#sets", DataTable).add_columns("Timestamp", "Script", "Tools", "Size", "CSV+Log", "Restorable")
        self.query_one("#restore", DataTable).add_columns("Tool", "Item", "From", "To", "Note")
        self.reload()

    def reload(self) -> None:
        """Rescan backup folders."""
        self.sets = list_backup_sets(self.tui.root, self.tui.catalog)
        table = self.query_one("#sets", DataTable)
        table.clear()
        for backup in self.sets:
            pair = "yes" if backup.csv and backup.log else ("csv only" if backup.csv else ("log only" if backup.log else "no"))
            table.add_row(
                backup.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                backup.script.name,
                str(backup.tools),
                human_size(backup.size),
                pair,
                Text("YES", style=f"bold {status_color('SUCCESS')}") if backup.restorable else Text("NO", style=f"bold {RED}"),
                key=str(backup.folder),
            )
        if self.sets:
            self.show(self.sets[0])
        else:
            self.query_one("#verdict", Static).update(Text("No backup sets yet. They appear after an APPLY run.", style=MUTED))
            self.query_one("#restore", DataTable).clear()

    def selected(self) -> BackupSet | None:
        table = self.query_one("#sets", DataTable)
        if not self.sets or table.row_count == 0:
            return None
        return self.sets[table.cursor_row]

    def show(self, backup: BackupSet) -> None:
        """Verdict line plus the file-by-file restore preview."""
        text = Text()
        text.append(f"{backup.folder}\n", style=MUTED)
        text.append(backup.verdict, style="bold" if backup.restorable else f"bold {RED}")
        if backup.manifest and backup.manifest in self.tui.rollback_dry_ok:
            text.append("\nDry-run passed this session: Enter applies.", style=status_color("SUCCESS"))
        self.query_one("#verdict", Static).update(text)
        table = self.query_one("#restore", DataTable)
        table.clear()
        for item in backup.items:
            note = Text(item.note or "restore", style=MUTED if item.restorable else RED)
            table.add_row(item.tool, item.item, item.source, item.target, note)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "sets" and self.sets:
            self.show(self.sets[event.cursor_row])

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "sets":
            event.stop()
            self.apply()

    def usable(self) -> BackupSet | None:
        backup = self.selected()
        if backup is None:
            self.notify("No backup set selected.", severity="warning")
            return None
        if not backup.restorable or backup.manifest is None:
            self.notify(backup.verdict, title="Rollback not possible", severity="error")
            return None
        return backup

    def action_dry_run(self) -> None:
        backup = self.usable()
        if backup:
            self.tui.start_rollback(backup, dry_run=True)

    def apply(self) -> None:
        backup = self.usable()
        if backup is None or backup.manifest is None:
            return
        if backup.manifest not in self.tui.rollback_dry_ok:
            self.notify("Dry-run this set first (press r). Apply unlocks when the dry-run passes.", severity="warning")
            return
        count = sum(i.restorable for i in backup.items)
        body = (
            f"[b]{backup.script.name}[/b] rollback\nSet: {backup.stamp}\n"
            f"[b]{count} file(s) on {backup.tools} tool(s) will be restored.[/b]\n"
            f"Runs the script's own {backup.script.rollback_flag} {backup.script.manifest_flag}."
        )

        def confirmed(ok: bool | None) -> None:
            if ok:
                self.tui.start_rollback(backup, dry_run=False)

        self.app.push_screen(TypedConfirm("APPLY", "APPLY rollback", body), confirmed)

    def action_reload(self) -> None:
        self.reload()
