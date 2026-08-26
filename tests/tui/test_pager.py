import curses
from dataclasses import dataclass

from stamm.tui.pager import PagerWidget
from stamm.tui.text import span_lines

from .fakes import Window


@dataclass
class _Context:
    screen: curses.window


def test_pager_draws_text_from_first_row() -> None:
    window = Window(3, 20)

    PagerWidget[_Context](span_lines('body')).draw(_Context(window.as_curses()))

    assert window.writes == [(0, 0, 'body', 20, 0)]
