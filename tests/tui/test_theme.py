from dataclasses import dataclass
from typing import cast

from stamm.tui.theme import FallbackInfo, Style, ThemeNode


@dataclass(frozen=True)
class _SectionTheme:
    value: int = 0


@dataclass(frozen=True)
class _Theme:
    normal: int = 0
    section: _SectionTheme = _SectionTheme()


@dataclass(frozen=True)
class _SectionColors:
    value: Style | None = Style(fg='green')


@dataclass(frozen=True)
class _Colors:
    normal: Style | None = Style(bg='black')
    section: _SectionColors = _SectionColors()


def test_theme_node_caches_nested_nodes_and_resolved_styles() -> None:
    resolved: list[Style] = []
    info = FallbackInfo(_Theme, 'normal')
    theme = cast(_Theme, ThemeNode('', _Colors(), info, lambda style: resolved.append(style) or 42))

    assert theme.section is theme.section
    assert theme.section.value == 42
    assert resolved == [Style(fg='green', bg='black')]
