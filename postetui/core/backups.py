"""Backup sets written by the scripts, read for the Rollback tab.

PostETUI only reads backups. Restores always go through the script's own
rollback flag, never through a copy routine here.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .catalog import Catalog, Script


@dataclass(frozen=True)
class RestoreItem:
    """One manifest row: what would be restored, from where, to where."""

    tool: str
    item: str
    source: str
    target: str
    restorable: bool
    note: str


@dataclass
class BackupSet:
    """One backup folder, e.g. scripts/backups/20260923_084500."""

    script: Script
    folder: Path
    stamp: str
    timestamp: datetime
    size: int
    manifest: Path | None
    items: list[RestoreItem] = field(default_factory=list)
    csv: Path | None = None
    log: Path | None = None
    error: str | None = None

    @property
    def tools(self) -> int:
        """Distinct tools in the manifest."""
        return len({i.tool for i in self.items if i.tool})

    @property
    def restorable(self) -> bool:
        """True when at least one file can be restored."""
        return any(i.restorable for i in self.items)

    @property
    def verdict(self) -> str:
        """One line for the operator."""
        if self.error:
            return f"Rollback not possible - {self.error}"
        if not self.restorable:
            return "Rollback not possible - audit trail only (no restorable backup files)."
        count = sum(i.restorable for i in self.items)
        return f"{count} file(s) can be restored. Dry-run first with r."


def read_manifest(path: Path) -> list[RestoreItem]:
    """Read a rollback manifest CSV (TargetTool, Recipe, ExistedBefore, BackupFile, OriginalRemote)."""
    items: list[RestoreItem] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            source = (row.get("BackupFile") or "").strip()
            existed = (row.get("ExistedBefore") or "True").strip().lower() != "false"
            if not existed:
                ok, note = False, "File was new - nothing to restore (deletes are not allowed)"
            elif not source or not Path(source).is_file():
                ok, note = False, "Backup file missing"
            else:
                ok, note = True, ""
            items.append(
                RestoreItem(
                    tool=(row.get("TargetTool") or "").strip(),
                    item=(row.get("Recipe") or row.get("File") or "").strip(),
                    source=source,
                    target=(row.get("OriginalRemote") or "").strip(),
                    restorable=ok,
                    note=note,
                )
            )
    return items


def _stamp_time(folder: Path) -> datetime:
    try:
        return datetime.strptime(folder.name, "%Y%m%d_%H%M%S")
    except ValueError:
        return datetime.fromtimestamp(folder.stat().st_mtime)


def _match(root: Path, pattern: str | None, stamp: str) -> Path | None:
    if not pattern:
        return None
    return next((p for p in root.glob(pattern) if stamp in p.name), None)


def list_backup_sets(root: Path, catalog: Catalog) -> list[BackupSet]:
    """Every backup folder of every script that declares backup_glob, newest first."""
    sets: list[BackupSet] = []
    for script in catalog.scripts:
        if not script.backup_glob:
            continue
        for folder in root.glob(script.backup_glob):
            if not folder.is_dir():
                continue
            size = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())
            manifest = folder / script.manifest_name
            backup = BackupSet(
                script=script,
                folder=folder,
                stamp=folder.name,
                timestamp=_stamp_time(folder),
                size=size,
                manifest=manifest if manifest.is_file() else None,
                csv=_match(root, script.report_csv_glob, folder.name),
                log=_match(root, script.log_glob, folder.name),
            )
            if backup.manifest is None:
                backup.error = f"no {script.manifest_name} in the folder."
            else:
                try:
                    backup.items = read_manifest(backup.manifest)
                except (OSError, csv.Error, UnicodeDecodeError) as exc:
                    backup.error = f"manifest unreadable ({exc})."
            sets.append(backup)
    return sorted(sets, key=lambda s: s.timestamp, reverse=True)
