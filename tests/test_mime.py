from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from stamm.config import Config, MimeRule
from stamm.config_model import DEFAULT_COLORS, HooksConfig
from stamm.mime import MimeManager, _OpenProcess


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
        hooks=HooksConfig(None),
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


def test_one_out_file_captures_stdout_and_stderr() -> None:
    manager = MimeManager(config())
    directory = tempfile.TemporaryDirectory(prefix='stamm-test-open-')
    output = Path(directory.name) / 'out'
    with output.open('wb') as out:
        process = manager._run(
            'printf stdout; printf stderr >&2; exit 7',
            b'',
            detached=True,
            output=out,
        )
    assert isinstance(process, subprocess.Popen)
    process.wait(timeout=5)
    manager._temporary.append(_OpenProcess(directory, process, output, 'test opener'))

    errors = manager.reap()

    assert len(errors) == 1
    assert 'exit status: 7' in errors[0]
    assert 'output:\nstdoutstderr' in errors[0]
    assert not Path(directory.name).exists()


def test_successful_opener_keeps_temporary_file_until_manager_closes() -> None:
    manager = MimeManager(config())
    directory = tempfile.TemporaryDirectory(prefix='stamm-test-open-')
    source = Path(directory.name) / 'part.html'
    output = Path(directory.name) / 'out'
    source.write_text('<p>content</p>', encoding='utf-8')
    with output.open('wb') as out:
        process = manager._run('true', b'', source, detached=True, output=out)
    assert isinstance(process, subprocess.Popen)
    process.wait(timeout=5)
    manager._temporary.append(_OpenProcess(directory, process, output, 'test opener'))

    assert manager.reap() == []
    assert source.exists()

    manager.close()
    assert not Path(directory.name).exists()
