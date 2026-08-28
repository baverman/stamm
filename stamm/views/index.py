from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from string import Formatter
from typing import ClassVar

from .. import compose, ui
from ..config import config
from ..message import parse_message, select_body
from ..mime import MimeManager
from ..search import parse_query
from ..state import IndexState, SearchState
from ..tui import keys, prompt, text
from . import GLOBAL_ACTIONS, MAIL_ACTIONS, MOVE_ACTIONS, PAGE_ACTIONS, DefaultActionView, Transition, UIContext
from .compose import ComposeView
from .mail_actions import MailActionsMixin
from .message import MessageView
from .pager import PagerView
from .parts import PartsView

COMMANDS = ('reindex', 'search', 'unmark_deleted')
COMMAND_HISTORY: list[str] = []
MAILDIR_HISTORY: list[str] = []


def _command_completer(value: str, cursor: int) -> list[prompt.Completion]:
    prefix = value[:cursor]
    if any(character.isspace() for character in prefix):
        return []
    suffix = value[cursor:]
    return [
        prompt.Completion(command + ' ' + suffix, command, accept=False)
        for command in COMMANDS
        if command.startswith(prefix)
    ]


def _format_flags(flags: str, deleted: bool) -> str:
    return ''.join(
        (
            '!' if 'F' in flags else ' ',
            'r' if 'R' in flags else ' ',
            'D' if deleted else ' ',
            'N' if 'S' not in flags else ' ',
        )
    )


def _index_summary(selected: int, count: int) -> str:
    return f'{selected + 1 if count else 0}/{count} messages'


def _status_with_delete_count(status: str, count: int) -> str:
    return f'{status} | {count} to delete' if count else status


def _maildir_completer(value: str, cursor: int) -> list[prompt.Completion]:
    suffix = value[cursor:]
    result: list[prompt.Completion] = []
    for item in prompt.path_completer(value, cursor):
        completed = item.value[: -len(suffix)] if suffix else item.value
        path = Path(completed)
        if not path.is_dir():
            continue
        is_maildir = (path / 'cur').is_dir() and (path / 'new').is_dir()
        label = item.label or item.value
        if is_maildir:
            label += ' [Maildir]'
        result.append(prompt.Completion(item.value, label, accept=is_maildir))
    return result


@dataclass
class IndexView(MailActionsMixin, DefaultActionView):
    namespace: ClassVar[str] = 'index'
    actions: ClassVar[keys.ActionSet] = (
        GLOBAL_ACTIONS
        | MOVE_ACTIONS
        | PAGE_ACTIONS
        | MAIL_ACTIONS
        | {
            'open': ('ENTER',),
            'open_html': ('H',),
            'refresh': ('R',),
            'command': (':',),
            'search': ('/',),
            'change': ('c',),
            'compose': ('m',),
            'delete': ('d',),
            'undelete': ('u',),
            'flag': ('F',),
            'unread': ('N',),
            'resume': ('e',),
        }
    )
    state: IndexState
    mime: MimeManager
    open_maildir: Callable[[Path], IndexView]
    notice: str = ''
    reconcile: bool = False

    def draw(self, context: UIContext) -> None:
        screen = context.screen
        screen.erase()
        height, width = screen.getmaxyx()
        theme = context.theme
        text.put(screen, 0, 0, self.state.title.ljust(width), width, theme.header)
        visible = max(1, height - 2)
        self.state.offset = ui.viewport_start(self.state.selected, len(self.state.rows), visible, self.state.offset)
        start = self.state.offset
        deleted = self.state.source_state.pending_delete
        format_parts = [
            (literal, name, specification or '', conversion)
            for literal, name, specification, conversion in Formatter().parse(config.index.format)
        ]
        fixed_width = sum(
            text.text_width(literal) + (0 if name is None or specification == '*' else int(specification))
            for literal, name, specification, _conversion in format_parts
        )
        flexible_width = max(0, width - fixed_width)
        styles = {
            'date': theme.index.column_date,
            'flags': theme.index.column_flags,
            'from': theme.index.column_from,
            'subject': theme.index.column_subject,
        }
        for y, row in enumerate(self.state.rows[start : start + visible], 1):
            item = row.message
            flags = _format_flags(item.flags, item.key in deleted)
            values = {
                'date': ui.format_index_date(item.timestamp),
                'flags': flags,
                'from': ui.format_sender(item.sender),
                'subject': '  ' * row.depth + item.subject.replace('\n', ' '),
            }
            selected = start + y - 1 == self.state.selected
            selected_attr = theme.index.indicator if selected else 0
            text.put(screen, y, 0, ' ' * width, width, selected_attr)
            x = 0
            for literal, name, specification, _conversion in format_parts:
                literal_width = text.text_width(literal)
                text.put(screen, y, x, literal, min(literal_width, max(0, width - x)), selected_attr)
                x += literal_width
                if name is None:
                    continue
                column_width = flexible_width if specification == '*' else int(specification)
                visible_width = min(column_width, max(0, width - x))
                attr = selected_attr if selected else styles[name]
                text.put(screen, y, x, values[name].ljust(column_width), visible_width, attr)
                x += column_width
        count = len(self.state.rows)
        summary = _index_summary(self.state.selected, count)
        status = self.notice or _status_with_delete_count(
            summary,
            len(self.state.source_state.pending_delete),
        )
        text.status(screen, status, theme.status)
        self.notice = ''

    def _message(self) -> EmailMessage:
        return parse_message(self.state.source_state.path / self.state.selected_message.path)

    def _render_body(self, message: EmailMessage) -> str:
        part = select_body(message, config)
        if part is None:
            return '[No displayable body. Press v to inspect MIME parts.]'
        try:
            return self.mime.display(part)
        except Exception as exc:
            return f'[Cannot display {part.get_content_type()}: {exc}]'

    def _mail_action_message(self) -> tuple[EmailMessage, str, str] | None:
        if not self.state.rows:
            return None
        message = self._message()
        return message, self._render_body(message), self.state.selected_message.key

    def _reload(self) -> None:
        self.state.reload()

    def _search(
        self,
        command: str,
        progress: Callable[[int, int], None] | None = None,
    ) -> Transition | None:
        parts = command.split(maxsplit=1)
        name = parts[0] if parts else ''
        if name == 'reindex':
            target = parts[1].strip() if len(parts) == 2 else ''
            if target not in ('full', 'fts', 'fts-full'):
                self.notice = 'usage: reindex full|fts|fts-full'
                return None
            if target == 'full':
                indexed = self.state.source_state.index.reindex(progress)
                self.state.reload()
                self.notice = f'Index rebuilt: {indexed} indexed'
                return None
            indexed, removed = self.state.source_state.index.reindex_fts(full=target == 'fts-full', progress=progress)
            action = 'rebuilt' if target == 'fts-full' else 'reconciled'
            self.notice = f'FTS index {action}: {indexed} indexed, {removed} removed'
            return None
        if name == 'unmark_deleted':
            if len(parts) == 2 and parts[1].strip():
                self.notice = 'usage: unmark_deleted'
                return None
            source = self.state.source_state
            visible = {row.message.key for row in self.state.rows}
            unmarked = source.pending_delete & visible
            for key in unmarked:
                source.unmark_deleted(key)
            noun = 'message' if len(unmarked) == 1 else 'messages'
            self.notice = f'{len(unmarked)} {noun} unmarked for deletion'
            return None
        if name != 'search':
            self.notice = f'unknown command: {name}'
            return None
        query = parts[1].strip() if len(parts) == 2 else ''
        try:
            expression = parse_query(query)
            state = SearchState.create(self.state.source_state, query, expression)
        except ValueError as exc:
            self.notice = str(exc)
            return None
        view = IndexView(state, self.mime, self.open_maildir)
        if isinstance(self.state, SearchState):
            return Transition.replace(view)
        return Transition.push(view)

    def _change_maildir(self, context: UIContext) -> IndexView | None:
        value = prompt.PromptView(
            'Maildir: ',
            str(config.root) + '/',
            completer=_maildir_completer,
            history=MAILDIR_HISTORY,
        ).run(context)
        if not value:
            return None
        try:
            return self.open_maildir(Path(value))
        except (OSError, ValueError) as exc:
            self.notice = str(exc)
            return None

    def _mark_deleted(self) -> None:
        if self.state.source_state.path.resolve() == config.trash.resolve():
            self.notice = 'messages in Trash cannot be marked for deletion'
            return
        self.state.source_state.mark_deleted(self.state.selected_message.key)
        self.state.select_next()

    def _manual_refresh(self, context: UIContext) -> None:
        if hook := config.hooks.pre_refresh:
            try:
                command = [
                    argument.replace('{maildir}', str(self.state.source_state.path)) for argument in shlex.split(hook)
                ]
                if not command:
                    raise ValueError('command is empty')
                text.status(context.screen, 'running pre-refresh hook...', context.theme.status)
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                output, err = process.communicate()
            except (OSError, ValueError) as exc:
                PagerView('Pre-refresh hook failed', text.span_lines(str(exc))).run(context)
            else:
                if err:
                    PagerView(
                        'Pre-refresh hook output',
                        text.span_lines(
                            output.decode('utf-8', errors='replace') + '\n' + err.decode('utf-8', errors='replace')
                        ),
                    ).run(context)
        self.state.source_state.refresh()
        self.notice = 'refreshed'

    def _set_notice(self, notice: str, _is_sent: bool) -> None:
        self.notice = notice

    def _resume_finished(self, notice: str, _is_sent: bool) -> None:
        self.notice = notice
        self.state.source_state.refresh()
        if self.state is not self.state.source_state:
            self.state.reload()

    def _resume(self) -> ComposeView | None:
        if self.state.source_state.path.resolve() != config.drafts.resolve() or not self.state.rows:
            self.notice = 'resume is available only in the Drafts Maildir'
            return None
        old_path = self.state.source_state.path / self.state.selected_message.path
        return ComposeView.resume(self._message(), old_path, self._resume_finished)

    def _reconcile(self, context: UIContext) -> None:
        self.notice = 'reconciling...' if self.state.rows else 'indexing...'
        self.draw(context)
        context.screen.refresh()
        self.state.source_state.refresh()
        self.reconcile = False

    def run(self, context: UIContext) -> Transition:
        if self.reconcile:
            self._reconcile(context)
        return super().run(context)

    def on_down(self, context: UIContext) -> None:
        if self.state.rows:
            self.state.select_next()

    def on_up(self, context: UIContext) -> None:
        if self.state.rows:
            self.state.select_previous()

    def _move_page(self, context: UIContext, direction: int) -> None:
        if not self.state.rows:
            return
        visible = max(1, context.screen.getmaxyx()[0] - 2)
        self.state.selected = min(
            len(self.state.rows) - 1,
            max(0, self.state.selected + direction * visible),
        )

    def on_pageup(self, context: UIContext) -> None:
        self._move_page(context, -1)

    def on_pagedown(self, context: UIContext) -> None:
        self._move_page(context, 1)

    def on_home(self, context: UIContext) -> None:
        if self.state.rows:
            self.state.selected = 0

    def on_end(self, context: UIContext) -> None:
        if self.state.rows:
            self.state.selected = len(self.state.rows) - 1

    def on_open(self, context: UIContext) -> Transition | None:
        if not self.state.rows:
            return None

        item = self.state.selected_message
        if 'S' not in item.flags:
            item = self.state.source_state.index.set_flags(item.key, add='S')
            self.state.reload()
        message = parse_message(self.state.source_state.path / item.path)
        body = self._render_body(message)
        return Transition.push(
            MessageView(
                message,
                body,
                self.mime,
                self.state,
                item.key,
            )
        )

    def on_open_html(self, _context: UIContext) -> None:
        if not self.state.rows:
            return
        message = self._message()
        part = message.get_body(preferencelist=('html',))
        if part is None:
            self.notice = 'no HTML part'
            return
        try:
            self.mime.open(part, message)
            self.notice = 'opened HTML externally'
        except Exception as exc:
            self.notice = str(exc)

    def on_refresh(self, context: UIContext) -> None:
        if self.state is self.state.source_state:
            self._manual_refresh(context)

    def _prompt_command(self, context: UIContext, initial: str = '') -> Transition | None:
        value = prompt.PromptView(
            ':',
            initial,
            completer=_command_completer,
            history=COMMAND_HISTORY,
        ).run(context)
        if value is None:
            return None

        progress_label = 'Indexing' if value.split() == ['reindex', 'full'] else 'FTS indexing'

        def progress(processed: int, total: int) -> None:
            text.status(context.screen, f'{progress_label}: {processed}/{total}', context.theme.status)

        return self._search(value, progress)

    def on_command(self, context: UIContext) -> Transition | None:
        return self._prompt_command(context)

    def on_search(self, context: UIContext) -> Transition | None:
        query = self.state.query if isinstance(self.state, SearchState) else ''
        return self._prompt_command(context, f'search {query}')

    def on_change(self, context: UIContext) -> Transition | None:
        view = self._change_maildir(context)
        return Transition.push(view) if view is not None else None

    def on_compose(self, context: UIContext) -> Transition:
        return Transition.push(ComposeView(compose.new(config), self._set_notice))

    def on_parts(self, context: UIContext) -> Transition | None:
        if not self.state.rows:
            return None

        return Transition.push(PartsView(self._message(), self.mime))

    def on_delete(self, context: UIContext) -> None:
        if self.state.rows:
            self._mark_deleted()

    def on_undelete(self, context: UIContext) -> None:
        if self.state.rows:
            self.state.source_state.unmark_deleted(self.state.selected_message.key)
            self.state.select_next()

    def on_flag(self, context: UIContext) -> None:
        if self.state.rows:
            item = self.state.selected_message
            self.state.source_state.index.set_flags(
                item.key,
                remove='F' if 'F' in item.flags else '',
                add='' if 'F' in item.flags else 'F',
            )
            self._reload()

    def on_unread(self, context: UIContext) -> None:
        if self.state.rows:
            self.state.source_state.index.set_flags(self.state.selected_message.key, remove='S')
            self._reload()

    def on_resume(self, context: UIContext) -> Transition | None:
        view = self._resume()
        return Transition.push(view) if view is not None else None
