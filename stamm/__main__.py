"""Command-line entry point."""

from __future__ import annotations

import argparse
import curses
import sys
from pathlib import Path

from . import keys, ui
from .app import App
from .config import ConfigError, config, load_config, set_config
from .views.choose import ChooseView
from .views.index import IndexView
from .views.message import MessageView
from .views.pager import PagerView
from .views.parts import PartsView


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='stamm', description='terminal Maildir client')
    parser.add_argument('maildir', nargs='?', type=Path)
    args = parser.parse_args(argv)
    try:
        set_config(load_config())
        diagnostics: list[str] = []
        views = (IndexView, MessageView, PartsView, PagerView, ChooseView)

        for view in views:
            view.compiled_actions, current = keys.compile_bindings(
                view.namespace,
                view.actions,
                config.keys.get(view.namespace, {}),
            )
            diagnostics.extend(current)

        known_namespaces = {view.namespace for view in views}
        for namespace in config.keys.keys() - known_namespaces:
            diagnostics.append(f'keys.{namespace}: unknown namespace')
        # CLI paths are intentionally not expanded by Stamm.
        selected = args.maildir if args.maildir is not None else config.spool

        def run(screen: curses.window) -> None:
            curses.set_escdelay(100)
            screen.keypad(True)
            theme = ui.initialize_colors(screen, config.colors)
            context = ui.UIContext(screen, theme)
            if diagnostics:
                PagerView(
                    'Key binding warnings',
                    '\n'.join(diagnostics) + '\n\nPress any unbound key to continue.',
                ).run(context)
            app = App(context)
            app.open_maildir(selected)
            app.run()

        curses.wrapper(run)
    except (ConfigError, OSError, RuntimeError) as exc:
        print(f'stamm: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
