from __future__ import annotations

from typing import ClassVar

from ..tui import keys, pager
from ..tui import text as tui_text
from . import GLOBAL_ACTIONS, MOVE_ACTIONS, PAGE_ACTIONS, ActionHandler, DefaultActionView, UIContext


class PagerWidget(pager.PagerWidget[UIContext], ActionHandler[None]):
    namespace: ClassVar[str] = 'pager'
    actions: ClassVar[keys.ActionSet] = MOVE_ACTIONS | PAGE_ACTIONS


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
