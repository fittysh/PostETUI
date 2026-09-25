"""Typed confirmation modal: the operator must type a word (APPLY, OVERRIDE)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static


class TypedConfirm(ModalScreen[bool]):
    """Dismisses True only when the exact word is typed. Esc cancels."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, word: str, title: str, body: str) -> None:
        super().__init__()
        self.word = word
        self.title_text = title
        self.body = body

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box") as box:
            box.border_title = f"|{self.title_text}|"
            yield Static(self.body, id="confirm-body")
            yield Static(f"Type [b]{self.word}[/b] and press Enter to continue. Esc cancels.")
            yield Input(placeholder=self.word, id="confirm-input")
            yield Static("", id="confirm-error")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        if event.value.strip() == self.word:
            self.dismiss(True)
        else:
            self.query_one("#confirm-error", Static).update(f"Not confirmed - type {self.word} exactly.")
            event.input.value = ""

    def action_cancel(self) -> None:
        self.dismiss(False)
