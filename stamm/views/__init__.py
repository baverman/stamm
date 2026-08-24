from __future__ import annotations

import curses
from dataclasses import dataclass
from typing import ClassVar, Literal, Protocol, Self

from ..keys import ActionSet, Bindings

GLOBAL_ACTIONS: ActionSet = {
    'back': ('q',),
}

MOVE_ACTIONS: ActionSet = {
    'down': ('j', 'DOWN'),
    'up': ('k', 'UP'),
}

PAGE_ACTIONS: ActionSet = {
    'pageup': ('PAGEUP', '^U'),
    'pagedown': ('PAGEDOWN', '^D'),
    'home': ('HOME',),
    'end': ('END',),
}

MAIL_ACTIONS: ActionSet = {
    'parts': ('v',),
    'reply': ('r',),
    'reply_all': ('g',),
    'forward': ('f',),
}


@dataclass(frozen=True, slots=True)
class ChangeView:
    operation: Literal['keep', 'push', 'replace']
    view: View[ChangeView] | None = None

    @classmethod
    def keep(cls) -> Self:
        return cls('keep')

    @classmethod
    def push(cls, view: View[ChangeView]) -> Self:
        return cls('push', view)

    @classmethod
    def replace(cls, view: View[ChangeView]) -> Self:
        return cls('replace', view)

    def apply(self, stack: list[View[ChangeView]]) -> None:
        if self.operation == 'keep':
            return
        assert self.view is not None
        if self.operation == 'replace':
            stack.pop()
        stack.append(self.view)


class View[T](Protocol):
    def run(self, screen: curses.window) -> T | None: ...


class ActionView[T](View[T], Protocol):
    namespace: ClassVar[str]
    actions: ClassVar[ActionSet]
    compiled_actions: ClassVar[Bindings]
