from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from .index import INITIAL_MESSAGE_LIMIT, IndexedMessage, MessageIndex
from .search import SearchExpression, body_queries, matches
from .threads import ThreadRow, build_threads


@dataclass
class IndexState(ABC):
    rows: list[ThreadRow]
    selected: int
    offset: int

    @property
    @abstractmethod
    def title(self) -> str: ...

    @property
    @abstractmethod
    def source_state(self) -> MaildirState: ...

    @property
    def selected_message(self) -> IndexedMessage:
        return self.rows[self.selected].message

    def select_next(self) -> None:
        self.selected = min(len(self.rows) - 1, self.selected + 1)

    def select_previous(self) -> None:
        self.selected = max(0, self.selected - 1)

    @abstractmethod
    def reload(self) -> None: ...


@dataclass
class MaildirState(IndexState):
    path: Path
    index: MessageIndex
    pending_delete: set[str]

    @classmethod
    def open(cls, path: Path) -> MaildirState:
        index = MessageIndex(path)
        try:
            rows = build_threads(index.messages(limit=INITIAL_MESSAGE_LIMIT))
        except Exception:
            index.close()
            raise
        return cls(rows, max(0, len(rows) - 1), 0, path, index, set())

    @property
    def title(self) -> str:
        return f'Stamm — {self.path}'

    @property
    def source_state(self) -> MaildirState:
        return self

    def load_rows(self, messages: list[IndexedMessage]) -> None:
        key = self.selected_message.key if self.rows else None
        self.rows = build_threads(messages)
        if key:
            self.selected = next((i for i, row in enumerate(self.rows) if row.message.key == key), 0)
        else:
            self.selected = min(self.selected, max(0, len(self.rows) - 1))

    def refresh(self) -> None:
        self.load_rows(self.index.refresh())

    def reload(self) -> None:
        self.load_rows(self.index.messages())

    def mark_replied(self, key: str) -> None:
        self.index.set_flags(key, add='R')

    def mark_deleted(self, key: str) -> None:
        self.pending_delete.add(key)

    def unmark_deleted(self, key: str) -> None:
        self.pending_delete.discard(key)

    def purge_deleted(self, trash: Path) -> list[str]:
        if not self.pending_delete:
            return []
        errors: list[str] = []
        position = self.selected
        for key in list(self.pending_delete):
            try:
                if self.index.get(key) is not None:
                    self.index.move_to(key, trash)
                self.pending_delete.discard(key)
            except (OSError, ValueError) as exc:
                errors.append(f'{self.path}: {exc}')
        self.rows = build_threads(self.index.messages())
        self.selected = min(position, max(0, len(self.rows) - 1))
        return errors


@dataclass
class SearchState(IndexState):
    source: MaildirState
    query: str
    expression: SearchExpression

    @staticmethod
    def _matching_rows(source: MaildirState, expression: SearchExpression) -> list[ThreadRow]:
        body_matches = {query: source.index.search_body(query) for query in body_queries(expression)}
        return [row for row in source.rows if matches(row.message, expression, body_matches)]

    @classmethod
    def create(cls, source: MaildirState, query: str, expression: SearchExpression) -> SearchState:
        rows = cls._matching_rows(source, expression)
        return cls(rows, max(0, len(rows) - 1), 0, source, query, expression)

    @property
    def title(self) -> str:
        return f'Search — {self.query}'

    @property
    def source_state(self) -> MaildirState:
        return self.source

    def rebuild(self) -> None:
        key = self.selected_message.key if self.rows else None
        self.rows = self._matching_rows(self.source, self.expression)
        if key:
            fallback = min(self.selected, max(0, len(self.rows) - 1))
            self.selected = next((i for i, row in enumerate(self.rows) if row.message.key == key), fallback)
        else:
            self.selected = min(self.selected, max(0, len(self.rows) - 1))
        self.offset = min(self.offset, max(0, len(self.rows) - 1))

    def reload(self) -> None:
        self.source.reload()
        self.rebuild()
