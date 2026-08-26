from __future__ import annotations

import curses
from typing import cast

from stamm.theme import Theme
from stamm.views import UIContext
from stamm.views.pager import PagerView, PagerWidget


class _Window:
    def __init__(self, height: int, width: int) -> None:
        self.height = height
        self.width = width
        self.writes: list[tuple[int, int, str, int, int]] = []
        self.derived: tuple[int, int, int, int, _Window] | None = None

    def erase(self) -> None:
        pass

    def getmaxyx(self) -> tuple[int, int]:
        return self.height, self.width

    def addnstr(self, y: int, x: int, text: str, width: int, attr: int) -> None:
        self.writes.append((y, x, text, width, attr))

    def refresh(self) -> None:
        pass

    def derwin(self, height: int, width: int, y: int, x: int) -> _Window:
        child = _Window(height, width)
        self.derived = height, width, y, x, child
        return child


def _context(window: _Window) -> UIContext:
    return UIContext(cast(curses.window, window), Theme())


def test_pager_widget_draws_text_from_first_row() -> None:
    window = _Window(3, 20)

    PagerWidget('body').draw(_context(window))

    assert window.writes == [(0, 0, 'body', 19, 0)]
    assert window.derived is None


def test_pager_view_draws_header_above_pager_subwindow() -> None:
    window = _Window(4, 20)

    PagerView('Title', 'body').draw(_context(window))

    assert window.writes == [(0, 0, 'Title'.ljust(20), 20, 0)]
    assert window.derived is not None
    height, width, y, x, child = window.derived
    assert (height, width, y, x) == (3, 20, 1, 0)
    assert child.writes == [(0, 0, 'body', 19, 0)]
