from __future__ import annotations

import curses

import pytest

from stamm import keys


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
    assert keys.parse_key(specification) == expected


def test_enter_and_backspace_expand_terminal_variants() -> None:
    assert keys.parse_key('ENTER') == ('\n', '\r', curses.KEY_ENTER)
    assert keys.parse_key('BACKSPACE') == ('\x08', '\x7f', curses.KEY_BACKSPACE)


def test_compile_merges_unbinds_and_collects_all_diagnostics() -> None:
    registry = {
        'view': keys.BindingDefinition(frozenset({'up', 'down'}), {'j': 'down', 'k': 'up', '^D': 'down'}),
    }
    bindings, diagnostics = keys.compile_bindings(
        registry,
        {
            'view': {'j': '', '^N': 'down', '^n': 'up', 'missing': 'down', 'x': 'unknown'},
            'other': {'q': 'back'},
        },
    )

    assert bindings['view'] == {'k': 'up', '\x04': 'down', '\x0e': 'up'}
    assert len(diagnostics) == 4
    assert any('overlaps' in diagnostic for diagnostic in diagnostics)
    assert any('invalid or unavailable' in diagnostic for diagnostic in diagnostics)
    assert any('unknown action' in diagnostic for diagnostic in diagnostics)
    assert any('unknown namespace' in diagnostic for diagnostic in diagnostics)


def test_resolve_returns_none_for_unbound_event() -> None:
    assert keys.resolve({'j': 'down'}, 'j') == 'down'
    assert keys.resolve({'j': 'down'}, curses.KEY_UP) is None
