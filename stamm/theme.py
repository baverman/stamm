from dataclasses import dataclass

from .tui.theme import BaseTheme, Style, color, fallback


@dataclass(frozen=True)
class IndexTheme:
    indicator: int = fallback('indicator')
    column_date: int = 0
    column_flags: int = 0
    column_from: int = 0
    column_subject: int = 0


@dataclass(frozen=True)
class MessageTheme:
    header: int = 0
    header_date: int = fallback('message.header')
    header_from: int = fallback('message.header')
    header_to: int = fallback('message.header')
    header_subject: int = fallback('message.header')


@dataclass(frozen=True)
class Theme(BaseTheme):
    normal: int = 0
    header: int = color(Style(attrs=('reverse',)))
    status: int = color(Style(attrs=('reverse',)))
    indicator: int = color(Style(attrs=('reverse',)))
    index: IndexTheme = IndexTheme()
    message: MessageTheme = MessageTheme()
