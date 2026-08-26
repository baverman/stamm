from __future__ import annotations

from typing import ClassVar

from ..tui import keys, pager, text
from . import GLOBAL_ACTIONS, MOVE_ACTIONS, PAGE_ACTIONS, ActionHandler, DefaultActionView, Transition, UIContext


class PagerWidget(pager.PagerWidget, ActionHandler[None]):
    namespace: ClassVar[str] = 'pager'
    actions: ClassVar[keys.ActionSet] = MOVE_ACTIONS | PAGE_ACTIONS


class PagerView(DefaultActionView):
    namespace: ClassVar[str] = 'pager'
    actions: ClassVar[keys.ActionSet] = GLOBAL_ACTIONS

    def __init__(self, title: str, lines: text.TextLines) -> None:
        self.title = title
        self.pager = PagerWidget(lines)

    def help_action_sets(self) -> tuple[tuple[str, keys.ActionSet], ...]:
        return super().help_action_sets() + ((PagerWidget.namespace, PagerWidget.actions),)

    def draw(self, context: UIContext) -> None:
        window = context.screen
        window.erase()
        height, width = window.getmaxyx()
        text.put(window, 0, 0, self.title.ljust(width), width, context.theme.header)
        if height > 1:
            self.pager.draw(context.subcontext(height - 1, width, 1, 0))
        window.refresh()

    def on_unknown(self, context: UIContext, ch: keys.Key) -> Transition | None:
        height, width = context.screen.getmaxyx()
        if height <= 1:
            return None
        return self.pager.handle_key(context.subcontext(height - 1, width, 1, 0), ch)
