from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from .. import keys, ui


@dataclass(frozen=True, slots=True)
class ChooseView:
    namespace: ClassVar[str] = 'choose'
    actions: ClassVar[keys.ActionSet] = {
        'accept': ('ENTER',),
        'cancel': ('^[',),
    }
    compiled_actions: ClassVar[keys.Bindings] = {}

    prompt: str
    choices: Mapping[str, str]
    primary: str

    def run(self, context: ui.UIContext) -> str | None:
        if self.primary not in self.choices.values():
            raise ValueError('primary item must be a choice')
        screen = context.screen
        ui.status(screen, f'{self.prompt} [{"/".join(self.choices)}]', context.theme.status)
        while True:
            action, ch = keys.read(screen, self.compiled_actions)
            if action == 'accept':
                return self.primary
            if action == 'cancel':
                return None
            if isinstance(ch, str) and ch in self.choices:
                return self.choices[ch]
