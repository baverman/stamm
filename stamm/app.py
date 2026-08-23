from __future__ import annotations

import curses
from pathlib import Path

from . import ui
from .config import Config
from .mime import MimeManager
from .state import MaildirState
from .views import View
from .views.index import IndexView


class App:
    def __init__(self, screen: curses.window, config: Config, theme: ui.CursesTheme):
        self.screen = screen
        self.config = config
        self.theme = theme
        self.maildirs: dict[Path, MaildirState] = {}
        self.mime = MimeManager(config)
        self.stack: list[View] = []

    def push(self, view: View) -> None:
        self.stack.append(view)

    def pop(self) -> None:
        if self.stack:
            self.stack.pop()

    def open_maildir(self, path: Path) -> None:
        key = path.resolve()
        state = self.maildirs.get(key)
        reconcile = state is None
        if state is None:
            state = MaildirState.open(path)
            self.maildirs[key] = state
        self.push(IndexView(state, reconcile=reconcile))

    def confirm_exit(self) -> bool:
        count = sum(len(state.pending_delete) for state in self.maildirs.values())
        if not count:
            return True
        answer = ui.choose(
            self.screen,
            f'Move {count} deleted message(s) to Trash?',
            'yn',
            self.theme.status,
            primary='y',
            cancel='n',
        )
        if answer == 'n':
            return True
        errors = [error for state in self.maildirs.values() for error in state.purge_deleted(self.config.trash)]
        if errors:
            ui.pager(self.screen, 'Cannot move deleted messages', '\n'.join(errors), self.theme.header)
            return False
        return True

    def run(self) -> None:
        self.screen.keypad(True)
        curses.curs_set(0)
        try:
            while self.stack:
                self.mime.reap()
                self.stack[-1].run(self)
        finally:
            for state in self.maildirs.values():
                state.index.close()
            self.mime.close()
