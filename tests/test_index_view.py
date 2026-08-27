from __future__ import annotations

from stamm.views.index import _format_flags


def test_index_flags_have_dedicated_positions() -> None:
    assert _format_flags('', False) == '   N'
    assert _format_flags('FRS', True) == '!rD '
