"""Command-line entry point."""

from __future__ import annotations

import argparse
import curses
import sys
from pathlib import Path

from . import ui
from .app import App
from .config import ConfigError, load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='stamm', description='terminal Maildir client')
    parser.add_argument('maildir', nargs='?', type=Path)
    args = parser.parse_args(argv)
    try:
        config = load_config()
        # CLI paths are intentionally not expanded by Stamm.
        selected = args.maildir if args.maildir is not None else config.spool

        def run(screen: curses.window) -> None:
            screen.keypad(True)
            theme = ui.initialize_colors(screen, config.colors)
            app = App(screen, config, theme)
            app.open_maildir(selected)
            app.run()

        curses.wrapper(run)
    except (ConfigError, OSError, RuntimeError) as exc:
        print(f'stamm: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
