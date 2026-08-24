"""Configuration loading and path resolution."""

from __future__ import annotations

import os
import tomllib
from dataclasses import replace
from pathlib import Path

from .config_model import Config, MimeRule
from .schema import parse

__all__ = ['Config', 'ConfigError', 'MimeRule', 'config', 'load_config', 'set_config']

config: Config = object.__new__(Config)


def set_config(value: Config) -> None:
    vars(config).clear()
    vars(config).update(vars(value))


class ConfigError(ValueError):
    """An invalid Stamm configuration."""


def expand_path(value: Path, base: Path | None = None) -> Path:
    path = Path(os.path.expandvars(os.path.expanduser(value)))
    return path if path.is_absolute() or base is None else base / path


def config_candidates() -> list[Path]:
    paths = [Path.cwd() / 'stamm.toml']
    if xdg := os.environ.get('XDG_CONFIG_HOME'):
        paths.append(Path(xdg) / 'stamm.toml')
    paths.append(Path.home() / '.config' / 'stamm.toml')
    return paths


def load_config(path: Path | None = None) -> Config:
    """Load the first available configuration file, or *path*."""
    if path is None:
        path = next((item for item in config_candidates() if item.is_file()), None)
    if path is None:
        raise ConfigError('no configuration file found')
    try:
        with path.open('rb') as stream:
            data = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f'cannot load {path}: {exc}') from exc

    if 'editor' not in data:
        data['editor'] = os.environ.get('EDITOR', '')
    try:
        config = parse(Config, data)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc

    root = expand_path(config.root)
    if not root.is_absolute():
        raise ConfigError('root must resolve to an absolute path')
    return replace(
        config,
        root=root,
        spool=expand_path(config.spool, root),
        sent=expand_path(config.sent, root),
        drafts=expand_path(config.drafts, root),
        trash=expand_path(config.trash, root),
        signatures={address.lower(): expand_path(value, root) for address, value in config.signatures.items()},
    )
