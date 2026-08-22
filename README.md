# Stamm

A fast, mutt-like terminal client for Maildir folders. Stamm requires Python 3.12 or later and uses only the Python standard library at runtime.

## Install

Install the project in editable mode:

```sh
python3 -m pip install -e .
```

Development tools must provide `pytest`, `ruff`, and `mypy`.

## Run

Open the configured spool Maildir:

```sh
stamm
```

Open a specified Maildir:

```sh
stamm /path/to/maildir
```

Run without installing the command:

```sh
python3 -m stamm [/path/to/maildir]
```

Stamm loads the first configuration file found at:

1. `$XDG_CONFIG_HOME/stamm.toml`
2. `~/.config/stamm.toml`


## Development commands

Use the Makefile commands so tools use the project configuration:

```sh
make fmt    # Format code and fix import order
make lint   # Run Ruff and mypy
pytest      # Run test suite
```
