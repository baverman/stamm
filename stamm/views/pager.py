from __future__ import annotations

import curses
from dataclasses import dataclass
from typing import ClassVar

from .. import keys, ui
from . import MOVE_ACTIONS, PAGE_ACTIONS


@dataclass(frozen=True, slots=True)
class PagerView:
    namespace: ClassVar[str] = 'pager'
    actions: ClassVar[keys.ActionSet] = MOVE_ACTIONS | PAGE_ACTIONS
    compiled_actions: ClassVar[keys.Bindings] = {}

    title: str
    text: str
    theme: ui.CursesTheme

    def run(self, screen: curses.window) -> keys.Key:
        """Display text and return the first event that is not a scroll action."""
        offset = 0
        window = screen
        while True:
            window.erase()
            height, width = window.getmaxyx()
            lines = ui.wrap_text(self.text, width - 1)
            visible = max(1, height - 1)
            maximum = max(0, len(lines) - visible)
            offset = min(offset, maximum)
            ui.put(window, 0, 0, self.title.ljust(width), width, self.theme.header)
            for row, line in enumerate(lines[offset : offset + visible], 1):
                ui.put(window, row, 0, line, width - 1)
            window.refresh()
            action, ch = keys.read(window, self.compiled_actions)
            if action == 'down':
                offset = min(maximum, offset + 1)
            elif action == 'up':
                offset = max(0, offset - 1)
            elif action == 'pageup':
                offset = max(0, offset - visible)
            elif action == 'pagedown':
                offset = min(maximum, offset + visible)
            elif action == 'home':
                offset = 0
            elif action == 'end':
                offset = maximum
            else:
                return ch
