from __future__ import annotations

import curses
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from email.utils import parseaddr
from pathlib import Path

from .theme import Theme as Theme
from .tui import text as tui_text

MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')


def format_index_date(timestamp: float, now: float | None = None) -> str:
    current = time.time() if now is None else now
    value = datetime.fromtimestamp(timestamp).astimezone()
    month = MONTHS[value.month - 1]
    if current - timestamp >= 365 * 24 * 60 * 60:
        return f'{value.year:04d} {month} {value.day:02d} '
    return f'{month} {value.day:02d} {value.hour:02d}:{value.minute:02d}'


def format_sender(value: str) -> str:
    name, address = parseaddr(value.replace('\n', ' '))
    return name or address or value.replace('\n', ' ')


def viewport_start(selected: int, total: int, visible: int, current: int) -> int:
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


def status(window: curses.window, text: str, attr: int) -> None:
    height, width = window.getmaxyx()
    tui_text.put(window, height - 1, 0, text.ljust(width), width, attr)
    window.refresh()


@dataclass(frozen=True, slots=True)
class Completion:
    value: str
    label: str | None = None
    accept: bool = True


Completer = Callable[[str, int], Sequence[Completion | str]]


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
                tui_text.put(window, y, 0, ' ' * width, width)
        for offset, item in enumerate(choices[start : start + rows]):
            y = height - 1 - rows + offset
            text = item.label if item.label is not None else item.value
            attr = curses.A_REVERSE if start + offset == selected else 0
            tui_text.put(window, y, 0, text.ljust(width), width, attr)
        popup_rows = rows

        label_width = tui_text.text_width(label)
        available = max(0, width - label_width)
        if available:
            cursor_width = tui_text.text_width(value[:cursor])
            cursor_column = min(cursor_width, available - 1)
            hidden_columns = cursor_width - cursor_column
            _hidden, remainder, hidden_width = tui_text.fit_text(value, hidden_columns)
            visible, _remainder, _visible_width = tui_text.fit_text(remainder, available)
            cursor_column = min(cursor_width - hidden_width, available - 1)
        else:
            visible = ''
            cursor_column = 0
        tui_text.put(window, height - 1, 0, (label + visible).ljust(width), width, status_attr)
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
