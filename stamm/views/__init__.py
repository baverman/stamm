from __future__ import annotations

import curses
from dataclasses import dataclass
from functools import cached_property

from ..config import config, update_known_actions
from ..theme import Theme
from ..tui import keys, text, views

GLOBAL_ACTIONS: keys.ActionSet = {
    'back': ('q',),
    'help': ('?',),
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

    def subcontext(self, height: int, width: int, y: int, x: int) -> UIContext:
        return UIContext(self.screen.derwin(height, width, y, x), self.theme)


Transition = views.Transition[UIContext]
type View[T] = views.View[UIContext, T]


class ActionHandler[T](views.ActionHandler[UIContext, T]):
    @cached_property
    def action_resolver(self) -> views.ActionResolver:
        binds = compile_actions(self.namespace, self.actions)
        return binds.get


class ActionView[T](ActionHandler[T], views.ActionView[UIContext, T]): ...


class DefaultActionView(ActionView[Transition]):
    def help_action_sets(self) -> tuple[tuple[str, keys.ActionSet], ...]:
        return ((self.namespace, self.actions),)

    def on_back(self, context: UIContext) -> Transition | None:
        return Transition.close()

    def on_help(self, context: UIContext) -> Transition:
        from .pager import PagerView

        bindings = keys.describe_binding_sets(
            tuple(
                (namespace, actions, config.keys.get(namespace) or {}) for namespace, actions in self.help_action_sets()
            )
        )
        key_width = max((len(key) for key, _action in bindings), default=0)
        lines = text.span_lines('\n'.join(f'{key:<{key_width}}  {action}' for key, action in bindings))
        return Transition.push(PagerView('Help', lines))


def compile_actions(namespace: str, actions: keys.ActionSet) -> keys.Bindings:
    return keys.compile_bindings(namespace, actions, config.keys.get(namespace) or {})


def setup() -> None:
    from ..tui.choice import ChoiceView
    from .index import IndexView
    from .message import MessageView
    from .pager import PagerView, PagerWidget
    from .parts import PartsView

    for view in (IndexView, MessageView, PartsView, PagerWidget, PagerView, ChoiceView):
        update_known_actions(view.namespace, view.actions)
