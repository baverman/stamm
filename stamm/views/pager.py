from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from .. import keys, ui
from . import GLOBAL_ACTIONS, MOVE_ACTIONS, PAGE_ACTIONS, ActionHandler, DefaultActionView


@dataclass(slots=True)
class PagerWidget(ActionHandler[None]):
    namespace: ClassVar[str] = 'pager'
    actions: ClassVar[keys.ActionSet] = MOVE_ACTIONS | PAGE_ACTIONS
    compiled_actions: ClassVar[keys.Bindings] = {}

    title: str
    text: str
    offset: int = field(default=0, init=False)
    visible: int = field(default=1, init=False)
    maximum: int = field(default=0, init=False)

    def draw(self, context: ui.UIContext) -> None:
        window = context.screen
        window.erase()
        height, width = window.getmaxyx()
        lines = ui.wrap_text(self.text, width - 1)
        self.visible = max(1, height - 1)
        self.maximum = max(0, len(lines) - self.visible)
        self.offset = min(self.offset, self.maximum)
        ui.put(window, 0, 0, self.title.ljust(width), width, context.theme.header)
        for row, line in enumerate(lines[self.offset : self.offset + self.visible], 1):
            ui.put(window, row, 0, line, width - 1)
        window.refresh()

    def on_down(self, context: ui.UIContext) -> None:
        self.offset = min(self.maximum, self.offset + 1)

    def on_up(self, context: ui.UIContext) -> None:
        self.offset = max(0, self.offset - 1)

    def on_pageup(self, context: ui.UIContext) -> None:
        self.offset = max(0, self.offset - self.visible)

    def on_pagedown(self, context: ui.UIContext) -> None:
        self.offset = min(self.maximum, self.offset + self.visible)

    def on_home(self, context: ui.UIContext) -> None:
        self.offset = 0

    def on_end(self, context: ui.UIContext) -> None:
        self.offset = self.maximum


class PagerView(PagerWidget, DefaultActionView):
    actions: ClassVar[keys.ActionSet] = GLOBAL_ACTIONS | PagerWidget.actions
