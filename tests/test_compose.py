from __future__ import annotations

import subprocess
from email.message import EmailMessage
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import stamm.views.compose as compose_view_module
from stamm import compose, delivery
from stamm.compose import ComposeData
from stamm.config import Config, set_config
from stamm.config_model import DEFAULT_COLORS, HooksConfig
from stamm.views import UIContext
from stamm.views.compose import ComposeView


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        root=tmp_path,
        spool=tmp_path / 'inbox',
        sent=tmp_path / 'sent',
        drafts=tmp_path / 'drafts',
        trash=tmp_path / 'trash',
        editor='editor',
        sendmail='sendmail',
        identities=('sender@example.com',),
        hooks=HooksConfig(None),
        auto_view=(),
        alternative_order=('text/plain', 'text/html'),
        signatures={},
        mime=(),
        colors=DEFAULT_COLORS,
    )


def test_empty_attachment_field_is_included_and_ignored_when_parsed() -> None:
    text = compose.format_buffer(ComposeData(sender='sender@example.com'))

    assert 'Subject: \nAttach:\n\n' in text
    assert compose.parse_buffer(text).attachments == []


def test_header_values_are_stripped() -> None:
    data = compose.parse_buffer('From:   sender@example.com   \nSubject:   example   \n\nbody')

    assert data.sender == 'sender@example.com'
    assert data.subject == 'example'


def test_editor_reports_unchanged_buffer(config: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    initial = ComposeData(sender='sender@example.com')
    monkeypatch.setattr(
        compose.subprocess,
        'run',
        lambda command: subprocess.CompletedProcess(command, 0),
    )

    data, changed = compose.edit(config, initial)

    assert data is initial
    assert not changed


def test_editor_returns_changed_buffer_without_forcing_validation(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    initial = ComposeData(sender='sender@example.com')

    def run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        path = Path(command[-1])
        path.write_text(path.read_text(encoding='utf-8') + 'changed', encoding='utf-8')
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(compose.subprocess, 'run', run)

    data, changed = compose.edit(config, initial)

    assert changed
    assert data.body == 'changed'
    assert compose.validate(data) == ['at least one recipient is required']


def test_forward_preserves_attachments_and_non_body_mime_parts(config: Config, tmp_path: Path) -> None:
    message = EmailMessage()
    message['From'] = 'author@example.com'
    message['Subject'] = 'report'
    message.set_content('plain body')
    message.add_related(b'png-data', maintype='image', subtype='png', cid='<chart>')
    message.add_attachment(b'pdf-data', maintype='application', subtype='pdf', filename='report.pdf')

    data = compose.forward(message, 'rendered body', config, tmp_path)

    assert data.subject == 'Fwd: report'
    assert [attachment.filename for attachment in data.attachments] == ['attachment-1.png', 'report.pdf']
    assert [attachment.path.read_bytes() for attachment in data.attachments] == [b'png-data', b'pdf-data']
    assert 'rendered body' in data.body


def test_successful_send_reports_is_sent(config: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    data = ComposeData(sender='sender@example.com', to='recipient@example.com')
    screen = SimpleNamespace(refresh=lambda: None)
    finished: list[tuple[str, bool]] = []
    statuses: list[str] = []
    theme = SimpleNamespace(status=0, header=0)
    set_config(config)
    view = ComposeView(data, lambda notice, is_sent: finished.append((notice, is_sent)))
    context = UIContext(screen, theme)  # type: ignore[arg-type]

    monkeypatch.setattr(compose_view_module.curses, 'def_prog_mode', lambda: None)
    monkeypatch.setattr(compose_view_module.curses, 'endwin', lambda: None)
    monkeypatch.setattr(compose_view_module.curses, 'reset_prog_mode', lambda: None)
    monkeypatch.setattr(compose, 'edit', lambda *_args: (data, True))
    monkeypatch.setattr(compose_view_module.ChoiceView, 'run', lambda *_args: 'send')
    monkeypatch.setattr(compose_view_module.text, 'status', lambda _screen, value, _attr: statuses.append(value))
    monkeypatch.setattr(delivery, 'send', lambda *_args: Path('/tmp/sent'))

    view.run(context)

    assert finished == [('message sent', True)]
    assert statuses == ['Sending...']
