from __future__ import annotations

from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path
from typing import Any, cast

from stamm.app import App
from stamm.theme import MessageTheme, Theme
from stamm.views import UIContext
from stamm.views.message import MessageView
from tests.tui.fakes import Window


def _view() -> MessageView:
    message = cast(
        EmailMessage,
        BytesParser(policy=policy.default).parsebytes(
            b'From: "=?utf-8?Q?=D0=9B=D0=B0=D0=B1=D0=BE=D1=80=D0=B0=D1=82=D0=BE=D1=80=D0=B8=D1=8F\r\n'
            b' =D0=9A=D0=94=D0=9B?=" <mo_uz@moscow.kdl-test.ru>\r\n'
            b'Subject: =?UTF-8?B?0KPQstC10LTQvtC80LvQtdC90LjQtSDQv9C+INC30LDQutCw0LfRgyA2OQ==?==?UTF-8?B?MzkwMDAxMTkxDQo=?=\r\n'
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
        Path('/mail/cur/message'),
    )


def test_message_view_header_shows_message_path() -> None:
    view = _view()
    window = Window(height=1, width=80)

    view.draw(UIContext(window.as_curses(), Theme()))

    assert window.writes[0][2].strip() == '/mail/cur/message'


def test_app_opens_standalone_message_as_only_view(tmp_path: Path) -> None:
    path = tmp_path / 'message.eml'
    message = EmailMessage()
    message.set_content('standalone body')
    path.write_bytes(message.as_bytes())

    class Mime:
        def display(self, part: EmailMessage) -> str:
            return str(part.get_content())

    app = object.__new__(App)
    app.mime = cast(Any, Mime())
    app.stack = []

    app.open_message(path)

    assert len(app.stack) == 1
    view = cast(MessageView, app.stack[0])
    assert view.path == path.resolve()
    assert view.state is None
    assert view.body == 'standalone body\n'


def test_toggle_headers_shows_raw_headers_without_raw_payloads() -> None:
    view = _view()
    view.pager.offset = 3
    initial = '\n'.join(''.join(span.text for span in line) for line in view.pager_lines(MessageTheme()))

    view.on_toggle_headers(cast(Any, None))

    expanded = '\n'.join(''.join(span.text for span in line) for line in view.pager_lines(MessageTheme()))
    assert 'From: Лаборатория КДЛ <mo_uz@moscow.kdl-test.ru>' in initial
    assert 'Subject: Уведомление по заказу 69390001191' in initial
    assert '\r' not in initial
    assert '=?UTF-8?' not in initial
    assert 'X-Extra:' not in initial
    assert '=?utf-8?' in expanded
    assert 'X-Extra: first line\n    second line\n    third line\n' in expanded
    assert 'rendered body' in expanded
    assert 'YXR0YWNobWVudCBwYXlsb2Fk' not in expanded
    assert view.pager.offset == 0

    view.on_toggle_headers(cast(Any, None))

    collapsed = '\n'.join(''.join(span.text for span in line) for line in view.pager_lines(MessageTheme()))
    assert collapsed == initial
