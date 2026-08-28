# Stamm

A fast, mutt-like terminal client for Maildir folders. Stamm requires Python 3.13 or later and uses only the Python standard library at runtime.


## Index format

```toml
[index]
format = "{date:12} {flags:4} {sender:20}  {subject:*}"
```

Available fields are `date`, `flags`, `sender`, and `subject`. A numeric width is fixed; `*` uses the remaining width. Fields can be reordered or omitted.

Thread branches use Unicode line-drawing characters by default. They can be replaced, including with ASCII or empty strings:

```toml
[index.thread]
vertical = "| "
branch = "+-"
last = "`-"
indent = "  "
```


## Key bindings

Input bindings use namespaced TOML tables and the `key = action` format. Configured entries override defaults, while an empty action removes a default binding:

Press `?` in a top-level view to show its active key bindings and actions. The key uses the configurable `help` action.

```toml
[keys.index]
j = "down"
DOWN = "down"
"^N" = "down"
q = ""

[keys.pager]
PAGEUP = "pageup"
PAGEDOWN = "pagedown"
```

The namespaces are `index`, `message`, `parts`, `pager`, and `choice`. A key can be one Unicode character, a control character from `^@` through `^_` or `^?`, or any available curses `KEY_*` name with or without the `KEY_` prefix. Named keys are case-insensitive. `PAGEUP` and `PAGEDOWN` are aliases for `PPAGE` and `NPAGE`. `ENTER` and `BACKSPACE` include the terminal-dependent forms of those keys.
