from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from stamm.index import MessageIndex
from stamm.maildir import ensure_maildir
from stamm.state import MaildirState, SearchState
from stamm.tui import prompt
from stamm.views.index import IndexView, _command_completer


def test_command_completer_completes_command_name() -> None:
    assert _command_completer('se', 2) == [prompt.Completion('search ', 'search', accept=False)]


def test_command_completer_stops_at_arguments() -> None:
    assert _command_completer('search from:bob', 15) == []


def test_command_completer_completes_reindex() -> None:
    assert _command_completer('rei', 3) == [prompt.Completion('reindex ', 'reindex', accept=False)]


def test_reindex_fts_command(tmp_path: Path) -> None:
    ensure_maildir(tmp_path)
    with MessageIndex(tmp_path) as index:
        source = MaildirState([], 0, 0, tmp_path, index, set())
        view = IndexView(source, cast(Any, None), cast(Any, None))

        assert view._search('reindex fts') is None
        assert view.notice == 'FTS index reconciled: 0 added, 0 removed'


def test_search_action_uses_slash_and_prefills_current_query(monkeypatch: pytest.MonkeyPatch) -> None:
    source = MaildirState([], 0, 0, Path('.'), cast(Any, None), set())
    dependency = cast(Any, None)
    initial_values: list[str] = []

    def run(view: prompt.PromptView, _context: Any) -> None:
        initial_values.append(view.initial)

    monkeypatch.setattr(prompt.PromptView, 'run', run)

    IndexView(source, dependency, dependency).on_search(dependency)
    IndexView(SearchState.create(source, 'from:bob', []), dependency, dependency).on_search(dependency)

    assert IndexView.actions['search'] == ('/',)
    assert initial_values == ['search ', 'search from:bob']


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
