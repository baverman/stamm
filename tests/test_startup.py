from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
from typing import Any, cast

import pytest

from stamm.index import MessageIndex
from stamm.maildir import ensure_maildir, store
from stamm.state import MaildirState
from stamm.views import UIContext
from stamm.views.index import IndexView


def _message(subject: str) -> bytes:
    message = EmailMessage()
    message['Subject'] = subject
    message.set_content('body')
    return message.as_bytes()


def test_maildir_state_opens_cached_rows_before_reconciliation(tmp_path: Path) -> None:
    ensure_maildir(tmp_path)
    for number in range(101):
        store(tmp_path, _message(f'cached {number}'))
    with MessageIndex(tmp_path) as index:
        index.refresh()
    store(tmp_path, _message('new'))

    state = MaildirState.open(tmp_path)
    try:
        assert len(state.rows) == 100

        state.refresh()

        assert len(state.rows) == 102
    finally:
        state.index.close()


def test_refresh_reuses_complete_cache_but_not_partial_startup_cache(tmp_path: Path) -> None:
    ensure_maildir(tmp_path)
    for number in range(101):
        store(tmp_path, _message(f'cached {number}'))
    with MessageIndex(tmp_path) as index:
        index.refresh()

    with MessageIndex(tmp_path) as index:
        assert len(index.messages(limit=100)) == 100
        statements: list[str] = []
        index.connection.set_trace_callback(statements.append)

        assert len(index.refresh()) == 101
        assert 'SELECT * FROM messages' in statements

        statements.clear()
        index.refresh()
        assert 'SELECT * FROM messages' not in statements


def test_force_refresh_discards_message_cache(tmp_path: Path) -> None:
    ensure_maildir(tmp_path)
    store(tmp_path, _message('original'))
    with MessageIndex(tmp_path) as index:
        assert index.refresh()[0].subject == 'original'
        with index.connection:
            index.connection.execute("UPDATE messages SET subject='changed'")

        assert index.refresh()[0].subject == 'original'
        assert index.refresh(force=True)[0].subject == 'changed'


def test_reconcile_paints_index_before_scanning(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    class State(MaildirState):
        def refresh(self) -> None:
            events.append('reconcile')

    class Screen:
        def refresh(self) -> None:
            events.append('refresh')

    state = State([], 0, 0, Path('.'), cast(Any, None), set())
    dependency = cast(Any, None)
    screen = cast(Any, Screen())
    context = UIContext(screen, dependency)
    view = IndexView(state, dependency, dependency, reconcile=True)
    monkeypatch.setattr(view, 'draw', lambda _context: events.append(f'draw:{view.notice}'))

    view._reconcile(context)

    assert events == ['draw:indexing...', 'refresh', 'reconcile']
