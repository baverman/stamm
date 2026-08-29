from __future__ import annotations

import curses
from abc import abstractmethod, abstractproperty
from dataclasses import dataclass
from typing import Any, Callable, ClassVar, Literal, Protocol, Self, cast

from . import keys
from .theme import BaseTheme


class Context[T: BaseTheme](Protocol):
    @property
    def screen(self) -> curses.window: ...

    @property
    def theme(self) -> T: ...


type BaseContext = Context[BaseTheme]


class View[C: Context[Any], T](Protocol):
    def run(self, context: C) -> T: ...


@dataclass(frozen=True)
class Transition[C: Context[Any]]:
    operation: Literal['close', 'push', 'replace']
    view: View[C, Transition[C]] | None = None

    @classmethod
    def close(cls) -> Self:
        return cls('close')

    @classmethod
    def push(cls, view: View[C, Transition[C]]) -> Self:
        return cls('push', view)

    @classmethod
    def replace(cls, view: View[C, Transition[C]]) -> Self:
        return cls('replace', view)

    def apply(self, stack: list[View[C, Transition[C]]]) -> None:
        if self.operation == 'close':
            stack.pop()
            return
        assert self.view is not None
        if self.operation == 'replace':
            stack.pop()
        stack.append(self.view)


class ActionSpec(Protocol):
    namespace: ClassVar[str]
    actions: ClassVar[keys.ActionSet]


ActionResolver = Callable[[keys.Key], keys.Binding | None]


class ActionHandler[C: Context[Any], T](ActionSpec):
    actions = {}

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        missing = [f'on_{action}' for action in cls.actions if not callable(getattr(cls, f'on_{action}', None))]
        if missing:
            raise TypeError(f'{cls.__name__} is missing action handlers: {", ".join(missing)}')

    @abstractproperty
    def action_resolver(self) -> ActionResolver: ...

    def handle(self, context: C, binding: keys.Binding) -> T | None:
        handler = cast(Callable[..., T | None], getattr(self, f'on_{binding.action}'))
        return handler(context, **binding.modifiers)

    def handle_key(self, context: C, ch: keys.Key) -> T | None:
        binding = self.action_resolver(ch)
        if binding:
            return self.handle(context, binding)
        else:
            return self.on_unknown(context, ch)

    def on_unknown(self, context: C, ch: keys.Key) -> T | None:
        return None


class ActionView[C: Context[Any], T](View[C, T], ActionHandler[C, T]):
    @abstractmethod
    def draw(self, context: C) -> None: ...

    def run(self, context: C) -> T:
        while True:
            self.draw(context)
            result = self.handle_key(context, context.screen.get_wch())
            if result is not None:
                return result
