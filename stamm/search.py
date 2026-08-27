from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import AbstractSet, Mapping

from .index import IndexedMessage

SUPPORTED_FIELDS = frozenset(('from', 'to', 'subject', 'body'))


@dataclass(frozen=True, slots=True)
class SearchTerm:
    field: str
    value: str
    negated: bool = False


@dataclass(frozen=True, slots=True)
class SearchGroup:
    operator: str
    operands: tuple[SearchExpression, ...]


SearchExpression = SearchTerm | SearchGroup


def parse_query(query: str) -> SearchExpression:
    lexer = shlex.shlex(query, posix=True, punctuation_chars='()')
    lexer.whitespace_split = True
    lexer.commenters = ''
    try:
        tokens = list(lexer)
    except ValueError as exc:
        raise ValueError(f'invalid search query: {exc}') from exc
    position = 0

    def parse_term(token: str) -> SearchExpression:
        negated = token.startswith('-')
        expression = token[1:] if negated else token
        field, separator, value = expression.partition(':')
        if not separator:
            if not expression or negated:
                raise ValueError(f'invalid search term: {token}')
            return SearchGroup('or', (SearchTerm('subject', expression), SearchTerm('body', expression)))
        if not field or not value:
            raise ValueError(f'invalid search term: {token}')
        if field not in SUPPORTED_FIELDS:
            raise ValueError(f'unsupported search field: {field}')
        return SearchTerm(field, value, negated)

    def parse_expression() -> SearchExpression:
        nonlocal position
        if position >= len(tokens):
            raise ValueError('invalid search query: missing expression')
        token = tokens[position]
        position += 1
        if token == ')':
            raise ValueError('invalid search query: unexpected )')
        if token != '(':
            return parse_term(token)
        if position >= len(tokens):
            raise ValueError('invalid search query: missing operator')
        operator = tokens[position].casefold()
        position += 1
        if operator not in ('and', 'or'):
            raise ValueError(f'unsupported search operator: {operator}')
        operands = []
        while position < len(tokens) and tokens[position] != ')':
            operands.append(parse_expression())
        if position >= len(tokens):
            raise ValueError('invalid search query: missing )')
        position += 1
        if not operands:
            raise ValueError(f'invalid search query: {operator} requires an operand')
        return SearchGroup(operator, tuple(operands))

    expressions = []
    while position < len(tokens):
        expressions.append(parse_expression())
    return SearchGroup('and', tuple(expressions))


def body_queries(expression: SearchExpression) -> set[str]:
    if isinstance(expression, SearchTerm):
        return {expression.value} if expression.field == 'body' else set()
    return set().union(*(body_queries(operand) for operand in expression.operands))


def matches(
    message: IndexedMessage,
    expression: SearchExpression,
    body_matches: Mapping[str, AbstractSet[str]] | None = None,
) -> bool:
    if isinstance(expression, SearchGroup):
        results = (matches(message, operand, body_matches) for operand in expression.operands)
        return all(results) if expression.operator == 'and' else any(results)
    if expression.field == 'body':
        matched = body_matches is not None and message.key in body_matches.get(expression.value, ())
    else:
        values = {
            'from': message.sender.casefold(),
            'to': message.recipient.casefold(),
            'subject': message.subject.casefold(),
        }
        matched = expression.value.casefold() in values[expression.field]
    return matched is not expression.negated
