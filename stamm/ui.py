"""Small curses drawing, pager, prompt, and completion helpers."""

from __future__ import annotations

import curses
import os
import time
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from email.utils import parseaddr
from pathlib import Path
from typing import TypeVar

from . import keys
from .config_model import ColorConfig, ColorStyle

T = TypeVar('T')

CHOOSE_ACTIONS = frozenset({'accept', 'cancel'})
CHOOSE_DEFAULT_BINDINGS: keys.BindingSpecs = {
    'ENTER': 'accept',
    '^[': 'cancel',
}
PAGER_ACTIONS = frozenset({'up', 'down', 'pageup', 'pagedown', 'home', 'end'})
PAGER_DEFAULT_BINDINGS: keys.BindingSpecs = {
    'j': 'down',
    'DOWN': 'down',
    'k': 'up',
    'UP': 'up',
    'PAGEUP': 'pageup',
    'PAGEDOWN': 'pagedown',
    'HOME': 'home',
    'END': 'end',
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
    choices: Mapping[str, T],
    status_attr: int,
    bindings: Mapping[keys.Key, str],
    *,
    primary: T,
) -> T | None:
    if primary not in choices.values():
        raise ValueError('primary item must be a choice')
    status(window, f'{prompt_text} [{"/".join(choices)}]', status_attr)
    while True:
        action, ch = keys.read(window, bindings)
        if action == 'accept':
            return primary
        if action == 'cancel':
            return None
        if isinstance(ch, str) and ch in choices:
            return choices[ch]


@dataclass(frozen=True, slots=True)
class Completion:
    value: str
    label: str | None = None
    accept: bool = True


Completer = Callable[[str, int], Sequence[Completion | str]]


def _character_width(character: str) -> int:
    if unicodedata.combining(character):
        return 0
    return 2 if unicodedata.east_asian_width(character) in ('W', 'F') else 1


def text_width(value: str) -> int:
    return sum(_character_width(character) for character in value)


def _input_view(value: str, cursor: int, columns: int) -> tuple[str, int]:
    if columns <= 0:
        return '', 0
    start = cursor
    used = 0
    while start > 0:
        width = _character_width(value[start - 1])
        if used + width >= columns:
            break
        start -= 1
        used += width
    end = start
    remaining = columns
    while end < len(value):
        width = _character_width(value[end])
        if width > remaining:
            break
        remaining -= width
        end += 1
    return value[start:end], text_width(value[start:cursor])


def _path_completion_items(value: str, cursor: int, *, directories_only: bool = False) -> list[Completion]:
    source = value[:cursor]
    suffix = value[cursor:]
    expanded = os.path.expandvars(os.path.expanduser(source))
    path = Path(expanded or '.')
    parent, prefix = (path, '') if source.endswith(os.sep) else (path.parent, path.name)
    try:
        matches = sorted(item for item in parent.iterdir() if item.name.startswith(prefix))
    except OSError:
        return []

    result: list[Completion] = []
    for item in matches:
        if directories_only and not item.is_dir():
            continue
        is_directory = item.is_dir()
        separator = os.sep if is_directory else ''
        label = item.name + separator
        is_maildir = directories_only and (item / 'cur').is_dir() and (item / 'new').is_dir()
        if is_maildir:
            label += ' [Maildir]'
        result.append(Completion(str(item) + separator + suffix, label, accept=is_maildir or not is_directory))
    return result


def _path_completions(value: str) -> list[str]:
    return [item.value for item in _path_completion_items(value, len(value))]


def path_completer(value: str, cursor: int) -> list[Completion]:
    return _path_completion_items(value, cursor)


def maildir_completer(value: str, cursor: int) -> list[Completion]:
    return _path_completion_items(value, cursor, directories_only=True)


def _add_history(history: list[str] | None, value: str, limit: int = 100) -> None:
    if history is None or not value:
        return
    history[:] = [entry for entry in history if entry != value]
    history.append(value)
    del history[:-limit]


def prompt(
    window: curses.window,
    label: str,
    initial: str = '',
    *,
    complete_paths: bool = False,
    completer: Completer | None = None,
    history: list[str] | None = None,
    status_attr: int,
) -> str | None:
    value = initial
    cursor = len(value)
    choices: list[Completion] = []
    selected = 0
    history_values = history if history is not None else []
    history_index = len(history_values)
    history_draft = value
    popup_rows = 0
    active_completer = path_completer if complete_paths and completer is None else completer

    def refresh_choices() -> None:
        nonlocal choices, selected
        if active_completer is None:
            choices = []
            return
        choices = [
            item if isinstance(item, Completion) else Completion(item) for item in active_completer(value, cursor)
        ]
        selected = min(selected, max(0, len(choices) - 1))

    def draw() -> None:
        nonlocal popup_rows
        height, width = window.getmaxyx()
        if height <= 0 or width <= 0:
            return
        rows = min(len(choices), max(0, height - 1), 8)
        start = min(max(0, selected - rows + 1), max(0, len(choices) - rows))
        clear_rows = max(rows, popup_rows)
        for offset in range(clear_rows):
            y = height - 2 - offset
            if y >= 0:
                put(window, y, 0, ' ' * width, width)
        for offset, item in enumerate(choices[start : start + rows]):
            y = height - 1 - rows + offset
            text = item.label if item.label is not None else item.value
            attr = curses.A_REVERSE if start + offset == selected else 0
            put(window, y, 0, text.ljust(width), width, attr)
        popup_rows = rows

        label_width = text_width(label)
        available = max(0, width - label_width)
        visible, cursor_column = _input_view(value, cursor, available)
        put(window, height - 1, 0, (label + visible).ljust(width), width, status_attr)
        try:
            window.move(height - 1, min(width - 1, label_width + cursor_column))
        except curses.error:
            pass
        window.refresh()

    previous_cursor: int | None = None
    try:
        try:
            previous_cursor = curses.curs_set(1)
        except curses.error:
            pass
        while True:
            draw()
            key = window.get_wch()
            tab = key in ('\t', 9, curses.KEY_STAB)
            if key in ('\n', '\r', curses.KEY_ENTER):
                if choices:
                    choice = choices[selected]
                    value = choice.value
                    cursor = len(value)
                    history_index = len(history_values)
                    history_draft = value
                    if not choice.accept:
                        selected = 0
                        refresh_choices()
                        continue
                result = os.path.expandvars(os.path.expanduser(value)) if complete_paths else value
                _add_history(history, result)
                return result
            if key in ('\x1b', 27):
                if choices:
                    choices = []
                    continue
                return None
            if tab and choices:
                selected = (selected + 1) % len(choices)
                continue
            if key == curses.KEY_BTAB and choices:
                selected = (selected - 1) % len(choices)
                continue
            if key == curses.KEY_RIGHT and choices:
                choice = choices[selected]
                value = choice.value
                cursor = len(value)
                selected = 0
                if choice.accept:
                    choices = []
                else:
                    refresh_choices()
                continue
            if tab:
                refresh_choices()
                if len(choices) == 1:
                    choice = choices[0]
                    value = choice.value
                    cursor = len(value)
                    choices = []
                    if not choice.accept:
                        refresh_choices()
                elif choices:
                    common = os.path.commonprefix([choice.value for choice in choices])
                    if cursor == len(value) and len(common) > len(value):
                        value = common
                        cursor = len(value)
                        refresh_choices()
                continue
            if choices and key in (curses.KEY_UP, 'k', '\x10'):
                selected = (selected - 1) % len(choices)
                continue
            if choices and key in (curses.KEY_DOWN, 'j', '\x0e'):
                selected = (selected + 1) % len(choices)
                continue
            if key == curses.KEY_UP:
                if history_values and history_index > 0:
                    if history_index == len(history_values):
                        history_draft = value
                    history_index -= 1
                    value = history_values[history_index]
                    cursor = len(value)
                continue
            if key == curses.KEY_DOWN:
                if history_index < len(history_values):
                    history_index += 1
                    value = history_draft if history_index == len(history_values) else history_values[history_index]
                    cursor = len(value)
                continue
            if key == curses.KEY_PPAGE and choices:
                selected = max(0, selected - 8)
                continue
            if key == curses.KEY_NPAGE and choices:
                selected = min(len(choices) - 1, selected + 8)
                continue

            old_value = value
            if key in ('\b', '\x7f') or key == curses.KEY_BACKSPACE:
                if cursor > 0:
                    value = value[: cursor - 1] + value[cursor:]
                    cursor -= 1
            elif key == curses.KEY_DC:
                value = value[:cursor] + value[cursor + 1 :]
            elif key in (curses.KEY_LEFT, '\x02'):
                cursor = max(0, cursor - 1)
            elif key in (curses.KEY_RIGHT, '\x06'):
                cursor = min(len(value), cursor + 1)
            elif key in (curses.KEY_HOME, '\x01'):
                cursor = 0
            elif key in (curses.KEY_END, '\x05'):
                cursor = len(value)
            elif key == '\x15':
                value = value[cursor:]
                cursor = 0
            elif isinstance(key, str) and key.isprintable():
                value = value[:cursor] + key + value[cursor:]
                cursor += len(key)

            if value != old_value:
                history_index = len(history_values)
                history_draft = value
            if choices:
                refresh_choices()
    finally:
        if previous_cursor is not None:
            try:
                curses.curs_set(previous_cursor)
            except curses.error:
                pass


def pager(
    window: curses.window,
    title: str,
    text: str,
    header_attr: int,
    bindings: Mapping[keys.Key, str],
) -> keys.Key:
    """Display text and return the first event that is not a scroll action."""
    offset = 0
    while True:
        window.erase()
        height, width = window.getmaxyx()
        lines = wrap_text(text, width - 1)
        visible = max(1, height - 1)
        maximum = max(0, len(lines) - visible)
        offset = min(offset, maximum)
        put(window, 0, 0, title.ljust(width), width, header_attr)
        for row, line in enumerate(lines[offset : offset + visible], 1):
            put(window, row, 0, line, width - 1)
        window.refresh()
        action, ch = keys.read(window, bindings)
        if action == 'down':
            offset = min(maximum, offset + 1)
        elif action == 'up':
            offset = max(0, offset - 1)
        elif action == 'pageup':
            offset = max(0, offset - visible)
        elif action == 'pagedown':
            offset = min(maximum, offset + visible)
        elif action == 'home':
            offset = 0
        elif action == 'end':
            offset = maximum
        else:
            return ch
