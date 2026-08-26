from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from .. import ui
from ..tui import keys
from . import GLOBAL_ACTIONS, MOVE_ACTIONS, PAGE_ACTIONS, ActionHandler, DefaultActionView, UIContext


@dataclass(slots=True)
class PagerWidget(ActionHandler[None]):
    namespace: ClassVar[str] = 'pager'
    actions: ClassVar[keys.ActionSet] = MOVE_ACTIONS | PAGE_ACTIONS

    text: str | tuple[ui.TextSpan, ...]
    offset: int = field(default=0, init=False)
    visible: int = field(default=1, init=False)
    maximum: int = field(default=0, init=False)
    _cached_lines: tuple[int, object, list[list[ui.TextSpan]] | None] = (0, None, None)

    def get_lines(self, width: int) -> list[list[ui.TextSpan]]:
        oldw, oldobj, lines = self._cached_lines
        if lines is None or oldw != width or oldobj is not self.text:
            spans = (ui.span(self.text),) if isinstance(self.text, str) else self.text
            lines = ui.wrap_spans(spans, width - 1)
            self._cached_lines = width, self.text, lines
        else:
            return lines
        return lines

    def draw(self, context: UIContext) -> None:
        window = context.screen
        window.erase()
        height, width = window.getmaxyx()
        lines = self.get_lines(width)
        self.visible = max(1, height)
        self.maximum = max(0, len(lines) - self.visible)
        self.offset = min(self.offset, self.maximum)
        for row, line in enumerate(lines[self.offset : self.offset + self.visible]):
            x = 0
            for span in line:
                ui.put(window, row, x, span.text, max(0, width - 1 - x), span.attr)
                x += span.width
        window.refresh()

    def on_down(self, context: UIContext) -> None:
        self.offset = min(self.maximum, self.offset + 1)

    def on_up(self, context: UIContext) -> None:
        self.offset = max(0, self.offset - 1)

    def on_pageup(self, context: UIContext) -> None:
        self.offset = max(0, self.offset - self.visible)

    def on_pagedown(self, context: UIContext) -> None:
        self.offset = min(self.maximum, self.offset + self.visible)

    def on_home(self, context: UIContext) -> None:
        self.offset = 0

    def on_end(self, context: UIContext) -> None:
        self.offset = self.maximum


class PagerView(PagerWidget, DefaultActionView):
    actions: ClassVar[keys.ActionSet] = GLOBAL_ACTIONS | PagerWidget.actions

    def __init__(self, title: str, text: str | tuple[ui.TextSpan, ...]) -> None:
        super().__init__(text)
        self.title = title

    def draw(self, context: UIContext) -> None:
        window = context.screen
        window.erase()
        height, width = window.getmaxyx()
        ui.put(window, 0, 0, self.title.ljust(width), width, context.theme.header)
        if height > 1:
            super().draw(context.subcontext(height - 1, width, 1, 0))
        window.refresh()
