from __future__ import annotations

import curses
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from typing import TYPE_CHECKING, ClassVar

from .. import compose, keys, ui
from ..message import parse_message, select_body
from ..search import parse_query
from ..state import IndexState, MaildirState, SearchState
from . import (
    GLOBAL_ACTIONS,
    MAIL_ACTIONS,
    MOVE_ACTIONS,
    PAGE_ACTIONS,
    ChangeView,
    ChangeViewHandlerMixin,
    HandlerView,
)
from .compose import ComposeView
from .pager import PagerView

if TYPE_CHECKING:
    from email.message import EmailMessage

    from ..app import App


COMMANDS = ('search',)


def _command_completer(value: str, cursor: int) -> list[ui.Completion]:
    prefix = value[:cursor]
    if any(character.isspace() for character in prefix):
        return []
    suffix = value[cursor:]
    return [
        ui.Completion(command + ' ' + suffix, command, accept=False)
        for command in COMMANDS
        if command.startswith(prefix)
    ]


@dataclass
class IndexView(ChangeViewHandlerMixin, HandlerView[ChangeView]):
    namespace: ClassVar[str] = 'index'
    actions: ClassVar[keys.ActionSet] = (
        GLOBAL_ACTIONS
        | MOVE_ACTIONS
        | PAGE_ACTIONS
        | MAIL_ACTIONS
        | {
            'open': ('ENTER',),
            'refresh': ('R',),
            'command': (':',),
            'change': ('c',),
            'compose': ('m',),
            'delete': ('d',),
            'undelete': ('u',),
            'flag': ('F',),
            'unread': ('N',),
            'resume': ('e',),
        }
    )
    compiled_actions: ClassVar[keys.Bindings] = {}
    state: IndexState
    app: App
    notice: str = ''
    reconcile: bool = False

    @property
    def maildir(self) -> MaildirState:
        if isinstance(self.state, MaildirState):
            return self.state
        assert isinstance(self.state, SearchState)
        return self.state.source

    def draw(self, screen: curses.window) -> None:
        app = self.app
        screen.erase()
        height, width = screen.getmaxyx()
        theme = app.theme
        ui.put(screen, 0, 0, self.state.title.ljust(width), width, theme.header)
        visible = max(1, height - 2)
        self.state.offset = ui.viewport_start(self.state.selected, len(self.state.rows), visible, self.state.offset)
        start = self.state.offset
        deleted = self.maildir.pending_delete
        format_parts = [
            (literal, name, specification or '', conversion)
            for literal, name, specification, conversion in Formatter().parse(app.config.index.format)
        ]
        fixed_width = sum(
            ui.text_width(literal) + (0 if name is None or specification == '*' else int(specification))
            for literal, name, specification, _conversion in format_parts
        )
        flexible_width = max(0, width - fixed_width)
        styles = {
            'date': theme.index_date,
            'flags': theme.index_flags,
            'sender': theme.index_sender,
            'subject': theme.index_subject,
        }
        for y, row in enumerate(self.state.rows[start : start + visible], 1):
            item = row.message
            flags = ''.join(
                (
                    'D' if item.key in deleted else '',
                    'N' if 'S' not in item.flags else '',
                    'r' if 'R' in item.flags else '',
                    'F' if 'F' in item.flags else '',
                )
            )[:3]
            values = {
                'date': ui.format_index_date(item.timestamp),
                'flags': flags,
                'sender': ui.format_sender(item.sender),
                'subject': '  ' * row.depth + item.subject.replace('\n', ' '),
            }
            selected = start + y - 1 == self.state.selected
            selected_attr = theme.indicator if selected else 0
            ui.put(screen, y, 0, ' ' * width, width, selected_attr)
            x = 0
            for literal, name, specification, _conversion in format_parts:
                literal_width = ui.text_width(literal)
                ui.put(screen, y, x, literal, min(literal_width, max(0, width - x)), selected_attr)
                x += literal_width
                if name is None:
                    continue
                column_width = flexible_width if specification == '*' else int(specification)
                visible_width = min(column_width, max(0, width - x))
                attr = selected_attr if selected else styles[name]
                ui.put(screen, y, x, values[name].ljust(column_width), visible_width, attr)
                x += column_width
        count = len(self.state.rows)
        summary = f' {count} {"message" if count == 1 else "messages"}'
        ui.status(screen, self.notice or summary, theme.status)
        self.notice = ''

    def _message(self) -> EmailMessage:
        return parse_message(self.maildir.path / self.state.selected_message.path)

    def _render_body(self, app: App, message: EmailMessage) -> str:
        part = select_body(message, app.config)
        if part is None:
            return '[No displayable body. Press v to inspect MIME parts.]'
        try:
            return app.mime.display(part)
        except Exception as exc:
            return f'[Cannot display {part.get_content_type()}: {exc}]'

    def _reload(self) -> None:
        self.state.reload()

    def _search(self, app: App, command: str) -> ChangeView | None:
        parts = command.split(maxsplit=1)
        name = parts[0] if parts else ''
        if name != 'search':
            self.notice = f'unknown command: {name}'
            return None
        query = parts[1].strip() if len(parts) == 2 else ''
        try:
            terms = parse_query(query)
        except ValueError as exc:
            self.notice = str(exc)
            return None
        view = IndexView(SearchState.create(self.maildir, query, terms), app)
        if isinstance(self.state, SearchState):
            return ChangeView.replace(view)
        return ChangeView.push(view)

    def _change_maildir(self, screen: curses.window) -> IndexView | None:
        app = self.app
        value = ui.prompt(
            screen,
            'Maildir: ',
            str(app.config.root) + '/',
            complete_paths=True,
            completer=ui.maildir_completer,
            history=app.history('maildir'),
            status_attr=app.theme.status,
        )
        if not value:
            return None
        try:
            return app.maildir_view(Path(value))
        except (OSError, ValueError) as exc:
            self.notice = str(exc)
            return None

    def _mark_deleted(self, app: App) -> None:
        if self.maildir.path.resolve() == app.config.trash.resolve():
            self.notice = 'messages in Trash cannot be marked for deletion'
            return
        self.maildir.mark_deleted(self.state.selected_message.key)
        self.state.select_next()
        self.notice = 'marked for deletion'

    def _manual_refresh(self, screen: curses.window) -> None:
        app = self.app
        if hook := app.config.hooks.pre_refresh:
            try:
                command = [argument.replace('{maildir}', str(self.maildir.path)) for argument in shlex.split(hook)]
                if not command:
                    raise ValueError('command is empty')
                ui.status(screen, 'running pre-refresh hook...', app.theme.status)
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                output, _ = process.communicate()
            except (OSError, ValueError) as exc:
                PagerView('Pre-refresh hook failed', str(exc), app.theme).run(screen)
            else:
                if output:
                    PagerView(
                        'Pre-refresh hook output',
                        output.decode('utf-8', errors='replace'),
                        app.theme,
                    ).run(screen)
        self.maildir.refresh()
        self.notice = 'refreshed'

    def _set_notice(self, notice: str) -> None:
        self.notice = notice

    def _resume_finished(self, notice: str) -> None:
        self.notice = notice
        self.maildir.refresh()
        if self.state is not self.maildir:
            self.state.reload()

    def _resume(self, app: App) -> ComposeView | None:
        if self.maildir.path.resolve() != app.config.drafts.resolve() or not self.state.rows:
            self.notice = 'resume is available only in the Drafts Maildir'
            return None
        old_path = self.maildir.path / self.state.selected_message.path
        return ComposeView.resume(self._message(), old_path, app, self._resume_finished)

    def _reconcile(self, screen: curses.window) -> None:
        self.notice = 'reconciling...' if self.state.rows else 'indexing...'
        self.draw(screen)
        screen.refresh()
        self.maildir.refresh()
        self.reconcile = False

    def run(self, screen: curses.window) -> ChangeView:
        if self.reconcile:
            self._reconcile(screen)
        return super().run(screen)

    def on_back(self, screen: curses.window) -> ChangeView | None:
        if len(self.app.stack) == 1 and not self.app.confirm_exit():
            return None
        return ChangeView.close()

    def on_down(self, screen: curses.window) -> None:
        if self.state.rows:
            self.state.select_next()

    def on_up(self, screen: curses.window) -> None:
        if self.state.rows:
            self.state.select_previous()

    def _move_page(self, screen: curses.window, direction: int) -> None:
        if not self.state.rows:
            return
        visible = max(1, screen.getmaxyx()[0] - 2)
        self.state.selected = min(
            len(self.state.rows) - 1,
            max(0, self.state.selected + direction * visible),
        )

    def on_pageup(self, screen: curses.window) -> None:
        self._move_page(screen, -1)

    def on_pagedown(self, screen: curses.window) -> None:
        self._move_page(screen, 1)

    def on_home(self, screen: curses.window) -> None:
        if self.state.rows:
            self.state.selected = 0

    def on_end(self, screen: curses.window) -> None:
        if self.state.rows:
            self.state.selected = len(self.state.rows) - 1

    def on_open(self, screen: curses.window) -> ChangeView | None:
        if not self.state.rows:
            return None
        from .message import MessageView

        return ChangeView.push(MessageView(self.maildir, self.state, self.state.selected_message, self.app))

    def on_refresh(self, screen: curses.window) -> None:
        if self.state is self.maildir:
            self._manual_refresh(screen)

    def on_command(self, screen: curses.window) -> ChangeView | None:
        app = self.app
        value = ui.prompt(
            screen,
            ':',
            completer=_command_completer,
            history=app.history('command'),
            status_attr=app.theme.status,
        )
        if value is None:
            return None
        return self._search(app, value)

    def on_change(self, screen: curses.window) -> ChangeView | None:
        view = self._change_maildir(screen)
        return ChangeView.push(view) if view is not None else None

    def on_compose(self, screen: curses.window) -> ChangeView:
        app = self.app
        return ChangeView.push(ComposeView(compose.new(app.config), self._set_notice, app))

    def on_parts(self, screen: curses.window) -> ChangeView | None:
        if not self.state.rows:
            return None
        from .parts import PartsView

        return ChangeView.push(PartsView(self._message(), self.app))

    def _reply(self, all_recipients: bool) -> ChangeView | None:
        if not self.state.rows:
            return None
        app = self.app
        message = self._message()
        return ChangeView.push(
            ComposeView(
                compose.reply(message, self._render_body(app, message), app.config, all_recipients=all_recipients),
                self._set_notice,
                app,
                replied_state=self.maildir,
                replied_index=self.state,
                replied_key=self.state.selected_message.key,
            )
        )

    def on_reply(self, screen: curses.window) -> ChangeView | None:
        return self._reply(False)

    def on_reply_all(self, screen: curses.window) -> ChangeView | None:
        return self._reply(True)

    def on_forward(self, screen: curses.window) -> ChangeView | None:
        if not self.state.rows:
            return None
        app = self.app
        message = self._message()
        return ChangeView.push(ComposeView.forward(message, self._render_body(app, message), app, self._set_notice))

    def on_delete(self, screen: curses.window) -> None:
        if self.state.rows:
            self._mark_deleted(self.app)

    def on_undelete(self, screen: curses.window) -> None:
        if self.state.rows:
            self.maildir.unmark_deleted(self.state.selected_message.key)
            self.state.select_next()
            self.notice = 'deletion mark removed'

    def on_flag(self, screen: curses.window) -> None:
        if self.state.rows:
            item = self.state.selected_message
            self.maildir.index.set_flags(
                item.key,
                remove='F' if 'F' in item.flags else '',
                add='' if 'F' in item.flags else 'F',
            )
            self._reload()

    def on_unread(self, screen: curses.window) -> None:
        if self.state.rows:
            self.maildir.index.set_flags(self.state.selected_message.key, remove='S')
            self._reload()

    def on_resume(self, screen: curses.window) -> ChangeView | None:
        view = self._resume(self.app)
        return ChangeView.push(view) if view is not None else None
