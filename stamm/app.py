from __future__ import annotations

import curses
from pathlib import Path

from . import ui
from .config import Config
from .mime import MimeManager
from .state import MaildirState
from .views import ChangeView, View
from .views.choose import ChooseView
from .views.index import IndexView
from .views.pager import PagerView


class App:
    def __init__(self, screen: curses.window, config: Config, theme: ui.CursesTheme):
        self.screen = screen
        self.config = config
        self.theme = theme
        self.maildirs: dict[Path, MaildirState] = {}
        self.mime = MimeManager(config)
        self.stack: list[View[ChangeView]] = []
        self.histories: dict[str, list[str]] = {}

    def history(self, name: str) -> list[str]:
        return self.histories.setdefault(name, [])

    def maildir_view(self, path: Path) -> IndexView:
        key = path.resolve()
        state = self.maildirs.get(key)
        reconcile = state is None
        if state is None:
            state = MaildirState.open(path)
            self.maildirs[key] = state
        return IndexView(state, self, reconcile=reconcile)

    def open_maildir(self, path: Path) -> None:
        self.stack.append(self.maildir_view(path))

    def confirm_exit(self) -> bool:
        count = sum(len(state.pending_delete) for state in self.maildirs.values())
        if not count:
            return True
        selected = ChooseView(
            f'Move {count} deleted message(s) to Trash?',
            {'y': 'yes', 'n': 'no'},
            primary='yes',
            theme=self.theme,
        ).run(self.screen)
        if selected != 'yes':
            return True
        errors = [error for state in self.maildirs.values() for error in state.purge_deleted(self.config.trash)]
        if errors:
            PagerView('Cannot move deleted messages', '\n'.join(errors), self.theme).run(self.screen)
            return False
        return True

    def run(self) -> None:
        self.screen.keypad(True)
        curses.curs_set(0)
        try:
            while self.stack:
                self.mime.reap()
                transition = self.stack[-1].run(self.screen)
                transition.apply(self.stack)
        finally:
            for state in self.maildirs.values():
                state.index.close()
            self.mime.close()
