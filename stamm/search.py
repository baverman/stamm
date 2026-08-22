"""Parse and evaluate message index search queries."""

from __future__ import annotations

import shlex
from dataclasses import dataclass

from .index import IndexedMessage

SUPPORTED_FIELDS = frozenset(('from', 'subject'))


@dataclass(frozen=True, slots=True)
class SearchTerm:
    field: str
    value: str


def parse_query(query: str) -> list[SearchTerm]:
    """Parse whitespace-separated ``field:value`` search terms."""
    try:
        tokens = shlex.split(query)
    except ValueError as exc:
        raise ValueError(f'invalid search query: {exc}') from exc

    terms: list[SearchTerm] = []
    for token in tokens:
        field, separator, value = token.partition(':')
        if not separator or not field or not value:
            raise ValueError(f'invalid search term: {token}')
        if field not in SUPPORTED_FIELDS:
            raise ValueError(f'unsupported search field: {field}')
        terms.append(SearchTerm(field, value))
    return terms


def matches(message: IndexedMessage, terms: list[SearchTerm]) -> bool:
    """Return whether all terms occur in their message fields."""
    values = {'from': message.sender.casefold(), 'subject': message.subject.casefold()}
    return all(term.value.casefold() in values[term.field] for term in terms)
