"""Script catalog: pydantic models, YAML loading and integrity checks.

Everything PostETUI knows about a script comes from catalog.yaml. Adding a
script means adding a YAML block, never changing code.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

BUNDLED_CATALOG = Path(__file__).resolve().parent.parent / "assets" / "catalog.yaml"

FLAG_RE = re.compile(r"^-{1,2}[A-Za-z][A-Za-z0-9_-]*$")

ParamType = Literal["string", "path", "int", "bool", "enum", "list"]
Interpreter = Literal["powershell", "pwsh", "python"]
ExitStatus = Literal["SUCCESS", "WARN", "FAILED"]
IntegrityState = Literal["OK", "UNPINNED", "MISMATCH", "MISSING", "OUTSIDE_ROOT"]


class CatalogError(Exception):
    """The catalog cannot be loaded, or a script fails its integrity checks."""


def _check_flag(value: str | None, what: str) -> str | None:
    if value is not None and not FLAG_RE.match(value):
        raise ValueError(f"{what} must look like -Name or --name, got {value!r}")
    return value


class Parameter(BaseModel):
    """One script parameter. Drives the generated form field and the argument."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    type: ParamType = "string"
    label: str | None = None
    help: str = ""
    default: Any = None
    required: bool = False
    must_exist: bool = False
    min: int | None = None
    max: int | None = None
    choices: list[str] = Field(default_factory=list)
    flag: str | None = None
    blast_radius: bool = False

    @model_validator(mode="after")
    def _check(self) -> Parameter:
        if self.type == "enum" and not self.choices:
            raise ValueError(f"parameter {self.name}: type enum needs choices")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"parameter {self.name}: min is greater than max")
        if self.must_exist and self.type != "path":
            raise ValueError(f"parameter {self.name}: must_exist only applies to type path")
        _check_flag(self.flag, f"parameter {self.name} flag")
        return self

    @property
    def title(self) -> str:
        """Label shown in the form."""
        return self.label or self.name


class Script(BaseModel):
    """One catalog entry."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    path: str
    interpreter: Interpreter = "powershell"
    sha256: str | None = Field(default=None, pattern=r"^[A-Fa-f0-9]{64}$")
    status: Literal["active", "draft"] = "active"
    tags: list[str] = Field(default_factory=list)
    synopsis: str = ""
    description: str = ""
    safety: list[str] = Field(default_factory=list)
    supports_dry_run: bool = False
    dry_run_flag: str | None = None
    base_args: list[str] = Field(default_factory=list)
    rollback_flag: str | None = None
    manifest_flag: str | None = None
    progress_regex: str | None = None
    report_csv_glob: str | None = None
    log_glob: str | None = None
    backup_glob: str | None = None
    manifest_name: str = "rollback_manifest.csv"
    timeout_seconds: int = Field(default=3600, ge=10)
    exit_codes: dict[int, ExitStatus] = Field(default_factory=lambda: {0: "SUCCESS"})
    one_of_required: list[list[str]] = Field(default_factory=list)
    parameters: list[Parameter] = Field(default_factory=list)

    @field_validator("dry_run_flag", "rollback_flag", "manifest_flag")
    @classmethod
    def _flags(cls, value: str | None) -> str | None:
        return _check_flag(value, "flag")

    @field_validator("base_args")
    @classmethod
    def _base_args(cls, value: list[str]) -> list[str]:
        for flag in value:
            _check_flag(flag, "base_args entry")
        return value

    @field_validator("progress_regex")
    @classmethod
    def _regex(cls, value: str | None) -> str | None:
        if value is None:
            return None
        # Accept .NET style (?<name>...) as written by PowerShell authors.
        value = re.sub(r"\(\?<(?![=!])", "(?P<", value)
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"progress_regex does not compile: {exc}") from exc
        return value

    @model_validator(mode="after")
    def _check(self) -> Script:
        if self.supports_dry_run and not self.dry_run_flag:
            raise ValueError(f"script {self.id}: supports_dry_run needs dry_run_flag")
        names = [p.name for p in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError(f"script {self.id}: duplicate parameter names")
        for group in self.one_of_required:
            unknown = set(group) - set(names)
            if unknown:
                raise ValueError(f"script {self.id}: one_of_required names unknown parameters {sorted(unknown)}")
        return self

    @property
    def progress_pattern(self) -> re.Pattern[str] | None:
        """Compiled progress regex, or None to use the default."""
        return re.compile(self.progress_regex) if self.progress_regex else None

    @property
    def can_rollback(self) -> bool:
        """True when the script exposes its own rollback entry point."""
        return bool(self.rollback_flag and self.manifest_flag and self.backup_glob)

    def exit_status(self, code: int | None) -> ExitStatus:
        """Map a process exit code to SUCCESS / WARN / FAILED."""
        if code is None:
            return "FAILED"
        return self.exit_codes.get(code, "FAILED")


class Settings(BaseModel):
    """Site-wide settings."""

    model_config = ConfigDict(extra="forbid")

    tools_file: str | None = "scripts/tools.txt"
    logs_dir: str = "Logs"
    docs_url: str | None = None
    cancel_grace_seconds: float = Field(default=5.0, ge=0)


class Catalog(BaseModel):
    """The whole catalog.yaml document."""

    model_config = ConfigDict(extra="forbid")

    settings: Settings = Field(default_factory=Settings)
    scripts: list[Script] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> Catalog:
        ids = [s.id for s in self.scripts]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate script ids: {duplicates}")
        return self

    def get(self, script_id: str) -> Script:
        """Return the script with this id or raise KeyError."""
        for script in self.scripts:
            if script.id == script_id:
                return script
        raise KeyError(script_id)


def default_catalog_path(root: Path) -> Path:
    """Use <root>/catalog.yaml when a site has one, else the bundled catalog."""
    site = root / "catalog.yaml"
    return site if site.is_file() else BUNDLED_CATALOG


def load_catalog(path: Path) -> Catalog:
    """Load and validate a catalog file. Raises CatalogError with a readable message."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise CatalogError(f"Catalog not found: {path}\nPass --catalog <file> or restore catalog.yaml.") from None
    except OSError as exc:
        raise CatalogError(f"Cannot read catalog {path}: {exc}") from None

    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        problem = getattr(exc, "problem", None) or exc
        raise CatalogError(f"{path.name} is not valid YAML{where}: {problem}") from None

    try:
        return Catalog.model_validate(data)
    except ValidationError as exc:
        lines = []
        for err in exc.errors():
            loc = ".".join(str(part) for part in err["loc"]) or "(top level)"
            lines.append(f"  - {loc}: {err['msg']}")
        raise CatalogError(f"{path.name} is invalid:\n" + "\n".join(lines)) from None


def file_sha256(path: Path) -> str:
    """SHA-256 of a file as upper-case hex (same format as Get-FileHash)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


@dataclass(frozen=True)
class Integrity:
    """Result of checking a catalog script on disk."""

    path: Path
    state: IntegrityState
    sha256: str | None = None
    modified: float | None = None

    @property
    def runnable(self) -> bool:
        """True when the script may run without an override."""
        return self.state in ("OK", "UNPINNED")


def resolve_script_path(root: Path, script: Script) -> Path:
    """Absolute script path. Raises CatalogError when it escapes the root."""
    root = root.resolve()
    path = (root / script.path).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise CatalogError(f"{script.id}: path {script.path!r} is outside the root {root}") from None
    return path


def check_integrity(root: Path, script: Script) -> Integrity:
    """Check a script exists inside the root and matches its SHA-256 pin."""
    try:
        path = resolve_script_path(root, script)
    except CatalogError:
        return Integrity(root / script.path, "OUTSIDE_ROOT")
    if not path.is_file():
        return Integrity(path, "MISSING")
    try:
        actual = file_sha256(path)
        modified = path.stat().st_mtime
    except OSError:
        return Integrity(path, "MISSING")
    if script.sha256 is None:
        return Integrity(path, "UNPINNED", actual, modified)
    state: IntegrityState = "OK" if actual == script.sha256.upper() else "MISMATCH"
    return Integrity(path, state, actual, modified)


def preflight(root: Path, script: Script, *, override_mismatch: bool = False) -> Path:
    """Return the script path if it may run, else raise CatalogError.

    A hash mismatch is refused unless the operator explicitly overrode it.
    A missing script or one outside the root is always refused.
    """
    integrity = check_integrity(root, script)
    if integrity.state == "OUTSIDE_ROOT":
        raise CatalogError(f"{script.name}: script path escapes the root folder. Refusing to run.")
    if integrity.state == "MISSING":
        raise CatalogError(f"{script.name}: script not found at {integrity.path}")
    if integrity.state == "MISMATCH" and not override_mismatch:
        raise CatalogError(
            f"{script.name}: SHA-256 does not match the catalog pin.\n"
            f"  pinned : {script.sha256}\n  actual : {integrity.sha256}\n"
            "The script changed since it was reviewed. Refusing to run without an override."
        )
    return integrity.path
