from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from stamm import app as app_module
from stamm import compose, delivery, ui
from stamm.app import App
from stamm.compose import ComposeData
from stamm.config import Config
from stamm.config_model import DEFAULT_COLORS


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
        auto_view=(),
        alternative_order=('text/plain', 'text/html'),
        signatures={},
        mime=(),
        colors=DEFAULT_COLORS,
    )


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


def test_successful_reply_sets_maildir_replied_flag(config: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    data = ComposeData(sender='sender@example.com', to='recipient@example.com')
    calls: list[tuple[str, str]] = []
    reloaded: list[bool] = []
    index = SimpleNamespace(set_flags=lambda key, *, add: calls.append((key, add)))
    state = SimpleNamespace(index=index, reload_cached=lambda: reloaded.append(True))
    screen = SimpleNamespace(refresh=lambda: None)
    app = object.__new__(App)
    app.config = config
    app.state = state
    app.screen = screen
    app.theme = SimpleNamespace(status=0, header=0)
    app.notice = ''

    monkeypatch.setattr(app_module.curses, 'def_prog_mode', lambda: None)
    monkeypatch.setattr(app_module.curses, 'endwin', lambda: None)
    monkeypatch.setattr(app_module.curses, 'reset_prog_mode', lambda: None)
    monkeypatch.setattr(compose, 'edit', lambda *_args: (data, True))
    monkeypatch.setattr(ui, 'choose', lambda *_args, **_kwargs: 's')
    monkeypatch.setattr(delivery, 'send', lambda *_args: Path('/tmp/sent'))

    app.compose(data, replied_key='message-key')

    assert calls == [('message-key', 'R')]
    assert reloaded == [True]
    assert app.notice == 'message sent'
