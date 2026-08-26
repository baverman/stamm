from __future__ import annotations

from email.message import EmailMessage

from .. import compose
from ..config import config
from ..state import IndexState
from . import Transition, UIContext
from .compose import ComposeView


class MailActionsMixin:
    state: IndexState

    def _mail_action_message(self) -> tuple[EmailMessage, str, str] | None:
        raise NotImplementedError

    def _set_notice(self, notice: str, is_sent: bool) -> None:
        raise NotImplementedError

    def _reply_finished(self, key: str, notice: str, is_sent: bool) -> None:
        if is_sent:
            try:
                self.state.source_state.mark_replied(key)
                self.state.reload()
            except (OSError, KeyError) as exc:
                notice = f'message sent; cannot mark replied: {exc}'
        self._set_notice(notice, is_sent)

    def _reply(self, all_recipients: bool) -> Transition | None:
        selected = self._mail_action_message()
        if selected is None:
            return None
        message, body, key = selected
        return Transition.push(
            ComposeView(
                compose.reply(message, body, config, all_recipients=all_recipients),
                lambda notice, is_sent: self._reply_finished(key, notice, is_sent),
            )
        )

    def on_reply(self, context: UIContext) -> Transition | None:
        return self._reply(False)

    def on_reply_all(self, context: UIContext) -> Transition | None:
        return self._reply(True)

    def on_forward(self, context: UIContext) -> Transition | None:
        selected = self._mail_action_message()
        if selected is None:
            return None
        message, body, _key = selected
        return Transition.push(ComposeView.forward(message, body, self._set_notice))
