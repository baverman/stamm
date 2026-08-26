from __future__ import annotations

import io
import mimetypes
import shlex
import subprocess
from email import policy
from email.generator import BytesGenerator
from email.message import EmailMessage, Message
from email.utils import formatdate, getaddresses, make_msgid, parseaddr
from pathlib import Path

from .compose import Attachment, ComposeData
from .config import Config
from .maildir import store
from .message import payload_bytes, payload_text


class DeliveryError(RuntimeError):
    pass


def append_signature(data: ComposeData, config: Config) -> str:
    if any(line == '-- ' for line in data.body.splitlines()):
        return data.body
    address = parseaddr(data.sender)[1].lower()
    path = config.signatures.get(address)
    if not path:
        return data.body
    try:
        signature = path.read_text(encoding='utf-8')
    except OSError as exc:
        raise DeliveryError(f'cannot read signature {path}: {exc}') from exc
    separator = '' if not data.body or data.body.endswith('\n') else '\n'
    return data.body + separator + signature


def build_message(
    data: ComposeData, config: Config, *, signing: bool = False, include_bcc: bool = True
) -> EmailMessage:
    message = EmailMessage(policy=policy.default)
    message['From'] = data.sender
    for name, value in (
        ('To', data.to),
        ('Cc', data.cc),
        ('Bcc', data.bcc if include_bcc else ''),
        ('Subject', data.subject),
    ):
        if value:
            message[name] = value
    message['Date'] = formatdate(localtime=True)
    message['Message-ID'] = make_msgid()
    if data.in_reply_to:
        message['In-Reply-To'] = data.in_reply_to
    if data.references:
        message['References'] = ' '.join(data.references)
    message.set_content(append_signature(data, config) if signing else data.body)
    for attachment in data.attachments:
        content_type, _ = mimetypes.guess_type(attachment.filename)
        maintype, subtype = (content_type or 'application/octet-stream').split('/', 1)
        message.add_attachment(
            attachment.path.read_bytes(), maintype=maintype, subtype=subtype, filename=attachment.filename
        )
    return message


def message_bytes(message: EmailMessage) -> bytes:
    stream = io.BytesIO()
    BytesGenerator(stream, policy=policy.default).flatten(message)
    return stream.getvalue()


def save_draft(data: ComposeData, config: Config) -> Path:
    return store(config.drafts, message_bytes(build_message(data, config)), flags='D', seen=True)


def envelope(data: ComposeData) -> tuple[str, list[str]]:
    sender = parseaddr(data.sender)[1]
    if not sender:
        raise DeliveryError('message has no envelope sender')
    recipients: list[str] = []
    seen: set[str] = set()
    for _, address in getaddresses([value for value in (data.to, data.cc, data.bcc) if value.strip()]):
        lower = address.lower()
        if address and lower not in seen:
            recipients.append(address)
            seen.add(lower)
    if not recipients:
        raise DeliveryError('message has no envelope recipients')
    return sender, recipients


def send(data: ComposeData, config: Config) -> Path:
    sender, recipients = envelope(data)
    command = [*shlex.split(config.sendmail), '-f', sender, *recipients]
    transport = build_message(data, config, signing=True, include_bcc=False)
    content = message_bytes(transport)
    try:
        sent_path = store(config.sent, content, flags='S', seen=True)
    except OSError as exc:
        raise DeliveryError(f'cannot save Sent message: {exc}') from exc
    try:
        result = subprocess.run(command, input=content, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        raise DeliveryError(f'cannot run sendmail command {shlex.join(command)}: {exc}') from exc
    if result.returncode:
        detail = result.stderr.decode('utf-8', errors='replace').strip()
        raise DeliveryError(
            f'sendmail command: {shlex.join(command)}\nexit status: {result.returncode}\nstderr:\n{detail or "[empty]"}'
        )
    return sent_path


def resume_draft(message: Message, workspace: Path) -> ComposeData:
    attachments: list[Attachment] = []
    body = ''
    counter = 0
    for part in message.walk():
        if part.is_multipart():
            continue
        if part.get_content_disposition() == 'attachment':
            counter += 1
            filename = Path(part.get_filename() or f'attachment-{counter}').name
            path = workspace / f'{counter}-{filename}'
            path.write_bytes(payload_bytes(part))
            attachments.append(Attachment(path, filename))
        elif not body and part.get_content_type() == 'text/plain':
            body = payload_text(part)
    return ComposeData(
        str(message.get('From', '')),
        str(message.get('To', '')),
        str(message.get('Cc', '')),
        str(message.get('Bcc', '')),
        str(message.get('Subject', '')),
        attachments,
        body,
        str(message.get('In-Reply-To')) if message.get('In-Reply-To') else None,
        tuple(str(message.get('References', '')).split()),
    )
