import curses
from dataclasses import dataclass, field, fields, is_dataclass
from operator import attrgetter
from typing import TYPE_CHECKING, Any, Callable, cast

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


COLOR_INDEXES = {
    'default': -1,
    'black': 0,
    'red': 1,
    'green': 2,
    'yellow': 3,
    'blue': 4,
    'magenta': 5,
    'cyan': 6,
    'white': 7,
    'bright-black': 8,
    'bright-red': 9,
    'bright-green': 10,
    'bright-yellow': 11,
    'bright-blue': 12,
    'bright-magenta': 13,
    'bright-cyan': 14,
    'bright-white': 15,
}

COLOR_ATTRIBUTES = {
    'bold': curses.A_BOLD,
    'dim': curses.A_DIM,
    'reverse': curses.A_REVERSE,
    'underline': curses.A_UNDERLINE,
    'standout': curses.A_STANDOUT,
}


def color_index(value: str) -> int:
    return int(value) if value.isdecimal() else COLOR_INDEXES[value]


def attributes(names: tuple[str, ...]) -> int:
    result = 0
    for name in names:
        result |= COLOR_ATTRIBUTES[name]
    return result


def make_theme[T](theme_cls: type[T], colors: Any) -> T:
    assert is_dataclass(theme_cls)

    pairs: dict[tuple[int, int], int] = {}
    next_pair = 1
    has_colors = curses.has_colors()
    if has_colors:
        try:
            curses.start_color()
            curses.use_default_colors()
        except curses.error as exc:
            raise RuntimeError(f'cannot initialize terminal colors: {exc}') from exc

    def fit_color(value: str) -> int:
        index = color_index(value)
        return index % curses.COLORS if index >= 0 else index

    def alloc_color(style: Style) -> int:
        nonlocal next_pair
        result = attributes(style.attrs or ())
        if not has_colors:
            return result
        colors_key = (fit_color(style.fg or 'default'), fit_color(style.bg or 'default'))
        pair = pairs.get(colors_key)
        if pair is None:
            if next_pair >= curses.COLOR_PAIRS:
                raise RuntimeError('terminal does not provide enough color pairs for the configured roles')
            pair = next_pair
            next_pair += 1
            try:
                curses.init_pair(pair, *colors_key)
            except curses.error as exc:
                raise RuntimeError(f'cannot initialize terminal colors: {exc}') from exc
            pairs[colors_key] = pair
        return result | curses.color_pair(pair)

    fbinfo = FallbackInfo(theme_cls, 'normal')
    return cast(T, ThemeNode('', colors, fbinfo, alloc_color))


@dataclass(frozen=True)
class BaseTheme:
    normal: int = 0
    header: int = color(Style(attrs=('reverse',)))
    status: int = color(Style(attrs=('reverse',)))
    indicator: int = color(Style(attrs=('reverse',)))
