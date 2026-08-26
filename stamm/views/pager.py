from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from ..tui import keys
from ..tui import text as tui_text
from . import GLOBAL_ACTIONS, MOVE_ACTIONS, PAGE_ACTIONS, ActionHandler, DefaultActionView, UIContext


@dataclass(slots=True)
class PagerWidget(ActionHandler[None]):
    namespace: ClassVar[str] = 'pager'
    actions: ClassVar[keys.ActionSet] = MOVE_ACTIONS | PAGE_ACTIONS

    lines: tui_text.TextLines
    offset: int = field(default=0, init=False)
    visible: int = field(default=1, init=False)
    maximum: int = field(default=0, init=False)
    _cached_lines: tuple[int, object, list[list[tui_text.TextSpan]] | None] = (0, None, None)

    def get_lines(self, width: int) -> list[list[tui_text.TextSpan]]:
        oldw, oldobj, wrapped = self._cached_lines
        if wrapped is None or oldw != width or oldobj is not self.lines:
            wrapped = tui_text.wrap_spans(self.lines, width)
            self._cached_lines = width, self.lines, wrapped
        return wrapped

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
                tui_text.put(window, row, x, span.text, max(0, width - x), span.attr)
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

    def __init__(self, title: str, lines: tui_text.TextLines) -> None:
        super().__init__(lines)
        self.title = title

    def draw(self, context: UIContext) -> None:
        window = context.screen
        window.erase()
        height, width = window.getmaxyx()
        tui_text.put(window, 0, 0, self.title.ljust(width), width, context.theme.header)
        if height > 1:
            super().draw(context.subcontext(height - 1, width, 1, 0))
        window.refresh()
