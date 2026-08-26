from __future__ import annotations

import curses
import tempfile
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Callable

from .. import compose, delivery
from ..config import config
from ..tui import text
from ..tui.choice import ChoiceView
from . import Transition, UIContext
from .pager import PagerView


@dataclass
class ComposeView:
    data: compose.ComposeData
    on_finish: Callable[[str, bool], None]
    old_draft: Path | None = None
    workspace: tempfile.TemporaryDirectory[str] | None = None

    @classmethod
    def forward(
        cls,
        message: EmailMessage,
        rendered_body: str,
        on_finish: Callable[[str, bool], None],
    ) -> ComposeView:
        workspace = tempfile.TemporaryDirectory(prefix='stamm-forward-')
        data = compose.forward(message, rendered_body, config, Path(workspace.name))
        return cls(data, on_finish, workspace=workspace)

    @classmethod
    def resume(
        cls,
        message: EmailMessage,
        old_draft: Path,
        on_finish: Callable[[str, bool], None],
    ) -> ComposeView:
        workspace = tempfile.TemporaryDirectory(prefix='stamm-draft-')
        data = delivery.resume_draft(message, Path(workspace.name))
        return cls(data, on_finish, old_draft=old_draft, workspace=workspace)

    def _finish(self, notice: str, is_sent: bool) -> None:
        self.on_finish(notice, is_sent)

    def run(self, context: UIContext) -> Transition:
        screen = context.screen
        data = self.data
        edited = False
        errors: list[str] | None = None
        try:
            while True:
                curses.def_prog_mode()
                curses.endwin()
                try:
                    data, changed = compose.edit(config, data, errors)
                finally:
                    curses.reset_prog_mode()
                    screen.refresh()
                if not changed and not edited:
                    self._finish('', False)
                    return Transition.close()
                edited = edited or changed
                errors = compose.validate(data)
                if errors:
                    action = ChoiceView(
                        'Compose invalid: edit, draft, discard',
                        {'e': 'edit', 'd': 'draft', 'x': 'discard'},
                        primary='edit',
                        overrides=config.keys.get(ChoiceView.namespace),
                    ).run(context)
                else:
                    action = ChoiceView(
                        'Compose: send, edit, draft, discard',
                        {'s': 'send', 'e': 'edit', 'd': 'draft', 'x': 'discard'},
                        primary='send',
                        overrides=config.keys.get(ChoiceView.namespace),
                    ).run(context)
                if action == 'edit':
                    continue
                if action in (None, 'discard'):
                    self._finish('', False)
                    return Transition.close()
                is_sent = False
                try:
                    if action == 'draft':
                        delivery.save_draft(data, config)
                        notice = 'draft saved'
                    else:
                        text.status(screen, 'Sending...', context.theme.status)
                        delivery.send(data, config)
                        is_sent = True
                        notice = 'message sent'
                    if self.old_draft:
                        self.old_draft.unlink(missing_ok=True)
                    self._finish(notice, is_sent)
                    return Transition.close()
                except (OSError, delivery.DeliveryError) as exc:
                    PagerView('Delivery failed', text.span_lines(str(exc))).run(context)
                    retry = ChoiceView(
                        'Delivery failed: edit, draft, discard',
                        {'e': 'edit', 'd': 'draft', 'x': 'discard'},
                        primary='edit',
                        overrides=config.keys.get(ChoiceView.namespace),
                    ).run(context)
                    if retry == 'edit':
                        continue
                    if retry == 'draft':
                        try:
                            delivery.save_draft(data, config)
                            if self.old_draft:
                                self.old_draft.unlink(missing_ok=True)
                            self._finish('draft saved', False)
                        except OSError as draft_exc:
                            self._finish(str(draft_exc), False)
                        return Transition.close()
                    self._finish(str(exc), is_sent)
                    return Transition.close()
        finally:
            if self.workspace:
                self.workspace.cleanup()
