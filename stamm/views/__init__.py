from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..app import App


class View(Protocol):
    def run(self, app: App) -> None: ...
