from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

from stamm.index import MessageIndex
from stamm.maildir import ensure_maildir, store
from stamm.search import matches, parse_query


def test_to_search_uses_indexed_recipient_header(tmp_path: Path) -> None:
    ensure_maildir(tmp_path)
    message = EmailMessage()
    message['From'] = 'sender@example.com'
    message['To'] = 'Alice <alice@example.com>, Bob <bob@example.com>'
    message['Cc'] = 'Dave <dave@example.com>'
    message['Delivered-To'] = 'list-identity@example.com'
    message['Subject'] = 'hello'
    message.set_content('body')
    store(tmp_path, message.as_bytes())

    with MessageIndex(tmp_path) as index:
        indexed = index.refresh()[0]
        stored = index.get(indexed.key)
        columns = {row['name'] for row in index.connection.execute('PRAGMA table_info(messages)')}

    assert stored is not None
    assert stored.recipient == (
        'Alice <alice@example.com>, Bob <bob@example.com>, Dave <dave@example.com>, list-identity@example.com'
    )
    assert matches(stored, parse_query('to:BOB@example.com'))
    assert matches(stored, parse_query('to:dave@example.com'))
    assert matches(stored, parse_query('to:list-identity@example.com'))
    assert not matches(stored, parse_query('to:carol@example.com'))
    assert matches(stored, parse_query('-to:carol@example.com'))
    assert not matches(stored, parse_query('-to:BOB@example.com'))
    assert matches(stored, parse_query('from:sender -subject:goodbye'))
    assert 'recipient' in columns
