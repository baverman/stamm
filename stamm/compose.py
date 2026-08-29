from __future__ import annotations

import mimetypes
import os
import shlex
import subprocess
import tempfile
from dataclasses import dataclass, field
from email.message import Message
from email.utils import getaddresses, parseaddr
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .config import Config
from .message import header_block, payload_bytes, quote

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


class MailtoError(ValueError):
    pass


def _unquote_mailto(value: str) -> str:
    index = 0
    while (index := value.find('%', index)) >= 0:
        if index + 2 >= len(value) or not all(
            char in '0123456789abcdefABCDEF' for char in value[index + 1 : index + 3]
        ):
            raise MailtoError('invalid percent escape in mailto URI')
        index += 3
    try:
        return unquote(value, encoding='utf-8', errors='strict')
    except UnicodeDecodeError as exc:
        raise MailtoError('invalid UTF-8 in mailto URI') from exc


def from_mailto(uri: str, config: Config) -> ComposeData:
    if any(ord(char) <= 0x20 or ord(char) == 0x7F for char in uri):
        raise MailtoError('invalid character in mailto URI')
    try:
        parsed = urlsplit(uri)
    except ValueError as exc:
        raise MailtoError(f'invalid mailto URI: {exc}') from exc
    if parsed.scheme.lower() != 'mailto' or parsed.netloc or parsed.fragment:
        raise MailtoError('invalid mailto URI')

    values: dict[str, list[str]] = {'to': [], 'cc': [], 'bcc': [], 'subject': [], 'body': []}
    path = _unquote_mailto(parsed.path)
    if path:
        values['to'].append(path)
    if parsed.query:
        for field in parsed.query.split('&'):
            name, separator, value = field.partition('=')
            if not separator:
                raise MailtoError('invalid mailto query field')
            name = _unquote_mailto(name).lower()
            value = _unquote_mailto(value)
            if name in values:
                values[name].append(value)

    for name in ('to', 'cc', 'bcc'):
        if any(not valid_addresses(value) for value in values[name]):
            raise MailtoError(f'invalid {name} address in mailto URI')
    for name in ('to', 'cc', 'bcc', 'subject'):
        if any('\r' in value or '\n' in value for value in values[name]):
            raise MailtoError(f'invalid {name} field in mailto URI')

    return ComposeData(
        sender=config.identities[0],
        to=', '.join(filter(None, values['to'])),
        cc=', '.join(filter(None, values['cc'])),
        bcc=', '.join(filter(None, values['bcc'])),
        subject=values['subject'][-1] if values['subject'] else '',
        body=values['body'][-1] if values['body'] else '',
    )


def valid_addresses(value: str) -> bool:
    if not value.strip():
        return True
    parsed = getaddresses([value])
    return bool(parsed) and all(
        address and '@' in address and not any(char in address for char in '\r\n') for _, address in parsed
    )


def parse_buffer(text: str) -> ComposeData:
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
        value = value.strip()
        if name == 'Attach':
            if not value:
                continue
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
    if not data.attachments:
        lines.append('Attach:')
    return '\n'.join(lines) + '\n\n' + data.body


def validate(data: ComposeData) -> list[str]:
    errors: list[str] = []
    if not data.sender or not valid_addresses(data.sender) or len(getaddresses([data.sender])) != 1:
        errors.append('From must contain one valid address')
    if not any((data.to.strip(), data.cc.strip(), data.bcc.strip())):
        errors.append('at least one recipient is required')
    for name, value in (('To', data.to), ('Cc', data.cc), ('Bcc', data.bcc)):
        if not valid_addresses(value):
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


def edit(config: Config, initial: ComposeData, errors: list[str] | None = None) -> tuple[ComposeData, bool]:
    content = format_buffer(initial)
    if errors:
        content = '# ' + '\n# '.join(errors) + '\n' + content
    with tempfile.NamedTemporaryFile(
        'w+', suffix='.eml', prefix='stamm-compose-', encoding='utf-8', delete=False
    ) as stream:
        path = Path(stream.name)
        stream.write(content)
    try:
        result = subprocess.run([*shlex.split(config.editor), str(path)])
        if result.returncode:
            raise RuntimeError(f'editor exited with status {result.returncode}')
        edited = path.read_text(encoding='utf-8')
    finally:
        path.unlink(missing_ok=True)
    if edited == content:
        return initial, False
    data = parse_buffer(edited)
    data.in_reply_to = initial.in_reply_to
    data.references = initial.references
    return data, True


def new(config: Config) -> ComposeData:
    return ComposeData(sender=config.identities[0])


def reply_sender(message: Message, config: Config) -> str:
    fields = [str(message.get(name, '')) for name in ('To', 'Cc') if message.get(name)]
    recipients = {address.lower() for _, address in getaddresses(fields)}
    for identity in config.identities:
        if parseaddr(identity)[1].lower() in recipients:
            return identity
    return ''


def reply_subject(subject: str) -> str:
    return subject if subject.lower().startswith('re:') else f'Re: {subject}'


def reply(message: Message, rendered_body: str, config: Config, *, all_recipients: bool = False) -> ComposeData:
    sender = reply_sender(message, config)
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
        reply_subject(str(message.get('Subject', ''))),
        [],
        f'\nOn {date}, {author} wrote:\n{quote(rendered_body)}',
        message_id,
        references,
    )


def forward(message: Message, rendered_body: str, config: Config, workspace: Path) -> ComposeData:
    subject = str(message.get('Subject', ''))
    if not subject.lower().startswith('fwd:'):
        subject = 'Fwd: ' + subject

    attachments: list[Attachment] = []
    counter = 0
    for part in message.walk():
        if part.is_multipart():
            continue
        disposition = part.get_content_disposition()
        filename = part.get_filename()
        if disposition is None and filename is None and part.get_content_type() in ('text/plain', 'text/html'):
            continue
        counter += 1
        if filename:
            safe_filename = Path(filename).name
        else:
            extension = mimetypes.guess_extension(part.get_content_type()) or ''
            safe_filename = f'attachment-{counter}{extension}'
        path = workspace / f'{counter}-{safe_filename}'
        path.write_bytes(payload_bytes(part))
        attachments.append(Attachment(path, safe_filename))

    return ComposeData(
        config.identities[0],
        subject=subject,
        attachments=attachments,
        body='\n---------- Forwarded message ----------\n' + header_block(message) + '\n\n' + rendered_body,
    )
