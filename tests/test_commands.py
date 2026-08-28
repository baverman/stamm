from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
from typing import Any, cast

import pytest

from stamm.index import MessageIndex
from stamm.maildir import ensure_maildir, store
from stamm.search import parse_query
from stamm.state import MaildirState, SearchState
from stamm.tui import prompt
from stamm.views.index import IndexView, command_completer


def test_command_completer_completes_command_name() -> None:
    assert command_completer('se', 2) == [prompt.Completion('search ', 'search', accept=False)]
    assert command_completer('unm', 3) == [prompt.Completion('unmark_deleted ', 'unmark_deleted', accept=False)]


def test_command_completer_stops_at_arguments() -> None:
    assert command_completer('search from:bob', 15) == []


def test_command_completer_completes_reindex() -> None:
    assert command_completer('rei', 3) == [prompt.Completion('reindex ', 'reindex', accept=False)]


def test_reindex_fts_command(tmp_path: Path) -> None:
    ensure_maildir(tmp_path)
    with MessageIndex(tmp_path) as index:
        source = MaildirState([], 0, 0, tmp_path, index, set())
        view = IndexView(source, cast(Any, None), cast(Any, None))

        assert view.search('reindex fts') is None
        assert view.notice == 'FTS index reconciled: 0 indexed, 0 removed'
        assert view.search('reindex fts-full') is None
        assert view.notice == 'FTS index rebuilt: 0 indexed, 0 removed'


def test_reindex_full_rebuilds_message_index(tmp_path: Path) -> None:
    ensure_maildir(tmp_path)
    store(
        tmp_path,
        b'Subject: =?UTF-8?B?0KPQstC10LTQvtC80LvQtdC90LjQtSDQv9C+INC30LDQutCw0LfRgyA2OQ==?='
        b'=?UTF-8?B?MzkwMDAxMTkxDQo=?=\r\n\r\nbody',
    )
    with MessageIndex(tmp_path) as index:
        source = MaildirState([], 0, 0, tmp_path, index, set())
        source.load_rows(index.refresh())
        with index.connection:
            index.connection.execute("UPDATE messages SET subject='stale'")
            index.connection.execute("UPDATE message_fts SET body='stale'")
        source.load_rows(index.refresh(force=True))
        view = IndexView(source, cast(Any, None), cast(Any, None))
        progress: list[tuple[int, int]] = []

        assert view.search('reindex full', lambda done, total: progress.append((done, total))) is None

        assert view.notice == 'Index rebuilt: 1 indexed'
        assert source.rows[0].message.subject == 'Уведомление по заказу 69390001191'
        assert index.search_body('stale') == {source.rows[0].message.key}
        assert index.search_body('body') == set()
        assert progress == [(1, 1)]


def test_unmark_deleted_command_only_affects_visible_messages(tmp_path: Path) -> None:
    ensure_maildir(tmp_path)
    for subject in ('visible one', 'visible two', 'hidden'):
        message = EmailMessage()
        message['Subject'] = subject
        message.set_content('body')
        store(tmp_path, message.as_bytes())

    with MessageIndex(tmp_path) as index:
        source = MaildirState([], 0, 0, tmp_path, index, set())
        source.load_rows(index.refresh())
        source.pending_delete.update(row.message.key for row in source.rows)
        state = SearchState.create(source, 'subject:visible', parse_query('subject:visible'))
        assert state.selected == 1
        view = IndexView(state, cast(Any, None), cast(Any, None))
        hidden_key = next(row.message.key for row in source.rows if row.message.subject == 'hidden')

        assert view.search('unmark_deleted') is None

        assert source.pending_delete == {hidden_key}
        assert view.notice == '2 messages unmarked for deletion'


def test_search_action_uses_slash_and_prefills_current_query(monkeypatch: pytest.MonkeyPatch) -> None:
    source = MaildirState([], 0, 0, Path('.'), cast(Any, None), set())
    dependency = cast(Any, None)
    initial_values: list[str] = []

    def run(view: prompt.PromptView, _context: Any) -> None:
        initial_values.append(view.initial)

    monkeypatch.setattr(prompt.PromptView, 'run', run)

    IndexView(source, dependency, dependency).on_search(dependency)
    IndexView(SearchState.create(source, 'from:bob', parse_query('')), dependency, dependency).on_search(dependency)

    assert IndexView.actions['search'] == ('/',)
    assert initial_values == ['search ', 'search from:bob']


def test_search_from_search_view_replaces_current_search() -> None:
    source = MaildirState([], 0, 0, Path('.'), cast(Any, None), set())
    dependency = cast(Any, None)
    maildir_view = IndexView(source, dependency, dependency)
    search_view = IndexView(SearchState.create(source, 'old', parse_query('')), dependency, dependency)
    stack = [maildir_view, search_view]

    change = search_view.search('search subject:new')
    assert change is not None
    change.apply(stack)

    assert len(stack) == 2
    assert stack[0] is maildir_view
    assert stack[1] is not search_view
    assert isinstance(stack[1], IndexView)
    assert isinstance(stack[1].state, SearchState)
    assert stack[1].state.query == 'subject:new'
