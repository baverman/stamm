from __future__ import annotations

import curses
import logging
from collections.abc import Mapping

from .compat import cache

Key = str | int
Bindings = dict[Key, str]
ActionSet = dict[str, tuple[str, ...]]

log = logging.getLogger(__name__)


@cache
def _named_keys() -> dict[str, tuple[Key, ...]]:
    result: dict[str, tuple[Key, ...]] = {}
    for name in dir(curses):
        if not name.startswith('KEY_'):
            continue
        value = getattr(curses, name)
        if isinstance(value, int):
            values = (value,)
            result[name] = values
            result[name[4:]] = values

    page_up = result.get('KEY_PPAGE')
    page_down = result.get('KEY_NPAGE')
    if page_up is not None:
        result['PAGEUP'] = page_up
    if page_down is not None:
        result['PAGEDOWN'] = page_down

    enter = ('\n', '\r') + result.get('KEY_ENTER', ())
    backspace = ('\x08', '\x7f') + result.get('KEY_BACKSPACE', ())
    result['ENTER'] = result['KEY_ENTER'] = enter
    result['BACKSPACE'] = result['KEY_BACKSPACE'] = backspace
    return result


@cache
def parse_key(specification: str, kind: str) -> tuple[Key, ...]:
    if len(specification) == 1:
        return (specification,)
    if len(specification) == 2 and specification[0] == '^':
        character = specification[1]
        if character == '?':
            return ('\x7f',)
        code = ord(character)
        if ord('a') <= code <= ord('z'):
            code -= ord('a') - ord('A')
        if ord('@') <= code <= ord('_'):
            return (chr(code & 0x1F),)
    values = _named_keys().get(specification.upper())
    if values is None:
        log.warning(f'invalid or unavailable key name: {kind}/{specification}')
    return values or ()


def compile_bindings(namespace: str, actions: Mapping[str, tuple[str, ...]], overrides: Mapping[str, str]) -> Bindings:
    configured: Bindings = {}
    removed: set[Key] = set()
    for source_key, action in overrides.items():
        if action and action not in actions:
            continue

        values = parse_key(source_key, 'config')
        if action:
            for key in values:
                configured[key] = action
        else:
            removed.update(values)

    defaults = {
        key: action
        for action, skeys in actions.items()
        for skey in skeys
        for key in parse_key(skey, 'app')
        if key not in removed
    }

    return defaults | configured


def resolve(bindings: Mapping[Key, str], ch: Key) -> str | None:
    return bindings.get(ch)


def read(window: curses.window, bindings: Mapping[Key, str]) -> tuple[str | None, Key]:
    ch = window.get_wch()
    return resolve(bindings, ch), ch
