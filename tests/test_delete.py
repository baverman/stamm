from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

import pytest

from stamm.app import App
from stamm.config import Config, set_config
from stamm.config_model import DEFAULT_COLORS, HooksConfig
from stamm.index import MessageIndex
from stamm.maildir import ensure_maildir, store
from stamm.state import MaildirState
from stamm.theme import Theme
from stamm.views import UIContext


def test_move_to_trash_moves_file_and_removes_index_record(tmp_path: Path) -> None:
    inbox = tmp_path / 'inbox'
    trash = tmp_path / 'trash'
    ensure_maildir(inbox)
    ensure_maildir(trash)
    message = EmailMessage()
    message['From'] = 'sender@example.com'
    message['To'] = 'recipient@example.com'
    message['Subject'] = 'delete me'
    message.set_content('body')
    source = store(inbox, message.as_bytes(), flags='FS', seen=True)

    with MessageIndex(inbox) as index:
        item = index.refresh()[0]
        target = index.move_to(item.key, trash)

        assert index.get(item.key) is None
        assert not source.exists()
        assert target.exists()
        assert target.parent == trash / 'cur'
        assert target.name.endswith(':2,FS')


def test_message_cannot_move_to_its_current_maildir(tmp_path: Path) -> None:
    ensure_maildir(tmp_path)
    message = EmailMessage()
    message.set_content('body')
    store(tmp_path, message.as_bytes())

    with MessageIndex(tmp_path) as index:
        item = index.refresh()[0]
        with pytest.raises(ValueError, match='already in'):
            index.move_to(item.key, tmp_path)


def test_mark_keeps_message_until_purge(tmp_path: Path) -> None:
    inbox = tmp_path / 'inbox'
    trash = tmp_path / 'trash'
    ensure_maildir(inbox)
    message = EmailMessage()
    message['Subject'] = 'delete later'
    message.set_content('body')
    source = store(inbox, message.as_bytes())
    config = Config(
        root=tmp_path,
        spool=inbox,
        sent=tmp_path / 'sent',
        drafts=tmp_path / 'drafts',
        trash=trash,
        editor='true',
        sendmail='true',
        identities=('sender@example.com',),
        hooks=HooksConfig(None),
        auto_view=(),
        alternative_order=('text/plain', 'text/html'),
        signatures={},
        mime=(),
        colors=DEFAULT_COLORS,
    )
    set_config(config)
    state = MaildirState.open(inbox)
    state.refresh()
    theme = Theme()
    context = UIContext(object(), theme)  # type: ignore[arg-type]
    app = App(context)
    app.maildirs[inbox.resolve()] = state
    view = app.maildir_view(inbox)
    app.stack.append(view)
    try:
        key = state.rows[0].message.key

        view.mark_deleted()
        state.offset = 9
        other = tmp_path / 'other'
        ensure_maildir(other)
        app.open_maildir(other)
        other_state = app.maildirs[other.resolve()]
        app.open_maildir(inbox)

        assert app.stack[-1].state is state  # type: ignore[attr-defined]
        assert state is not other_state
        assert state.offset == 9

        assert source.exists()
        assert key in state.pending_delete
        assert state.purge_deleted(config.trash) == []
        assert not source.exists()
        assert not state.pending_delete
        assert len(list((trash / 'new').iterdir())) == 1
    finally:
        for maildir in app.maildirs.values():
            maildir.index.close()
        app.mime.close()
