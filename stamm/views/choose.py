from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from .. import ui
from ..tui import keys
from . import UIContext, compile_actions


@dataclass(frozen=True, slots=True)
class ChooseView:
    namespace: ClassVar[str] = 'choose'
    actions: ClassVar[keys.ActionSet] = {
        'accept': ('ENTER',),
        'cancel': ('^[',),
    }

    prompt: str
    choices: Mapping[str, str]
    primary: str

    def run(self, context: UIContext) -> str | None:
        if self.primary not in self.choices.values():
            raise ValueError('primary item must be a choice')
        screen = context.screen
        ui.status(screen, f'{self.prompt} [{"/".join(self.choices)}]', context.theme.status)
        bindings = compile_actions(self.namespace, self.actions)
        while True:
            action, ch = keys.read(screen, bindings)
            if action == 'accept':
                return self.primary
            if action == 'cancel':
                return None
            if isinstance(ch, str) and ch in self.choices:
                return self.choices[ch]
