from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from time import monotonic

from . import maildir
from .message import normalize_header, payload_text

INITIAL_MESSAGE_LIMIT = 100


@dataclass(frozen=True)
class IndexedMessage:
    key: str
    path: str
    size: int
    mtime_ns: int
    flags: str
    date: str
    timestamp: float
    sender: str
    recipient: str
    subject: str
    message_id: str | None
    in_reply_to: str | None
    references: tuple[str, ...]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
 key TEXT PRIMARY KEY, path TEXT NOT NULL, size INTEGER NOT NULL,
 mtime_ns INTEGER NOT NULL, flags TEXT NOT NULL, date TEXT NOT NULL,
 timestamp REAL NOT NULL, sender TEXT NOT NULL, recipient TEXT NOT NULL,
 subject TEXT NOT NULL, message_id TEXT, in_reply_to TEXT, refs TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(
 key UNINDEXED, body, tokenize = 'unicode61 remove_diacritics 2'
);
"""


class _HTMLTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.ignored = 0

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag in ('script', 'style'):
            self.ignored += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ('script', 'style') and self.ignored:
            self.ignored -= 1

    def handle_data(self, data: str) -> None:
        if not self.ignored and data.strip():
            self.parts.append(data)

    def text(self) -> str:
        return ' '.join(self.parts)


class MessageIndex:
    def __init__(self, path: Path):
        if not (path / 'new').is_dir() or not (path / 'cur').is_dir():
            raise NotADirectoryError(f'not a Maildir: {path}')
        self.maildir = path
        self.connection = sqlite3.connect(path / '.stamm.sqlite3')
        self.connection.row_factory = sqlite3.Row
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.executescript(_SCHEMA)
        self._message_cache: dict[str, IndexedMessage] | None = None

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> MessageIndex:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _from_row(row: sqlite3.Row) -> IndexedMessage:
        refs = row['refs']
        return IndexedMessage(
            key=row['key'],
            path=row['path'],
            size=row['size'],
            mtime_ns=row['mtime_ns'],
            flags=row['flags'],
            date=row['date'],
            timestamp=row['timestamp'],
            sender=row['sender'],
            recipient=row['recipient'],
            subject=row['subject'],
            message_id=row['message_id'],
            in_reply_to=row['in_reply_to'],
            references=() if not refs or refs == '[]' else tuple(json.loads(refs)),
        )

    def messages(self, *, limit: int | None = None) -> list[IndexedMessage]:
        if limit is None and self._message_cache is not None:
            return list(self._message_cache.values())
        if limit is None:
            rows = self.connection.execute('SELECT * FROM messages')
        else:
            rows = self.connection.execute('SELECT * FROM messages ORDER BY timestamp DESC LIMIT ?', (limit,))
        messages = [self._from_row(row) for row in rows]
        if limit is None:
            self._message_cache = {item.key: item for item in messages}
        return messages

    def get(self, key: str) -> IndexedMessage | None:
        row = self.connection.execute('SELECT * FROM messages WHERE key = ?', (key,)).fetchone()
        return self._from_row(row) if row else None

    def search_body(self, query: str) -> set[str]:
        try:
            rows = self.connection.execute('SELECT key FROM message_fts WHERE message_fts MATCH ?', (query,))
            return {row['key'] for row in rows}
        except sqlite3.OperationalError as exc:
            raise ValueError(f'invalid body search: {exc}') from exc

    def reindex_fts(
        self,
        *,
        full: bool = False,
        progress: Callable[[int, int], None] | None = None,
    ) -> tuple[int, int]:
        messages = self.messages()
        message_keys = {item.key for item in messages}
        body_keys = {row['key'] for row in self.connection.execute('SELECT key FROM message_fts')}
        targets = messages if full else [item for item in messages if item.key not in body_keys]
        orphaned = body_keys - message_keys
        total = len(targets)
        next_progress = monotonic() + 0.1
        with self.connection:
            if full:
                self.connection.execute('DELETE FROM message_fts')
            else:
                for key in orphaned:
                    self.connection.execute('DELETE FROM message_fts WHERE key = ?', (key,))
            for processed, item in enumerate(targets, 1):
                path = self.maildir / item.path
                with path.open('rb') as stream:
                    message = BytesParser(policy=policy.default).parse(stream)
                self.connection.execute('INSERT INTO message_fts VALUES (?,?)', (item.key, self._body(message)))
                if progress is not None:
                    now = monotonic()
                    if now >= next_progress or processed == total:
                        progress(processed, total)
                        next_progress = now + 0.1
        return len(targets), len(orphaned)

    @staticmethod
    def _ids(value: str | None) -> tuple[str, ...]:
        if not value:
            return ()

        found = re.findall(r'<[^<>]+>', value)
        return tuple(found or value.split())

    @staticmethod
    def _body(message: Message) -> str:
        plain = [payload_text(part) for part in message.walk() if part.get_content_type() == 'text/plain']
        if plain:
            return '\n'.join(plain)
        html = [payload_text(part) for part in message.walk() if part.get_content_type() == 'text/html']
        result = []
        for content in html:
            parser = _HTMLTextParser()
            parser.feed(content)
            parser.close()
            result.append(parser.text())
        return '\n'.join(result)

    def _parse(self, entry: maildir.MaildirEntry, *, include_body: bool = True) -> tuple[IndexedMessage, str]:
        with entry.path.open('rb') as stream:
            msg = BytesParser(policy=policy.default).parse(stream)
        raw_date = str(msg.get('Date', ''))
        try:
            parsed = parsedate_to_datetime(raw_date)
            if parsed is None:
                raise ValueError
            timestamp = parsed.timestamp()
            shown_date = parsed.astimezone().strftime('%Y-%m-%d %H:%M')
        except (TypeError, ValueError, OverflowError):
            timestamp = entry.mtime_ns / 1_000_000_000
            shown_date = datetime.fromtimestamp(timestamp).astimezone().strftime('%Y-%m-%d %H:%M')
        refs = self._ids(str(msg.get('References', '')))
        reply_ids = self._ids(str(msg.get('In-Reply-To', '')))
        recipients = ', '.join(
            normalize_header(value) for name in ('To', 'Cc', 'Delivered-To') for value in msg.get_all(name, ())
        )
        item = IndexedMessage(
            entry.key,
            entry.relative_path,
            entry.size,
            entry.mtime_ns,
            entry.flags,
            shown_date,
            timestamp,
            normalize_header(msg.get('From', '')),
            recipients,
            normalize_header(msg.get('Subject', '')),
            str(msg.get('Message-ID')) if msg.get('Message-ID') else None,
            reply_ids[-1] if reply_ids else None,
            refs,
        )
        return item, self._body(msg) if include_body else ''

    def _store_message(self, item: IndexedMessage) -> None:
        self.connection.execute(
            'INSERT OR REPLACE INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (
                item.key,
                item.path,
                item.size,
                item.mtime_ns,
                item.flags,
                item.date,
                item.timestamp,
                item.sender,
                item.recipient,
                item.subject,
                item.message_id,
                item.in_reply_to,
                json.dumps(item.references),
            ),
        )

    def _store(self, item: IndexedMessage, body: str) -> None:
        self._store_message(item)
        self.connection.execute('DELETE FROM message_fts WHERE key = ?', (item.key,))
        self.connection.execute('INSERT INTO message_fts VALUES (?,?)', (item.key, body))

    def reindex(self, progress: Callable[[int, int], None] | None = None) -> int:
        disk = maildir.scan(self.maildir)
        total = len(disk)
        indexed: dict[str, IndexedMessage] = {}
        next_progress = monotonic() + 0.1
        self._message_cache = None
        with self.connection:
            self.connection.execute('DELETE FROM messages')
            for processed, (key, entry) in enumerate(disk.items(), 1):
                item, _body = self._parse(entry, include_body=False)
                self._store_message(item)
                indexed[key] = item
                if progress is not None:
                    now = monotonic()
                    if now >= next_progress or processed == total:
                        progress(processed, total)
                        next_progress = now + 0.1
        self._message_cache = indexed
        return total

    def refresh(self, *, force: bool = False) -> list[IndexedMessage]:
        disk = maildir.scan(self.maildir)
        if force:
            self._message_cache = None
        cached = {item.key: item for item in self.messages()}
        with self.connection:
            for key in cached.keys() - disk.keys():
                self.connection.execute('DELETE FROM message_fts WHERE key = ?', (key,))
                self.connection.execute('DELETE FROM messages WHERE key = ?', (key,))
                cached.pop(key)
            for key, entry in disk.items():
                old = cached.get(key)
                if old and old.size == entry.size and old.mtime_ns == entry.mtime_ns:
                    if old.path != entry.relative_path or old.flags != entry.flags:
                        self.connection.execute(
                            'UPDATE messages SET path=?, flags=? WHERE key=?', (entry.relative_path, entry.flags, key)
                        )
                        cached[key] = replace(old, path=entry.relative_path, flags=entry.flags)
                    continue
                item, body = self._parse(entry)
                self._store(item, body)
                cached[key] = item
        self._message_cache = cached
        return list(cached.values())

    def set_flags(self, key: str, *, add: str = '', remove: str = '') -> IndexedMessage:
        item = self.get(key)
        if item is None:
            raise KeyError(key)
        path, flags = maildir.rename_flags(self.maildir, item.path, add, remove)
        with self.connection:
            self.connection.execute('UPDATE messages SET path=?, flags=? WHERE key=?', (path, flags, key))
        item = replace(item, path=path, flags=flags)
        if self._message_cache is not None:
            self._message_cache[key] = item
        return item

    def move_to(self, key: str, destination: Path) -> Path:
        if self.maildir.resolve() == destination.resolve():
            raise ValueError('message is already in the destination Maildir')
        item = self.get(key)
        if item is None:
            raise KeyError(key)
        target = maildir.move(self.maildir, item.path, destination)
        with self.connection:
            self.connection.execute('DELETE FROM message_fts WHERE key = ?', (key,))
            self.connection.execute('DELETE FROM messages WHERE key = ?', (key,))
        if self._message_cache is not None:
            self._message_cache.pop(key, None)
        return target
