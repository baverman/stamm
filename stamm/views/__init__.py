from __future__ import annotations

import curses
from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar, Literal, Protocol, Self, cast

from .. import keys
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
    operation: Literal['close', 'push', 'replace']
    view: View[ChangeView] | None = None

    @classmethod
    def close(cls) -> Self:
        return cls('close')

    @classmethod
    def push(cls, view: View[ChangeView]) -> Self:
        return cls('push', view)

    @classmethod
    def replace(cls, view: View[ChangeView]) -> Self:
        return cls('replace', view)

    def apply(self, stack: list[View[ChangeView]]) -> None:
        if self.operation == 'close':
            stack.pop()
            return
        assert self.view is not None
        if self.operation == 'replace':
            stack.pop()
        stack.append(self.view)


class View[T](Protocol):
    def run(self, screen: curses.window) -> T: ...


class ActionView[T](View[T], Protocol):
    namespace: ClassVar[str]
    actions: ClassVar[ActionSet]
    compiled_actions: ClassVar[Bindings]


class HandlerView[T](ActionView[T]):
    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        missing = [f'on_{action}' for action in cls.actions if not callable(getattr(cls, f'on_{action}', None))]
        if missing:
            raise TypeError(f'{cls.__name__} is missing action handlers: {", ".join(missing)}')

    @abstractmethod
    def draw(self, screen: curses.window) -> None: ...

    def run(self, screen: curses.window) -> T:
        while True:
            self.draw(screen)
            action, _ch = keys.read(screen, self.compiled_actions)
            if action is None:
                continue
            handler = cast(Callable[[curses.window], T | None], getattr(self, f'on_{action}'))
            result = handler(screen)
            if result is not None:
                return result


class ChangeViewHandlerMixin:
    def on_back(self, screen: curses.window) -> ChangeView | None:
        return ChangeView.close()
