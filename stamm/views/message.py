from __future__ import annotations

from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import ClassVar

from .. import keys, ui
from ..message import message_headers
from ..mime import MimeManager
from ..state import IndexState
from ..theme import MessageTheme
from . import GLOBAL_ACTIONS, MAIL_ACTIONS, ChangeView, DefaultActionView
from .mail_actions import MailActionsMixin
from .pager import PagerWidget
from .parts import PartsView


@dataclass
class MessageView(MailActionsMixin, DefaultActionView):
    namespace: ClassVar[str] = 'message'
    actions: ClassVar[keys.ActionSet] = GLOBAL_ACTIONS | MAIL_ACTIONS
    compiled_actions: ClassVar[keys.Bindings] = {}

    message: EmailMessage
    body: str
    mime: MimeManager
    state: IndexState
    key: str
    notice: str = field(default='', init=False)
    pager: PagerWidget = field(init=False)

    def __post_init__(self) -> None:
        self.pager = PagerWidget(self.message.get('Subject', ''), '')

    def _set_notice(self, notice: str, _is_sent: bool) -> None:
        self.notice = notice

    def _mail_action_message(self) -> tuple[EmailMessage, str, str]:
        return self.message, self.body, self.key

    def _pager_text(self, theme: MessageTheme) -> tuple[ui.TextSpan, ...]:
        spans: list[ui.TextSpan] = []
        for name, value in message_headers(self.message):
            try:
                attr = getattr(theme, 'header_' + name.lower())
            except AttributeError:
                attr = theme.header
            spans.append(ui.TextSpan(f'{name}: {value}\n', attr))
        spans.extend((ui.TextSpan('\n'), ui.TextSpan(self.body)))
        return tuple(spans)

    def draw(self, context: ui.UIContext) -> None:
        text = self._pager_text(context.theme.message)
        if not self.pager.text:
            self.pager.text = text
        if self.notice:
            self.pager.text = text + (ui.TextSpan(f'\n\n[{self.notice}]'),)
            self.notice = ''
        self.pager.draw(context)

    def on_unknown(self, context: ui.UIContext, ch: keys.Key) -> ChangeView | None:
        action = keys.resolve(PagerWidget.compiled_actions, ch)
        return self.pager.handle(context, action, ch)

    def on_parts(self, context: ui.UIContext) -> ChangeView:
        return ChangeView.push(PartsView(self.message, self.mime))
