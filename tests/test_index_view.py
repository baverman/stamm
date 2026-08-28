from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
from typing import Any, cast

from stamm.index import MessageIndex
from stamm.maildir import ensure_maildir, store
from stamm.state import MaildirState
from stamm.views.index import IndexView, format_flags, index_summary, status_with_delete_count


def test_index_flags_have_dedicated_positions() -> None:
    assert format_flags('', False) == '   N'
    assert format_flags('FRS', True) == '!rD '


def test_index_status_shows_position_and_pending_deletions() -> None:
    assert index_summary(0, 0) == '0/0 messages'
    assert index_summary(2, 5) == '3/5 messages'
    assert status_with_delete_count('3/5 messages', 0) == '3/5 messages'
    assert status_with_delete_count('3/5 messages', 2) == '3/5 messages | 2 to delete'


def test_index_open_html_action_opens_selected_message(tmp_path: Path) -> None:
    ensure_maildir(tmp_path)
    message = EmailMessage()
    message.set_content('plain body')
    message.add_alternative('<p>HTML body</p>', subtype='html')
    store(tmp_path, message.as_bytes())

    class Mime:
        opened: tuple[str, EmailMessage] | None = None

        def open(self, part: EmailMessage, source: EmailMessage) -> None:
            self.opened = part.get_content_type(), source

    mime = Mime()
    with MessageIndex(tmp_path) as index:
        item = index.refresh()[0]
        state = MaildirState([], 0, 0, tmp_path, index, set())
        state.load_rows([item])
        view = IndexView(state, cast(Any, mime), cast(Any, None))

        view.on_open_html(cast(Any, None))

    assert IndexView.actions['open_html'] == ('H',)
    assert mime.opened is not None
    assert mime.opened[0] == 'text/html'
    assert view.notice == 'opened HTML externally'
