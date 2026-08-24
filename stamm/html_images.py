"""Prepare images for HTML opened outside the mail client."""

from __future__ import annotations

import logging
import mimetypes
import re
from email.message import Message
from pathlib import Path
from urllib.parse import quote, unquote

from .message import payload_bytes

logger = logging.getLogger(__name__)

_CID_REFERENCE = re.compile(rb'cid:([^\s\"\'<>\)]+)', re.IGNORECASE)


def prepare_html_images(content: bytes, message: Message, directory: Path) -> bytes:
    images = [part for part in message.walk() if part.get_content_maintype() == 'image']
    reserved = {name for part in images if (name := _source_name(part)) is not None}
    cid_filenames: dict[str, str] = {}
    generated = 0

    for part in images:
        try:
            original_filename = part.get_filename()
            if original_filename is not None and not _is_safe_filename(original_filename):
                continue
            filename = _source_name(part)
            if filename is None:
                generated += 1
                extension = mimetypes.guess_extension(part.get_content_type()) or '.bin'
                filename = f'image-{generated}{extension}'
                while filename in reserved or (directory / filename).exists():
                    generated += 1
                    filename = f'image-{generated}{extension}'

            path = directory / filename
            if path.exists():
                continue
            path.write_bytes(payload_bytes(part))

            content_id = _content_id(part)
            if content_id is not None:
                cid_filenames[content_id.casefold()] = filename
        except Exception:
            logger.exception('failed to prepare HTML image')

    return _rewrite_cid_references(content, cid_filenames)


def _source_name(part: Message) -> str | None:
    filename = part.get_filename()
    if filename is not None and _is_safe_filename(filename):
        return filename

    location = part.get('Content-Location')
    if location is not None and _is_safe_filename(location):
        return location
    return None


def _is_safe_filename(filename: str) -> bool:
    path = Path(filename)
    return (
        bool(filename)
        and '\0' not in filename
        and filename not in ('.', '..')
        and not path.is_absolute()
        and path.name == filename
    )


def _content_id(part: Message) -> str | None:
    value = part.get('Content-ID')
    if value is None:
        return None
    value = value.strip()
    if value.startswith('<') and value.endswith('>'):
        value = value[1:-1]
    return value or None


def _rewrite_cid_references(content: bytes, filenames: dict[str, str]) -> bytes:
    def replace(match: re.Match[bytes]) -> bytes:
        try:
            content_id = unquote(match.group(1).decode('ascii')).casefold()
        except UnicodeDecodeError:
            return match.group(0)
        filename = filenames.get(content_id)
        if filename is None:
            return match.group(0)
        return quote(filename).encode('ascii')

    return _CID_REFERENCE.sub(replace, content)
