"""Run tab: parameter form generated from the catalog, command preview, actions.

Keys: Up/Down or Enter move between fields, Esc leaves a field. With no field
focused, d = dry-run and Enter = apply (typed APPLY confirmation).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Select, Static, Switch

from ..core.catalog import Integrity, Parameter, Script
from ..core.runner import ArgumentError, build_argv, build_arguments, command_line, validate_values
from ..theme import MUTED, RED, SOFT_YELLOW
from .confirm import TypedConfirm

if TYPE_CHECKING:
    from ..app import PostETUIApp


class FormSelect(Select[str], inherit_bindings=False):
    """Select that opens on Enter/Space only, so Up/Down stay free for field navigation."""

    BINDINGS = [Binding("enter,space", "show_overlay", "Open", show=False)]


class ListInput(Input):
    """Input that keeps every line of a multi-line paste, e.g. a tool column copied from Excel."""

    def _on_paste(self, event: events.Paste) -> None:
        # Input's own handler (next in the MRO) inserts event.text; it keeps only line 1.
        event.text = ", ".join(line.strip() for line in event.text.splitlines() if line.strip())


def _as_bool(value: Any) -> bool:
    return value if isinstance(value, bool) else str(value or "").strip().lower() in ("1", "true", "yes", "on")


class ParamField(Vertical):
    """Label, input widget, inline error and help text for one parameter."""

    def __init__(self, param: Parameter, value: Any) -> None:
        super().__init__()
        self.param = param
        self.initial = value

    def compose(self) -> ComposeResult:
        param = self.param
        yield Label(param.title + (" *" if param.required else ""), classes="field-label")
        yield self._make_widget()
        yield Static("", classes="field-error")
        if param.help:
            yield Static(param.help, classes="field-help")

    def _make_widget(self) -> Widget:
        param, value, wid = self.param, self.initial, f"f-{self.param.name}"
        if param.type == "bool":
            return Switch(value=_as_bool(value), id=wid)
        if param.type == "enum":
            selected = value if value in param.choices else Select.NULL
            return FormSelect([(c, c) for c in param.choices], value=selected, allow_blank=not param.required, id=wid)
        if param.type == "list":
            text = ", ".join(value) if isinstance(value, list) else str(value or "")
            return ListInput(value=text, placeholder="A, B, C", id=wid)
        if param.type == "int":
            hint = f"{param.min if param.min is not None else ''}..{param.max if param.max is not None else ''}"
            return Input(value="" if value is None else str(value), type="integer", placeholder=hint, id=wid)
        return Input(value=str(value or ""), placeholder=param.type, id=wid)

    @property
    def widget(self) -> Widget:
        """The focusable input widget."""
        return self.query_one(f"#f-{self.param.name}")

    @property
    def value(self) -> Any:
        """Raw value as typed (validation happens in core.runner)."""
        widget = self.widget
        if isinstance(widget, Switch):
            return widget.value
        if isinstance(widget, Select):
            return "" if widget.is_blank() else widget.value
        return cast(Input, widget).value

    def set_error(self, message: str | None) -> None:
        """Show or clear the inline error and red border."""
        error = self.query_one(".field-error", Static)
        error.update(message or "")
        error.set_class(bool(message), "-shown")
        self.widget.set_class(bool(message), "-invalid")


class RunPane(Vertical, can_focus=True):
    """Parameter form, live command preview and the DRY-RUN / APPLY actions."""

    BINDINGS = [
        Binding("d", "dry_run", "Dry-Run"),
        Binding("enter", "apply", "Apply"),
        Binding("c", "copy", "Copy cmd"),
        Binding("ctrl+o", "override", "Override hash", show=False),
        Binding("escape", "leave_field", "Leave field", show=False),
        Binding("up", "move(-1)", "Prev field", show=False),
        Binding("down", "move(1)", "Next field", show=False),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.script: Script | None = None
        self.command = ""
        self.blast = ""

    @property
    def tui(self) -> PostETUIApp:
        return cast("PostETUIApp", self.app)

    def compose(self) -> ComposeResult:
        yield Static("Pick a script on the Scripts tab and press Enter to load it here.", id="run-banner")
        with Horizontal(id="run-body"):
            form = VerticalScroll(id="form", classes="panel")
            form.border_title = "|Parameters|"
            form.can_focus = False
            yield form
            with Vertical(id="run-side"):
                preview = Static("", id="preview", classes="panel")
                preview.border_title = "|Command Preview|"
                yield preview
                yield Static("", id="blast")
                with Horizontal(id="actions"):
                    yield Button("d  DRY-RUN", id="btn-dry", variant="success", disabled=True)
                    yield Button("Enter  APPLY", id="btn-apply", variant="error", disabled=True)
        yield Static(
            "Up/Down/Enter next field  Esc leave field  d dry-run  Enter apply  c copy  ctrl+o override",
            id="run-hint",
        )

    def on_mount(self) -> None:
        for button in self.query(Button):
            button.can_focus = False

    async def load(self, script: Script) -> None:
        """Build the form for a script, pre-filled with last-used values."""
        self.script = script
        saved = self.tui.state.last_values.get(script.id, {})
        values = {p.name: saved.get(p.name, p.default) for p in script.parameters}
        form = self.query_one("#form", VerticalScroll)
        await form.remove_children()
        if script.parameters:
            await form.mount_all([ParamField(p, values[p.name]) for p in script.parameters])
        else:
            await form.mount(Static("This script takes no parameters.", classes="field-help"))
        self.revalidate()
        self.focus()

    def fields(self) -> list[ParamField]:
        return list(self.query(ParamField))

    def values(self) -> dict[str, Any]:
        """Raw values from every field."""
        return {f.param.name: f.value for f in self.fields()}

    def integrity(self) -> Integrity | None:
        return self.tui.integrity(self.script) if self.script else None

    def revalidate(self) -> dict[str, str]:
        """Validate every field, update errors, preview, blast radius and buttons."""
        script = self.script
        if script is None:
            return {}
        coerced, errors = validate_values(script, self.tui.root, self.values())
        for field in self.fields():
            field.set_error(errors.get(field.param.name))

        valid = not errors
        self.query_one("#btn-dry", Button).disabled = not valid or not script.supports_dry_run
        self.query_one("#btn-apply", Button).disabled = not valid
        self.command = ""
        preview = Text()
        if valid:
            try:
                integrity = self.integrity()
                assert integrity is not None
                args = build_arguments(script, self.tui.root, self.values(), dry_run=script.supports_dry_run)
                self.command = command_line(build_argv(script, integrity.path, args))
                preview.append(self.command)
                if script.supports_dry_run:
                    preview.append(f"\n\nAPPLY runs the same command without {script.dry_run_flag}.", style=MUTED)
            except ArgumentError as exc:
                preview.append(str(exc), style=RED)
        else:
            preview.append("Fix the highlighted fields to see the command.", style=MUTED)
        self.query_one("#preview", Static).update(preview)

        blast = Text()
        if errors.get("_form"):
            blast.append(errors["_form"] + "\n", style=f"bold {RED}")
        count = self.blast_radius(coerced)
        self.blast = f"{count} tool(s) will be written." if count is not None else "Target count unknown."
        blast.append("Blast radius: ", style=MUTED)
        blast.append(self.blast, style=f"bold {SOFT_YELLOW}")
        self.query_one("#blast", Static).update(blast)
        self.update_banner()
        return errors

    def blast_radius(self, coerced: dict[str, Any]) -> int | None:
        """Tools touched: list lengths plus tools.txt when a blast_radius switch is on."""
        assert self.script is not None
        total, known = 0, False
        for param in self.script.parameters:
            value = coerced.get(param.name)
            if not param.blast_radius or value is None or value is False:
                continue
            count: int | None
            if isinstance(value, list):
                count = len(value)
            elif value is True:
                count = self.tui.tools_count()
            else:
                count = self.tui.count_list_file(Path(str(value)))
            if count is not None:
                total, known = total + count, True
        return total if known else None

    def update_banner(self) -> None:
        """Script name plus any pin / draft / no-dry-run warning."""
        script, integrity = self.script, self.integrity()
        if script is None or integrity is None:
            return
        text = Text(script.name, style="bold white")
        text.append(f"   {script.id}\n", style=MUTED)
        state = integrity.state
        if state == "MISSING":
            text.append(f"Script file not found: {integrity.path}. Runs are blocked.", style=f"bold {RED}")
        elif state == "OUTSIDE_ROOT":
            text.append("Script path is outside the root folder. Runs are blocked.", style=f"bold {RED}")
        elif state == "MISMATCH" and script.id not in self.tui.overrides:
            text.append(
                "HASH MISMATCH: the script changed since it was pinned. Runs are blocked. "
                "Press ctrl+o and type OVERRIDE to allow it for this session.",
                style=f"bold reverse {RED}",
            )
        elif state == "MISMATCH":
            text.append("Hash mismatch overridden for this session.", style=f"bold {SOFT_YELLOW}")
        elif state == "UNPINNED":
            text.append("Not pinned: run  postetui --print-hashes  and add sha256 to catalog.yaml.", style=SOFT_YELLOW)
        else:
            text.append("Pinned SHA-256 verified.", style="#87d787")
        if script.status == "draft":
            text.append("   Draft entry: parameters not confirmed.", style=MUTED)
        if not script.supports_dry_run:
            text.append("   No dry-run mode: every run writes.", style=f"bold {SOFT_YELLOW}")
        self.query_one("#run-banner", Static).update(text)

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self.revalidate()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        event.stop()
        self.revalidate()

    def on_select_changed(self, event: Select.Changed) -> None:
        event.stop()
        self.revalidate()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.action_move(1)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "btn-dry":
            self.action_dry_run()
        else:
            self.action_apply()

    def action_move(self, delta: int) -> None:
        """Focus the next/previous field; past either end, focus returns to the pane."""
        widgets = [f.widget for f in self.fields()]
        if not widgets:
            return
        focused = self.app.focused
        index = next((i for i, w in enumerate(widgets) if w is focused), None)
        if index is None:
            target = widgets[0 if delta > 0 else -1]
        elif 0 <= index + delta < len(widgets):
            target = widgets[index + delta]
        else:
            self.focus()
            return
        target.focus()
        target.scroll_visible()

    def action_leave_field(self) -> None:
        self.focus()

    def action_dry_run(self) -> None:
        if self.script is None:
            self.notify("Pick a script on the Scripts tab first.", severity="warning")
            return
        if not self.script.supports_dry_run:
            self.notify(f"{self.script.name} has no dry-run mode.", severity="warning")
            return
        if self.revalidate():
            self.notify("Fix the highlighted fields first.", severity="error")
            return
        self.tui.start_run(self.script, self.values(), "DRY-RUN")

    def action_apply(self) -> None:
        script = self.script
        if script is None:
            self.notify("Pick a script on the Scripts tab first.", severity="warning")
            return
        if self.revalidate():
            self.notify("Fix the highlighted fields first.", severity="error")
            return
        values = self.values()
        body = (
            f"[b]{script.name}[/b]\nMode: [b]APPLY[/b] - this writes to the tools.\n"
            f"[b]{self.blast}[/b]\n\n[dim]{self.command}[/dim]"
        )

        def confirmed(ok: bool | None) -> None:
            if ok:
                self.tui.start_run(script, values, "APPLY")

        self.app.push_screen(TypedConfirm("APPLY", f"APPLY {script.name}", body), confirmed)

    def action_copy(self) -> None:
        if self.command:
            self.tui.copy_text(self.command)
        else:
            self.notify("Nothing to copy yet - fix the form first.", severity="warning")

    def action_override(self) -> None:
        integrity = self.integrity()
        script = self.script
        if script is None or integrity is None or integrity.state != "MISMATCH":
            self.notify("There is no hash mismatch to override.", severity="information")
            return
        body = (
            f"[b]{script.name}[/b] does not match its pinned SHA-256.\n\n"
            f"pinned: {script.sha256}\nactual: {integrity.sha256}\n\n"
            "Only continue if you know why the script changed. The override lasts until PostETUI closes."
        )

        def confirmed(ok: bool | None) -> None:
            if ok:
                self.tui.overrides.add(script.id)
                self.update_banner()
                self.notify("Hash mismatch overridden for this session.", severity="warning")

        self.app.push_screen(TypedConfirm("OVERRIDE", "Hash mismatch", body), confirmed)
