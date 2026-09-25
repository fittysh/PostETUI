"""Per-user state in %APPDATA%\\PostETUI\\state.json: last-used values and recent runs."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

MAX_RECENT = 50


class RecentRun(BaseModel):
    """Summary of one finished run."""

    run_id: str
    script_id: str
    mode: str
    status: str
    started: str
    elapsed: float = 0.0
    log_path: str = ""
    csv_path: str = ""
    backup_path: str = ""


class State(BaseModel):
    """Everything PostETUI remembers between sessions."""

    last_values: dict[str, dict[str, Any]] = Field(default_factory=dict)
    recent_runs: list[RecentRun] = Field(default_factory=list)

    def record_run(self, run: RecentRun) -> None:
        """Add a run, newest first, keeping the last MAX_RECENT."""
        self.recent_runs.insert(0, run)
        del self.recent_runs[MAX_RECENT:]

    def last_run(self, script_id: str | None = None) -> RecentRun | None:
        """Newest run, optionally for one script."""
        for run in self.recent_runs:
            if script_id is None or run.script_id == script_id:
                return run
        return None


def state_path() -> Path:
    """%APPDATA%\\PostETUI\\state.json (home folder when APPDATA is unset)."""
    return Path(os.environ.get("APPDATA") or Path.home()) / "PostETUI" / "state.json"


def load_state(path: Path | None = None) -> State:
    """Load state. A corrupt file is kept as state.json.bad and a fresh state returned."""
    path = path or state_path()
    try:
        return State.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return State()
    except (OSError, ValueError, ValidationError):
        try:
            path.replace(path.with_suffix(".json.bad"))
        except OSError:
            pass
        return State()


def save_state(state: State, path: Path | None = None) -> str | None:
    """Write state atomically. Returns a warning instead of raising."""
    path = path or state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        return f"Could not save {path}: {exc}"
    return None
