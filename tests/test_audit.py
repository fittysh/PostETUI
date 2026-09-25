from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from postetui.core.audit import AUDIT_COLUMNS, AuditRecord, append_audit


def record(**overrides: object) -> AuditRecord:
    values: dict[str, object] = dict(
        run_id="r1", timestamp="2026-09-25T10:00:00", user="tech", host="PC1", script="kla", script_hash="AB",
        mode="APPLY", args="-Recipe 'A.rcp'", exit_code=0, elapsed=12.345, ok=3, failed=0, skipped=1,
        log_path="l.log", csv_path="r.csv", backup_path="b",
    )
    values.update(overrides)
    return AuditRecord(**values)  # type: ignore[arg-type]


def test_audit_appends_with_one_header(tmp_path: Path) -> None:
    assert append_audit(tmp_path, record()) == []
    assert append_audit(tmp_path, record(run_id="r2", exit_code=None)) == []
    with (tmp_path / "postetui_audit.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0].keys()) == AUDIT_COLUMNS
    assert [r["RunId"] for r in rows] == ["r1", "r2"]
    assert rows[0]["Elapsed"] == "12.3" and rows[1]["ExitCode"] == ""
    lines = (tmp_path / "postetui_audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[1])["RunId"] == "r2"


def test_locked_csv_falls_back_to_jsonl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_open = Path.open

    def locked(self: Path, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if self.suffix == ".csv":
            raise PermissionError("locked by Excel")
        return real_open(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "open", locked)
    warnings = append_audit(tmp_path, record())
    assert warnings and "locked" in warnings[0]
    assert (tmp_path / "postetui_audit.jsonl").exists()
