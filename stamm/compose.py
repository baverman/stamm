"""Composition buffers, validation, and reply/forward preparation."""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from dataclasses import dataclass, field
from email.message import Message
from email.utils import getaddresses, parseaddr
from pathlib import Path

from .config import Config
from .message import header_block, quote

HEADERS = ('From', 'To', 'Cc', 'Bcc', 'Subject')


@dataclass(frozen=True)
class Attachment:
    path: Path
    filename: str


@dataclass
class ComposeData:
    sender: str = ''
    to: str = ''
    cc: str = ''
    bcc: str = ''
    subject: str = ''
    attachments: list[Attachment] = field(default_factory=list)
    body: str = ''
    in_reply_to: str | None = None
    references: tuple[str, ...] = ()


def _valid_addresses(value: str) -> bool:
    if not value.strip():
        return True
    parsed = getaddresses([value])
    return bool(parsed) and all(
        address and '@' in address and not any(char in address for char in '\r\n') for _, address in parsed
    )


def parse_buffer(text: str) -> ComposeData:
    """Parse the editable format. Headers end at the first empty line."""
    lines = text.splitlines()
    values = {name: '' for name in HEADERS}
    attachments: list[Attachment] = []
    split = len(lines)
    for index, line in enumerate(lines):
        if not line:
            split = index + 1
            break
        name, separator, value = line.partition(':')
        if not separator:
            continue
        value = value.lstrip()
        if name == 'Attach':
            source, marker, filename = value.partition(' -> ')
            path = Path(os.path.expandvars(os.path.expanduser(source)))
            attachments.append(Attachment(path, filename if marker else path.name))
        elif name in values:
            values[name] = value
    return ComposeData(
        values['From'],
        values['To'],
        values['Cc'],
        values['Bcc'],
        values['Subject'],
        attachments,
        '\n'.join(lines[split:]),
    )


def format_buffer(data: ComposeData) -> str:
    lines = [
        f'From: {data.sender}',
        f'To: {data.to}',
        f'Cc: {data.cc}',
        f'Bcc: {data.bcc}',
        f'Subject: {data.subject}',
    ]
    for attachment in data.attachments:
        suffix = f' -> {attachment.filename}' if attachment.filename != attachment.path.name else ''
        lines.append(f'Attach: {attachment.path}{suffix}')
    return '\n'.join(lines) + '\n\n' + data.body


def validate(data: ComposeData) -> list[str]:
    errors: list[str] = []
    if not data.sender or not _valid_addresses(data.sender) or len(getaddresses([data.sender])) != 1:
        errors.append('From must contain one valid address')
    if not any((data.to.strip(), data.cc.strip(), data.bcc.strip())):
        errors.append('at least one recipient is required')
    for name, value in (('To', data.to), ('Cc', data.cc), ('Bcc', data.bcc)):
        if not _valid_addresses(value):
            errors.append(f'{name} contains an invalid address')
    for attachment in data.attachments:
        if not attachment.path.is_file():
            errors.append(f'attachment is not a readable regular file: {attachment.path}')
        else:
            try:
                with attachment.path.open('rb'):
                    pass
            except OSError:
                errors.append(f'attachment is not readable: {attachment.path}')
        if (
            not attachment.filename
            or Path(attachment.filename).name != attachment.filename
            or attachment.filename in ('.', '..')
        ):
            errors.append(f'unsafe attachment filename: {attachment.filename}')
    return errors


def edit(config: Config, initial: ComposeData, errors: list[str] | None = None) -> ComposeData:
    """Run the configured editor until the buffer is valid."""
    content = format_buffer(initial)
    while True:
        with tempfile.NamedTemporaryFile(
            'w+', suffix='.eml', prefix='stamm-compose-', encoding='utf-8', delete=False
        ) as stream:
            path = Path(stream.name)
            if errors:
                stream.write('# ' + '\n# '.join(errors) + '\n')
            stream.write(content)
        try:
            result = subprocess.run([*shlex.split(config.editor), str(path)])
            if result.returncode:
                raise RuntimeError(f'editor exited with status {result.returncode}')
            content = path.read_text(encoding='utf-8')
        finally:
            path.unlink(missing_ok=True)
        data = parse_buffer(content)
        data.in_reply_to = initial.in_reply_to
        data.references = initial.references
        errors = validate(data)
        if not errors:
            return data


def new(config: Config) -> ComposeData:
    return ComposeData(sender=config.identities[0])


def _reply_sender(message: Message, config: Config) -> str:
    fields = [str(message.get(name, '')) for name in ('To', 'Cc') if message.get(name)]
    recipients = {address.lower() for _, address in getaddresses(fields)}
    for identity in config.identities:
        if parseaddr(identity)[1].lower() in recipients:
            return identity
    return ''


def _reply_subject(subject: str) -> str:
    return subject if subject.lower().startswith('re:') else f'Re: {subject}'


def reply(message: Message, rendered_body: str, config: Config, *, all_recipients: bool = False) -> ComposeData:
    sender = _reply_sender(message, config)
    original_sender = str(message.get('Reply-To') or message.get('From', ''))
    to = [original_sender]
    cc: list[str] = []
    if all_recipients:
        own = {parseaddr(sender)[1].lower()} if parseaddr(sender)[1] else set()
        seen: set[str] = set()
        to, cc = [], []
        for target, fields in ((to, [original_sender, str(message.get('To', ''))]), (cc, [str(message.get('Cc', ''))])):
            for name, address in getaddresses([field for field in fields if field.strip()]):
                lower = address.lower()
                if address and lower not in own and lower not in seen:
                    target.append(f'{name} <{address}>' if name else address)
                    seen.add(lower)
    date = str(message.get('Date', 'an unknown date'))
    author = str(message.get('From', 'an unknown sender'))
    message_id = str(message.get('Message-ID')) if message.get('Message-ID') else None
    references = tuple(str(message.get('References', '')).split())
    if message_id:
        references += (message_id,)
    return ComposeData(
        sender,
        ', '.join(to),
        ', '.join(cc),
        '',
        _reply_subject(str(message.get('Subject', ''))),
        [],
        f'\nOn {date}, {author} wrote:\n{quote(rendered_body)}',
        message_id,
        references,
    )


def forward(message: Message, rendered_body: str, config: Config) -> ComposeData:
    subject = str(message.get('Subject', ''))
    if not subject.lower().startswith('fwd:'):
        subject = 'Fwd: ' + subject
    return ComposeData(
        config.identities[0],
        subject=subject,
        body='\n---------- Forwarded message ----------\n' + header_block(message) + '\n\n' + rendered_body,
    )
