from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IndexTheme:
    column_date: int
    column_flags: int
    column_from: int
    column_subject: int


@dataclass(frozen=True, slots=True)
class CursesTheme:
    normal: int
    header: int
    status: int
    indicator: int
    index: IndexTheme
