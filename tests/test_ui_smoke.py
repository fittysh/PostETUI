"""Textual Pilot smoke tests across all five tabs."""

from __future__ import annotations

import csv
import time
from collections.abc import Callable
from pathlib import Path

from textual.pilot import Pilot
from textual.widgets import DataTable, Static

from postetui.app import PostETUIApp, TooSmallScreen
from postetui.core.catalog import load_catalog
from postetui.core.state import State, save_state
from postetui.widgets.confirm import TypedConfirm
from postetui.widgets.console_view import OutputPane
from postetui.widgets.report_table import ReportsPane
from postetui.widgets.rollback_list import RollbackPane

from .helpers import DEMO_VALUES

SIZE = (120, 40)


def make_app(root: Path, values: dict | None = None, *, unicode: bool = True) -> PostETUIApp:
    state_file = root / "state.json"
    if values is not None:
        save_state(State(last_values={"demo_kla": values}), state_file)
    return PostETUIApp(root, load_catalog(root / "catalog.yaml"), root / "catalog.yaml", unicode=unicode, state_file=state_file)


async def wait_for(pilot: Pilot, condition: Callable[[], bool], timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out waiting for the UI"
        await pilot.pause(0.1)


def console_text(app: PostETUIApp) -> str:
    return "\n".join(line.text for line in app.query_one(OutputPane).console.lines)


def run_finished(app: PostETUIApp) -> bool:
    return app.runner is None and app.query_one(OutputPane).status != "RUNNING"


async def test_all_tabs_reachable_by_tab_and_numbers(demo_root: Path) -> None:
    app = make_app(demo_root)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        seen = [app.active_tab]
        for _ in range(4):
            await pilot.press("tab")
            await pilot.pause()
            seen.append(app.active_tab)
        assert seen == ["scripts", "run", "output", "reports", "rollback"]
        await pilot.press("shift+tab")
        assert app.active_tab == "reports"
        await pilot.press("2")  # on Reports, 1-4 are the status filters
        assert app.active_tab == "reports" and app.query_one(ReportsPane).filter_key == "failed"
        for key, tab in [("5", "rollback"), ("1", "scripts"), ("3", "output"), ("2", "run")]:
            await pilot.press("escape", key)  # escape leaves any focused field first
            await pilot.pause()
            assert app.active_tab == tab
        await pilot.press("backspace")
        await pilot.pause()
        assert app.active_tab == "output"


async def test_scripts_tab_lists_every_catalog_entry(demo_root: Path) -> None:
    app = make_app(demo_root)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        table = app.query_one("#catalog", DataTable)
        assert table.row_count == len(app.catalog.scripts)
        await pilot.press("slash", *"hung", "enter")
        assert table.row_count == 1


async def test_d_dry_runs_with_live_output_and_audit(demo_root: Path) -> None:
    app = make_app(demo_root, DEMO_VALUES)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await pilot.press("d")
        assert app.active_tab == "output"
        await wait_for(pilot, lambda: run_finished(app))
        assert app.query_one(OutputPane).status == "WARN"
        assert "TOOL-A03   WOULD OVERWRITE" in console_text(app)
        assert app.query_one("#summary", Static).has_class("-shown")
        with (demo_root / "Logs" / "postetui_audit.csv").open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert rows[-1]["Mode"] == "DRY-RUN" and rows[-1]["ExitCode"] == "1" and "--dry-run" in rows[-1]["Args"]
        assert rows[-1]["OK"] == "2" and rows[-1]["Failed"] == "1"
        assert app.state.last_run("demo_kla") is not None


async def test_apply_needs_the_typed_word(demo_root: Path) -> None:
    app = make_app(demo_root, DEMO_VALUES)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await pilot.press("enter")  # Scripts -> Run tab with the form
        await pilot.pause()
        assert app.active_tab == "run"
        await pilot.press("enter")  # APPLY -> modal
        await pilot.pause()
        assert isinstance(app.screen, TypedConfirm)
        await pilot.press(*"apply", "enter")  # wrong case: refused
        await pilot.pause()
        assert isinstance(app.screen, TypedConfirm) and app.runner is None
        await pilot.press(*"APPLY", "enter")
        await pilot.pause()
        assert not isinstance(app.screen, TypedConfirm)
        await wait_for(pilot, lambda: run_finished(app) and app.query_one(OutputPane).mode == "APPLY")
        assert any(p.is_dir() for p in (demo_root / "scripts" / "backups").iterdir())


async def test_k_cancels_a_hung_run(demo_root: Path) -> None:
    app = make_app(demo_root)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await pilot.press("down", "d")  # second row: the hung UNC simulator
        await wait_for(pilot, lambda: "simulated hung UNC path" in console_text(app))
        await pilot.press("k")
        await wait_for(pilot, lambda: app.runner is None)
        assert app.query_one(OutputPane).status == "CANCELLED"


async def test_mismatch_and_missing_scripts_are_refused(demo_root: Path) -> None:
    app = make_app(demo_root)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await pilot.press("down", "down", "down", "d")  # tampered script
        await pilot.pause()
        assert app.runner is None and app.active_tab == "scripts"
        assert app.start_run(app.catalog.get("demo_missing"), {}, "APPLY") is False


async def test_tiny_terminal_shows_enlarge_screen(demo_root: Path) -> None:
    app = make_app(demo_root)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await pilot.resize_terminal(60, 20)
        await pilot.pause(0.2)
        assert isinstance(app.screen, TooSmallScreen)
        await pilot.resize_terminal(*SIZE)
        await pilot.pause(0.2)
        assert not isinstance(app.screen, TooSmallScreen)


async def test_reports_tab_loads_and_filters(demo_root: Path) -> None:
    app = make_app(demo_root)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await pilot.press("4")
        await pilot.pause()
        pane = app.query_one(ReportsPane)
        assert pane.current is not None and pane.current.path.name.endswith("20260922_080000.csv")
        await pilot.press("2")
        assert pane.filter_key == "failed" and pane.view is not None and len(pane.view) == 0  # newest: TIMEOUT only
        await pilot.press("4")
        assert pane.filter_key == "timeout" and pane.view is not None and len(pane.view) == 1
        assert str(app.query_one("#card-rate", Static).content) == "75.0 %"


async def test_rollback_is_dry_run_first_and_flags_audit_only(demo_root: Path) -> None:
    app = make_app(demo_root)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await pilot.press("5")
        await pilot.pause()
        pane = app.query_one(RollbackPane)
        assert [s.stamp for s in pane.sets] == ["20260922_080000", "20260921_080000"]
        await pilot.press("enter")  # apply before any dry-run: refused
        await pilot.pause()
        assert app.runner is None and not isinstance(app.screen, TypedConfirm)
        await pilot.press("r")
        await wait_for(pilot, lambda: run_finished(app))
        assert app.query_one(OutputPane).status == "SUCCESS"
        assert "WOULD RESTORE" in console_text(app)
        assert pane.sets[0].manifest in app.rollback_dry_ok
        await pilot.press("5", "down")
        await pilot.pause()
        assert "audit trail only" in str(app.query_one("#verdict", Static).content)


async def test_no_unicode_mode_uses_ascii(demo_root: Path) -> None:
    app = make_app(demo_root, unicode=False)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        assert app.screen.has_class("ascii")
        assert app.get_css_variables()["box"] == "ascii"
        banner = str(app.query_one("#banner", Static).content)
        assert "#####^" in banner and "\u2588" not in banner
