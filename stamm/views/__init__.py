from __future__ import annotations

from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar, Literal, Protocol, Self, cast

from .. import keys, ui
from ..config import config
from ..keys import ActionSet, Bindings, Key

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
    def run(self, context: ui.UIContext) -> T: ...


class ActionSpec:
    namespace: ClassVar[str]
    actions: ClassVar[ActionSet]


class ActionHandler[T](ActionSpec):
    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        missing = [f'on_{action}' for action in cls.actions if not callable(getattr(cls, f'on_{action}', None))]
        if missing:
            raise TypeError(f'{cls.__name__} is missing action handlers: {", ".join(missing)}')

    def handle(self, context: ui.UIContext, action: str | None, ch: Key) -> T | None:
        if action is None:
            return self.on_unknown(context, ch)
        return cast(Callable[[ui.UIContext], T | None], getattr(self, f'on_{action}'))(context)

    def on_unknown(self, context: ui.UIContext, ch: Key) -> T | None:
        return None


class ActionView[T](View[T], ActionHandler[T]):
    actions = {}

    @abstractmethod
    def draw(self, context: ui.UIContext) -> None: ...

    def run(self, context: ui.UIContext) -> T:
        bindings = compile_actions(self.namespace, self.actions)
        while True:
            self.draw(context)
            action, ch = keys.read(context.screen, bindings)
            result = self.handle(context, action, ch)
            if result is not None:
                return result


class DefaultActionView(ActionView[ChangeView]):
    def on_back(self, context: ui.UIContext) -> ChangeView | None:
        return ChangeView.close()


def compile_actions(namespace: str, actions: ActionSet) -> Bindings:
    return keys.compile_bindings(namespace, actions, config.keys.get(namespace) or {})
