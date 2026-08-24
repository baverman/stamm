from __future__ import annotations

from pathlib import Path

from stamm.config import load_config
from stamm.config_model import ColorStyle


def test_nested_hooks_config_and_typed_defaults(tmp_path: Path) -> None:
    path = tmp_path / 'stamm.toml'
    path.write_text(
        '\n'.join(
            (
                f'root = "{tmp_path}"',
                'spool = "inbox"',
                'sent = "sent"',
                'drafts = "drafts"',
                'trash = "trash"',
                'editor = "true"',
                'sendmail = "true"',
                'identities = ["sender@example.com"]',
                '[hooks]',
                'pre_refresh = "sync {maildir}"',
                '[index]',
                'format = "{from:15} {subject:*}"',
                '[colors.index]',
                'column_from = { fg = "green" }',
                '[colors.message]',
                'header = { fg = "cyan", attrs = ["bold"] }',
                '[keys.index]',
                '"^N" = "down"',
            )
        ),
        encoding='utf-8',
    )

    config = load_config(path)

    assert config.hooks.pre_refresh == 'sync {maildir}'
    assert config.colors.index.column_from == ColorStyle('green', None, None)
    assert config.colors.message.header == ColorStyle('cyan', None, ('bold',))
    assert config.colors.normal is None
    assert config.index.format == '{from:15} {subject:*}'
    assert config.keys == {'index': {'^N': 'down'}}
