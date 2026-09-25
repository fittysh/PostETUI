from __future__ import annotations

from pathlib import Path

import pytest

from postetui.core.catalog import Catalog, load_catalog

from .helpers import make_demo_root


@pytest.fixture
def demo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # Keep state.json out of the real %APPDATA%.
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    return make_demo_root(tmp_path / "root")


@pytest.fixture
def demo_catalog(demo_root: Path) -> Catalog:
    return load_catalog(demo_root / "catalog.yaml")
