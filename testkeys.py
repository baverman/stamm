#!/usr/bin/env python3
"""Display the curses representation of each pressed key."""

import curses


def main(screen: curses.window) -> None:
    screen.keypad(True)
    screen.scrollok(True)

    while True:
        ch = screen.getch()
        keyname = curses.keyname(ch)
        try:
            unctrl = curses.unctrl(ch)
        except (OverflowError, ValueError):
            unctrl = b'<not a character>'
        screen.addstr(f'ch={ch} keyname={keyname!r} unctrl={unctrl!r}\n')
        screen.refresh()


if __name__ == '__main__':
    curses.wrapper(main)
