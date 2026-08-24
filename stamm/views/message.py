from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import ClassVar

from .. import keys, ui
from ..message import header_block
from . import GLOBAL_ACTIONS, MAIL_ACTIONS, ChangeView, DefaultActionView
from .pager import PagerWidget

MessageAction = Callable[[str, Callable[[str, bool], None]], ChangeView]


@dataclass
class MessageView(DefaultActionView):
    namespace: ClassVar[str] = 'message'
    actions: ClassVar[keys.ActionSet] = GLOBAL_ACTIONS | MAIL_ACTIONS
    compiled_actions: ClassVar[keys.Bindings] = {}

    message: EmailMessage
    body: str
    action: MessageAction
    notice: str = field(default='', init=False)
    pager: PagerWidget = field(init=False)

    def __post_init__(self) -> None:
        self.pager = PagerWidget(self.message.get('Subject', ''), '')

    def _set_notice(self, notice: str, _is_sent: bool) -> None:
        self.notice = notice

    def draw(self, context: ui.UIContext) -> None:
        text = header_block(self.message) + '\n\n' + self.body
        if not self.pager.text:
            self.pager.text = text
        if self.notice:
            self.pager.text = text + f'\n\n[{self.notice}]'
            self.notice = ''
        self.pager.draw(context)

    def on_unknown(self, context: ui.UIContext, ch: keys.Key) -> ChangeView | None:
        action = keys.resolve(PagerWidget.compiled_actions, ch)
        return self.pager.handle(context, action, ch)

    def on_parts(self, context: ui.UIContext) -> ChangeView:
        return self.action('parts', self._set_notice)

    def on_reply(self, context: ui.UIContext) -> ChangeView:
        return self.action('reply', self._set_notice)

    def on_reply_all(self, context: ui.UIContext) -> ChangeView:
        return self.action('reply_all', self._set_notice)

    def on_forward(self, context: ui.UIContext) -> ChangeView:
        return self.action('forward', self._set_notice)
