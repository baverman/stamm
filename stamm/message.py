"""Message parsing, MIME selection, and text rendering."""

from __future__ import annotations

from email import policy
from email.message import EmailMessage, Message
from email.parser import BytesParser
from pathlib import Path

from .config import Config


def parse_message(path: Path) -> EmailMessage:
    with path.open("rb") as stream:
        return BytesParser(policy=policy.default).parse(stream)


def payload_bytes(part: Message) -> bytes:
    value = part.get_payload(decode=True)
    if isinstance(value, bytes):
        return value
    return str(value or "").encode(part.get_content_charset() or "utf-8", errors="replace")


def payload_text(part: Message) -> str:
    try:
        if isinstance(part, EmailMessage):
            content = part.get_content()
            if isinstance(content, str):
                return content
    except (LookupError, UnicodeError, AttributeError):
        pass
    return payload_bytes(part).decode(part.get_content_charset() or "utf-8", errors="replace")


def select_body(message: Message, config: Config) -> Message | None:
    if message.get_content_type() == "multipart/alternative":
        parts = list(message.iter_parts())  # type: ignore[attr-defined]
        for wanted in config.alternative_order:
            found = next((part for part in parts if part.get_content_type() == wanted), None)
            if found is not None:
                return select_body(found, config)
    if message.is_multipart():
        for part in message.iter_parts():  # type: ignore[attr-defined]
            if part.get_content_disposition() == "attachment":
                continue
            selected = select_body(part, config)
            if selected is not None:
                return selected
        return None
    content_type = message.get_content_type()
    if content_type == "text/plain" or content_type in config.auto_view:
        return message
    return None


def header_block(message: Message) -> str:
    names = ("From", "To", "Cc", "Date", "Subject")
    return "\n".join(f"{name}: {message.get(name, '')}" for name in names if message.get(name))


def quote(text: str) -> str:
    return "\n".join("> " + line if line else ">" for line in text.splitlines())
