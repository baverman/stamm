from __future__ import annotations

from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from typing import Any, cast

from stamm.theme import MessageTheme
from stamm.views.message import MessageView


def _view() -> MessageView:
    message = cast(
        EmailMessage,
        BytesParser(policy=policy.default).parsebytes(
            b'From: sender@example.com\r\n'
            b'Subject: Subject\r\n'
            b'X-Extra: first line\r\n'
            b'\tsecond line\r\n'
            b' third line\r\n'
            b'\r\n'
            b'decoded body\r\n'
        ),
    )
    message.add_attachment(b'attachment payload', maintype='application', subtype='octet-stream')
    dependency = cast(Any, None)
    return MessageView(
        message,
        'rendered body',
        dependency,
        dependency,
        'key',
    )


def test_toggle_headers_shows_all_headers_without_raw_payloads() -> None:
    view = _view()
    view.pager.offset = 3
    initial = '\n'.join(''.join(span.text for span in line) for line in view._pager_lines(MessageTheme()))

    view.on_toggle_headers(cast(Any, None))

    expanded = '\n'.join(''.join(span.text for span in line) for line in view._pager_lines(MessageTheme()))
    assert 'X-Extra:' not in initial
    assert 'X-Extra: first line\n    second line\n    third line\n' in expanded
    assert 'rendered body' in expanded
    assert 'YXR0YWNobWVudCBwYXlsb2Fk' not in expanded
    assert view.pager.offset == 0

    view.on_toggle_headers(cast(Any, None))

    collapsed = '\n'.join(''.join(span.text for span in line) for line in view._pager_lines(MessageTheme()))
    assert collapsed == initial
