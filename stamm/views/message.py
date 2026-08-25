from __future__ import annotations

from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import ClassVar

from .. import keys, ui
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
    actions: ClassVar[keys.ActionSet] = (
        GLOBAL_ACTIONS
        | MAIL_ACTIONS
        | {
            'open_html': ('h',),
            'toggle_headers': ('w',),
        }
    )
    compiled_actions: ClassVar[keys.Bindings] = {}

    message: EmailMessage
    body: str
    mime: MimeManager
    state: IndexState
    key: str
    notice: str = field(default='', init=False)
    show_all_headers: bool = field(default=False, init=False)
    pager: PagerWidget = field(init=False)

    def __post_init__(self) -> None:
        self.pager = PagerWidget(self.message.get('Subject', ''), '')

    def _set_notice(self, notice: str, _is_sent: bool) -> None:
        self.notice = notice

    def _mail_action_message(self) -> tuple[EmailMessage, str, str]:
        return self.message, self.body, self.key

    def _pager_text(self, theme: MessageTheme) -> tuple[ui.TextSpan, ...]:
        spans: list[ui.TextSpan] = []
        headers = list(self.message.raw_items())
        if not self.show_all_headers:
            wanted = ('date', 'from', 'to', 'cc', 'subject')
            headers = [
                header
                for wanted_name in wanted
                if (header := next((item for item in headers if item[0].lower() == wanted_name), None))
            ]
        for name, value in headers:
            try:
                attr = getattr(theme, 'header_' + name.lower())
            except AttributeError:
                attr = theme.header
            lines = value.replace('\r\n', '\n').replace('\r', '\n').split('\n')
            text = f'{name}: {lines[0]}\n' + ''.join(f'    {line.lstrip()}\n' for line in lines[1:])
            spans.append(ui.TextSpan(text, attr))
        spans.extend((ui.TextSpan('\n'), ui.TextSpan(self.body)))
        return tuple(spans)

    def draw(self, context: ui.UIContext) -> None:
        text = self._pager_text(context.theme.message)
        if not self.pager.text:
            self.pager.text = text
        notice = self.notice
        self.notice = ''
        self.pager.draw(context)
        if notice:
            ui.status(context.screen, notice, context.theme.status)

    def on_unknown(self, context: ui.UIContext, ch: keys.Key) -> ChangeView | None:
        action = keys.resolve(PagerWidget.compiled_actions, ch)
        return self.pager.handle(context, action, ch)

    def on_open_html(self, _context: ui.UIContext) -> None:
        part = self.message.get_body(preferencelist=('html',))
        if part is None:
            self.notice = 'no HTML part'
            return
        try:
            self.mime.open(part, self.message)
            self.notice = 'opened HTML externally'
        except Exception as exc:
            self.notice = str(exc)

    def on_toggle_headers(self, _context: ui.UIContext) -> None:
        self.show_all_headers = not self.show_all_headers
        self.pager.text = ''
        self.pager.offset = 0

    def on_parts(self, context: ui.UIContext) -> ChangeView:
        return ChangeView.push(PartsView(self.message, self.mime))
