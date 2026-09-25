from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from postetui.core.catalog import (
    BUNDLED_CATALOG,
    Catalog,
    CatalogError,
    check_integrity,
    file_sha256,
    load_catalog,
    preflight,
)


def write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "catalog.yaml"
    path.write_text(data if isinstance(data, str) else yaml.safe_dump(data), encoding="utf-8")
    return path


def test_bundled_catalog_is_valid() -> None:
    catalog = load_catalog(BUNDLED_CATALOG)
    kla = catalog.get("kla_recipe_proliferate")
    assert len(catalog.scripts) == 5
    assert kla.supports_dry_run and kla.dry_run_flag == "-DryRun"
    assert kla.base_args == ["-NonInteractive", "-Force"]
    assert kla.progress_pattern is not None and "(?P<idx>" in kla.progress_regex
    assert catalog.get("mam_reports_autotrigger").interpreter == "python"


def test_invalid_yaml_names_the_line(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="line"):
        load_catalog(write(tmp_path, "scripts:\n  - id: a\n    name: 'unterminated\n"))


def test_unknown_field_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="bogus"):
        load_catalog(write(tmp_path, {"scripts": [{"id": "a", "name": "A", "path": "a.ps1", "bogus": 1}]}))


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    entry = {"id": "a", "name": "A", "path": "a.ps1"}
    with pytest.raises(CatalogError, match="duplicate"):
        load_catalog(write(tmp_path, {"scripts": [entry, entry]}))


def test_dry_run_needs_a_flag(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="dry_run_flag"):
        load_catalog(write(tmp_path, {"scripts": [{"id": "a", "name": "A", "path": "a.ps1", "supports_dry_run": True}]}))


def test_missing_catalog_is_actionable(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="--catalog"):
        load_catalog(tmp_path / "nope.yaml")


def _catalog(path: str, sha: str | None = None) -> Catalog:
    return Catalog.model_validate({"scripts": [{"id": "a", "name": "A", "path": path, "sha256": sha}]})


def test_path_outside_root_is_refused(tmp_path: Path) -> None:
    (tmp_path / "evil.ps1").write_text("x")
    root = tmp_path / "root"
    root.mkdir()
    script = _catalog("../evil.ps1").scripts[0]
    assert check_integrity(root, script).state == "OUTSIDE_ROOT"
    with pytest.raises(CatalogError, match="escapes"):
        preflight(root, script)


def test_hash_mismatch_is_refused_unless_overridden(tmp_path: Path) -> None:
    (tmp_path / "a.ps1").write_text("Write-Host hi")
    script = _catalog("a.ps1", "0" * 64).scripts[0]
    assert check_integrity(tmp_path, script).state == "MISMATCH"
    with pytest.raises(CatalogError, match="does not match"):
        preflight(tmp_path, script)
    assert preflight(tmp_path, script, override_mismatch=True) == (tmp_path / "a.ps1").resolve()


def test_pinned_and_unpinned_scripts_run(tmp_path: Path) -> None:
    path = tmp_path / "a.ps1"
    path.write_text("Write-Host hi")
    assert check_integrity(tmp_path, _catalog("a.ps1", file_sha256(path)).scripts[0]).state == "OK"
    assert check_integrity(tmp_path, _catalog("a.ps1", file_sha256(path).lower()).scripts[0]).state == "OK"
    assert check_integrity(tmp_path, _catalog("a.ps1").scripts[0]).state == "UNPINNED"


def test_missing_script_is_refused(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="not found"):
        preflight(tmp_path, _catalog("gone.ps1").scripts[0])
