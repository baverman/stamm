from __future__ import annotations

from dataclasses import dataclass, field

from . import text
from .views import BaseContext


@dataclass
class PagerWidget:
    lines: text.TextLines
    offset: int = field(default=0, init=False)
    _cached_lines: tuple[int, object, list[list[text.TextSpan]] | None] = (0, None, None)

    def get_lines(self, width: int) -> list[list[text.TextSpan]]:
        old_width, old_lines, wrapped = self._cached_lines
        if wrapped is None or old_width != width or old_lines is not self.lines:
            wrapped = text.wrap_spans(self.lines, width)
            self._cached_lines = width, self.lines, wrapped
        return wrapped

    def _scroll_bounds(self, context: BaseContext) -> tuple[int, int]:
        height, width = context.screen.getmaxyx()
        page_size = max(1, height)
        return page_size, max(0, len(self.get_lines(width)) - page_size)

    def draw(self, context: BaseContext) -> None:
        window = context.screen
        window.erase()
        height, width = window.getmaxyx()
        lines = self.get_lines(width)
        page_size = max(1, height)
        max_offset = max(0, len(lines) - page_size)
        self.offset = min(self.offset, max_offset)
        for row, line in enumerate(lines[self.offset : self.offset + page_size]):
            x = 0
            for item in line:
                text.put(window, row, x, item.text, max(0, width - x), item.attr)
                x += item.width
        window.refresh()

    def on_down(self, context: BaseContext) -> None:
        _page_size, max_offset = self._scroll_bounds(context)
        self.offset = min(max_offset, self.offset + 1)

    def on_up(self, context: BaseContext) -> None:
        self.offset = max(0, self.offset - 1)

    def on_pageup(self, context: BaseContext) -> None:
        page_size, _max_offset = self._scroll_bounds(context)
        self.offset = max(0, self.offset - page_size)

    def on_pagedown(self, context: BaseContext) -> None:
        page_size, max_offset = self._scroll_bounds(context)
        self.offset = min(max_offset, self.offset + page_size)

    def on_home(self, context: BaseContext) -> None:
        self.offset = 0

    def on_end(self, context: BaseContext) -> None:
        _page_size, max_offset = self._scroll_bounds(context)
        self.offset = max_offset
