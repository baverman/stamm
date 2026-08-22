"""Small curses drawing, pager, prompt, and completion helpers."""

from __future__ import annotations

import curses
from datetime import datetime
from email.utils import parseaddr
import time
import os
from pathlib import Path
import unicodedata


KEYS = {
    "down": (ord("j"), curses.KEY_DOWN), "up": (ord("k"), curses.KEY_UP),
    "open": (10, 13, curses.KEY_ENTER), "back": (ord("q"),),
    "change": (ord("c"),), "compose": (ord("m"),), "reply": (ord("r"),),
    "reply_all": (ord("g"),), "forward": (ord("f"),), "flag": (ord("F"),),
    "unread": (ord("N"),), "parts": (ord("v"),), "resume": (ord("e"),),
    "refresh": (ord("R"),), "save": (ord("s"),), "delete": (ord("d"),), "undelete": (ord("u"),),
}

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
DEFAULT_COLOR_PAIR = 1
INDEX_DATE_COLOR_PAIR = 2
INDEX_FLAGS_COLOR_PAIR = 3
INDEX_INDICATOR_COLOR_PAIR = 4
_default_color_attr = 0
_index_date_color_attr = 0
_index_flags_color_attr = 0
_index_indicator_color_attr = curses.A_REVERSE


def initialize_colors(window: curses.window) -> None:
    """Use the terminal's natural colors and initialize index colors."""
    global _default_color_attr, _index_date_color_attr, _index_flags_color_attr, _index_indicator_color_attr
    if not curses.has_colors():
        return
    try:
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(DEFAULT_COLOR_PAIR, -1, -1)
        curses.init_pair(INDEX_DATE_COLOR_PAIR, curses.COLOR_BLUE, -1)
        curses.init_pair(INDEX_FLAGS_COLOR_PAIR, curses.COLOR_RED, -1)
        curses.init_pair(INDEX_INDICATOR_COLOR_PAIR, curses.COLOR_BLACK, curses.COLOR_WHITE)
    except curses.error:
        return
    _default_color_attr = curses.color_pair(DEFAULT_COLOR_PAIR)
    _index_date_color_attr = curses.color_pair(INDEX_DATE_COLOR_PAIR)
    _index_flags_color_attr = curses.color_pair(INDEX_FLAGS_COLOR_PAIR) | curses.A_BOLD
    _index_indicator_color_attr = curses.color_pair(INDEX_INDICATOR_COLOR_PAIR)
    window.bkgd(" ", _default_color_attr)


def index_date_color() -> int:
    return _index_date_color_attr


def index_flags_color() -> int:
    return _index_flags_color_attr


def index_indicator_color() -> int:
    return _index_indicator_color_attr


def format_index_date(timestamp: float, now: float | None = None) -> str:
    """Format an index date in a fixed 12-character field."""
    current = time.time() if now is None else now
    value = datetime.fromtimestamp(timestamp).astimezone()
    month = MONTHS[value.month - 1]
    if current - timestamp >= 365 * 24 * 60 * 60:
        return f"{value.year:04d} {month} {value.day:02d} "
    return f"{month} {value.day:02d} {value.hour:02d}:{value.minute:02d}"


def format_sender(value: str) -> str:
    """Show the display name when present, otherwise show the address."""
    name, address = parseaddr(value.replace("\n", " "))
    return name or address or value.replace("\n", " ")


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
    for source in text.splitlines() or [""]:
        source = source.expandtabs(8)
        if not source:
            result.append("")
            continue
        chunk: list[str] = []
        used = 0
        for character in source:
            cell_width = 0 if unicodedata.combining(character) else (
                2 if unicodedata.east_asian_width(character) in ("W", "F") else 1
            )
            if chunk and used + cell_width > columns:
                result.append("".join(chunk))
                chunk = []
                used = 0
            chunk.append(character)
            used += cell_width
        result.append("".join(chunk))
    return result


def put(window: curses.window, y: int, x: int, text: str, width: int, attr: int = 0) -> None:
    if width > 0:
        try:
            color = _default_color_attr if curses.pair_number(attr) == 0 else 0
            window.addnstr(y, x, text, width, attr | color)
        except curses.error:
            pass


def status(window: curses.window, text: str) -> None:
    height, width = window.getmaxyx()
    put(window, height - 1, 0, text.ljust(width), width, curses.A_REVERSE)
    window.refresh()


def choose(window: curses.window, prompt_text: str, choices: str) -> str:
    status(window, f"{prompt_text} [{'/'.join(choices)}]")
    while True:
        key = window.get_wch()
        if isinstance(key, str) and key in choices:
            return key


def prompt(window: curses.window, label: str, initial: str = "", *, complete_paths: bool = False) -> str | None:
    value = initial
    while True:
        status(window, label + value)
        key = window.get_wch()
        if key in ("\n", "\r"):
            return os.path.expandvars(os.path.expanduser(value))
        if key == "\x1b":
            return None
        if key in ("\b", "\x7f") or key == curses.KEY_BACKSPACE:
            value = value[:-1]
        elif key == "\t" and complete_paths:
            path = Path(value or ".")
            parent, prefix = (path, "") if value.endswith(os.sep) else (path.parent, path.name)
            try:
                matches = sorted(item for item in parent.iterdir() if item.name.startswith(prefix))
                if len(matches) == 1:
                    value = str(matches[0]) + (os.sep if matches[0].is_dir() else "")
                elif matches:
                    common = os.path.commonprefix([item.name for item in matches])
                    value = str(parent / common)
            except OSError:
                pass
        elif isinstance(key, str) and key.isprintable():
            value += key


def pager(window: curses.window, title: str, text: str) -> int:
    """Display text and return the first key that is not a scroll command."""
    offset = 0
    while True:
        window.erase()
        height, width = window.getmaxyx()
        lines = wrap_text(text, width - 1)
        maximum = max(0, len(lines) - height + 1)
        offset = min(offset, maximum)
        put(window, 0, 0, title.ljust(width), width, curses.A_REVERSE)
        for row, line in enumerate(lines[offset:offset + height - 1], 1):
            put(window, row, 0, line, width - 1)
        window.refresh()
        key = window.getch()
        if key in KEYS["down"]:
            offset = min(maximum, offset + 1)
        elif key in KEYS["up"]:
            offset = max(0, offset - 1)
        else:
            return key
