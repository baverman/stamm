from __future__ import annotations

import curses
import tempfile
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from .. import compose, delivery, ui
from ..state import IndexState, MaildirState
from . import ChangeView
from .choose import ChooseView
from .pager import PagerView

if TYPE_CHECKING:
    from ..app import App


@dataclass
class ComposeView:
    data: compose.ComposeData
    on_finish: Callable[[str], None]
    app: App
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
        return cls(data, on_finish, app, workspace=workspace)

    @classmethod
    def resume(
        cls,
        message: EmailMessage,
        old_draft: Path,
        app: App,
        on_finish: Callable[[str], None],
    ) -> ComposeView:
        workspace = tempfile.TemporaryDirectory(prefix='stamm-draft-')
        data = delivery.resume_draft(message, Path(workspace.name))
        return cls(data, on_finish, app, old_draft=old_draft, workspace=workspace)

    def _finish(self, notice: str) -> None:
        self.on_finish(notice)

    def run(self, screen: curses.window) -> ChangeView:
        app = self.app
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
                    screen.refresh()
                if not changed and not edited:
                    self._finish('')
                    return ChangeView.close()
                edited = edited or changed
                errors = compose.validate(data)
                if errors:
                    action = ChooseView(
                        'Compose invalid: edit, draft, discard',
                        {'e': 'edit', 'd': 'draft', 'x': 'discard'},
                        primary='edit',
                        theme=app.theme,
                    ).run(screen)
                else:
                    action = ChooseView(
                        'Compose: send, edit, draft, discard',
                        {'s': 'send', 'e': 'edit', 'd': 'draft', 'x': 'discard'},
                        primary='send',
                        theme=app.theme,
                    ).run(screen)
                if action == 'edit':
                    continue
                if action in (None, 'discard'):
                    self._finish('')
                    return ChangeView.close()
                try:
                    if action == 'draft':
                        delivery.save_draft(data, app.config)
                        notice = 'draft saved'
                    else:
                        ui.status(screen, 'Sending...', app.theme.status)
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
                    self._finish(notice)
                    return ChangeView.close()
                except (OSError, delivery.DeliveryError) as exc:
                    PagerView('Delivery failed', str(exc), app.theme).run(screen)
                    retry = ChooseView(
                        'Delivery failed: edit, draft, discard',
                        {'e': 'edit', 'd': 'draft', 'x': 'discard'},
                        primary='edit',
                        theme=app.theme,
                    ).run(screen)
                    if retry == 'edit':
                        continue
                    if retry == 'draft':
                        try:
                            delivery.save_draft(data, app.config)
                            if self.old_draft:
                                self.old_draft.unlink(missing_ok=True)
                            self._finish('draft saved')
                        except OSError as draft_exc:
                            self._finish(str(draft_exc))
                        return ChangeView.close()
                    self._finish(str(exc))
                    return ChangeView.close()
        finally:
            if self.workspace:
                self.workspace.cleanup()
