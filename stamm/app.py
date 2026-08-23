from __future__ import annotations

import curses
from pathlib import Path

from . import keys, ui
from .config import Config
from .mime import MimeManager
from .state import MaildirState
from .views import View
from .views.index import IndexView
from .views.message import MessageView
from .views.parts import PartsView

BINDING_REGISTRY = {
    'index': keys.BindingDefinition(IndexView.ACTIONS, IndexView.DEFAULT_BINDINGS),
    'message': keys.BindingDefinition(MessageView.ACTIONS, MessageView.DEFAULT_BINDINGS),
    'parts': keys.BindingDefinition(PartsView.ACTIONS, PartsView.DEFAULT_BINDINGS),
    'pager': keys.BindingDefinition(ui.PAGER_ACTIONS, ui.PAGER_DEFAULT_BINDINGS),
    'choose': keys.BindingDefinition(ui.CHOOSE_ACTIONS, ui.CHOOSE_DEFAULT_BINDINGS),
}


class App:
    def __init__(self, screen: curses.window, config: Config, theme: ui.CursesTheme):
        self.screen = screen
        self.config = config
        self.theme = theme
        self.maildirs: dict[Path, MaildirState] = {}
        self.mime = MimeManager(config)
        self.stack: list[View] = []
        self.histories: dict[str, list[str]] = {}
        self.bindings, self.binding_diagnostics = keys.compile_bindings(BINDING_REGISTRY, config.keys)

    def push(self, view: View) -> None:
        self.stack.append(view)

    def history(self, name: str) -> list[str]:
        return self.histories.setdefault(name, [])

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
            {'y': 'yes', 'n': 'no'},
            self.theme.status,
            self.bindings['choose'],
            primary='yes',
        )
        if answer != 'yes':
            return True
        errors = [error for state in self.maildirs.values() for error in state.purge_deleted(self.config.trash)]
        if errors:
            ui.pager(
                self.screen,
                'Cannot move deleted messages',
                '\n'.join(errors),
                self.theme.header,
                self.bindings['pager'],
            )
            return False
        return True

    def run(self) -> None:
        self.screen.keypad(True)
        curses.curs_set(0)
        if self.binding_diagnostics:
            ui.pager(
                self.screen,
                'Key binding warnings',
                '\n'.join(self.binding_diagnostics) + '\n\nPress any unbound key to continue.',
                self.theme.header,
                self.bindings['pager'],
            )
        try:
            while self.stack:
                self.mime.reap()
                self.stack[-1].run(self)
        finally:
            for state in self.maildirs.values():
                state.index.close()
            self.mime.close()
