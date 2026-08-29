from __future__ import annotations

import subprocess
import tempfile
from email.message import EmailMessage
from pathlib import Path

from stamm.config import Config, MimeRule
from stamm.config_model import DEFAULT_COLORS
from stamm.mime import MimeManager, OpenProcess


def config(rules: tuple[MimeRule, ...] = ()) -> Config:
    return Config(
        root=Path('/tmp'),
        spool=Path('/tmp/inbox'),
        sent=Path('/tmp/sent'),
        drafts=Path('/tmp/drafts'),
        trash=Path('/tmp/trash'),
        editor='true',
        sendmail='true',
        identities=('sender@example.com',),
        auto_view=(),
        alternative_order=('text/plain', 'text/html'),
        signatures={},
        mime=rules,
        colors=DEFAULT_COLORS,
    )


def test_unknown_mime_type_uses_xdg_open() -> None:
    manager = MimeManager(config())
    assert manager.opener_command('application/pdf') == 'xdg-open {file}'


def test_configured_opener_takes_priority() -> None:
    manager = MimeManager(config((MimeRule('application/pdf', None, 'custom {file}'),)))
    assert manager.opener_command('application/pdf') == 'custom {file}'


def test_successful_opener_keeps_temporary_file_until_manager_closes() -> None:
    manager = MimeManager(config())
    directory = tempfile.TemporaryDirectory(prefix='stamm-test-open-')
    source = Path(directory.name) / 'part.html'
    output = Path(directory.name) / 'out'
    source.write_text('<p>content</p>', encoding='utf-8')
    with output.open('wb') as out:
        process = manager.run('true', b'', source, detached=True, output=out)
    assert isinstance(process, subprocess.Popen)
    process.wait(timeout=5)
    manager._temporary.append(OpenProcess(directory, process, output, 'test opener'))

    manager.reap()
    assert source.exists()

    manager.close()
    assert not Path(directory.name).exists()


def test_open_html_prepares_message_images() -> None:
    manager = MimeManager(config((MimeRule('text/html', None, 'true {file}'),)))
    message = EmailMessage()
    message.make_related()
    html = EmailMessage()
    html.set_content('<img src="cid:logo@example.com">', subtype='html')
    image = EmailMessage()
    image.set_content(b'logo', maintype='image', subtype='png')
    image.add_header('Content-Disposition', 'inline', filename='logo.png')
    image['Content-ID'] = '<logo@example.com>'
    message.attach(html)
    message.attach(image)

    manager.open(html, message)
    entry = manager._temporary[-1]
    entry.process.wait(timeout=5)
    directory = Path(entry.directory.name)

    assert (directory / 'logo.png').read_bytes() == b'logo'
    assert b'src="logo.png"' in (directory / 'part.html').read_bytes()
    manager.close()
