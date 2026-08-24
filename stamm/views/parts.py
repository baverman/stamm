from __future__ import annotations

from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path
from typing import ClassVar

from .. import keys, ui
from ..mime import MimeManager, PartRow, part_rows, save_part
from . import GLOBAL_ACTIONS, MOVE_ACTIONS, DefaultActionView


@dataclass
class PartsView(DefaultActionView):
    namespace: ClassVar[str] = 'parts'
    actions: ClassVar[keys.ActionSet] = GLOBAL_ACTIONS | MOVE_ACTIONS | {'open': ('ENTER',), 'save': ('s',)}
    compiled_actions: ClassVar[keys.Bindings] = {}
    message: EmailMessage
    mime: MimeManager
    rows: list[PartRow] = field(init=False)
    selected: int = 0
    notice: str = ''

    def __post_init__(self) -> None:
        self.rows = part_rows(self.message)

    def draw(self, context: ui.UIContext) -> None:
        screen = context.screen
        screen.erase()
        height, width = screen.getmaxyx()
        ui.put(screen, 0, 0, ' MIME parts '.ljust(width), width, context.theme.header)
        visible = max(1, height - 2)
        start = min(max(0, self.selected - visible + 1), self.selected)
        for index, row in enumerate(self.rows[start : start + visible], 1):
            attr = context.theme.indicator if start + index - 1 == self.selected else 0
            ui.put(screen, index, 0, '  ' * row.depth + row.label, width, attr)
        ui.status(screen, self.notice, context.theme.status)
        self.notice = ''

    def on_down(self, context: ui.UIContext) -> None:
        self.selected = min(len(self.rows) - 1, self.selected + 1)

    def on_up(self, context: ui.UIContext) -> None:
        self.selected = max(0, self.selected - 1)

    def on_open(self, context: ui.UIContext) -> None:
        part = self.rows[self.selected].part
        if part.is_multipart():
            return
        try:
            self.mime.open(part, self.message)
            self.notice = 'opened externally'
        except Exception as exc:
            self.notice = str(exc)

    def on_save(self, context: ui.UIContext) -> None:
        part = self.rows[self.selected].part
        if part.is_multipart():
            return
        value = ui.prompt(
            context.screen,
            'Save to: ',
            part.get_filename() or '',
            complete_paths=True,
            status_attr=context.theme.status,
        )
        if value:
            try:
                path = save_part(part, Path(value))
                self.notice = f'saved {path}'
            except OSError as exc:
                self.notice = str(exc)
