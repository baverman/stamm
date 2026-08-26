from __future__ import annotations

import curses
from collections.abc import Iterable
from typing import cast


class Window:
    def __init__(self, height: int = 12, width: int = 80, keys: Iterable[str | int] = ()) -> None:
        self.height = height
        self.width = width
        self.keys = iter(keys)
        self.writes: list[tuple[int, int, str, int, int]] = []
        self.moves: list[tuple[int, int]] = []
        self.derived: tuple[int, int, int, int, Window] | None = None

    def as_curses(self) -> curses.window:
        return cast(curses.window, self)

    def erase(self) -> None:
        pass

    def getmaxyx(self) -> tuple[int, int]:
        return self.height, self.width

    def addnstr(self, y: int, x: int, text: str, width: int, attr: int) -> None:
        self.writes.append((y, x, text, width, attr))

    def move(self, y: int, x: int) -> None:
        self.moves.append((y, x))

    def refresh(self) -> None:
        pass

    def get_wch(self) -> str | int:
        return next(self.keys)

    def derwin(self, height: int, width: int, y: int, x: int) -> curses.window:
        child = Window(height, width)
        self.derived = height, width, y, x, child
        return child.as_curses()
