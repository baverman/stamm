from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stamm.config import ColorConfig, ColorStyle, ConfigError, load_config


class ColorConfigTests(unittest.TestCase):
    def test_roles_inherit_missing_foreground_and_background_from_normal(self) -> None:
        colors = ColorConfig(
            normal=ColorStyle(fg=2, bg='default'),
            roles={
                'index_date': ColorStyle(fg='blue'),
                'header': ColorStyle(attrs=('reverse',)),
            },
        )

        self.assertEqual(colors.resolved('index_date'), ColorStyle(fg='blue', bg='default'))
        self.assertEqual(colors.resolved('header'), ColorStyle(fg=2, bg='default', attrs=('reverse',)))
        self.assertEqual(colors.resolved('index_sender'), ColorStyle(fg=2, bg='default'))

    def test_loads_named_numeric_and_attribute_colors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'stamm.toml'
            path.write_text(
                f'''root = "{root}"
spool = "inbox"
sent = "sent"
drafts = "drafts"
trash = "trash"
editor = "true"
sendmail = "true"
identities = ["sender@example.com"]

[colors]
normal = {{ fg = 2, bg = "default" }}
header = {{ attrs = ["reverse"] }}
index_date = {{ fg = "blue" }}
''',
                encoding='utf-8',
            )

            config = load_config(path)

            self.assertEqual(config.colors.normal, ColorStyle(fg=2, bg='default'))
            self.assertEqual(config.colors.resolved('header').attrs, ('reverse',))
            self.assertEqual(config.colors.resolved('index_date').fg, 'blue')

    def test_rejects_unknown_color_roles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'stamm.toml'
            path.write_text(
                f'''root = "{root}"
spool = "inbox"
sent = "sent"
drafts = "drafts"
trash = "trash"
editor = "true"
sendmail = "true"
identities = ["sender@example.com"]

[colors]
unknown = {{ fg = "red" }}
''',
                encoding='utf-8',
            )

            with self.assertRaisesRegex(ConfigError, 'unknown color roles'):
                load_config(path)


if __name__ == '__main__':
    unittest.main()
