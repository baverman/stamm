"""Maildir-local SQLite message metadata index."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from email import policy
from email.parser import BytesHeaderParser
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
import sqlite3

from . import maildir


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
    subject: str
    message_id: str | None
    in_reply_to: str | None
    references: tuple[str, ...]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
 key TEXT PRIMARY KEY, path TEXT NOT NULL, size INTEGER NOT NULL,
 mtime_ns INTEGER NOT NULL, flags TEXT NOT NULL, date TEXT NOT NULL,
 timestamp REAL NOT NULL, sender TEXT NOT NULL, subject TEXT NOT NULL,
 message_id TEXT, in_reply_to TEXT, refs TEXT NOT NULL
);
"""


class MessageIndex:
    def __init__(self, path: Path):
        if not (path / "new").is_dir() or not (path / "cur").is_dir():
            raise NotADirectoryError(f"not a Maildir: {path}")
        self.maildir = path
        self.connection = sqlite3.connect(path / ".stamm.sqlite3")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(_SCHEMA)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> MessageIndex:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _from_row(row: sqlite3.Row) -> IndexedMessage:
        values = dict(row)
        values["references"] = tuple(json.loads(values.pop("refs")))
        return IndexedMessage(**values)

    def messages(self) -> list[IndexedMessage]:
        return [self._from_row(row) for row in self.connection.execute("SELECT * FROM messages")]

    def get(self, key: str) -> IndexedMessage | None:
        row = self.connection.execute("SELECT * FROM messages WHERE key = ?", (key,)).fetchone()
        return self._from_row(row) if row else None

    @staticmethod
    def _ids(value: str | None) -> tuple[str, ...]:
        if not value:
            return ()
        import re
        found = re.findall(r"<[^<>]+>", value)
        return tuple(found or value.split())

    def _parse(self, entry: maildir.MaildirEntry) -> IndexedMessage:
        with entry.path.open("rb") as stream:
            msg = BytesHeaderParser(policy=policy.default).parse(stream)
        raw_date = str(msg.get("Date", ""))
        try:
            parsed = parsedate_to_datetime(raw_date)
            if parsed is None:
                raise ValueError
            timestamp = parsed.timestamp()
            shown_date = parsed.astimezone().strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError, OverflowError):
            timestamp = entry.mtime_ns / 1_000_000_000
            shown_date = datetime.fromtimestamp(timestamp).astimezone().strftime("%Y-%m-%d %H:%M")
        refs = self._ids(str(msg.get("References", "")))
        reply_ids = self._ids(str(msg.get("In-Reply-To", "")))
        return IndexedMessage(
            entry.key, entry.relative_path, entry.size, entry.mtime_ns, entry.flags,
            shown_date, timestamp, str(msg.get("From", "")), str(msg.get("Subject", "")),
            str(msg.get("Message-ID")) if msg.get("Message-ID") else None,
            reply_ids[-1] if reply_ids else None, refs,
        )

    def refresh(self) -> list[IndexedMessage]:
        disk = maildir.scan(self.maildir)
        cached = {item.key: item for item in self.messages()}
        with self.connection:
            for key in cached.keys() - disk.keys():
                self.connection.execute("DELETE FROM messages WHERE key = ?", (key,))
            for key, entry in disk.items():
                old = cached.get(key)
                if old and old.size == entry.size and old.mtime_ns == entry.mtime_ns:
                    if old.path != entry.relative_path or old.flags != entry.flags:
                        self.connection.execute("UPDATE messages SET path=?, flags=? WHERE key=?", (entry.relative_path, entry.flags, key))
                    continue
                item = self._parse(entry)
                self.connection.execute(
                    "INSERT OR REPLACE INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (item.key, item.path, item.size, item.mtime_ns, item.flags, item.date,
                     item.timestamp, item.sender, item.subject, item.message_id,
                     item.in_reply_to, json.dumps(item.references)),
                )
        return self.messages()

    def set_flags(self, key: str, *, add: str = "", remove: str = "") -> IndexedMessage:
        item = self.get(key)
        if item is None:
            raise KeyError(key)
        path, flags = maildir.rename_flags(self.maildir, item.path, add, remove)
        with self.connection:
            self.connection.execute("UPDATE messages SET path=?, flags=? WHERE key=?", (path, flags, key))
        return replace(item, path=path, flags=flags)
