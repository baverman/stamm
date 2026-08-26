from __future__ import annotations

import curses
from datetime import datetime
from pathlib import Path

import pytest

from stamm import ui
from stamm.config import config
from stamm.theme import IndexTheme, MessageTheme, Theme
from stamm.ui import format_index_date, format_sender, viewport_start
from stamm.views import UIContext
from stamm.views.choose import ChooseView


def test_recent_date_uses_time() -> None:
    timestamp = datetime(2026, 4, 5, 14, 30).astimezone().timestamp()
    assert format_index_date(timestamp, timestamp + 60) == 'Apr 05 14:30'


def test_old_date_uses_year() -> None:
    timestamp = datetime(2024, 4, 5, 14, 30).astimezone().timestamp()
    value = format_index_date(timestamp, timestamp + 366 * 24 * 60 * 60)
    assert value == '2024 Apr 05 '


@pytest.mark.parametrize(
    ('sender', 'expected'),
    [
        ('Anton Bobrov <anton@example.com>', 'Anton Bobrov'),
        ('anton@example.com', 'anton@example.com'),
    ],
)
def test_format_sender(sender: str, expected: str) -> None:
    assert format_sender(sender) == expected


def test_cursor_does_not_scroll_in_middle_seventy_percent() -> None:
    assert viewport_start(26, 100, 20, 20) == 20
    assert viewport_start(33, 100, 20, 20) == 20


def test_cursor_scrolls_inside_top_and_bottom_margins() -> None:
    assert viewport_start(25, 100, 20, 20) == 19
    assert viewport_start(34, 100, 20, 20) == 21


def test_margin_is_capped_at_ten_rows() -> None:
    assert viewport_start(39, 200, 100, 50) == 29
    assert viewport_start(140, 200, 100, 50) == 51


def test_viewport_is_clamped_at_list_edges() -> None:
    assert viewport_start(0, 100, 20, 20) == 0
    assert viewport_start(2, 5, 20, 4) == 0


def test_final_message_keeps_the_bottom_scroll_margin() -> None:
    assert viewport_start(99, 100, 20, 0) == 86
    assert viewport_start(199, 200, 100, 0) == 110


class _ChoiceWindow:
    def __init__(self, key: str | int):
        self.key = key

    def get_wch(self) -> str | int:
        return self.key


@pytest.mark.parametrize(
    ('key', 'expected'),
    [
        ('\n', 'send'),
        ('\r', 'send'),
        (curses.KEY_ENTER, 'send'),
        ('\x1b', None),
        ('e', 'edit'),
    ],
)
def test_choose_maps_generic_and_explicit_keys(
    key: str | int, expected: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ui, 'status', lambda *_args: None)
    monkeypatch.setitem(vars(config), 'keys', {})
    theme = Theme(0, 0, 0, 0, IndexTheme(0, 0, 0, 0), MessageTheme(0))
    context = UIContext(_ChoiceWindow(key), theme)  # type: ignore[arg-type]

    assert (
        ChooseView(
            'Compose',
            {'s': 'send', 'e': 'edit', 'd': 'draft', 'x': 'discard'},
            primary='send',
        ).run(context)
        == expected
    )


def test_path_completions_include_matching_directories_and_files(tmp_path: Path) -> None:
    directory = tmp_path / 'mailbox'
    directory.mkdir()
    file = tmp_path / 'mail.txt'
    file.write_text('', encoding='utf-8')
    (tmp_path / 'other').mkdir()

    assert ui._path_completions(str(tmp_path / 'mail')) == [str(file), str(directory) + '/']


class _PromptWindow:
    def __init__(self, keys: list[str | int]):
        self.keys = iter(keys)

    def getmaxyx(self) -> tuple[int, int]:
        return 12, 80

    def addnstr(self, *_args: object) -> None:
        pass

    def move(self, *_args: object) -> None:
        pass

    def refresh(self) -> None:
        pass

    def get_wch(self) -> str | int:
        return next(self.keys)


def test_prompt_edits_at_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curses, 'curs_set', lambda _visibility: 0)
    window = _PromptWindow([curses.KEY_LEFT, 'b', '\n'])

    assert ui.prompt(window, '> ', 'ac', status_attr=0) == 'abc'  # type: ignore[arg-type]


def test_prompt_navigates_completion_choices(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curses, 'curs_set', lambda _visibility: 0)
    window = _PromptWindow(['\t', curses.KEY_DOWN, '\n'])

    value = ui.prompt(
        window,  # type: ignore[arg-type]
        '> ',
        completer=lambda _value, _cursor: [ui.Completion('first'), ui.Completion('second')],
        status_attr=0,
    )

    assert value == 'second'


def test_prompt_completes_common_prefix_and_supports_j_navigation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curses, 'curs_set', lambda _visibility: 0)
    completed_values: list[str] = []

    def complete(value: str, _cursor: int) -> list[ui.Completion]:
        completed_values.append(value)
        return [ui.Completion('alpha'), ui.Completion('alpine')]

    window = _PromptWindow(['\t', 'j', '\n'])

    assert ui.prompt(window, '> ', completer=complete, status_attr=0) == 'alpine'  # type: ignore[arg-type]
    assert completed_values == ['', 'alp']


def test_repeated_tab_selects_next_without_applying_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curses, 'curs_set', lambda _visibility: 0)
    choices = [ui.Completion('draft'), ui.Completion('drafts')]
    window = _PromptWindow(['\t', '\t', '\n'])

    assert ui.prompt(window, '> ', completer=lambda _value, _cursor: choices, status_attr=0) == 'drafts'  # type: ignore[arg-type]


def test_prompt_accepts_numeric_tab_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curses, 'curs_set', lambda _visibility: 0)
    window = _PromptWindow(['s', 'e', 9, '\n'])

    def complete(value: str, _cursor: int) -> list[ui.Completion]:
        return [] if ' ' in value else [ui.Completion('search ', accept=False)]

    assert ui.prompt(window, ':', completer=complete, status_attr=0) == 'search '  # type: ignore[arg-type]


def test_prompt_page_navigation_scrolls_completion_menu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curses, 'curs_set', lambda _visibility: 0)
    window = _PromptWindow(['\t', curses.KEY_NPAGE, '\n'])
    choices = [ui.Completion(str(index)) for index in range(12)]

    assert ui.prompt(window, '> ', completer=lambda _value, _cursor: choices, status_attr=0) == '8'  # type: ignore[arg-type]


def test_prompt_navigates_history(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curses, 'curs_set', lambda _visibility: 0)
    history = ['first', 'second']
    window = _PromptWindow([curses.KEY_UP, '\n'])

    assert ui.prompt(window, '> ', history=history, status_attr=0) == 'second'  # type: ignore[arg-type]


def test_maildir_completer_only_returns_directories(tmp_path: Path) -> None:
    maildir = tmp_path / 'Inbox'
    (maildir / 'cur').mkdir(parents=True)
    (maildir / 'new').mkdir()
    (tmp_path / 'Invoice').mkdir()
    (tmp_path / 'index').write_text('', encoding='utf-8')

    choices = ui.maildir_completer(str(tmp_path / 'In'), len(str(tmp_path / 'In')))

    assert [choice.value for choice in choices] == [str(maildir) + '/', str(tmp_path / 'Invoice') + '/']
    assert choices[0].label == 'Inbox/ [Maildir]'
    assert choices[0].accept
    assert not choices[1].accept


def test_prompt_completes_one_maildir_without_entering_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curses, 'curs_set', lambda _visibility: 0)
    maildir = tmp_path / 'Inbox'
    (maildir / 'cur').mkdir(parents=True)
    (maildir / 'new').mkdir()
    initial = str(tmp_path / 'In')
    window = _PromptWindow(['\t', '\n'])

    assert (
        ui.prompt(
            window,  # type: ignore[arg-type]
            'Maildir: ',
            initial,
            complete_paths=True,
            completer=ui.maildir_completer,
            status_attr=0,
        )
        == str(maildir) + '/'
    )
