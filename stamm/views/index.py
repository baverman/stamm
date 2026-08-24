from __future__ import annotations

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
from .compose import ComposeView

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
class IndexView:
    ACTIONS: ClassVar[frozenset[str]] = frozenset(
        {
            'back',
            'down',
            'up',
            'pageup',
            'pagedown',
            'home',
            'end',
            'open',
            'refresh',
            'command',
            'change',
            'compose',
            'parts',
            'reply',
            'reply_all',
            'forward',
            'delete',
            'undelete',
            'flag',
            'unread',
            'resume',
        }
    )
    DEFAULT_BINDINGS: ClassVar[keys.BindingSpecs] = {
        'q': 'back',
        'j': 'down',
        'DOWN': 'down',
        'k': 'up',
        'UP': 'up',
        'PAGEUP': 'pageup',
        'PAGEDOWN': 'pagedown',
        'HOME': 'home',
        '^D': 'pagedown',
        '^U': 'pageup',
        'END': 'end',
        'ENTER': 'open',
        'R': 'refresh',
        ':': 'command',
        'c': 'change',
        'm': 'compose',
        'v': 'parts',
        'r': 'reply',
        'g': 'reply_all',
        'f': 'forward',
        'd': 'delete',
        'u': 'undelete',
        'F': 'flag',
        'N': 'unread',
        'e': 'resume',
    }
    state: IndexState
    notice: str = ''
    reconcile: bool = False

    @property
    def maildir(self) -> MaildirState:
        if isinstance(self.state, MaildirState):
            return self.state
        assert isinstance(self.state, SearchState)
        return self.state.source

    def draw(self, app: App) -> None:
        screen = app.screen
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

    def _search(self, app: App, command: str) -> bool:
        parts = command.split(maxsplit=1)
        name = parts[0] if parts else ''
        if name != 'search':
            self.notice = f'unknown command: {name}'
            return False
        query = parts[1].strip() if len(parts) == 2 else ''
        try:
            terms = parse_query(query)
        except ValueError as exc:
            self.notice = str(exc)
            return False
        if isinstance(self.state, SearchState):
            app.pop()
        app.push(IndexView(SearchState.create(self.maildir, query, terms)))
        return True

    def _change_maildir(self, app: App) -> bool:
        value = ui.prompt(
            app.screen,
            'Maildir: ',
            str(app.config.root) + '/',
            complete_paths=True,
            completer=ui.maildir_completer,
            history=app.history('maildir'),
            status_attr=app.theme.status,
        )
        if not value:
            return False
        try:
            app.open_maildir(Path(value))
        except (OSError, ValueError) as exc:
            self.notice = str(exc)
            return False
        return True

    def _mark_deleted(self, app: App) -> None:
        if self.maildir.path.resolve() == app.config.trash.resolve():
            self.notice = 'messages in Trash cannot be marked for deletion'
            return
        self.maildir.mark_deleted(self.state.selected_message.key)
        self.state.select_next()
        self.notice = 'marked for deletion'

    def _manual_refresh(self, app: App) -> None:
        if hook := app.config.hooks.pre_refresh:
            try:
                command = [argument.replace('{maildir}', str(self.maildir.path)) for argument in shlex.split(hook)]
                if not command:
                    raise ValueError('command is empty')
                ui.status(app.screen, 'running pre-refresh hook...', app.theme.status)
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                output, _ = process.communicate()
            except (OSError, ValueError) as exc:
                ui.pager(app.screen, 'Pre-refresh hook failed', str(exc), app.theme.header, app.bindings['pager'])
            else:
                if output:
                    ui.pager(
                        app.screen,
                        'Pre-refresh hook output',
                        output.decode('utf-8', errors='replace'),
                        app.theme.header,
                        app.bindings['pager'],
                    )
        self.maildir.refresh()
        self.notice = 'refreshed'

    def _set_notice(self, notice: str) -> None:
        self.notice = notice

    def _resume_finished(self, notice: str) -> None:
        self.notice = notice
        self.maildir.refresh()
        if self.state is not self.maildir:
            self.state.reload()

    def _resume(self, app: App) -> bool:
        if self.maildir.path.resolve() != app.config.drafts.resolve() or not self.state.rows:
            self.notice = 'resume is available only in the Drafts Maildir'
            return False
        old_path = self.maildir.path / self.state.selected_message.path
        app.push(ComposeView.resume(self._message(), old_path, self._resume_finished))
        return True

    def _reconcile(self, app: App) -> None:
        self.notice = 'reconciling...' if self.state.rows else 'indexing...'
        self.draw(app)
        app.screen.refresh()
        self.maildir.refresh()
        self.reconcile = False

    def run(self, app: App) -> None:
        if self.reconcile:
            self._reconcile(app)
        while True:
            self.draw(app)
            action, _ch = keys.read(app.screen, app.bindings['index'])
            if action == 'back':
                if len(app.stack) == 1 and not app.confirm_exit():
                    continue
                app.pop()
                return
            if action == 'down' and self.state.rows:
                self.state.select_next()
            elif action == 'up' and self.state.rows:
                self.state.select_previous()
            elif action in ('pageup', 'pagedown') and self.state.rows:
                visible = max(1, app.screen.getmaxyx()[0] - 2)
                movement = -visible if action == 'pageup' else visible
                self.state.selected = min(len(self.state.rows) - 1, max(0, self.state.selected + movement))
            elif action == 'home' and self.state.rows:
                self.state.selected = 0
            elif action == 'end' and self.state.rows:
                self.state.selected = len(self.state.rows) - 1
            elif action == 'open' and self.state.rows:
                from .message import MessageView

                app.push(MessageView(self.maildir, self.state, self.state.selected_message))
                return
            elif action == 'refresh' and self.state is self.maildir:
                self._manual_refresh(app)
            elif action == 'command':
                value = ui.prompt(
                    app.screen,
                    ':',
                    completer=_command_completer,
                    history=app.history('command'),
                    status_attr=app.theme.status,
                )
                if value is not None and self._search(app, value):
                    return
            elif action == 'change':
                if self._change_maildir(app):
                    return
            elif action == 'compose':
                app.push(ComposeView(compose.new(app.config), self._set_notice))
                return
            elif action == 'parts' and self.state.rows:
                from .parts import PartsView

                app.push(PartsView(self._message()))
                return
            elif action == 'reply' and self.state.rows:
                message = self._message()
                app.push(
                    ComposeView(
                        compose.reply(message, self._render_body(app, message), app.config),
                        self._set_notice,
                        replied_state=self.maildir,
                        replied_index=self.state,
                        replied_key=self.state.selected_message.key,
                    )
                )
                return
            elif action == 'reply_all' and self.state.rows:
                message = self._message()
                app.push(
                    ComposeView(
                        compose.reply(message, self._render_body(app, message), app.config, all_recipients=True),
                        self._set_notice,
                        replied_state=self.maildir,
                        replied_index=self.state,
                        replied_key=self.state.selected_message.key,
                    )
                )
                return
            elif action == 'forward' and self.state.rows:
                message = self._message()
                app.push(ComposeView.forward(message, self._render_body(app, message), app, self._set_notice))
                return
            elif action == 'delete' and self.state.rows:
                self._mark_deleted(app)
            elif action == 'undelete' and self.state.rows:
                self.maildir.unmark_deleted(self.state.selected_message.key)
                self.state.select_next()
                self.notice = 'deletion mark removed'
            elif action == 'flag' and self.state.rows:
                item = self.state.selected_message
                self.maildir.index.set_flags(
                    item.key, remove='F' if 'F' in item.flags else '', add='' if 'F' in item.flags else 'F'
                )
                self._reload()
            elif action == 'unread' and self.state.rows:
                self.maildir.index.set_flags(self.state.selected_message.key, remove='S')
                self._reload()
            elif action == 'resume' and self._resume(app):
                return
