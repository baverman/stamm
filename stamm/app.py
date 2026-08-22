"""Application state and curses screen transitions."""

from __future__ import annotations

import curses
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

from . import compose, delivery, ui
from .config import Config
from .index import INITIAL_MESSAGE_LIMIT, IndexedMessage, MessageIndex
from .message import header_block, parse_message, select_body
from .mime import MimeManager, part_rows, save_part
from .threads import ThreadRow, build_threads


@dataclass
class MaildirState:
    path: Path
    index: MessageIndex
    rows: list[ThreadRow]
    selected: int
    offset: int
    pending_delete: set[str]

    @classmethod
    def open(cls, path: Path) -> MaildirState:
        index = MessageIndex(path)
        try:
            rows = build_threads(index.messages(limit=INITIAL_MESSAGE_LIMIT))
        except Exception:
            index.close()
            raise
        return cls(path, index, rows, max(0, len(rows) - 1), 0, set())

    @property
    def selected_message(self) -> IndexedMessage:
        return self.rows[self.selected].message

    def load_rows(self, messages: list[IndexedMessage]) -> None:
        key = self.selected_message.key if self.rows else None
        self.rows = build_threads(messages)
        if key:
            self.selected = next((i for i, row in enumerate(self.rows) if row.message.key == key), 0)
        else:
            self.selected = min(self.selected, max(0, len(self.rows) - 1))

    def refresh(self) -> None:
        self.load_rows(self.index.refresh())

    def reload_cached(self) -> None:
        self.load_rows(self.index.messages())

    def mark_deleted(self) -> None:
        self.pending_delete.add(self.selected_message.key)
        self.selected = min(len(self.rows) - 1, self.selected + 1)

    def unmark_deleted(self) -> None:
        self.pending_delete.discard(self.selected_message.key)
        self.selected = min(len(self.rows) - 1, self.selected + 1)

    def purge_deleted(self, trash: Path) -> list[str]:
        if not self.pending_delete:
            return []
        errors: list[str] = []
        position = self.selected
        for key in list(self.pending_delete):
            try:
                if self.index.get(key) is not None:
                    self.index.move_to(key, trash)
                self.pending_delete.discard(key)
            except (OSError, ValueError) as exc:
                errors.append(f'{self.path}: {exc}')
        self.rows = build_threads(self.index.messages())
        self.selected = min(position, max(0, len(self.rows) - 1))
        return errors


class App:
    def __init__(
        self,
        screen: curses.window,
        config: Config,
        state: MaildirState,
        theme: ui.CursesTheme,
    ):
        self.screen = screen
        self.config = config
        self.state = state
        self.maildirs = {state.path.resolve(): state}
        self.notice = ''
        self.mime = MimeManager(config)
        self.theme = theme

    def open_maildir(self, path: Path) -> None:
        key = path.resolve()
        state = self.maildirs.get(key)
        if state is None:
            state = MaildirState.open(path)
            self.maildirs[key] = state
            self.state = state
            self.reconcile()
            return
        self.state = state

    def reconcile(self) -> None:
        self.notice = 'reconciling...' if self.state.rows else 'indexing...'
        self.draw_index()
        self.screen.refresh()
        self.state.refresh()

    def draw_index(self) -> None:
        self.screen.erase()
        height, width = self.screen.getmaxyx()
        theme = self.theme
        ui.put(self.screen, 0, 0, f'Stamm — {self.state.path}'.ljust(width), width, theme.header)
        visible = max(1, height - 2)
        self.state.offset = ui.viewport_start(self.state.selected, len(self.state.rows), visible, self.state.offset)
        start = self.state.offset
        deleted = self.state.pending_delete
        date_attr = theme.index_date
        flags_attr = theme.index_flags
        sender_attr = theme.index_sender
        subject_attr = theme.index_subject
        indicator_attr = theme.indicator
        for y, row in enumerate(self.state.rows[start : start + visible], 1):
            item = row.message
            marked = item.key in deleted
            flags = ''.join(
                (
                    'D' if marked else '',
                    'N' if 'S' not in item.flags else '',
                    'r' if 'R' in item.flags else '',
                    'F' if 'F' in item.flags else '',
                )
            )[:3]
            sender = ui.format_sender(item.sender)[:20]
            subject = '  ' * row.depth + item.subject.replace('\n', ' ')
            date = ui.format_index_date(item.timestamp)
            line = f'{date} {flags:3} {sender:20}  {subject}'
            selected = start + y - 1 == self.state.selected
            attr = indicator_attr if selected else 0
            ui.put(self.screen, y, 0, line.ljust(width), width, attr)
            if not selected:
                ui.put(self.screen, y, 0, date, 12, date_attr)
                ui.put(self.screen, y, 13, flags, 3, flags_attr)
                ui.put(self.screen, y, 17, sender, 20, sender_attr)
                ui.put(self.screen, y, 39, subject, max(0, width - 39), subject_attr)
        count = len(self.state.rows)
        summary = f' {count} {"message" if count == 1 else "messages"}'
        ui.status(self.screen, self.notice or summary, theme.status)
        self.notice = ''

    def _message(self) -> EmailMessage:
        item = self.state.selected_message
        return parse_message(self.state.path / item.path)

    def _render_body(self, message: EmailMessage) -> str:
        part = select_body(message, self.config)
        if part is None:
            return '[No displayable body. Press v to inspect MIME parts.]'
        try:
            return self.mime.display(part)
        except Exception as exc:
            return f'[Cannot display {part.get_content_type()}: {exc}]'

    def mark_deleted(self) -> None:
        if not self.state.rows:
            return
        if self.state.path.resolve() == self.config.trash.resolve():
            self.notice = 'messages in Trash cannot be marked for deletion'
            return
        self.state.mark_deleted()
        self.notice = 'marked for deletion'

    def unmark_deleted(self) -> None:
        if not self.state.rows:
            return
        self.state.unmark_deleted()
        self.notice = 'deletion mark removed'

    def purge_deleted(self) -> list[str]:
        """Move all marked messages to Trash and return failures."""
        return [error for state in self.maildirs.values() for error in state.purge_deleted(self.config.trash)]

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
        errors = self.purge_deleted()
        if errors:
            ui.pager(self.screen, 'Cannot move deleted messages', '\n'.join(errors), self.theme.header)
            return False
        return True

    def message_view(self) -> None:
        item = self.state.selected_message
        if 'S' not in item.flags:
            self.state.index.set_flags(item.key, add='S')
            self.state.reload_cached()
            item = self.state.selected_message
        message = self._message()
        body = self._render_body(message)
        while True:
            key = ui.pager(self.screen, item.subject, header_block(message) + '\n\n' + body, self.theme.header)
            if key in ui.KEYS['back']:
                return
            if key in ui.KEYS['parts']:
                self.parts_view(message)
            elif key in ui.KEYS['reply']:
                self.compose(compose.reply(message, body, self.config), replied_key=item.key)
            elif key in ui.KEYS['reply_all']:
                self.compose(compose.reply(message, body, self.config, all_recipients=True), replied_key=item.key)
            elif key in ui.KEYS['forward']:
                self.compose(compose.forward(message, body, self.config))

    def show_opener_errors(self) -> None:
        errors = self.mime.reap()
        if errors:
            ui.pager(self.screen, 'External opener failed', '\n\n'.join(errors), self.theme.header)

    def manual_refresh(self) -> None:
        if hook := self.config.hooks.pre_refresh:
            try:
                command = [argument.replace('{maildir}', str(self.state.path)) for argument in shlex.split(hook)]
                if not command:
                    raise ValueError('command is empty')
                ui.status(self.screen, 'running pre-refresh hook...', self.theme.status)
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                output, _ = process.communicate()
            except (OSError, ValueError) as exc:
                ui.pager(self.screen, 'Pre-refresh hook failed', str(exc), self.theme.header)
            else:
                if output:
                    ui.pager(
                        self.screen,
                        'Pre-refresh hook output',
                        output.decode('utf-8', errors='replace'),
                        self.theme.header,
                    )
        self.state.refresh()
        self.notice = 'refreshed'

    def parts_view(self, message: EmailMessage) -> None:
        rows = part_rows(message)
        selected = 0
        while True:
            self.show_opener_errors()
            self.screen.erase()
            height, width = self.screen.getmaxyx()
            ui.put(self.screen, 0, 0, ' MIME parts '.ljust(width), width, self.theme.header)
            visible = max(1, height - 1)
            start = min(max(0, selected - visible + 1), selected)
            for index, row in enumerate(rows[start : start + visible], 1):
                attr = self.theme.indicator if start + index - 1 == selected else 0
                ui.put(self.screen, index, 0, '  ' * row.depth + row.label, width, attr)
            self.screen.refresh()
            key = self.screen.getch()
            if key in ui.KEYS['back']:
                return
            if key in ui.KEYS['down']:
                selected = min(len(rows) - 1, selected + 1)
            elif key in ui.KEYS['up']:
                selected = max(0, selected - 1)
            elif key in ui.KEYS['open'] and not rows[selected].part.is_multipart():
                try:
                    self.mime.open(rows[selected].part)
                    self.notice = 'opened externally'
                except Exception as exc:
                    self.notice = str(exc)
            elif key in ui.KEYS['save'] and not rows[selected].part.is_multipart():
                value = ui.prompt(
                    self.screen,
                    'Save to: ',
                    rows[selected].part.get_filename() or '',
                    complete_paths=True,
                    status_attr=self.theme.status,
                )
                if value:
                    try:
                        path = save_part(rows[selected].part, Path(value))
                        self.notice = f'saved {path}'
                    except OSError as exc:
                        self.notice = str(exc)

    def compose(
        self,
        initial: compose.ComposeData,
        old_draft: Path | None = None,
        replied_key: str | None = None,
    ) -> None:
        data = initial
        edited = False
        errors: list[str] | None = None
        while True:
            curses.def_prog_mode()
            curses.endwin()
            try:
                data, changed = compose.edit(self.config, data, errors)
            finally:
                curses.reset_prog_mode()
                self.screen.refresh()
            if not changed and not edited:
                return
            edited = edited or changed
            errors = compose.validate(data)
            if errors:
                action = ui.choose(
                    self.screen,
                    'Compose invalid: edit, draft, discard',
                    'edx',
                    self.theme.status,
                    primary='e',
                    cancel='x',
                )
            else:
                action = ui.choose(
                    self.screen,
                    'Compose: send, edit, draft, discard',
                    'sedx',
                    self.theme.status,
                    primary='s',
                    cancel='x',
                )
            if action == 'e':
                continue
            if action == 'x':
                return
            try:
                if action == 'd':
                    delivery.save_draft(data, self.config)
                    self.notice = 'draft saved'
                else:
                    delivery.send(data, self.config)
                    self.notice = 'message sent'
                    if replied_key:
                        try:
                            self.state.index.set_flags(replied_key, add='R')
                            self.state.reload_cached()
                        except (OSError, KeyError) as flag_exc:
                            self.notice = f'message sent; cannot mark replied: {flag_exc}'
                if old_draft:
                    old_draft.unlink(missing_ok=True)
                return
            except (OSError, delivery.DeliveryError) as exc:
                self.notice = str(exc)
                ui.pager(self.screen, 'Delivery failed', str(exc), self.theme.header)
                retry = ui.choose(
                    self.screen,
                    'Delivery failed: edit, draft, discard',
                    'edx',
                    self.theme.status,
                    primary='e',
                    cancel='x',
                )
                if retry == 'e':
                    continue
                if retry == 'd':
                    try:
                        delivery.save_draft(data, self.config)
                        if old_draft:
                            old_draft.unlink(missing_ok=True)
                        self.notice = 'draft saved'
                    except OSError as draft_exc:
                        self.notice = str(draft_exc)
                return

    def resume(self) -> None:
        if self.state.path.resolve() != self.config.drafts.resolve() or not self.state.rows:
            self.notice = 'resume is available only in the Drafts Maildir'
            return
        old_path = self.state.path / self.state.selected_message.path
        message = self._message()
        with tempfile.TemporaryDirectory(prefix='stamm-draft-') as workspace:
            self.compose(delivery.resume_draft(message, Path(workspace)), old_path)
        self.state.refresh()

    def run(self) -> None:
        self.screen.keypad(True)
        curses.curs_set(0)
        try:
            self.reconcile()
            while True:
                self.show_opener_errors()
                self.draw_index()
                key = self.screen.getch()
                if key in ui.KEYS['back']:
                    if self.confirm_exit():
                        return
                    continue
                if key in ui.KEYS['down'] and self.state.rows:
                    self.state.selected = min(len(self.state.rows) - 1, self.state.selected + 1)
                elif key in ui.KEYS['up'] and self.state.rows:
                    self.state.selected = max(0, self.state.selected - 1)
                elif key in ui.KEYS['open'] and self.state.rows:
                    self.message_view()
                elif key in ui.KEYS['refresh']:
                    self.manual_refresh()
                elif key in ui.KEYS['change']:
                    value = ui.prompt(
                        self.screen,
                        'Maildir: ',
                        str(self.config.root) + '/',
                        complete_paths=True,
                        status_attr=self.theme.status,
                    )
                    if value:
                        try:
                            self.open_maildir(Path(value))
                        except (OSError, ValueError) as exc:
                            self.notice = str(exc)
                elif key in ui.KEYS['compose']:
                    self.compose(compose.new(self.config))
                elif key in ui.KEYS['parts'] and self.state.rows:
                    self.parts_view(self._message())
                elif key in ui.KEYS['reply'] and self.state.rows:
                    message = self._message()
                    self.compose(
                        compose.reply(message, self._render_body(message), self.config),
                        replied_key=self.state.selected_message.key,
                    )
                elif key in ui.KEYS['reply_all'] and self.state.rows:
                    message = self._message()
                    self.compose(
                        compose.reply(message, self._render_body(message), self.config, all_recipients=True),
                        replied_key=self.state.selected_message.key,
                    )
                elif key in ui.KEYS['forward'] and self.state.rows:
                    message = self._message()
                    self.compose(compose.forward(message, self._render_body(message), self.config))
                elif key in ui.KEYS['delete'] and self.state.rows:
                    self.mark_deleted()
                elif key in ui.KEYS['undelete'] and self.state.rows:
                    self.unmark_deleted()
                elif key in ui.KEYS['flag'] and self.state.rows:
                    item = self.state.selected_message
                    self.state.index.set_flags(
                        item.key, remove='F' if 'F' in item.flags else '', add='' if 'F' in item.flags else 'F'
                    )
                    self.state.reload_cached()
                elif key in ui.KEYS['unread'] and self.state.rows:
                    self.state.index.set_flags(self.state.selected_message.key, remove='S')
                    self.state.reload_cached()
                elif key in ui.KEYS['resume']:
                    self.resume()
        finally:
            for state in self.maildirs.values():
                state.index.close()
            self.mime.close()
