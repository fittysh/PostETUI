"""Entry point: python -m postetui, the postetui console script, and postetui.exe."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Absolute imports: PyInstaller runs this file as a script, outside the package.
from postetui import __version__
from postetui.core.catalog import Catalog, CatalogError, check_integrity, default_catalog_path, load_catalog


def default_root() -> Path:
    """POSTETUI_ROOT, else the folder of postetui.exe, else the source checkout."""
    if os.environ.get("POSTETUI_ROOT"):
        return Path(os.environ["POSTETUI_ROOT"])
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def print_hashes(root: Path, catalog: Catalog) -> int:
    """Print each script's SHA-256 and pin state. Exit 1 when any pin mismatches."""
    print(f"Root: {root}\n")
    mismatch = False
    for script in catalog.scripts:
        integrity = check_integrity(root, script)
        mismatch |= integrity.state == "MISMATCH"
        print(f"{script.id:<30} {integrity.state:<12} {integrity.sha256 or '-'}")
    print("\nPin a script by setting  sha256: <value>  on its catalog.yaml entry.")
    return 1 if mismatch else 0


def _pause_if_double_clicked() -> None:
    # A double-clicked postetui.exe closes its window at once; keep the error readable.
    if getattr(sys, "frozen", False) and sys.stdin and sys.stdin.isatty():
        input("\nPress Enter to close...")


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, load the catalog, run the TUI."""
    parser = argparse.ArgumentParser(prog="postetui", description="PostETUI - Post-E automation console.")
    parser.add_argument("--root", type=Path, help="folder holding catalog.yaml, scripts\\ and Logs\\ (default: install folder)")
    parser.add_argument("--catalog", type=Path, help="catalog file (default: <root>\\catalog.yaml, else the bundled one)")
    parser.add_argument("--no-unicode", action="store_true", help="ASCII borders and banner for legacy consoles")
    parser.add_argument("--print-hashes", action="store_true", help="print script SHA-256 values for pinning, then exit")
    parser.add_argument("--version", action="version", version=f"PostETUI {__version__}")
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    root = (args.root or default_root()).resolve()
    catalog_path = args.catalog or default_catalog_path(root)
    try:
        catalog = load_catalog(catalog_path)
    except CatalogError as exc:
        print(f"PostETUI cannot start.\n\n{exc}", file=sys.stderr)
        _pause_if_double_clicked()
        return 2

    if args.print_hashes:
        return print_hashes(root, catalog)

    logs_dir = root / catalog.settings.logs_dir
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=logs_dir / "postetui_app.log",
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
    except OSError:
        pass  # no log folder: the TUI still runs, runs report the transcript problem

    from postetui.app import PostETUIApp  # import after arg parsing: --version stays fast

    unicode = not (args.no_unicode or os.environ.get("POSTETUI_NO_UNICODE"))
    app = PostETUIApp(root, catalog, catalog_path, unicode=unicode)
    if args.smoke_test:
        return smoke_test(app)
    app.run()
    return 0


def smoke_test(app: object) -> int:
    """Headless start + visit every tab. Proves a frozen build can load and render all widgets."""
    from textual.app import App
    from textual.pilot import Pilot

    assert isinstance(app, App)
    visited: list[str] = []

    async def drive(pilot: Pilot[None]) -> None:
        await pilot.pause(0.5)
        for key in "12345":
            await pilot.press(key)
            await pilot.pause(0.2)
            visited.append(pilot.app.active_tab)  # type: ignore[attr-defined]
        pilot.app.exit()

    app.run(headless=True, size=(120, 40), auto_pilot=drive)
    ok = visited == ["scripts", "run", "output", "reports", "rollback"]
    print("smoke test", "passed" if ok else f"FAILED: {visited}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
