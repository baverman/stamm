from __future__ import annotations

from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import TYPE_CHECKING

from .. import compose, ui
from ..index import IndexedMessage
from ..message import header_block, parse_message, select_body
from ..state import IndexState, MaildirState
from .compose import ComposeView

if TYPE_CHECKING:
    from ..app import App


@dataclass
class MessageView:
    maildir: MaildirState
    index_state: IndexState
    item: IndexedMessage
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

    def run(self, app: App) -> None:
        if self.message is None:
            self._open(app)
        assert self.message is not None
        while True:
            text = header_block(self.message) + '\n\n' + self.body
            if self.notice:
                text += f'\n\n[{self.notice}]'
                self.notice = ''
            key = ui.pager(app.screen, self.item.subject, text, app.theme.header)
            if key in ui.KEYS['back']:
                app.pop()
                return
            if key in ui.KEYS['parts']:
                from .parts import PartsView

                app.push(PartsView(self.message))
                return
            if key in ui.KEYS['reply']:
                app.push(
                    ComposeView(
                        compose.reply(self.message, self.body, app.config),
                        self._set_notice,
                        replied_state=self.maildir,
                        replied_index=self.index_state,
                        replied_key=self.item.key,
                    )
                )
                return
            if key in ui.KEYS['reply_all']:
                app.push(
                    ComposeView(
                        compose.reply(self.message, self.body, app.config, all_recipients=True),
                        self._set_notice,
                        replied_state=self.maildir,
                        replied_index=self.index_state,
                        replied_key=self.item.key,
                    )
                )
                return
            if key in ui.KEYS['forward']:
                app.push(ComposeView.forward(self.message, self.body, app, self._set_notice))
                return
