from __future__ import annotations

import curses
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import TYPE_CHECKING, ClassVar

from .. import compose, keys
from ..index import IndexedMessage
from ..message import header_block, parse_message, select_body
from ..state import IndexState, MaildirState
from . import GLOBAL_ACTIONS, MAIL_ACTIONS, ChangeView
from .compose import ComposeView
from .pager import PagerView

if TYPE_CHECKING:
    from ..app import App


@dataclass
class MessageView:
    namespace: ClassVar[str] = 'message'
    actions: ClassVar[keys.ActionSet] = GLOBAL_ACTIONS | MAIL_ACTIONS
    compiled_actions: ClassVar[keys.Bindings] = {}
    maildir: MaildirState
    index_state: IndexState
    item: IndexedMessage
    app: App
    message: EmailMessage | None = field(default=None, init=False)
    body: str = field(default='', init=False)
    notice: str = field(default='', init=False)

    def _open(self, app: App) -> None:
        if 'S' not in self.item.flags:
            self.item = self.maildir.index.set_flags(self.item.key, add='S')
            self.maildir.reload()
            if self.index_state is not self.maildir:
                self.index_state.reload()
        self.message = parse_message(self.maildir.path / self.item.path)
        part = select_body(self.message, app.config)
        if part is None:
            self.body = '[No displayable body. Press v to inspect MIME parts.]'
            return
        try:
            self.body = app.mime.display(part)
        except Exception as exc:
            self.body = f'[Cannot display {part.get_content_type()}: {exc}]'

    def _set_notice(self, notice: str) -> None:
        self.notice = notice

    def run(self, screen: curses.window) -> ChangeView | None:
        app = self.app
        if self.message is None:
            self._open(app)
        assert self.message is not None
        while True:
            text = header_block(self.message) + '\n\n' + self.body
            if self.notice:
                text += f'\n\n[{self.notice}]'
                self.notice = ''
            pressed = PagerView(self.item.subject, text, app.theme).run(screen)
            action = keys.resolve(self.compiled_actions, pressed)
            if action == 'back':
                return None
            if action == 'parts':
                from .parts import PartsView

                return ChangeView.push(PartsView(self.message, app))
            if action == 'reply':
                return ChangeView.push(
                    ComposeView(
                        compose.reply(self.message, self.body, app.config),
                        self._set_notice,
                        app,
                        replied_state=self.maildir,
                        replied_index=self.index_state,
                        replied_key=self.item.key,
                    )
                )
            if action == 'reply_all':
                return ChangeView.push(
                    ComposeView(
                        compose.reply(self.message, self.body, app.config, all_recipients=True),
                        self._set_notice,
                        app,
                        replied_state=self.maildir,
                        replied_index=self.index_state,
                        replied_key=self.item.key,
                    )
                )
            if action == 'forward':
                return ChangeView.push(ComposeView.forward(self.message, self.body, app, self._set_notice))
