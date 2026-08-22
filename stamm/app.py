"""Application state and curses screen transitions."""

from __future__ import annotations

import curses
import tempfile
from email.message import EmailMessage
from pathlib import Path

from . import compose, delivery, ui
from .config import Config
from .index import IndexedMessage, MessageIndex
from .message import header_block, parse_message, select_body
from .mime import MimeManager, part_rows, save_part
from .threads import ThreadRow, build_threads


class App:
    def __init__(self, screen: curses.window, config: Config, maildir: Path, theme: ui.CursesTheme):
        self.screen = screen
        self.config = config
        self.maildir = maildir
        self.index: MessageIndex | None = None
        self.rows: list[ThreadRow] = []
        self.selected = 0
        self.index_offset = 0
        self.notice = ''
        self.mime = MimeManager(config)
        self.pending_delete: dict[Path, set[str]] = {}
        self.theme = theme

    def open_maildir(self, path: Path) -> None:
        candidate = MessageIndex(path)
        try:
            rows = build_threads(candidate.refresh())
        except Exception:
            candidate.close()
            raise
        if self.index:
            self.index.close()
        self.index = candidate
        self.maildir = path
        self.rows = rows
        self.selected = max(0, len(self.rows) - 1)
        self.index_offset = 0

    def _load_rows(self, messages: list[IndexedMessage]) -> None:
        key = self.rows[self.selected].message.key if self.rows else None
        self.rows = build_threads(messages)
        if key:
            self.selected = next((i for i, row in enumerate(self.rows) if row.message.key == key), 0)

    def refresh(self) -> None:
        assert self.index
        self._load_rows(self.index.refresh())

    def reload_cached(self) -> None:
        assert self.index
        self._load_rows(self.index.messages())

    def draw_index(self) -> None:
        self.screen.erase()
        height, width = self.screen.getmaxyx()
        theme = self.theme
        ui.put(self.screen, 0, 0, f'Stamm — {self.maildir}'.ljust(width), width, theme.header)
        visible = max(1, height - 2)
        self.index_offset = ui.viewport_start(self.selected, len(self.rows), visible, self.index_offset)
        start = self.index_offset
        deleted = self.pending_delete.get(self.maildir.resolve(), set())
        date_attr = theme.index_date
        flags_attr = theme.index_flags
        sender_attr = theme.index_sender
        subject_attr = theme.index_subject
        indicator_attr = theme.indicator
        for y, row in enumerate(self.rows[start : start + visible], 1):
            item = row.message
            marked = item.key in deleted
            flags = ('D' if marked else ('N' if 'S' not in item.flags else ' ')) + ('F' if 'F' in item.flags else ' ')
            sender = ui.format_sender(item.sender)[:20]
            subject = '  ' * row.depth + item.subject.replace('\n', ' ')
            date = ui.format_index_date(item.timestamp)
            line = f'{date} {flags:2} {sender:20}  {subject}'
            selected = start + y - 1 == self.selected
            attr = indicator_attr if selected else 0
            ui.put(self.screen, y, 0, line.ljust(width), width, attr)
            if not selected:
                ui.put(self.screen, y, 0, date, 12, date_attr)
                ui.put(self.screen, y, 13, flags, 2, flags_attr)
                ui.put(self.screen, y, 16, sender, 20, sender_attr)
                ui.put(self.screen, y, 38, subject, max(0, width - 38), subject_attr)
        count = len(self.rows)
        summary = f' {count} {"message" if count == 1 else "messages"}'
        ui.status(self.screen, self.notice or summary, theme.status)
        self.notice = ''

    def _message(self) -> EmailMessage:
        item = self.rows[self.selected].message
        return parse_message(self.maildir / item.path)

    def _render_body(self, message: EmailMessage) -> str:
        part = select_body(message, self.config)
        if part is None:
            return '[No displayable body. Press v to inspect MIME parts.]'
        try:
            return self.mime.display(part)
        except Exception as exc:
            return f'[Cannot display {part.get_content_type()}: {exc}]'

    def mark_deleted(self) -> None:
        if not self.rows:
            return
        folder = self.maildir.resolve()
        if folder == self.config.trash.resolve():
            self.notice = 'messages in Trash cannot be marked for deletion'
            return
        key = self.rows[self.selected].message.key
        self.pending_delete.setdefault(folder, set()).add(key)
        self.notice = 'marked for deletion'
        self.selected = min(len(self.rows) - 1, self.selected + 1)

    def unmark_deleted(self) -> None:
        if not self.rows:
            return
        folder = self.maildir.resolve()
        keys = self.pending_delete.get(folder)
        if keys:
            keys.discard(self.rows[self.selected].message.key)
            if not keys:
                self.pending_delete.pop(folder, None)
        self.notice = 'deletion mark removed'
        self.selected = min(len(self.rows) - 1, self.selected + 1)

    def purge_deleted(self) -> list[str]:
        """Move all marked messages to Trash and return failures."""
        errors: list[str] = []
        current_folder = self.maildir.resolve()
        current_position = self.selected
        for folder, keys in list(self.pending_delete.items()):
            index = self.index if folder == current_folder else None
            owned_index = index is None
            try:
                if index is None:
                    index = MessageIndex(folder)
                for key in list(keys):
                    try:
                        if index.get(key) is not None:
                            index.move_to(key, self.config.trash)
                        keys.discard(key)
                    except (OSError, ValueError) as exc:
                        errors.append(f'{folder}: {exc}')
            except OSError as exc:
                errors.append(f'{folder}: {exc}')
            finally:
                if owned_index and index is not None:
                    index.close()
            if not keys:
                self.pending_delete.pop(folder, None)
        if self.index and current_folder == self.maildir.resolve():
            self.rows = build_threads(self.index.messages())
            self.selected = min(current_position, max(0, len(self.rows) - 1))
        return errors

    def confirm_exit(self) -> bool:
        count = sum(len(keys) for keys in self.pending_delete.values())
        if not count:
            return True
        answer = ui.choose(self.screen, f'Move {count} deleted message(s) to Trash?', 'yn', self.theme.status)
        if answer == 'n':
            return True
        errors = self.purge_deleted()
        if errors:
            ui.pager(self.screen, 'Cannot move deleted messages', '\n'.join(errors), self.theme.header)
            return False
        return True

    def message_view(self) -> None:
        assert self.index
        item = self.rows[self.selected].message
        if 'S' not in item.flags:
            self.index.set_flags(item.key, add='S')
            self.reload_cached()
            item = self.rows[self.selected].message
        message = self._message()
        body = self._render_body(message)
        while True:
            key = ui.pager(self.screen, item.subject, header_block(message) + '\n\n' + body, self.theme.header)
            if key in ui.KEYS['back']:
                return
            if key in ui.KEYS['parts']:
                self.parts_view(message)
            elif key in ui.KEYS['reply']:
                self.compose(compose.reply(message, body, self.config))
            elif key in ui.KEYS['reply_all']:
                self.compose(compose.reply(message, body, self.config, all_recipients=True))
            elif key in ui.KEYS['forward']:
                self.compose(compose.forward(message, body, self.config))

    def show_opener_errors(self) -> None:
        errors = self.mime.reap()
        if errors:
            ui.pager(self.screen, 'External opener failed', '\n\n'.join(errors), self.theme.header)

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

    def compose(self, initial: compose.ComposeData, old_draft: Path | None = None) -> None:
        data = initial
        while True:
            curses.def_prog_mode()
            curses.endwin()
            try:
                data = compose.edit(self.config, data)
            finally:
                curses.reset_prog_mode()
                self.screen.refresh()
            action = ui.choose(self.screen, 'Compose: send, edit, draft, discard', 'sedx', self.theme.status)
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
                if old_draft:
                    old_draft.unlink(missing_ok=True)
                return
            except (OSError, delivery.DeliveryError) as exc:
                self.notice = str(exc)
                ui.pager(self.screen, 'Delivery failed', str(exc), self.theme.header)
                retry = ui.choose(self.screen, 'Delivery failed: edit, draft, discard', 'edx', self.theme.status)
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
        if self.maildir.resolve() != self.config.drafts.resolve() or not self.rows:
            self.notice = 'resume is available only in the Drafts Maildir'
            return
        old_path = self.maildir / self.rows[self.selected].message.path
        message = self._message()
        with tempfile.TemporaryDirectory(prefix='stamm-draft-') as workspace:
            self.compose(delivery.resume_draft(message, Path(workspace)), old_path)
        self.refresh()

    def run(self) -> None:
        self.screen.keypad(True)
        curses.curs_set(0)
        try:
            self.open_maildir(self.maildir)
            while True:
                self.show_opener_errors()
                self.draw_index()
                key = self.screen.getch()
                if key in ui.KEYS['back']:
                    if self.confirm_exit():
                        return
                    continue
                if key in ui.KEYS['down'] and self.rows:
                    self.selected = min(len(self.rows) - 1, self.selected + 1)
                elif key in ui.KEYS['up'] and self.rows:
                    self.selected = max(0, self.selected - 1)
                elif key in ui.KEYS['open'] and self.rows:
                    self.message_view()
                elif key in ui.KEYS['refresh']:
                    self.refresh()
                    self.notice = 'refreshed'
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
                elif key in ui.KEYS['parts'] and self.rows:
                    self.parts_view(self._message())
                elif key in ui.KEYS['reply'] and self.rows:
                    message = self._message()
                    self.compose(compose.reply(message, self._render_body(message), self.config))
                elif key in ui.KEYS['reply_all'] and self.rows:
                    message = self._message()
                    self.compose(compose.reply(message, self._render_body(message), self.config, all_recipients=True))
                elif key in ui.KEYS['forward'] and self.rows:
                    message = self._message()
                    self.compose(compose.forward(message, self._render_body(message), self.config))
                elif key in ui.KEYS['delete'] and self.rows:
                    self.mark_deleted()
                elif key in ui.KEYS['undelete'] and self.rows:
                    self.unmark_deleted()
                elif key in ui.KEYS['flag'] and self.rows:
                    assert self.index is not None
                    item = self.rows[self.selected].message
                    self.index.set_flags(
                        item.key, remove='F' if 'F' in item.flags else '', add='' if 'F' in item.flags else 'F'
                    )
                    self.reload_cached()
                elif key in ui.KEYS['unread'] and self.rows:
                    assert self.index is not None
                    self.index.set_flags(self.rows[self.selected].message.key, remove='S')
                    self.reload_cached()
                elif key in ui.KEYS['resume']:
                    self.resume()
        finally:
            if self.index:
                self.index.close()
            self.mime.close()
