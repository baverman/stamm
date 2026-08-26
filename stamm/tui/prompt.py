from __future__ import annotations

import curses
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from . import text
from .views import BaseContext, View


@dataclass(frozen=True, slots=True)
class Completion:
    value: str
    label: str | None = None
    accept: bool = True


Completer = Callable[[str, int], Sequence[Completion | str]]


def path_completer(value: str, cursor: int) -> list[Completion]:
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
        is_directory = item.is_dir()
        separator = os.sep if is_directory else ''
        label = item.name + separator
        result.append(Completion(str(item) + separator + suffix, label, accept=not is_directory))
    return result


def _add_history(history: list[str] | None, value: str, limit: int = 100) -> None:
    if history is None or not value:
        return
    history[:] = [entry for entry in history if entry != value]
    history.append(value)
    del history[:-limit]


@dataclass
class PromptView(View[BaseContext, str | None]):
    label: str
    initial: str = ''
    completer: Completer | None = None
    history: list[str] | None = None

    def run(self, context: BaseContext) -> str | None:
        window = context.screen
        value = self.initial
        cursor = len(value)
        choices: list[Completion] = []
        selected = 0
        history_values = self.history if self.history is not None else []
        history_index = len(history_values)
        history_draft = value
        popup_rows = 0

        def refresh_choices() -> None:
            nonlocal choices, selected
            if self.completer is None:
                choices = []
                return
            choices = [
                item if isinstance(item, Completion) else Completion(item) for item in self.completer(value, cursor)
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
                    text.put(window, y, 0, ' ' * width, width)
            for offset, item in enumerate(choices[start : start + rows]):
                y = height - 1 - rows + offset
                item_text = item.label if item.label is not None else item.value
                attr = curses.A_REVERSE if start + offset == selected else 0
                text.put(window, y, 0, item_text.ljust(width), width, attr)
            popup_rows = rows

            label_width = text.text_width(self.label)
            available = max(0, width - label_width)
            if available:
                cursor_width = text.text_width(value[:cursor])
                cursor_column = min(cursor_width, available - 1)
                hidden_columns = cursor_width - cursor_column
                _hidden, remainder, hidden_width = text.fit_text(value, hidden_columns)
                visible, _remainder, _visible_width = text.fit_text(remainder, available)
                cursor_column = min(cursor_width - hidden_width, available - 1)
            else:
                visible = ''
                cursor_column = 0
            text.put(
                window,
                height - 1,
                0,
                (self.label + visible).ljust(width),
                width,
                context.theme.status,
            )
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
                    _add_history(self.history, value)
                    return value
                if key in ('\x1b', 27):
                    if choices:
                        choices = []
                        continue
                    return None
                if tab and len(choices) > 1:
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
