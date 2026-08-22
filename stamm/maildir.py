"""Maildir enumeration, creation, storage, and flag-safe renames."""

from __future__ import annotations

import errno
import os
import secrets
import shutil
import socket
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MaildirEntry:
    key: str
    path: Path
    relative_path: str
    flags: str
    size: int
    mtime_ns: int


def ensure_maildir(path: Path) -> None:
    for name in ('tmp', 'new', 'cur'):
        (path / name).mkdir(parents=True, exist_ok=True)


def split_name(name: str) -> tuple[str, str]:
    if ':2,' in name:
        key, flags = name.rsplit(':2,', 1)
        return key, ''.join(sorted(set(flags)))
    return name, ''


def scan(path: Path) -> dict[str, MaildirEntry]:
    entries: dict[str, MaildirEntry] = {}
    for directory in ('new', 'cur'):
        folder = path / directory
        if not folder.is_dir():
            raise NotADirectoryError(f'not a Maildir: {path}')
        for item in folder.iterdir():
            if not item.is_file():
                continue
            key, flags = split_name(item.name)
            stat = item.stat()
            entries[key] = MaildirEntry(key, item, str(item.relative_to(path)), flags, stat.st_size, stat.st_mtime_ns)
    return entries


def rename_flags(maildir: Path, relative_path: str, add: str = '', remove: str = '') -> tuple[str, str]:
    source = maildir / relative_path
    key, old_flags = split_name(source.name)
    flags = ''.join(sorted((set(old_flags) | set(add)) - set(remove)))
    target = maildir / 'cur' / f'{key}:2,{flags}'
    if target != source:
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, target)
    return str(target.relative_to(maildir)), flags


def _unique_name() -> str:
    return f'{time.time_ns()}.{os.getpid()}_{secrets.token_hex(6)}.{socket.gethostname()}'


def move(source_maildir: Path, relative_path: str, destination_maildir: Path) -> Path:
    """Move one message to another Maildir, including across filesystems."""
    ensure_maildir(destination_maildir)
    source = source_maildir / relative_path
    subdirectory = source.parent.name
    if subdirectory not in ('new', 'cur'):
        raise ValueError(f'invalid indexed Maildir path: {relative_path}')
    target = destination_maildir / subdirectory / source.name
    if target.exists():
        _, flags = split_name(source.name)
        suffix = f':2,{flags}' if ':2,' in source.name else ''
        target = destination_maildir / subdirectory / f'{_unique_name()}{suffix}'
    try:
        os.rename(source, target)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        temporary = destination_maildir / 'tmp' / _unique_name()
        try:
            with source.open('rb') as input_stream, temporary.open('xb') as output_stream:
                shutil.copyfileobj(input_stream, output_stream)
                output_stream.flush()
                os.fsync(output_stream.fileno())
            os.replace(temporary, target)
            source.unlink()
        finally:
            temporary.unlink(missing_ok=True)
    return target


def store(maildir: Path, content: bytes, *, flags: str = '', seen: bool = False) -> Path:
    """Atomically store complete message bytes and return the final path."""
    ensure_maildir(maildir)
    name = _unique_name()
    temporary = maildir / 'tmp' / name
    directory = 'cur' if seen or flags else 'new'
    final_name = f'{name}:2,{"".join(sorted(set(flags)))}' if directory == 'cur' else name
    final = maildir / directory / final_name
    with temporary.open('xb') as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, final)
    return final
