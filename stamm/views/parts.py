from __future__ import annotations

import curses
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from .. import keys, ui
from ..mime import PartRow, part_rows, save_part
from . import GLOBAL_ACTIONS, MOVE_ACTIONS, ChangeView

if TYPE_CHECKING:
    from ..app import App


@dataclass
class PartsView:
    namespace: ClassVar[str] = 'parts'
    actions: ClassVar[keys.ActionSet] = GLOBAL_ACTIONS | MOVE_ACTIONS | {'open': ('ENTER',), 'save': ('s',)}
    compiled_actions: ClassVar[keys.Bindings] = {}
    message: EmailMessage
    app: App
    rows: list[PartRow] = field(init=False)
    selected: int = 0
    notice: str = ''

    def __post_init__(self) -> None:
        self.rows = part_rows(self.message)

    def draw(self, app: App) -> None:
        screen = app.screen
        screen.erase()
        height, width = screen.getmaxyx()
        ui.put(screen, 0, 0, ' MIME parts '.ljust(width), width, app.theme.header)
        visible = max(1, height - 2)
        start = min(max(0, self.selected - visible + 1), self.selected)
        for index, row in enumerate(self.rows[start : start + visible], 1):
            attr = app.theme.indicator if start + index - 1 == self.selected else 0
            ui.put(screen, index, 0, '  ' * row.depth + row.label, width, attr)
        ui.status(screen, self.notice, app.theme.status)
        self.notice = ''

    def run(self, screen: curses.window) -> ChangeView | None:
        app = self.app
        while True:
            self.draw(app)
            action, _ch = keys.read(screen, self.compiled_actions)
            if action == 'back':
                return None
            if action == 'down':
                self.selected = min(len(self.rows) - 1, self.selected + 1)
            elif action == 'up':
                self.selected = max(0, self.selected - 1)
            elif action == 'open' and not self.rows[self.selected].part.is_multipart():
                try:
                    app.mime.open(self.rows[self.selected].part)
                    self.notice = 'opened externally'
                except Exception as exc:
                    self.notice = str(exc)
            elif action == 'save' and not self.rows[self.selected].part.is_multipart():
                value = ui.prompt(
                    app.screen,
                    'Save to: ',
                    self.rows[self.selected].part.get_filename() or '',
                    complete_paths=True,
                    status_attr=app.theme.status,
                )
                if value:
                    try:
                        path = save_part(self.rows[self.selected].part, Path(value))
                        self.notice = f'saved {path}'
                    except OSError as exc:
                        self.notice = str(exc)
