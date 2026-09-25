"""Regenerate the SVG screenshots in docs/img used by OPERATOR_GUIDE.md.

    .venv\\Scripts\\python docs\\screenshots.py

Runs the real app against the demo root from tests/helpers.py (fake scripts,
no tools touched). Host and user are replaced with neutral values.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import postetui.app as app_module  # noqa: E402
from postetui.core.catalog import load_catalog  # noqa: E402
from postetui.core.state import State, save_state  # noqa: E402
from tests.helpers import DEMO_VALUES, make_demo_root  # noqa: E402

OUT = REPO / "docs" / "img"
SIZE = (120, 36)


async def main() -> None:
    app_module.current_host = lambda: "TOOLPC-01"  # type: ignore[assignment]
    app_module.current_user = lambda: "technician"  # type: ignore[assignment]
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="PostETUI-demo-") as tmp:
        root = make_demo_root(Path(tmp) / "root")
        state_file = Path(tmp) / "state.json"
        save_state(State(last_values={"demo_kla": DEMO_VALUES}), state_file)
        app = app_module.PostETUIApp(root, load_catalog(root / "catalog.yaml"), root / "catalog.yaml", state_file=state_file)

        async with app.run_test(size=SIZE) as pilot:

            async def shot(name: str, wait: float = 0.3) -> None:
                await pilot.pause(wait)
                app.save_screenshot(filename=f"{name}.svg", path=str(OUT))
                print("wrote", OUT / f"{name}.svg")

            await pilot.pause(3)  # PowerShell version probe
            await shot("01-scripts")
            await pilot.press("enter")
            await shot("02-run")
            await pilot.press("enter")
            await shot("03-confirm-apply")
            await pilot.press("escape", "d")
            deadline = time.monotonic() + 30
            while app.runner is not None and time.monotonic() < deadline:
                await pilot.pause(0.2)
            await shot("04-output")
            await pilot.press("4")
            await shot("05-reports")
            await pilot.press("5")
            await shot("06-rollback")


if __name__ == "__main__":
    asyncio.run(main())
