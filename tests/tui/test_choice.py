from __future__ import annotations

import curses

import pytest

from stamm.theme import Theme
from stamm.tui.choice import ChoiceView
from stamm.views import UIContext

from .fakes import Window


@pytest.mark.parametrize(
    ('key', 'expected'),
    [
        ('\n', 'send'),
        ('\r', 'send'),
        (curses.KEY_ENTER, 'send'),
        ('\x1b', None),
        ('e', 'edit'),
    ],
)
def test_choice_maps_generic_and_explicit_keys(key: str | int, expected: str | None) -> None:
    context = UIContext(Window(keys=[key]).as_curses(), Theme())

    assert (
        ChoiceView(
            'Compose',
            {'s': 'send', 'e': 'edit', 'd': 'draft', 'x': 'discard'},
            primary='send',
        ).run(context)
        == expected
    )


def test_choice_applies_key_overrides() -> None:
    context = UIContext(Window(keys=['a']).as_curses(), Theme())

    result = ChoiceView('Compose', {'s': 'send'}, primary='send', overrides={'a': 'accept'}).run(context)

    assert result == 'send'
