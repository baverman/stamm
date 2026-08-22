"""Small curses drawing, pager, prompt, and completion helpers."""

from __future__ import annotations

import curses
import os
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from email.utils import parseaddr
from pathlib import Path

from .config_model import ColorConfig, ColorStyle

KEYS = {
    'down': (ord('j'), curses.KEY_DOWN),
    'up': (ord('k'), curses.KEY_UP),
    'open': (10, 13, curses.KEY_ENTER),
    'back': (ord('q'),),
    'change': (ord('c'),),
    'command': (ord(':'),),
    'compose': (ord('m'),),
    'reply': (ord('r'),),
    'reply_all': (ord('g'),),
    'forward': (ord('f'),),
    'flag': (ord('F'),),
    'unread': (ord('N'),),
    'parts': (ord('v'),),
    'resume': (ord('e'),),
    'refresh': (ord('R'),),
    'save': (ord('s'),),
    'delete': (ord('d'),),
    'undelete': (ord('u'),),
}

MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
COLOR_INDEXES = {
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


@dataclass(frozen=True, slots=True)
class CursesTheme:
    normal: int
    header: int
    status: int
    indicator: int
    index_date: int
    index_flags: int
    index_sender: int
    index_subject: int


def _color_index(value: str) -> int:
    if value == 'default':
        return -1
    index = int(value) if value.isdecimal() else COLOR_INDEXES[value]
    if index >= curses.COLORS:
        raise RuntimeError(f'terminal supports {curses.COLORS} colors, but color index {index} was requested')
    return index


def _attributes(names: tuple[str, ...]) -> int:
    result = 0
    for name in names:
        result |= COLOR_ATTRIBUTES[name]
    return result


def initialize_colors(window: curses.window, colors: ColorConfig) -> CursesTheme:
    """Allocate curses color pairs and return their final attributes."""
    normal = colors.normal or ColorStyle('default', 'default', ())
    normal_fg = 'default' if normal.fg is None else normal.fg
    normal_bg = 'default' if normal.bg is None else normal.bg
    pairs: dict[tuple[int, int], int] = {}
    next_pair = 1
    has_colors = curses.has_colors()
    if has_colors:
        try:
            curses.start_color()
            curses.use_default_colors()
        except curses.error as exc:
            raise RuntimeError(f'cannot initialize terminal colors: {exc}') from exc

    def attr(style: ColorStyle | None) -> int:
        nonlocal next_pair
        style = style or ColorStyle(None, None, ())
        result = _attributes(style.attrs)
        if not has_colors:
            return result
        foreground = _color_index(normal_fg if style.fg is None else style.fg)
        background = _color_index(normal_bg if style.bg is None else style.bg)
        colors_key = (foreground, background)
        pair = pairs.get(colors_key)
        if pair is None:
            if next_pair >= curses.COLOR_PAIRS:
                raise RuntimeError('terminal does not provide enough color pairs for the configured roles')
            pair = next_pair
            next_pair += 1
            try:
                curses.init_pair(pair, foreground, background)
            except curses.error as exc:
                raise RuntimeError(f'cannot initialize terminal colors: {exc}') from exc
            pairs[colors_key] = pair
        return result | curses.color_pair(pair)

    theme = CursesTheme(
        normal=attr(normal),
        header=attr(colors.header),
        status=attr(colors.status),
        indicator=attr(colors.indicator),
        index_date=attr(colors.index_date),
        index_flags=attr(colors.index_flags),
        index_sender=attr(colors.index_sender),
        index_subject=attr(colors.index_subject),
    )
    window.bkgd(' ', theme.normal)
    return theme


def format_index_date(timestamp: float, now: float | None = None) -> str:
    """Format an index date in a fixed 12-character field."""
    current = time.time() if now is None else now
    value = datetime.fromtimestamp(timestamp).astimezone()
    month = MONTHS[value.month - 1]
    if current - timestamp >= 365 * 24 * 60 * 60:
        return f'{value.year:04d} {month} {value.day:02d} '
    return f'{month} {value.day:02d} {value.hour:02d}:{value.minute:02d}'


def format_sender(value: str) -> str:
    """Show the display name when present, otherwise show the address."""
    name, address = parseaddr(value.replace('\n', ' '))
    return name or address or value.replace('\n', ' ')


def viewport_start(selected: int, total: int, visible: int, current: int) -> int:
    """Keep the cursor inside a 30% scroll margin, capped at 10 rows."""
    if total <= visible:
        return 0
    margin = min(10, int(visible * 0.3), max(0, (visible - 1) // 2))
    # Permit trailing blank rows so the final message can stay above the
    # bottom scroll margin instead of being forced onto the last screen row.
    maximum = total - visible + margin
    start = min(max(0, current), maximum)
    if selected < start + margin:
        start = selected - margin
    elif selected >= start + visible - margin:
        start = selected - visible + margin + 1
    return min(max(0, start), maximum)


def wrap_text(text: str, columns: int) -> list[str]:
    """Wrap text to terminal cell width while preserving whitespace."""
    columns = max(1, columns)
    result: list[str] = []
    for source in text.splitlines() or ['']:
        source = source.expandtabs(8)
        if not source:
            result.append('')
            continue
        chunk: list[str] = []
        used = 0
        for character in source:
            cell_width = (
                0
                if unicodedata.combining(character)
                else (2 if unicodedata.east_asian_width(character) in ('W', 'F') else 1)
            )
            if chunk and used + cell_width > columns:
                result.append(''.join(chunk))
                chunk = []
                used = 0
            chunk.append(character)
            used += cell_width
        result.append(''.join(chunk))
    return result


def put(window: curses.window, y: int, x: int, text: str, width: int, attr: int = 0) -> None:
    if width > 0:
        try:
            window.addnstr(y, x, text, width, attr)
        except curses.error:
            pass


def status(window: curses.window, text: str, attr: int) -> None:
    height, width = window.getmaxyx()
    put(window, height - 1, 0, text.ljust(width), width, attr)
    window.refresh()


def choose(
    window: curses.window,
    prompt_text: str,
    choices: str,
    status_attr: int,
    *,
    primary: str,
    cancel: str,
) -> str:
    if primary not in choices or cancel not in choices:
        raise ValueError('primary and cancel actions must be choices')
    status(window, f'{prompt_text} [{"/".join(choices)}]', status_attr)
    while True:
        key = window.get_wch()
        if key in ('\n', '\r', curses.KEY_ENTER):
            return primary
        if key in ('\x1b', 27):
            return cancel
        if isinstance(key, str) and key in choices:
            return key


def prompt(
    window: curses.window,
    label: str,
    initial: str = '',
    *,
    complete_paths: bool = False,
    status_attr: int,
) -> str | None:
    value = initial
    while True:
        status(window, label + value, status_attr)
        key = window.get_wch()
        if key in ('\n', '\r'):
            return os.path.expandvars(os.path.expanduser(value)) if complete_paths else value
        if key == '\x1b':
            return None
        if key in ('\b', '\x7f') or key == curses.KEY_BACKSPACE:
            value = value[:-1]
        elif key == '\t' and complete_paths:
            path = Path(value or '.')
            parent, prefix = (path, '') if value.endswith(os.sep) else (path.parent, path.name)
            try:
                matches = sorted(item for item in parent.iterdir() if item.name.startswith(prefix))
                if len(matches) == 1:
                    value = str(matches[0]) + (os.sep if matches[0].is_dir() else '')
                elif matches:
                    common = os.path.commonprefix([item.name for item in matches])
                    value = str(parent / common)
            except OSError:
                pass
        elif isinstance(key, str) and key.isprintable():
            value += key


def pager(window: curses.window, title: str, text: str, header_attr: int) -> int:
    """Display text and return the first key that is not a scroll command."""
    offset = 0
    while True:
        window.erase()
        height, width = window.getmaxyx()
        lines = wrap_text(text, width - 1)
        maximum = max(0, len(lines) - height + 1)
        offset = min(offset, maximum)
        put(window, 0, 0, title.ljust(width), width, header_attr)
        for row, line in enumerate(lines[offset : offset + height - 1], 1):
            put(window, row, 0, line, width - 1)
        window.refresh()
        key = window.getch()
        if key in KEYS['down']:
            offset = min(maximum, offset + 1)
        elif key in KEYS['up']:
            offset = max(0, offset - 1)
        else:
            return key
