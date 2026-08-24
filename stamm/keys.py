from __future__ import annotations

import curses
from collections.abc import Mapping

Key = str | int
Bindings = dict[Key, str]
ActionSet = dict[str, tuple[str, ...]]


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


def parse_key(specification: str) -> tuple[Key, ...]:
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
        raise ValueError(f'invalid or unavailable key name: {specification}')
    return values


def compile_bindings(
    namespace: str, actions: Mapping[str, tuple[str, ...]], overrides: Mapping[str, str]
) -> tuple[Bindings, list[str]]:
    diagnostics: list[str] = []
    defaults = {specification: action for action, specifications in actions.items() for specification in specifications}
    configured: dict[str, tuple[str, tuple[Key, ...]]] = {}
    seen: dict[Key, str] = {}

    for source_key, action in overrides.items():
        try:
            values = parse_key(source_key)
        except ValueError as exc:
            diagnostics.append(f'keys.{namespace}.{source_key} = {action!r}: {exc}')
            continue
        if action and action not in actions:
            diagnostics.append(f'keys.{namespace}.{source_key} = {action!r}: unknown action')
            continue
        previous = {seen[value] for value in values if value in seen and seen[value] != source_key}
        if previous:
            sources = ', '.join(repr(value) for value in sorted(previous))
            diagnostics.append(f'keys.{namespace}.{source_key} = {action!r}: overlaps configured key {sources}')
        for value in values:
            seen[value] = source_key
        configured[source_key] = (action, values)

    configured_keys = configured.keys()
    merged = [
        (source_key, action, parse_key(source_key))
        for source_key, action in defaults.items()
        if source_key not in configured_keys
    ]
    merged.extend((source_key, action, values) for source_key, (action, values) in configured.items())

    bindings: Bindings = {}
    for _source_key, action, values in merged:
        for value in values:
            if action:
                bindings[value] = action
            else:
                bindings.pop(value, None)

    return bindings, diagnostics


def resolve(bindings: Mapping[Key, str], ch: Key) -> str | None:
    return bindings.get(ch)


def read(window: curses.window, bindings: Mapping[Key, str]) -> tuple[str | None, Key]:
    ch = window.get_wch()
    return resolve(bindings, ch), ch
