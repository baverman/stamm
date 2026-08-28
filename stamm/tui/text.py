from __future__ import annotations

import curses
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from .compat import cache


@dataclass(frozen=True, slots=True)
class TextSpan:
    text: str
    attr: int
    width: int


type TextLine = list[TextSpan]
type TextLines = list[TextLine]


def span(text: str, attr: int = 0) -> TextSpan:
    return TextSpan(text, attr, text_width(text))


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


def split_spans(spans: Sequence[TextSpan]) -> TextLines:
    result: list[list[TextSpan]] = [[]]
    ended_with_newline = False
    for item in spans:
        for index, part in enumerate(item.text.split('\n')):
            if index:
                result.append([])
                ended_with_newline = True
            if part:
                result[-1].append(span(part, item.attr))
                ended_with_newline = False
    if ended_with_newline:
        result.pop()
    return result


def span_lines(value: str, attr: int = 0) -> TextLines:
    return split_spans([span(value, attr)])


@cache
def get_character_width(character: str) -> int:
    if unicodedata.combining(character):
        return 0
    return 2 if unicodedata.east_asian_width(character) in ('W', 'F') else 1


def text_width(value: str) -> int:
    return sum(get_character_width(character) for character in value)


def fit_text(value: str, width: int) -> tuple[str, str, int]:
    used_width = 0
    for index, character in enumerate(value):
        character_width = get_character_width(character)
        if used_width + character_width > width:
            return value[:index], value[index:], used_width
        used_width += character_width
    return value, '', used_width


def wrap_text(text: str, columns: int) -> list[str]:
    columns = max(1, columns)
    result: list[str] = []
    for source in text.splitlines() or ['']:
        source = source.expandtabs(8)
        if not source:
            result.append('')
            continue
        while source:
            fitted, source, _used_width = fit_text(source, columns)
            result.append(fitted)
    return result


def wrap_spans(lines: Sequence[Sequence[TextSpan]], columns: int) -> list[list[TextSpan]]:
    result: list[list[TextSpan]] = []
    for line in lines:
        wrapped: list[list[TextSpan]] = [[]]
        used_width = 0
        for item in line:
            remainder = item.text
            while remainder:
                fitted, remainder, fitted_width = fit_text(remainder, columns - used_width)
                if not fitted:
                    wrapped.append([])
                    used_width = 0
                    continue
                wrapped[-1].append(TextSpan(fitted, item.attr, fitted_width))
                used_width += fitted_width
                if remainder:
                    wrapped.append([])
                    used_width = 0
        result.extend(wrapped)
    return result
