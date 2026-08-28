from __future__ import annotations

from email.message import EmailMessage

from .. import compose
from ..config import config
from ..state import IndexState
from . import Transition, UIContext
from .compose import ComposeView


class MailActionsMixin:
    state: IndexState

    def mail_action_message(self) -> tuple[EmailMessage, str, str] | None:
        raise NotImplementedError

    def set_notice(self, notice: str, is_sent: bool) -> None:
        raise NotImplementedError

    def reply_finished(self, key: str, notice: str, is_sent: bool) -> None:
        if is_sent:
            try:
                self.state.source_state.mark_replied(key)
                self.state.reload()
            except (OSError, KeyError) as exc:
                notice = f'message sent; cannot mark replied: {exc}'
        self.set_notice(notice, is_sent)

    def reply(self, all_recipients: bool) -> Transition | None:
        selected = self.mail_action_message()
        if selected is None:
            return None
        message, body, key = selected
        return Transition.push(
            ComposeView(
                compose.reply(message, body, config, all_recipients=all_recipients),
                lambda notice, is_sent: self.reply_finished(key, notice, is_sent),
            )
        )

    def on_reply(self, context: UIContext) -> Transition | None:
        return self.reply(False)

    def on_reply_all(self, context: UIContext) -> Transition | None:
        return self.reply(True)

    def on_forward(self, context: UIContext) -> Transition | None:
        selected = self.mail_action_message()
        if selected is None:
            return None
        message, body, _key = selected
        return Transition.push(ComposeView.forward(message, body, self.set_notice))
