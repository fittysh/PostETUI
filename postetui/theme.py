"""Palette, status colours, box styles, CSS and the PostETUI banner."""

from __future__ import annotations

from rich.text import Text
from textual.theme import Theme

from . import __version__

BACKGROUND = "#1c1c1c"
SURFACE = "#262626"
TEAL = "#5fd7d7"
SOFT_YELLOW = "#f0d98c"
SOFT_GREEN = "#a8d8a0"
MUTED = "#8a8a8a"
RED = "#ff6b6b"

STATUS_COLORS: dict[str, str] = {
    "SUCCESS": "#87d787",
    "READY": SOFT_GREEN,
    "OK": "#87d787",
    "SKIPPED": MUTED,
    "UNKNOWN": MUTED,
    "DRAFT": MUTED,
    "WARN": SOFT_YELLOW,
    "UNPINNED": SOFT_YELLOW,
    "RUNNING": TEAL,
    "FAILED": RED,
    "ERROR": RED,
    "MISMATCH": RED,
    "MISSING": RED,
    "OUTSIDE_ROOT": RED,
    "TIMEOUT": "#d787d7",
    "CANCELLED": "#ffaf5f",
    "DRY-RUN": "#5fd7ff",
    "ROLLBACK-DRY-RUN": "#5fd7ff",
    "APPLY": SOFT_YELLOW,
    "ROLLBACK": SOFT_YELLOW,
}

THEME = Theme(
    name="postetui",
    primary=TEAL,
    secondary=SOFT_YELLOW,
    accent=SOFT_YELLOW,
    foreground="#d0d0d0",
    background=BACKGROUND,
    surface=SURFACE,
    panel="#303030",
    success=SOFT_GREEN,
    warning=SOFT_YELLOW,
    error=RED,
    dark=True,
)

# Micron logo in half blocks: '#' full, '^' upper half, ',' lower half.
# The raw template doubles as the --no-unicode rendering.
LOGO = """\
      ,######,,######,
     ##^    ^##^    ^##
     ##      ##      ##
     ##      ##      ##
    ,##      ##      ##
#####^       ##      ##"""

# figlet -f doom PostETUI
TITLE = r"""______         _   _____ _____ _   _ _____
| ___ \       | | |  ___|_   _| | | |_   _|
| |_/ /__  ___| |_| |__   | | | | | | | |
|  __/ _ \/ __| __|  __|  | | | | | | | |
| | | (_) \__ \ |_| |___  | | | |_| |_| |_
\_|  \___/|___/\__\____/  \_/  \___/ \___/"""

TAGLINE = "Run Post-E automation like a boss."
REPO = "fittysh/PostETUI"
APP_LABEL = f"|PostETUI-{__version__}|"


def status_color(status: str) -> str:
    """Colour for a status word; muted when unknown."""
    return STATUS_COLORS.get(status.upper(), "#d0d0d0")


def status_text(status: str) -> Text:
    """Coloured status cell."""
    return Text(status, style=f"bold {status_color(status)}")


def banner(unicode: bool = True) -> Text:
    """Logo beside the Doom title, then the tagline and credit line."""
    logo = LOGO
    if unicode:
        logo = logo.replace("#", "\u2588").replace("^", "\u2580").replace(",", "\u2584")
    text = Text()
    for logo_line, title_line in zip(logo.splitlines(), TITLE.splitlines(), strict=True):
        text.append(logo_line.ljust(27), style=f"bold {TEAL}")
        text.append(title_line + "\n", style="bold white")
    text.append("\n" + TAGLINE + "\n", style=f"italic {SOFT_YELLOW}")
    heart = "\u2665" if unicode else "<3"
    text.append(f"{REPO}  [with {heart} by Post-E Scanner Team]", style=MUTED)
    return text


CSS = """
Screen { background: $background; }

.panel {
    border: $box $primary 60%;
    border-title-color: $secondary;
    border-title-style: bold;
    border-title-align: left;
}
.panel:focus-within { border: $box $primary; }
DataTable > .datatable--cursor { background: $secondary; color: $background; text-style: bold; }
DataTable:blur > .datatable--cursor { background: $secondary 40%; color: $foreground; }

#topbar {
    height: 4;
    border: $box-strong $primary;
    border-title-align: center;
    border-title-color: $secondary;
    border-title-style: bold;
    padding: 0 1;
}
#topbar Tabs { width: 1fr; height: 2; }
#ctx-path { width: auto; max-width: 42; height: 2; color: $text-muted; content-align: right middle; padding-left: 2; }
#main { height: 1fr; }
Screen.ascii Underline { display: none; }
Screen.ascii Tab.-active { text-style: bold reverse; }

/* Scripts tab */
#home-top { height: 10; }
#banner { width: 73; height: 10; padding: 0 1; }
#env { width: 1fr; height: 10; padding: 0 1; }
#filter { display: none; height: 3; }
#filter.-shown { display: block; }
#home-main { height: 1fr; }
#catalog { width: 2fr; height: 1fr; }
#detail { width: 1fr; min-width: 34; max-width: 64; height: 1fr; padding: 0 1; }

/* Run tab */
#run-banner { height: auto; padding: 0 1; }
#run-body { height: 1fr; }
#form { width: 1fr; height: 1fr; padding: 0 1; }
#run-side { width: 1fr; height: 1fr; }
#preview { height: 1fr; padding: 0 1; }
#blast { height: auto; padding: 0 1; }
#actions { height: 3; }
#actions Button { margin: 0 1; min-width: 16; }
#run-hint { height: 1; color: $text-muted; padding: 0 1; }
ParamField { height: auto; }
ParamField .field-label { color: $secondary; text-style: bold; }
ParamField .field-help { color: $text-muted; }
ParamField .field-error { color: $error; height: auto; display: none; }
ParamField .field-error.-shown { display: block; }
ParamField .-invalid { border: tall $error; }
ParamField Switch { width: auto; }

/* Output tab */
#out-head { height: 1; padding: 0 1; }
#out-bar { height: 1; padding: 0 1; }
#out-bar ProgressBar { width: 1fr; }
#out-counters { height: 1; padding: 0 1; }
#console { height: 1fr; }
#summary { height: auto; max-height: 14; padding: 0 1; display: none; }
#summary.-shown { display: block; }
Screen.ascii Bar { display: none; }

/* Reports tab */
#cards { height: 5; }
.card { width: 1fr; height: 5; border: $box $primary 60%; border-title-color: $secondary; content-align: center middle; text-style: bold; }
#rep-body { height: 1fr; }
#rep-left { width: 38; }
#files { height: 1fr; }
#trend { height: 7; padding: 0 1; }
#spark { height: 3; }
#rep-right { width: 1fr; }
#rows { height: 2fr; }
#offenders { height: 1fr; }

/* Rollback tab */
#sets { height: 1fr; }
#verdict { height: auto; padding: 0 1; }
#restore { height: 1fr; }
#rb-hint { height: 1; color: $text-muted; padding: 0 1; }

/* Modals */
TypedConfirm { align: center middle; }
#confirm-box { width: 72; height: auto; border: $box-strong $error; padding: 1 2; background: $surface; }
#confirm-box Input { margin-top: 1; }
#confirm-error { color: $error; height: auto; }
TooSmallScreen { align: center middle; }
#too-small { width: auto; height: auto; border: $box $warning; padding: 1 2; }
"""
