from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:

    def cache[T, **P](fn: Callable[P, T]) -> Callable[P, T]: ...
else:
    from functools import cache as cache
