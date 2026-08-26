from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from . import keys, text
from .views import BaseContext, View


@dataclass(frozen=True, slots=True)
class ChoiceView(View[BaseContext, str | None]):
    namespace: ClassVar[str] = 'choice'
    actions: ClassVar[keys.ActionSet] = {
        'accept': ('ENTER',),
        'cancel': ('^[',),
    }

    prompt: str
    choices: Mapping[str, str]
    primary: str
    overrides: Mapping[str, str] | None = None

    def run(self, context: BaseContext) -> str | None:
        if self.primary not in self.choices.values():
            raise ValueError('primary item must be a choice')
        screen = context.screen
        text.status(screen, f'{self.prompt} [{"/".join(self.choices)}]', context.theme.status)
        bindings = keys.compile_bindings(self.namespace, self.actions, self.overrides or {})
        while True:
            action, ch = keys.read(screen, bindings)
            if action == 'accept':
                return self.primary
            if action == 'cancel':
                return None
            if isinstance(ch, str) and ch in self.choices:
                return self.choices[ch]
