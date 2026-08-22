"""Declarative configuration schema."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from email.utils import getaddresses
from pathlib import Path
from typing import Callable, TypeVar

from .schema import Typ, as_kv, as_list, field, optfield

T = TypeVar('T')

COLOR_NAMES = frozenset(
    {
        'default',
        'black',
        'red',
        'green',
        'yellow',
        'blue',
        'magenta',
        'cyan',
        'white',
        'bright-black',
        'bright-red',
        'bright-green',
        'bright-yellow',
        'bright-blue',
        'bright-magenta',
        'bright-cyan',
        'bright-white',
    }
)
COLOR_ATTRIBUTES = frozenset({'bold', 'dim', 'reverse', 'underline', 'standout'})


def color(value: object) -> str:
    value = str(value)
    if value not in COLOR_NAMES and not value.isdecimal():
        raise ValueError(f'unknown color: {value}')
    return value


def color_attribute(value: object) -> str:
    value = str(value)
    if value not in COLOR_ATTRIBUTES:
        raise ValueError(f'unknown color attribute: {value}')
    return value


def as_tuple(typ: Typ[T]) -> Callable[[object], tuple[T, ...]]:
    convert = as_list(typ)

    def inner(value: object) -> tuple[T, ...]:
        return tuple(convert(value))

    return inner


def identities(value: object) -> tuple[str, ...]:
    result = as_tuple(str)(value)
    if not result or any(not address for _, address in getaddresses(result)):
        raise ValueError('must contain at least one valid address')
    return result


@dataclass(frozen=True)
class ColorStyle:
    fg: str | None = optfield(color)
    bg: str | None = optfield(color)
    attrs: tuple[str, ...] = field(as_tuple(color_attribute), default=(), required=False)


@dataclass(frozen=True)
class ColorConfig:
    normal: ColorStyle | None = optfield(ColorStyle)
    header: ColorStyle | None = optfield(ColorStyle)
    status: ColorStyle | None = optfield(ColorStyle)
    indicator: ColorStyle | None = optfield(ColorStyle)
    index_date: ColorStyle | None = optfield(ColorStyle)
    index_flags: ColorStyle | None = optfield(ColorStyle)
    index_sender: ColorStyle | None = optfield(ColorStyle)
    index_subject: ColorStyle | None = optfield(ColorStyle)


DEFAULT_COLORS = ColorConfig(None, None, None, None, None, None, None, None)


@dataclass(frozen=True)
class MimeRule:
    type: str = field(str)
    display: str | None = optfield(str)
    open: str | None = optfield(str)

    def matches(self, content_type: str) -> bool:
        return fnmatch.fnmatchcase(content_type.lower(), self.type.lower())


@dataclass(frozen=True)
class Config:
    root: Path = field(Path)
    spool: Path = field(Path)
    sent: Path = field(Path)
    drafts: Path = field(Path)
    trash: Path = field(Path)
    editor: str = field(str)
    sendmail: str = field(str)
    identities: tuple[str, ...] = field(identities)
    auto_view: tuple[str, ...] = field(as_tuple(str), default=(), required=False)
    alternative_order: tuple[str, ...] = field(as_tuple(str), default=('text/plain', 'text/html'), required=False)
    signatures: dict[str, Path] = field(as_kv(Path), default={}, required=False)
    mime: tuple[MimeRule, ...] = field(as_tuple(MimeRule), default=(), required=False)
    colors: ColorConfig = field(ColorConfig, default=DEFAULT_COLORS, required=False)

    @property
    def identity_addresses(self) -> tuple[str, ...]:
        return tuple(address.lower() for _, address in getaddresses(self.identities) if address)
