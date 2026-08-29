from __future__ import annotations

import curses
from pathlib import Path

from .compose import ComposeData
from .config import config
from .message import parse_message
from .mime import MimeManager
from .state import MaildirState
from .tui import text
from .tui.choice import ChoiceView
from .views import Transition, UIContext, View
from .views.compose import ComposeView
from .views.index import IndexView
from .views.message import MessageView, render_body
from .views.pager import PagerView


class App:
    def __init__(self, context: UIContext):
        self.context = context
        self.maildirs: dict[Path, MaildirState] = {}
        self.mime = MimeManager(config)
        self.stack: list[View[Transition]] = []

    def maildir_view(self, path: Path) -> IndexView:
        key = path.resolve()
        state = self.maildirs.get(key)
        reconcile = state is None
        if state is None:
            state = MaildirState.open(path)
            self.maildirs[key] = state
        return IndexView(
            state,
            self.mime,
            self.maildir_view,
            reconcile=reconcile,
        )

    def open_maildir(self, path: Path) -> None:
        self.stack.append(self.maildir_view(path))

    def open_composer(self, data: ComposeData) -> None:
        self.stack.append(ComposeView(data, lambda _notice, _is_sent: None))

    def open_message(self, path: Path) -> None:
        path = path.resolve()
        message = parse_message(path)
        self.stack.append(MessageView(message, render_body(message, self.mime), self.mime, None, str(path), path))

    def confirm_exit(self) -> bool:
        count = sum(len(state.pending_delete) for state in self.maildirs.values())
        if not count:
            return True
        selected = ChoiceView(
            f'Move {count} deleted message(s) to Trash?',
            {'y': 'yes', 'n': 'no'},
            primary='yes',
            overrides=config.keys.get(ChoiceView.namespace),
        ).run(self.context)
        if selected != 'yes':
            return True
        errors = [error for state in self.maildirs.values() for error in state.purge_deleted(config.trash)]
        if errors:
            PagerView('Cannot move deleted messages', text.span_lines('\n'.join(errors))).run(self.context)
            return False
        return True

    def run(self) -> None:
        screen = self.context.screen
        screen.keypad(True)
        if curses.tigetstr('civis') is not None:
            curses.curs_set(0)
        try:
            while self.stack:
                self.mime.reap()
                transition = self.stack[-1].run(self.context)
                if transition.operation == 'close' and len(self.stack) == 1 and not self.confirm_exit():
                    continue
                transition.apply(self.stack)
        finally:
            for state in self.maildirs.values():
                state.index.close()
            self.mime.close()
