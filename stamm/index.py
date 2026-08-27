from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime
from email import policy
from email.parser import BytesHeaderParser
from email.utils import parsedate_to_datetime
from pathlib import Path

from . import maildir

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
"""


class MessageIndex:
    def __init__(self, path: Path):
        if not (path / 'new').is_dir() or not (path / 'cur').is_dir():
            raise NotADirectoryError(f'not a Maildir: {path}')
        self.maildir = path
        self.connection = sqlite3.connect(path / '.stamm.sqlite3')
        self.connection.row_factory = sqlite3.Row
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.executescript(_SCHEMA)

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
        if limit is None:
            rows = self.connection.execute('SELECT * FROM messages')
        else:
            rows = self.connection.execute('SELECT * FROM messages ORDER BY timestamp DESC LIMIT ?', (limit,))
        return [self._from_row(row) for row in rows]

    def get(self, key: str) -> IndexedMessage | None:
        row = self.connection.execute('SELECT * FROM messages WHERE key = ?', (key,)).fetchone()
        return self._from_row(row) if row else None

    @staticmethod
    def _ids(value: str | None) -> tuple[str, ...]:
        if not value:
            return ()

        found = re.findall(r'<[^<>]+>', value)
        return tuple(found or value.split())

    def _parse(self, entry: maildir.MaildirEntry) -> IndexedMessage:
        with entry.path.open('rb') as stream:
            msg = BytesHeaderParser(policy=policy.default).parse(stream)
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
        return IndexedMessage(
            entry.key,
            entry.relative_path,
            entry.size,
            entry.mtime_ns,
            entry.flags,
            shown_date,
            timestamp,
            str(msg.get('From', '')),
            str(msg.get('To', '')),
            str(msg.get('Subject', '')),
            str(msg.get('Message-ID')) if msg.get('Message-ID') else None,
            reply_ids[-1] if reply_ids else None,
            refs,
        )

    def refresh(self) -> list[IndexedMessage]:
        disk = maildir.scan(self.maildir)
        cached = {item.key: item for item in self.messages()}
        with self.connection:
            for key in cached.keys() - disk.keys():
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
                item = self._parse(entry)
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
                cached[key] = item
        return list(cached.values())

    def set_flags(self, key: str, *, add: str = '', remove: str = '') -> IndexedMessage:
        item = self.get(key)
        if item is None:
            raise KeyError(key)
        path, flags = maildir.rename_flags(self.maildir, item.path, add, remove)
        with self.connection:
            self.connection.execute('UPDATE messages SET path=?, flags=? WHERE key=?', (path, flags, key))
        return replace(item, path=path, flags=flags)

    def move_to(self, key: str, destination: Path) -> Path:
        if self.maildir.resolve() == destination.resolve():
            raise ValueError('message is already in the destination Maildir')
        item = self.get(key)
        if item is None:
            raise KeyError(key)
        target = maildir.move(self.maildir, item.path, destination)
        with self.connection:
            self.connection.execute('DELETE FROM messages WHERE key = ?', (key,))
        return target
