from dataclasses import dataclass, field, fields, is_dataclass
from operator import attrgetter
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from _typeshed import DataclassInstance


@dataclass(frozen=True)
class Style:
    fg: str | None = None
    bg: str | None = None
    attrs: tuple[str, ...] | None = None


def fallback(name: str, default: Style | None = None) -> int:
    return field(default=0, metadata={'fallback': name, 'default': default})


def color(default: Style) -> int:
    return field(default=0, metadata={'default': default})


def style_fallback(self: Style | None, other: Style | None) -> Style:
    if self is None:
        self = Style()
    if other is None:
        return self
    return Style(self.fg or other.fg, self.bg or other.bg, self.attrs if self.attrs is not None else other.attrs)


def fallback_info(
    info: dict[str, str], cls: type[DataclassInstance] | DataclassInstance, default_fallback: str, parent: str = ''
) -> None:
    for f in fields(cls):
        fname = parent + f.name
        if fname == default_fallback:
            continue
        else:
            if is_dataclass(f.type):
                info[fname] = '.'
                fallback_info(info, f.type, default_fallback, fname + '.')
            else:
                fb = f.metadata.get('fallback', default_fallback)
                info[fname] = fb


class FallbackInfo:
    _info: dict[str, str]
    _cache: dict[str, Style | None]

    def __init__(self, cls: type[DataclassInstance], default_fallback: str) -> None:
        self._info = {}
        self._cache = {}
        fallback_info(self._info, cls, default_fallback)

    def has_children(self, name: str) -> bool:
        return self._info.get(name) == '.'

    def resolve_fallback(self, name: str, root: object) -> Style | None:
        try:
            return self._cache[name]
        except KeyError:
            pass
        fb = self._info.get(name)
        if fb is None:
            style = None
        else:
            style = style_fallback(attrgetter(fb)(root), self.resolve_fallback(fb, root))
        self._cache[name] = style
        return style


class ThemeNode:
    def __init__(self, parent: str, root: object, info: FallbackInfo, resolve: Callable[[Style], int]) -> None:
        self._parent = parent
        self._root = root
        self._resolve = resolve
        self._info = info

    def __getattr__(self, name: str) -> object:
        fname = self._parent + name
        result: object
        if self._info.has_children(fname):
            result = ThemeNode(fname + '.', self._root, self._info, self._resolve)
        else:
            value = attrgetter(fname)(self._root)
            style = style_fallback(value, self._info.resolve_fallback(fname, self._root))
            result = self._resolve(style)
        setattr(self, name, result)
        return result


@dataclass(frozen=True)
class BaseTheme:
    normal: int = 0
    header: int = color(Style(attrs=('reverse',)))
    status: int = color(Style(attrs=('reverse',)))
    indicator: int = color(Style(attrs=('reverse',)))
