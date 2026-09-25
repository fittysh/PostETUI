"""Home banner and the Environment info box."""

from __future__ import annotations

from rich.table import Table
from rich.text import Text
from textual.widgets import Static

from ..theme import MUTED, banner, status_text


class Banner(Static):
    """Micron logo + PostETUI Doom title, tagline and credit line."""

    def __init__(self, *, unicode: bool, **kwargs: object) -> None:
        super().__init__(banner(unicode), **kwargs)  # type: ignore[arg-type]


class EnvironmentBox(Static):
    """Key/value box: host, user, PowerShell, root, counts, last run."""

    def show(self, info: dict[str, str]) -> None:
        """Render the info dict. The 'Status' value is colour-coded."""
        grid = Table.grid(padding=(0, 1))
        grid.add_column(style=f"bold {MUTED}", no_wrap=True, min_width=8)
        grid.add_column(overflow="ellipsis", no_wrap=True, ratio=1)
        for key, value in info.items():
            cell = status_text(value) if key == "Status" and value != "-" else Text(value)
            grid.add_row(key, cell)
        self.update(grid)
