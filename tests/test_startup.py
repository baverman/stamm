from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
from typing import Any, cast

import pytest

from stamm.app import App, MaildirState
from stamm.index import MessageIndex
from stamm.maildir import ensure_maildir, store


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


def test_reconcile_paints_index_before_scanning(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    class State:
        rows: list[object] = []

        def refresh(self) -> None:
            events.append('reconcile')

    class Screen:
        def refresh(self) -> None:
            events.append('refresh')

    app = object.__new__(App)
    app.state = cast(Any, State())
    app.screen = cast(Any, Screen())
    app.notice = ''
    monkeypatch.setattr(app, 'draw_index', lambda: events.append(f'draw:{app.notice}'))

    app.reconcile()

    assert events == ['draw:indexing...', 'refresh', 'reconcile']
