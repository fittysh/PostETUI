from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import load_workbook

from postetui.core.backups import list_backup_sets
from postetui.core.catalog import Catalog
from postetui.core.reports import (
    ReportError,
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

from .helpers import write_report


def test_summary_and_filters(tmp_path: Path) -> None:
    path = tmp_path / "KLA_Recipe_Audit_20260925_080000.csv"
    write_report(path, [("T1", "RECIPE PRESENT"), ("T2", "RECIPE MISSING"), ("T3", "UNREACHABLE"), ("T4", "IDENTICAL")])
    df = load_report(path)
    summary = summarize(df)
    assert (summary.rows, summary.tools, summary.failed, summary.skipped) == (4, 4, 1, 1)
    assert summary.success_rate == pytest.approx(75.0)
    assert summary.avg_duration == pytest.approx(11.5)
    assert list(filter_status(df, "failed")["_Tool"]) == ["T3"]
    assert len(filter_status(df, "all")) == 4


def test_trend_and_repeat_offenders(demo_root: Path, demo_catalog: Catalog) -> None:
    files = list_report_files(demo_root, demo_catalog)
    family = family_files(files, "KLA_Recipe_Transfer")
    assert [f.path.name[-19:-4] for f in family] == ["20260922_080000", "20260921_080000", "20260920_080000"]
    points = trend(family)
    assert [round(rate) for _, rate in points] == [67, 67, 75]  # oldest first
    offenders = repeat_offenders(family)
    assert list(offenders["Tool"]) == ["TOOL-A03"] and int(offenders["FailedRuns"][0]) == 3


def test_malformed_csv_is_reported(tmp_path: Path) -> None:
    bad = tmp_path / "bad.csv"
    bad.write_text("Status,Tool\nOK,T1\nOK,T2,extra,fields\n", encoding="utf-8")
    with pytest.raises(ReportError, match="cannot read"):
        load_report(bad)
    no_status = tmp_path / "nostatus.csv"
    no_status.write_text("Tool,Value\nT1,1\n", encoding="utf-8")
    with pytest.raises(ReportError, match="no Status column"):
        load_report(no_status)


def test_exports(tmp_path: Path) -> None:
    path = tmp_path / "r.csv"
    write_report(path, [("T1", "SUCCESS"), ("T2", "FAILED")])
    df = load_report(path)
    out = export_csv(filter_status(df, "failed"), tmp_path / "Reports")
    assert out.read_text(encoding="utf-8-sig").splitlines()[0].startswith("Result,TargetTool")

    xlsx = export_xlsx(df, summarize(df), path.name, tmp_path / "Reports")
    book = load_workbook(xlsx)
    rows = book["Rows"]
    assert rows["A1"].value == "Result" and rows["A3"].value == "FAILED"
    assert len(rows.conditional_formatting) >= 1
    assert book["Summary"]["A6"].value == "Success rate %"


def test_backup_sets_flag_audit_only(demo_root: Path, demo_catalog: Catalog) -> None:
    sets = {s.stamp: s for s in list_backup_sets(demo_root, demo_catalog)}
    good, audit_only = sets["20260922_080000"], sets["20260921_080000"]
    assert good.restorable and good.tools == 2 and good.csv is not None and good.log is not None
    assert [i.restorable for i in good.items] == [True, False]
    assert not audit_only.restorable
    assert "audit trail only" in audit_only.verdict
