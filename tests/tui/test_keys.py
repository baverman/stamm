from __future__ import annotations

import curses

import pytest

from stamm.tui import keys


@pytest.mark.parametrize(
    ('specification', 'expected'),
    [
        ('ж', ('ж',)),
        ('^@', ('\x00',)),
        ('^a', ('\x01',)),
        ('^_', ('\x1f',)),
        ('^?', ('\x7f',)),
        ('UP', (curses.KEY_UP,)),
        ('KEY_UP', (curses.KEY_UP,)),
        ('PAGEUP', (curses.KEY_PPAGE,)),
    ],
)
def test_parse_key(specification: str, expected: tuple[str | int, ...]) -> None:
    assert keys.parse_key(specification, 'app') == expected


def test_enter_and_backspace_expand_terminal_variants() -> None:
    assert keys.parse_key('ENTER', 'app') == ('\n', '\r', curses.KEY_ENTER)
    assert keys.parse_key('BACKSPACE', 'app') == ('\x08', '\x7f', curses.KEY_BACKSPACE)


def test_compile_merges_and_unbinds() -> None:
    bindings = keys.compile_bindings(
        'view',
        {'up': ('k',), 'down': ('j', '^D')},
        {'j': '', '^N': 'down'},
    )

    assert bindings == {'k': 'up', '\x04': 'down', '\x0e': 'down'}


def test_resolve_returns_none_for_unbound_event() -> None:
    assert keys.resolve({'j': 'down'}, 'j') == 'down'
    assert keys.resolve({'j': 'down'}, curses.KEY_UP) is None
