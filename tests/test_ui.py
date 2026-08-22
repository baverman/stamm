from __future__ import annotations

import unittest
from datetime import datetime

from stamm.ui import format_index_date, format_sender, viewport_start, wrap_text


class IndexDateTests(unittest.TestCase):
    def test_recent_date_uses_time(self) -> None:
        timestamp = datetime(2026, 4, 5, 14, 30).astimezone().timestamp()
        self.assertEqual(format_index_date(timestamp, timestamp + 60), 'Apr 05 14:30')

    def test_old_date_uses_year(self) -> None:
        timestamp = datetime(2024, 4, 5, 14, 30).astimezone().timestamp()
        value = format_index_date(timestamp, timestamp + 366 * 24 * 60 * 60)
        self.assertEqual(value, '2024 Apr 05 ')
        self.assertEqual(len(value), 12)


class SenderFormatTests(unittest.TestCase):
    def test_name_hides_email_address(self) -> None:
        self.assertEqual(format_sender('Anton Bobrov <anton@example.com>'), 'Anton Bobrov')

    def test_address_is_used_when_name_is_missing(self) -> None:
        self.assertEqual(format_sender('anton@example.com'), 'anton@example.com')


class TextWrapTests(unittest.TestCase):
    def test_long_lines_wrap_at_screen_width(self) -> None:
        self.assertEqual(wrap_text('abcdefgh', 3), ['abc', 'def', 'gh'])

    def test_blank_lines_are_preserved(self) -> None:
        self.assertEqual(wrap_text('one\n\ntwo', 10), ['one', '', 'two'])

    def test_wide_characters_use_two_terminal_cells(self) -> None:
        self.assertEqual(wrap_text('界界a', 3), ['界', '界a'])


class ViewportTests(unittest.TestCase):
    def test_cursor_does_not_scroll_in_middle_seventy_percent(self) -> None:
        self.assertEqual(viewport_start(26, 100, 20, 20), 20)
        self.assertEqual(viewport_start(33, 100, 20, 20), 20)

    def test_cursor_scrolls_inside_top_and_bottom_margins(self) -> None:
        self.assertEqual(viewport_start(25, 100, 20, 20), 19)
        self.assertEqual(viewport_start(34, 100, 20, 20), 21)

    def test_margin_is_capped_at_ten_rows(self) -> None:
        self.assertEqual(viewport_start(39, 200, 100, 50), 29)
        self.assertEqual(viewport_start(140, 200, 100, 50), 51)

    def test_viewport_is_clamped_at_list_edges(self) -> None:
        self.assertEqual(viewport_start(0, 100, 20, 20), 0)
        self.assertEqual(viewport_start(2, 5, 20, 4), 0)

    def test_final_message_keeps_the_bottom_scroll_margin(self) -> None:
        # Twenty visible rows produce a six-row margin.
        self.assertEqual(viewport_start(99, 100, 20, 0), 86)
        # The margin is capped at ten on large screens.
        self.assertEqual(viewport_start(199, 200, 100, 0), 110)


if __name__ == '__main__':
    unittest.main()
