from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from stamm.state import MaildirState, SearchState
from stamm.tui import prompt
from stamm.views.index import IndexView, _command_completer


def test_command_completer_completes_command_name() -> None:
    assert _command_completer('se', 2) == [prompt.Completion('search ', 'search', accept=False)]


def test_command_completer_stops_at_arguments() -> None:
    assert _command_completer('search from:bob', 15) == []


def test_search_from_search_view_replaces_current_search() -> None:
    source = MaildirState([], 0, 0, Path('.'), cast(Any, None), set())
    dependency = cast(Any, None)
    maildir_view = IndexView(source, dependency, dependency)
    search_view = IndexView(SearchState.create(source, 'old', []), dependency, dependency)
    stack = [maildir_view, search_view]

    change = search_view._search('search subject:new')
    assert change is not None
    change.apply(stack)

    assert len(stack) == 2
    assert stack[0] is maildir_view
    assert stack[1] is not search_view
    assert isinstance(stack[1], IndexView)
    assert isinstance(stack[1].state, SearchState)
    assert stack[1].state.query == 'subject:new'
