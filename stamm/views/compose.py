from __future__ import annotations

import curses
import tempfile
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from .. import compose, delivery, ui
from ..state import IndexState, MaildirState

if TYPE_CHECKING:
    from ..app import App


@dataclass
class ComposeView:
    data: compose.ComposeData
    on_finish: Callable[[str], None]
    old_draft: Path | None = None
    replied_state: MaildirState | None = None
    replied_index: IndexState | None = None
    replied_key: str | None = None
    workspace: tempfile.TemporaryDirectory[str] | None = None

    @classmethod
    def forward(
        cls,
        message: EmailMessage,
        rendered_body: str,
        app: App,
        on_finish: Callable[[str], None],
    ) -> ComposeView:
        workspace = tempfile.TemporaryDirectory(prefix='stamm-forward-')
        data = compose.forward(message, rendered_body, app.config, Path(workspace.name))
        return cls(data, on_finish, workspace=workspace)

    @classmethod
    def resume(
        cls,
        message: EmailMessage,
        old_draft: Path,
        on_finish: Callable[[str], None],
    ) -> ComposeView:
        workspace = tempfile.TemporaryDirectory(prefix='stamm-draft-')
        data = delivery.resume_draft(message, Path(workspace.name))
        return cls(data, on_finish, old_draft=old_draft, workspace=workspace)

    def _finish(self, app: App, notice: str) -> None:
        app.pop()
        self.on_finish(notice)

    def run(self, app: App) -> None:
        data = self.data
        edited = False
        errors: list[str] | None = None
        try:
            while True:
                curses.def_prog_mode()
                curses.endwin()
                try:
                    data, changed = compose.edit(app.config, data, errors)
                finally:
                    curses.reset_prog_mode()
                    app.screen.refresh()
                if not changed and not edited:
                    self._finish(app, '')
                    return
                edited = edited or changed
                errors = compose.validate(data)
                if errors:
                    action = ui.choose(
                        app.screen,
                        'Compose invalid: edit, draft, discard',
                        {'e': 'edit', 'd': 'draft', 'x': 'discard'},
                        app.theme.status,
                        app.bindings['choose'],
                        primary='edit',
                    )
                else:
                    action = ui.choose(
                        app.screen,
                        'Compose: send, edit, draft, discard',
                        {'s': 'send', 'e': 'edit', 'd': 'draft', 'x': 'discard'},
                        app.theme.status,
                        app.bindings['choose'],
                        primary='send',
                    )
                if action == 'edit':
                    continue
                if action in (None, 'discard'):
                    self._finish(app, '')
                    return
                try:
                    if action == 'draft':
                        delivery.save_draft(data, app.config)
                        notice = 'draft saved'
                    else:
                        ui.status(app.screen, 'Sending...', app.theme.status)
                        delivery.send(data, app.config)
                        notice = 'message sent'
                        if self.replied_key and self.replied_state and self.replied_index:
                            try:
                                self.replied_state.index.set_flags(self.replied_key, add='R')
                                self.replied_index.reload()
                            except (OSError, KeyError) as flag_exc:
                                notice = f'message sent; cannot mark replied: {flag_exc}'
                    if self.old_draft:
                        self.old_draft.unlink(missing_ok=True)
                    self._finish(app, notice)
                    return
                except (OSError, delivery.DeliveryError) as exc:
                    ui.pager(app.screen, 'Delivery failed', str(exc), app.theme.header, app.bindings['pager'])
                    retry = ui.choose(
                        app.screen,
                        'Delivery failed: edit, draft, discard',
                        {'e': 'edit', 'd': 'draft', 'x': 'discard'},
                        app.theme.status,
                        app.bindings['choose'],
                        primary='edit',
                    )
                    if retry == 'edit':
                        continue
                    if retry == 'draft':
                        try:
                            delivery.save_draft(data, app.config)
                            if self.old_draft:
                                self.old_draft.unlink(missing_ok=True)
                            self._finish(app, 'draft saved')
                        except OSError as draft_exc:
                            self._finish(app, str(draft_exc))
                        return
                    self._finish(app, str(exc))
                    return
        finally:
            if self.workspace:
                self.workspace.cleanup()
