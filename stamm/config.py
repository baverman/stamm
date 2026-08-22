"""Configuration loading and path resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from email.utils import getaddresses
import fnmatch
import os
from pathlib import Path
import tomllib
from typing import Any


class ConfigError(ValueError):
    """An invalid Stamm configuration."""


@dataclass(frozen=True)
class MimeRule:
    type: str
    display: str | None = None
    open: str | None = None

    def matches(self, content_type: str) -> bool:
        return fnmatch.fnmatchcase(content_type.lower(), self.type.lower())


@dataclass(frozen=True)
class Config:
    root: Path
    spool: Path
    sent: Path
    drafts: Path
    trash: Path
    editor: str
    sendmail: str
    identities: tuple[str, ...]
    auto_view: tuple[str, ...] = ()
    alternative_order: tuple[str, ...] = ("text/plain", "text/html")
    signatures: dict[str, Path] = field(default_factory=dict)
    mime: tuple[MimeRule, ...] = ()

    @property
    def identity_addresses(self) -> tuple[str, ...]:
        return tuple(address.lower() for _, address in getaddresses(self.identities) if address)


def expand_path(value: str, base: Path | None = None) -> Path:
    path = Path(os.path.expandvars(os.path.expanduser(value)))
    return path if path.is_absolute() or base is None else base / path


def config_candidates() -> list[Path]:
    paths = [Path.cwd() / "stamm.toml"]
    if xdg := os.environ.get("XDG_CONFIG_HOME"):
        paths.append(Path(xdg) / "stamm.toml")
    paths.append(Path.home() / ".config" / "stamm.toml")
    return paths


def _strings(data: dict[str, Any], key: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    value = data.get(key, list(default))
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{key} must be an array of strings")
    return tuple(value)


def load_config(path: Path | None = None) -> Config:
    """Load the first available configuration file, or *path*."""
    if path is None:
        path = next((item for item in config_candidates() if item.is_file()), None)
    if path is None:
        raise ConfigError("no configuration file found")
    try:
        with path.open("rb") as stream:
            data = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot load {path}: {exc}") from exc

    root_value = data.get("root")
    if not isinstance(root_value, str):
        raise ConfigError("root must be a path string")
    root = expand_path(root_value)
    if not root.is_absolute():
        raise ConfigError("root must resolve to an absolute path")

    def required_path(key: str) -> Path:
        value = data.get(key)
        if not isinstance(value, str) or not value:
            raise ConfigError(f"{key} must be a path string")
        return expand_path(value, root)

    identities = _strings(data, "identities")
    if not identities or not getaddresses(identities) or any(not addr for _, addr in getaddresses(identities)):
        raise ConfigError("identities must contain at least one valid address")
    editor = data.get("editor", os.environ.get("EDITOR", ""))
    sendmail = data.get("sendmail")
    if not isinstance(editor, str) or not editor:
        raise ConfigError("editor is not configured and EDITOR is empty")
    if not isinstance(sendmail, str) or not sendmail:
        raise ConfigError("sendmail must be a command string")

    raw_signatures = data.get("signatures", {})
    if not isinstance(raw_signatures, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in raw_signatures.items()):
        raise ConfigError("signatures must map addresses to paths")
    signatures = {key.lower(): expand_path(value, root) for key, value in raw_signatures.items()}

    raw_mime = data.get("mime", [])
    if not isinstance(raw_mime, list):
        raise ConfigError("mime must be an array of tables")
    rules: list[MimeRule] = []
    for item in raw_mime:
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            raise ConfigError("each MIME rule needs a type")
        display, opener = item.get("display"), item.get("open")
        if display is not None and not isinstance(display, str) or opener is not None and not isinstance(opener, str):
            raise ConfigError("MIME commands must be strings")
        rules.append(MimeRule(item["type"], display, opener))

    return Config(
        root=root,
        spool=required_path("spool"),
        sent=required_path("sent"),
        drafts=required_path("drafts"),
        trash=required_path("trash"),
        editor=editor,
        sendmail=sendmail,
        identities=identities,
        auto_view=_strings(data, "auto_view"),
        alternative_order=_strings(data, "alternative_order", ("text/plain", "text/html")),
        signatures=signatures,
        mime=tuple(rules),
    )
