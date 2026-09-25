"""Append-only audit trail: <logs>/postetui_audit.csv plus a JSONL twin."""

from __future__ import annotations

import csv
import getpass
import json
import socket
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

AUDIT_COLUMNS = [
    "RunId", "Timestamp", "User", "Host", "Script", "ScriptHash", "Mode", "Args", "ExitCode",
    "Elapsed", "OK", "Failed", "Skipped", "LogPath", "CsvPath", "BackupPath",
]


@dataclass
class AuditRecord:
    """One launch. Field order matches AUDIT_COLUMNS."""

    run_id: str
    timestamp: str
    user: str
    host: str
    script: str
    script_hash: str
    mode: str
    args: str
    exit_code: int | None
    elapsed: float
    ok: int
    failed: int
    skipped: int
    log_path: str
    csv_path: str
    backup_path: str

    def as_row(self) -> dict[str, str]:
        """Row keyed by the CSV column names."""
        values = ["" if v is None else str(v) for v in asdict(self).values()]
        values[AUDIT_COLUMNS.index("Elapsed")] = f"{self.elapsed:.1f}"
        return dict(zip(AUDIT_COLUMNS, values, strict=True))


def new_run_id(now: datetime | None = None) -> str:
    """Sortable, unique run id, e.g. 20260925143002-a1b2c3."""
    return f"{(now or datetime.now()):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}"


def current_user() -> str:
    """Windows user name, or 'unknown'."""
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def current_host() -> str:
    """Computer name."""
    return socket.gethostname()


def append_audit(logs_dir: Path, record: AuditRecord) -> list[str]:
    """Append one record to the CSV and the JSONL file.

    Never raises. Returns warnings for the operator, e.g. when Excel has the
    CSV open (Windows locks it) - the JSONL copy still gets the row.
    """
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return [f"Audit not written: cannot create {logs_dir} ({exc})."]

    warnings: list[str] = []
    row = record.as_row()
    csv_path = logs_dir / "postetui_audit.csv"
    try:
        is_new = not csv_path.exists() or csv_path.stat().st_size == 0
        # BOM on a new file so Excel opens it as UTF-8.
        with csv_path.open("a", newline="", encoding="utf-8-sig" if is_new else "utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=AUDIT_COLUMNS)
            if is_new:
                writer.writeheader()
            writer.writerow(row)
    except PermissionError:
        warnings.append(f"{csv_path.name} is locked (open in Excel?). Run recorded in postetui_audit.jsonl only.")
    except OSError as exc:
        warnings.append(f"Cannot write {csv_path.name}: {exc}")

    try:
        with (logs_dir / "postetui_audit.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
    except OSError as exc:
        warnings.append(f"Cannot write postetui_audit.jsonl: {exc}")
    return warnings
