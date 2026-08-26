from __future__ import annotations

import curses
from pathlib import Path

import pytest

from stamm.theme import Theme
from stamm.tui import prompt
from stamm.views import UIContext

from .fakes import Window


def test_path_completer_includes_matching_directories_and_files(tmp_path: Path) -> None:
    directory = tmp_path / 'mailbox'
    directory.mkdir()
    file = tmp_path / 'mail.txt'
    file.write_text('', encoding='utf-8')
    (tmp_path / 'other').mkdir()

    choices = prompt.path_completer(str(tmp_path / 'mail'), len(str(tmp_path / 'mail')))

    assert [item.value for item in choices] == [str(file), str(directory) + '/']


def test_prompt_edits_at_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curses, 'curs_set', lambda _visibility: 0)
    context = UIContext(Window(keys=[curses.KEY_LEFT, 'b', '\n']).as_curses(), Theme())

    assert prompt.PromptView('> ', 'ac').run(context) == 'abc'


def test_prompt_navigates_completion_choices(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curses, 'curs_set', lambda _visibility: 0)
    context = UIContext(Window(keys=['\t', curses.KEY_DOWN, '\n']).as_curses(), Theme())

    value = prompt.PromptView(
        '> ',
        completer=lambda _value, _cursor: [prompt.Completion('first'), prompt.Completion('second')],
    ).run(context)

    assert value == 'second'


def test_prompt_completes_common_prefix_and_supports_j_navigation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curses, 'curs_set', lambda _visibility: 0)
    completed_values: list[str] = []

    def complete(value: str, _cursor: int) -> list[prompt.Completion]:
        completed_values.append(value)
        return [prompt.Completion('alpha'), prompt.Completion('alpine')]

    context = UIContext(Window(keys=['\t', 'j', '\n']).as_curses(), Theme())

    assert prompt.PromptView('> ', completer=complete).run(context) == 'alpine'
    assert completed_values == ['', 'alp']


def test_tab_applies_single_visible_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curses, 'curs_set', lambda _visibility: 0)

    def complete(value: str, _cursor: int) -> list[prompt.Completion]:
        return [prompt.Completion(item) for item in ('alpha', 'alpine') if item.startswith(value)]

    context = UIContext(Window(keys=['\t', 'h', '\t', '!', '\n']).as_curses(), Theme())

    assert prompt.PromptView('> ', completer=complete).run(context) == 'alpha!'


def test_repeated_tab_selects_next_without_applying_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curses, 'curs_set', lambda _visibility: 0)
    choices = [prompt.Completion('draft'), prompt.Completion('drafts')]
    context = UIContext(Window(keys=['\t', '\t', '\n']).as_curses(), Theme())

    assert prompt.PromptView('> ', completer=lambda _value, _cursor: choices).run(context) == 'drafts'


def test_prompt_accepts_numeric_tab_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curses, 'curs_set', lambda _visibility: 0)
    context = UIContext(Window(keys=['s', 'e', 9, '\n']).as_curses(), Theme())

    def complete(value: str, _cursor: int) -> list[prompt.Completion]:
        return [] if ' ' in value else [prompt.Completion('search ', accept=False)]

    assert prompt.PromptView(':', completer=complete).run(context) == 'search '


def test_prompt_page_navigation_scrolls_completion_menu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curses, 'curs_set', lambda _visibility: 0)
    context = UIContext(Window(keys=['\t', curses.KEY_NPAGE, '\n']).as_curses(), Theme())
    choices = [prompt.Completion(str(index)) for index in range(12)]

    assert prompt.PromptView('> ', completer=lambda _value, _cursor: choices).run(context) == '8'


def test_prompt_navigates_history(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curses, 'curs_set', lambda _visibility: 0)
    history = ['first', 'second']
    context = UIContext(Window(keys=[curses.KEY_UP, '\n']).as_curses(), Theme())

    assert prompt.PromptView('> ', history=history).run(context) == 'second'
