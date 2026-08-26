import pytest

from stamm.tui.text import fit_text, span, wrap_spans, wrap_text


def test_fit_text_splits_at_terminal_width() -> None:
    assert fit_text('ab界cd', 4) == ('ab界', 'cd', 4)


@pytest.mark.parametrize(
    ('text', 'width', 'expected'),
    [
        ('abcdefgh', 3, ['abc', 'def', 'gh']),
        ('one\n\ntwo', 10, ['one', '', 'two']),
        ('界界a', 3, ['界', '界a']),
    ],
)
def test_wrap_text(text: str, width: int, expected: list[str]) -> None:
    assert wrap_text(text, width) == expected


def test_wrap_spans_preserves_attributes_across_rows() -> None:
    spans = [span('From:', 1), span(' Alice')]

    assert wrap_spans([spans], 7) == [
        [span('From:', 1), span(' A')],
        [span('lice')],
    ]
