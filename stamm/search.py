from __future__ import annotations

import shlex
from dataclasses import dataclass

from .index import IndexedMessage

SUPPORTED_FIELDS = frozenset(('from', 'to', 'subject'))


@dataclass(frozen=True, slots=True)
class SearchTerm:
    field: str
    value: str
    negated: bool = False


def parse_query(query: str) -> list[SearchTerm]:
    try:
        tokens = shlex.split(query)
    except ValueError as exc:
        raise ValueError(f'invalid search query: {exc}') from exc

    terms: list[SearchTerm] = []
    for token in tokens:
        negated = token.startswith('-')
        expression = token[1:] if negated else token
        field, separator, value = expression.partition(':')
        if not separator or not field or not value:
            raise ValueError(f'invalid search term: {token}')
        if field not in SUPPORTED_FIELDS:
            raise ValueError(f'unsupported search field: {field}')
        terms.append(SearchTerm(field, value, negated))
    return terms


def matches(message: IndexedMessage, terms: list[SearchTerm]) -> bool:
    values = {
        'from': message.sender.casefold(),
        'to': message.recipient.casefold(),
        'subject': message.subject.casefold(),
    }
    return all((term.value.casefold() in values[term.field]) is not term.negated for term in terms)
