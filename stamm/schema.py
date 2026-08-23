from dataclasses import _MISSING_TYPE, MISSING, fields, is_dataclass
from dataclasses import field as dc_field
from functools import partial
from typing import Any, Callable, Generic, TypedDict, TypeVar

T = TypeVar('T')

Typ = type[T] | Callable[[Any], T]
Factory = type[T] | Callable[[], T]


class Meta(TypedDict, Generic[T]):
    typ: Callable[[Any], T]
    src: str | None
    required: bool


def norm_typ(typ: Typ[T]) -> Callable[[Any], T]:
    if is_dataclass(typ):
        return partial(parse, typ)  # type: ignore[return-value]
    return typ


def field(
    typ: Typ[T],
    default: T | _MISSING_TYPE = MISSING,
    *,
    src: str | None = None,
    required: bool = True,
    default_factory: Factory[T] | _MISSING_TYPE = MISSING,
) -> T:
    meta: Meta[T] = {'typ': norm_typ(typ), 'src': src, 'required': required}
    return dc_field(metadata=meta, default=default, default_factory=default_factory)  # type: ignore[no-any-return,call-overload]


def optfield(
    typ: Typ[T],
    default: T | None = None,
    *,
    src: str | None = None,
    default_factory: Factory[T] | _MISSING_TYPE = MISSING,
) -> T | None:
    if default_factory is not MISSING:
        default = MISSING  # type: ignore[assignment]
    return field(typ, default, src=src, required=False, default_factory=default_factory)


def as_list(typ: Typ[T]) -> Callable[[Any], list[T]]:
    ltyp = norm_typ(typ)

    def inner(data: list[Any]) -> list[T]:
        return [ltyp(it) for it in data]

    return inner


def as_kv(typ: Typ[T]) -> Callable[[Any], dict[str, T]]:
    ltyp = norm_typ(typ)

    def inner(data: dict[str, Any]) -> dict[str, T]:
        return {k: ltyp(v) for k, v in data.items()}

    return inner


class ValidationError(ValueError):
    def __init__(self, path: str, msg: str) -> None:
        super().__init__(f'{path}: {msg}')
        self.path = path
        self.msg = msg


def add_error_path(name: str, error: Exception) -> ValidationError:
    if isinstance(error, ValidationError):
        return ValidationError(f'{name}.{error.path}', error.msg)
    return ValidationError(name, str(error))


def parse(cls: type[T], data: dict[str, object]) -> T:
    result: dict[str, object] = {}
    used = set()
    for f in fields(cls):  # type: ignore[arg-type]
        m: Meta[T] = f.metadata  # type: ignore[assignment]

        v = data.get(src := m['src'] or f.name)
        if v is None:
            if m['required']:
                raise ValidationError(src, 'required field')
        else:
            try:
                v = m['typ'](v)
            except Exception as e:
                raise add_error_path(src, e)
            result[f.name] = v

        used.add(src)

    unknown = data.keys() - used
    if unknown:
        raise ValueError(f'Unknown field: {unknown}')

    return cls(**result)
