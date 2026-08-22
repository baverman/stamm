from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from stamm.compose import ComposeData
from stamm.config import Config
from stamm.config_model import DEFAULT_COLORS, HooksConfig
from stamm.delivery import DeliveryError, envelope, send


@pytest.fixture
def config() -> Config:
    return Config(
        root=Path('/tmp'),
        spool=Path('/tmp/inbox'),
        sent=Path('/tmp/sent'),
        drafts=Path('/tmp/drafts'),
        trash=Path('/tmp/trash'),
        editor='true',
        sendmail='sendmail --mode test',
        identities=('Sender <sender@example.com>',),
        hooks=HooksConfig(None),
        auto_view=(),
        alternative_order=('text/plain', 'text/html'),
        signatures={},
        mime=(),
        colors=DEFAULT_COLORS,
    )


def test_envelope_collects_and_deduplicates_all_recipient_fields() -> None:
    data = ComposeData(
        sender='Sender <sender@example.com>',
        to='One <one@example.com>, duplicate@example.com',
        cc='duplicate@example.com',
        bcc='two@example.com',
    )

    assert envelope(data) == (
        'sender@example.com',
        ['one@example.com', 'duplicate@example.com', 'two@example.com'],
    )


def test_envelope_rejects_an_empty_recipient_list() -> None:
    with pytest.raises(DeliveryError, match='no envelope recipients'):
        envelope(ComposeData(sender='sender@example.com'))


def test_send_passes_sender_and_recipients_as_separate_arguments(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    call: dict[str, Any] = {}

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        call['command'] = command
        call['input'] = kwargs['input']
        return subprocess.CompletedProcess(command, 0, b'', b'')

    monkeypatch.setattr('stamm.delivery.subprocess.run', run)
    monkeypatch.setattr('stamm.delivery.store', lambda *_args, **_kwargs: Path('/tmp/sent/message'))
    data = ComposeData(
        sender='Sender <sender@example.com>',
        to='Recipient <recipient@example.com>',
        body='hello',
    )

    send(data, config)

    assert call['command'] == ['sendmail', '--mode', 'test', '-f', 'sender@example.com', 'recipient@example.com']
    assert b'Bcc:' not in call['input']
