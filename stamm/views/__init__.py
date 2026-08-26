from __future__ import annotations

import curses
from dataclasses import dataclass

from ..config import config, update_known_actions
from ..theme import Theme
from ..tui import keys, views

GLOBAL_ACTIONS: keys.ActionSet = {
    'back': ('q',),
}

MOVE_ACTIONS: keys.ActionSet = {
    'down': ('j', 'DOWN'),
    'up': ('k', 'UP'),
}

PAGE_ACTIONS: keys.ActionSet = {
    'pageup': ('PAGEUP', '^U'),
    'pagedown': ('PAGEDOWN', '^D'),
    'home': ('HOME',),
    'end': ('END',),
}

MAIL_ACTIONS: keys.ActionSet = {
    'parts': ('v',),
    'reply': ('r',),
    'reply_all': ('g',),
    'forward': ('f',),
}


@dataclass(frozen=True, slots=True)
class UIContext(views.Context[Theme]):
    screen: curses.window
    theme: Theme


Transition = views.Transition[UIContext]
type View[T] = views.View[UIContext, T]


class ActionView[T](views.ActionView[UIContext, T]):
    def get_bindings(self) -> keys.Bindings:
        return compile_actions(self.namespace, self.actions)


class ActionHandler[T](views.ActionHandler[UIContext, T]): ...


class DefaultActionView(ActionView[Transition]):
    def on_back(self, context: UIContext) -> Transition | None:
        return Transition.close()


def compile_actions(namespace: str, actions: keys.ActionSet) -> keys.Bindings:
    return keys.compile_bindings(namespace, actions, config.keys.get(namespace) or {})


def setup() -> None:
    from .choose import ChooseView
    from .index import IndexView
    from .message import MessageView
    from .pager import PagerView, PagerWidget
    from .parts import PartsView

    for view in (IndexView, MessageView, PartsView, PagerWidget, PagerView, ChooseView):
        update_known_actions(view.namespace, view.actions)
