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


def test_body_search_indexes_text_plain_and_reconciles_missing_rows(tmp_path: Path) -> None:
    ensure_maildir(tmp_path)
    message = EmailMessage()
    message['Subject'] = 'multipart message'
    message.set_content('alpha exact phrase')
    message.add_alternative('<p>html-only-marker</p>', subtype='html')
    store(tmp_path, message.as_bytes())

    with MessageIndex(tmp_path) as index:
        indexed = index.refresh()[0]

        assert index.search_body('alpha') == {indexed.key}
        assert index.search_body('"exact phrase"') == {indexed.key}
        assert index.search_body('"html-only-marker"') == set()

        changes = index.connection.total_changes
        assert index.reindex_fts() == (0, 0)
        assert index.connection.total_changes == changes

        with index.connection:
            index.connection.execute('DELETE FROM message_fts WHERE key = ?', (indexed.key,))
            index.connection.execute('INSERT INTO message_fts VALUES (?,?)', ('orphan', 'orphan body'))
        assert index.search_body('alpha') == set()

        index.refresh()
        assert index.search_body('alpha') == set()

        assert index.reindex_fts() == (1, 1)
        assert index.search_body('alpha') == {indexed.key}
        assert index.search_body('orphan') == set()


def test_body_search_uses_html_only_without_text_plain(tmp_path: Path) -> None:
    ensure_maildir(tmp_path)
    message = EmailMessage()
    message.set_content(
        '<html><body><p>visible marker</p><script>hidden-script</script></body></html>',
        subtype='html',
    )
    store(tmp_path, message.as_bytes())

    progress: list[tuple[int, int]] = []
    with MessageIndex(tmp_path) as index:
        indexed = index.refresh()[0]
        assert index.search_body('visible') == {indexed.key}
        assert index.search_body('"hidden-script"') == set()

        with index.connection:
            index.connection.execute('DELETE FROM message_fts WHERE key = ?', (indexed.key,))
            index.connection.execute('INSERT INTO message_fts VALUES (?,?)', (indexed.key, 'outdated'))

        assert index.reindex_fts() == (0, 0)
        assert index.search_body('outdated') == {indexed.key}
        assert index.reindex_fts(full=True, progress=lambda done, total: progress.append((done, total))) == (1, 0)
        assert index.search_body('visible') == {indexed.key}
        assert index.search_body('outdated') == set()

    assert progress == [(1, 1)]


def test_body_search_terms_use_fts_matches(tmp_path: Path) -> None:
    ensure_maildir(tmp_path)
    message = EmailMessage()
    message['From'] = 'alice@example.com'
    message.set_content('project starlight')
    store(tmp_path, message.as_bytes())

    with MessageIndex(tmp_path) as index:
        indexed = index.refresh()[0]
        body_matches = {'project': index.search_body('project'), 'missing': index.search_body('missing')}

    assert matches(indexed, parse_query('from:alice body:project'), body_matches)
    assert matches(indexed, parse_query('body:project -body:missing'), body_matches)
    assert not matches(indexed, parse_query('body:missing'), body_matches)
