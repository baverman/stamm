from __future__ import annotations

import argparse
import curses
import logging
import os
import sys
from pathlib import Path

from . import compose, views
from .app import App
from .config import ConfigError, config, load_config, set_config
from .theme import Theme
from .tui import theme as tui_theme


def configure_logging() -> None:
    try:
        state_home = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local' / 'state')
        directory = state_home / 'stamm'
        directory.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=directory / 'stamm.log',
            level=logging.WARNING,
            format='%(asctime)s %(levelname)s %(name)s: %(message)s',
            encoding='utf-8',
        )
    except Exception:
        logging.basicConfig(handlers=[logging.NullHandler()])


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog='stamm', description='terminal Maildir client')
    parser.add_argument('target', nargs='?')
    args = parser.parse_args(argv)
    try:
        views.setup()
        set_config(load_config())
        is_mailto = args.target is not None and args.target.lower().startswith('mailto:')
        initial = compose.from_mailto(args.target, config) if is_mailto else None
        selected = None if is_mailto else Path(args.target) if args.target is not None else config.spool
        if selected is not None:
            if not selected.exists():
                raise FileNotFoundError(f'path does not exist: {selected}')
            if not selected.is_file() and not selected.is_dir():
                raise OSError(f'path is not a regular file or directory: {selected}')

        def run(screen: curses.window) -> None:
            curses.set_escdelay(100)
            screen.keypad(True)

            theme = tui_theme.make_theme(Theme, config.colors)
            screen.bkgd(' ', theme.normal)
            context = views.UIContext(screen, theme)

            app = App(context)
            if initial is not None:
                app.open_composer(initial)
            elif selected is not None and selected.is_file():
                app.open_message(selected)
            elif selected is not None:
                app.open_maildir(selected)
            app.run()

        curses.wrapper(run)
    except (compose.MailtoError, ConfigError, OSError, RuntimeError) as exc:
        print(f'stamm: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
