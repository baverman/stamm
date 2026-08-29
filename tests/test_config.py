from __future__ import annotations

from pathlib import Path

from stamm import views
from stamm.config import load_config
from stamm.config_model import ColorStyle, ThreadConfig
from stamm.tui import keys


def test_nested_config_and_typed_defaults(tmp_path: Path) -> None:
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
                '[index]',
                'format = "{from:15} {subject:*}"',
                '[index.thread]',
                'vertical = "| "',
                'branch = "+-"',
                'last = "`-"',
                'indent = "  "',
                '[colors.index]',
                'column_from = { fg = "green" }',
                '[colors.message]',
                'header = { fg = "cyan", attrs = ["bold"] }',
                '[keys.index]',
                '"^N" = "down"',
                'R = { action = "refresh", before = "sync {maildir}", custom = 42 }',
            )
        ),
        encoding='utf-8',
    )
    views.setup()

    config = load_config(path)

    assert config.colors.index.column_from == ColorStyle('green', None, None)
    assert config.colors.message.header == ColorStyle('cyan', None, ('bold',))
    assert config.colors.normal is None
    assert config.index.format == '{from:15} {subject:*}'
    assert config.index.thread == ThreadConfig('| ', '+-', '`-', '  ')
    assert config.keys == {
        'index': {
            '^N': keys.Binding('down'),
            'R': keys.Binding('refresh', {'before': 'sync {maildir}', 'custom': 42}),
        }
    }
