from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from stamm import ui
from stamm.app import App
from stamm.state import MaildirState, SearchState
from stamm.views.index import IndexView, _command_completer


def test_command_completer_completes_command_name() -> None:
    assert _command_completer('se', 2) == [ui.Completion('search ', 'search', accept=False)]


def test_command_completer_stops_at_arguments() -> None:
    assert _command_completer('search from:bob', 15) == []


def test_search_from_search_view_replaces_current_search() -> None:
    source = MaildirState([], 0, 0, Path('.'), cast(Any, None), set())
    app = object.__new__(App)
    maildir_view = IndexView(source, app)
    search_view = IndexView(SearchState.create(source, 'old', []), app)
    app.stack = [maildir_view, search_view]

    change = search_view._search(app, 'search subject:new')
    assert change is not None
    change.apply(app.stack)

    assert len(app.stack) == 2
    assert app.stack[0] is maildir_view
    assert app.stack[1] is not search_view
    assert isinstance(app.stack[1], IndexView)
    assert isinstance(app.stack[1].state, SearchState)
    assert app.stack[1].state.query == 'subject:new'
