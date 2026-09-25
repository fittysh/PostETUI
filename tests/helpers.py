"""Demo root for tests and screenshots: fake scripts that talk like KLA_Recipe_Proliferate.ps1."""

from __future__ import annotations

import csv
import textwrap
from pathlib import Path

FAKE_PROLIFERATE = r'''
import argparse, csv, datetime, pathlib, sys, time

p = argparse.ArgumentParser()
p.add_argument("--Recipe", default="")
p.add_argument("--SourceTool", default="")
p.add_argument("--TargetTools", default="")
p.add_argument("--UseToolsFile", action="store_true")
p.add_argument("--Delay", type=float, default=0)
p.add_argument("--dry-run", action="store_true")
p.add_argument("--rollback", action="store_true")
p.add_argument("--manifest-path", default="")
a = p.parse_args()
here = pathlib.Path(__file__).parent
stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

if a.rollback:
    rows = list(csv.DictReader(open(a.manifest_path, encoding="utf-8-sig")))
    print("[STEP ] ROLLBACK - restore recipes from a backup manifest", flush=True)
    for i, r in enumerate(rows, 1):
        print(f"  [ {i} / {len(rows)} ] {r['TargetTool']}   {'WOULD RESTORE' if a.dry_run else 'RESTORED'}", flush=True)
    sys.exit(0)

tools = [t for t in a.TargetTools.split(",") if t]
if a.UseToolsFile:
    tools += [l.strip() for l in open(here / "tools.txt") if l.strip() and not l.startswith("#")]
print("[STEP ] KLA_Recipe_Proliferate (demo)  -  mode " + ("DRY-RUN" if a.dry_run else "COMMIT"), flush=True)
print("[INFO ] Source tool : " + a.SourceTool, flush=True)
print("[OK   ] Staged + verified: " + a.Recipe, flush=True)
print("[WARN ] demo stderr line", file=sys.stderr, flush=True)
results = []
for i, tool in enumerate(tools, 1):
    time.sleep(a.Delay)
    status = "UNREACHABLE" if tool.endswith("9") else ("WOULD OVERWRITE" if a.dry_run else "SUCCESS")
    print(f"  [ {i} / {len(tools)} ] {tool}   {status}", flush=True)
    results.append({"TargetTool": tool, "Recipe": a.Recipe, "Status": status})
reports = here / "reports"
reports.mkdir(exist_ok=True)
with open(reports / f"KLA_Recipe_Transfer_{stamp}.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["TargetTool", "Recipe", "Status"])
    w.writeheader()
    w.writerows(results)
if not a.dry_run:
    folder = here / "backups" / stamp
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / "rollback_manifest.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["TargetTool", "Recipe", "ExistedBefore", "BackupFile", "OriginalRemote"])
        w.writeheader()
        for r in results:
            backup = folder / (r["TargetTool"] + "__" + r["Recipe"])
            backup.write_text("old recipe")
            w.writerow({"TargetTool": r["TargetTool"], "Recipe": r["Recipe"], "ExistedBefore": "True",
                        "BackupFile": str(backup), "OriginalRemote": "\\\\" + r["TargetTool"] + "\\C\\recipes\\" + r["Recipe"]})
sys.exit(1 if any(r["Status"] == "UNREACHABLE" for r in results) else 0)
'''

FAKE_HANG = r'''
import sys, time
print("  [ 1 / 3 ] TOOL-A02   REACHABLE", flush=True)
print("waiting on \\\\TOOL-A03\\C\\recipes (simulated hung UNC path)", flush=True)
time.sleep(600)
'''

CATALOG = """
settings:
  tools_file: scripts/tools.txt
  logs_dir: Logs
  cancel_grace_seconds: 0.5
scripts:
  - id: demo_kla
    name: "KLA Recipe Audit + Proliferate"
    path: scripts/fake_proliferate.py
    interpreter: python
    tags: [kla, recipe, fleet]
    synopsis: "Pull a known-good .rcp from a source tool, audit the targets, then overwrite it across the fleet."
    safety:
      - "Never deletes any file, local or remote"
      - "Backs up the existing remote recipe before overwrite"
    supports_dry_run: true
    dry_run_flag: "--dry-run"
    rollback_flag: "--rollback"
    manifest_flag: "--manifest-path"
    report_csv_glob: "scripts/reports/*.csv"
    log_glob: "scripts/reports/*.log"
    backup_glob: "scripts/backups/*"
    exit_codes: {0: SUCCESS, 1: WARN, 2: FAILED}
    one_of_required: [[TargetTools, UseToolsFile]]
    parameters:
      - {name: Recipe, type: list, required: true, label: "Recipe file name(s)"}
      - {name: SourceTool, type: string, required: true, label: "Source tool ID"}
      - {name: TargetTools, type: list, blast_radius: true, label: "Target tool IDs"}
      - {name: UseToolsFile, type: bool, default: false, blast_radius: true, label: "Use tools.txt as targets"}
      - {name: Delay, type: int, default: 0, min: 0, max: 5}
  - id: demo_hang
    name: "Hung UNC path simulator"
    path: scripts/fake_hang.py
    interpreter: python
    supports_dry_run: true
    dry_run_flag: "--dry-run"
    timeout_seconds: 60
  - id: demo_missing
    name: "Script that is not deployed"
    path: scripts/not_here.ps1
    status: draft
  - id: demo_mismatch
    name: "Tampered script"
    path: scripts/fake_hang.py
    interpreter: python
    sha256: "0000000000000000000000000000000000000000000000000000000000000000"
    supports_dry_run: true
    dry_run_flag: "--dry-run"
"""

DEMO_VALUES = {"Recipe": "EXAMPLE_PRODUCT_RECIPE.rcp", "SourceTool": "TOOL-A01",
               "TargetTools": "TOOL-A02, TOOL-A03, TOOL-A09", "UseToolsFile": False, "Delay": "0"}


def write_report(path: Path, rows: list[tuple[str, str]]) -> None:
    """A KLA-style report CSV with TargetTool/Status columns."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["TargetTool", "Recipe", "Status", "DurationSeconds"])
        for i, (tool, status) in enumerate(rows):
            writer.writerow([tool, "A.rcp", status, 10 + i])


def make_demo_root(root: Path) -> Path:
    """Build a self-contained PostETUI root with scripts, tools.txt, reports and backups."""
    scripts = root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (root / "catalog.yaml").write_text(textwrap.dedent(CATALOG), encoding="utf-8")
    (scripts / "fake_proliferate.py").write_text(FAKE_PROLIFERATE, encoding="utf-8")
    (scripts / "fake_hang.py").write_text(FAKE_HANG, encoding="utf-8")
    (scripts / "tools.txt").write_text("# targets\nTOOL-A02\nTOOL-A03\nTOOL-A04\n", encoding="utf-8")

    reports = scripts / "reports"
    write_report(reports / "KLA_Recipe_Transfer_20260920_080000.csv",
                 [("TOOL-A02", "SUCCESS"), ("TOOL-A03", "FAILED"), ("TOOL-A04", "SUCCESS")])
    write_report(reports / "KLA_Recipe_Transfer_20260921_080000.csv",
                 [("TOOL-A02", "SUCCESS"), ("TOOL-A03", "UNREACHABLE"), ("TOOL-A04", "IDENTICAL")])
    write_report(reports / "KLA_Recipe_Transfer_20260922_080000.csv",
                 [("TOOL-A02", "SUCCESS"), ("TOOL-A03", "TIMEOUT"), ("TOOL-A04", "SUCCESS"),
                  ("TOOL-A10", "SKIPPED")])
    (reports / "KLA_Recipe_Transfer_20260922_080000.log").write_text("log\n", encoding="utf-8")

    good = scripts / "backups" / "20260922_080000"
    good.mkdir(parents=True, exist_ok=True)
    (good / "TOOL-A02__A.rcp").write_text("old", encoding="utf-8")
    with (good / "rollback_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["TargetTool", "Recipe", "ExistedBefore", "BackupFile", "OriginalRemote"])
        writer.writerow(["TOOL-A02", "A.rcp", "True", str(good / "TOOL-A02__A.rcp"), r"\\TOOL-A02\C\recipes\A.rcp"])
        writer.writerow(["TOOL-A04", "A.rcp", "False", "", r"\\TOOL-A04\C\recipes\A.rcp"])

    audit_only = scripts / "backups" / "20260921_080000"
    audit_only.mkdir(parents=True, exist_ok=True)
    with (audit_only / "rollback_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["TargetTool", "Recipe", "ExistedBefore", "BackupFile", "OriginalRemote"])
        writer.writerow(["TOOL-A03", "A.rcp", "False", "", r"\\TOOL-A03\C\recipes\A.rcp"])
    return root
