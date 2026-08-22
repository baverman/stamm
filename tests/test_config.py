from __future__ import annotations

from pathlib import Path

import pytest

from stamm.config import ColorConfig, ColorStyle, ConfigError, load_config


def write_config(path: Path, colors: str) -> Path:
    config = path / 'stamm.toml'
    config.write_text(
        f'''root = "{path}"
spool = "inbox"
sent = "sent"
drafts = "drafts"
trash = "trash"
editor = "true"
sendmail = "true"
identities = ["sender@example.com"]

[colors]
{colors}
''',
        encoding='utf-8',
    )
    return config


def test_roles_inherit_missing_foreground_and_background_from_normal() -> None:
    colors = ColorConfig(
        normal=ColorStyle(fg=2, bg='default'),
        roles={
            'index_date': ColorStyle(fg='blue'),
            'header': ColorStyle(attrs=('reverse',)),
        },
    )

    assert colors.resolved('index_date') == ColorStyle(fg='blue', bg='default')
    assert colors.resolved('header') == ColorStyle(fg=2, bg='default', attrs=('reverse',))
    assert colors.resolved('index_sender') == ColorStyle(fg=2, bg='default')


def test_loads_named_numeric_and_attribute_colors(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        """normal = { fg = 2, bg = "default" }
header = { attrs = ["reverse"] }
index_date = { fg = "blue" }""",
    )

    config = load_config(path)

    assert config.colors.normal == ColorStyle(fg=2, bg='default')
    assert config.colors.resolved('header').attrs == ('reverse',)
    assert config.colors.resolved('index_date').fg == 'blue'


def test_rejects_unknown_color_roles(tmp_path: Path) -> None:
    path = write_config(tmp_path, 'unknown = { fg = "red" }')

    with pytest.raises(ConfigError, match='unknown color roles'):
        load_config(path)
