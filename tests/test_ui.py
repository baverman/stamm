from __future__ import annotations

import curses

from datetime import datetime

import pytest

from stamm import ui
from stamm.ui import format_index_date, format_sender, viewport_start, wrap_text


def test_recent_date_uses_time() -> None:
    timestamp = datetime(2026, 4, 5, 14, 30).astimezone().timestamp()
    assert format_index_date(timestamp, timestamp + 60) == 'Apr 05 14:30'


def test_old_date_uses_year() -> None:
    timestamp = datetime(2024, 4, 5, 14, 30).astimezone().timestamp()
    value = format_index_date(timestamp, timestamp + 366 * 24 * 60 * 60)
    assert value == '2024 Apr 05 '
    assert len(value) == 12


@pytest.mark.parametrize(
    ('sender', 'expected'),
    [
        ('Anton Bobrov <anton@example.com>', 'Anton Bobrov'),
        ('anton@example.com', 'anton@example.com'),
    ],
)
def test_format_sender(sender: str, expected: str) -> None:
    assert format_sender(sender) == expected


@pytest.mark.parametrize(
    ('text', 'width', 'expected'),
    [
        ('abcdefgh', 3, ['abc', 'def', 'gh']),
        ('one\n\ntwo', 10, ['one', '', 'two']),
        ('界界a', 3, ['界', '界a']),
    ],
)
def test_wrap_text(text: str, width: int, expected: list[str]) -> None:
    assert wrap_text(text, width) == expected


def test_cursor_does_not_scroll_in_middle_seventy_percent() -> None:
    assert viewport_start(26, 100, 20, 20) == 20
    assert viewport_start(33, 100, 20, 20) == 20


def test_cursor_scrolls_inside_top_and_bottom_margins() -> None:
    assert viewport_start(25, 100, 20, 20) == 19
    assert viewport_start(34, 100, 20, 20) == 21


def test_margin_is_capped_at_ten_rows() -> None:
    assert viewport_start(39, 200, 100, 50) == 29
    assert viewport_start(140, 200, 100, 50) == 51


def test_viewport_is_clamped_at_list_edges() -> None:
    assert viewport_start(0, 100, 20, 20) == 0
    assert viewport_start(2, 5, 20, 4) == 0


def test_final_message_keeps_the_bottom_scroll_margin() -> None:
    # Twenty visible rows produce a six-row margin.
    assert viewport_start(99, 100, 20, 0) == 86
    # The margin is capped at ten on large screens.
    assert viewport_start(199, 200, 100, 0) == 110


class _ChoiceWindow:
    def __init__(self, key: str | int):
        self.key = key

    def get_wch(self) -> str | int:
        return self.key


@pytest.mark.parametrize(
    ('key', 'expected'),
    [
        ('\n', 's'),
        ('\r', 's'),
        (curses.KEY_ENTER, 's'),
        ('\x1b', 'x'),
        (27, 'x'),
        ('e', 'e'),
    ],
)
def test_choose_maps_generic_and_explicit_keys(
    key: str | int, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ui, 'status', lambda *_args: None)

    assert ui.choose(
        _ChoiceWindow(key),  # type: ignore[arg-type]
        'Compose',
        'sedx',
        0,
        primary='s',
        cancel='x',
    ) == expected
