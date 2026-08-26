from __future__ import annotations

import time
from datetime import datetime
from email.utils import parseaddr

from .theme import Theme as Theme

MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')


def format_index_date(timestamp: float, now: float | None = None) -> str:
    current = time.time() if now is None else now
    value = datetime.fromtimestamp(timestamp).astimezone()
    month = MONTHS[value.month - 1]
    if current - timestamp >= 365 * 24 * 60 * 60:
        return f'{value.year:04d} {month} {value.day:02d} '
    return f'{month} {value.day:02d} {value.hour:02d}:{value.minute:02d}'


def format_sender(value: str) -> str:
    name, address = parseaddr(value.replace('\n', ' '))
    return name or address or value.replace('\n', ' ')


def viewport_start(selected: int, total: int, visible: int, current: int) -> int:
    if total <= visible:
        return 0
    margin = min(10, int(visible * 0.3), max(0, (visible - 1) // 2))
    # Permit trailing blank rows so the final message can stay above the
    # bottom scroll margin instead of being forced onto the last screen row.
    maximum = total - visible + margin
    start = min(max(0, current), maximum)
    if selected < start + margin:
        start = selected - margin
    elif selected >= start + visible - margin:
        start = selected - visible + margin + 1
    return min(max(0, start), maximum)
