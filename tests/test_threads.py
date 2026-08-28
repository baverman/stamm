from __future__ import annotations

from stamm.config_model import ThreadConfig
from stamm.index import IndexedMessage
from stamm.threads import build_threads
from stamm.views.index import thread_prefix


def message(identifier: str, timestamp: float, *references: str) -> IndexedMessage:
    return IndexedMessage(
        key=identifier,
        path=identifier,
        size=0,
        mtime_ns=0,
        flags='',
        date='',
        timestamp=timestamp,
        sender='',
        recipient='',
        subject=identifier,
        message_id=identifier,
        in_reply_to=references[-1] if references else None,
        references=references,
    )


def test_thread_rows_render_tree_branches() -> None:
    rows = build_threads(
        [
            message('root', 1),
            message('first', 2, 'root'),
            message('nested', 3, 'root', 'first'),
            message('last', 4, 'root'),
        ]
    )
    symbols = ThreadConfig()

    rendered = [thread_prefix(row, symbols) + row.message.subject for row in rows]

    assert rendered == ['root', '├─first', '│ └─nested', '└─last']
