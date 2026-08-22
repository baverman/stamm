from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from stamm import compose
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


def test_editor_reports_unchanged_buffer(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
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
