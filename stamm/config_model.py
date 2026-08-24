"""Declarative configuration schema."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, fields, is_dataclass, make_dataclass
from email.utils import getaddresses
from pathlib import Path
from string import Formatter
from typing import Any, Callable, TypeVar, get_type_hints

from .schema import Typ, as_kv, as_list, field, optfield
from .theme import CursesTheme

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
    attrs: tuple[str, ...] | None = optfield(as_tuple(color_attribute))

    def fallback(self, other: ColorStyle) -> ColorStyle:
        return ColorStyle(
            self.fg or other.fg, self.bg or other.bg, self.attrs if self.attrs is not None else other.attrs
        )


def config_from_theme(theme: type[Any], name: str) -> type[Any]:
    config_fields: list[tuple[str, Any, Any]] = []
    hints = get_type_hints(theme)
    for theme_field in fields(theme):
        field_type = hints[theme_field.name]
        if isinstance(field_type, type) and is_dataclass(field_type):
            nested_name = field_type.__name__.removesuffix('Theme') + 'ColorConfig'
            nested = config_from_theme(field_type, nested_name)
            config_fields.append((theme_field.name, nested, field(nested, default=nested(), required=False)))
        elif field_type is int:
            config_fields.append((theme_field.name, ColorStyle | None, optfield(ColorStyle)))
        else:
            raise TypeError(f'unsupported theme field type: {field_type}')
    return make_dataclass(name, config_fields, frozen=True)


ColorConfig: Any = config_from_theme(CursesTheme, 'ColorConfig')
DEFAULT_COLORS: Any = ColorConfig()


@dataclass(frozen=True)
class MimeRule:
    type: str = field(str)
    display: str | None = optfield(str)
    open: str | None = optfield(str)

    def matches(self, content_type: str) -> bool:
        return fnmatch.fnmatchcase(content_type.lower(), self.type.lower())


@dataclass(frozen=True)
class HooksConfig:
    pre_refresh: str | None = optfield(str)


DEFAULT_HOOKS = HooksConfig(None)


INDEX_FIELDS = frozenset({'date', 'flags', 'from', 'subject'})


def index_format(value: object) -> str:
    value = str(value)
    fields: list[str] = []
    flexible = 0
    try:
        parts = Formatter().parse(value)
        for _literal, name, specification, conversion in parts:
            if name is None:
                continue
            specification = specification or ''
            if name not in INDEX_FIELDS:
                raise ValueError(f'unknown index field: {name}')
            if name in fields:
                raise ValueError(f'duplicate index field: {name}')
            if conversion is not None:
                raise ValueError('index fields do not support conversions')
            if specification == '*':
                flexible += 1
            elif not specification.isdecimal() or int(specification) <= 0:
                raise ValueError(f'invalid width for index field {name}: {specification}')
            fields.append(name)
    except ValueError as exc:
        raise ValueError(f'invalid index format: {exc}') from exc
    if not fields:
        raise ValueError('invalid index format: must contain at least one field')
    if flexible > 1:
        raise ValueError('invalid index format: only one field can use * width')
    return value


@dataclass(frozen=True)
class IndexConfig:
    format: str = field(index_format, default='{date:12} {flags:3} {from:25}  {subject:*}', required=False)


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
    hooks: HooksConfig = field(HooksConfig, default=DEFAULT_HOOKS, required=False)
    auto_view: tuple[str, ...] = field(as_tuple(str), default=(), required=False)
    alternative_order: tuple[str, ...] = field(as_tuple(str), default=('text/plain', 'text/html'), required=False)
    signatures: dict[str, Path] = field(as_kv(Path), default_factory=dict, required=False)
    mime: tuple[MimeRule, ...] = field(as_tuple(MimeRule), default=(), required=False)
    colors: ColorConfig = field(ColorConfig, default=DEFAULT_COLORS, required=False)
    index: IndexConfig = field(IndexConfig, default=IndexConfig(), required=False)
    keys: dict[str, dict[str, str]] = field(as_kv(as_kv(str)), default_factory=dict, required=False)

    @property
    def identity_addresses(self) -> tuple[str, ...]:
        return tuple(address.lower() for _, address in getaddresses(self.identities) if address)
