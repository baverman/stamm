# Stamm

A fast, mutt-like terminal client for Maildir folders. Stamm requires Python 3.12 or later and uses only the Python standard library at runtime.


## Key bindings

Input bindings use namespaced TOML tables and the `key = action` format. Configured entries override defaults, while an empty action removes a default binding:

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

The namespaces are `index`, `message`, `parts`, `pager`, and `choose`. A key can be one Unicode character, a control character from `^@` through `^_` or `^?`, or any available curses `KEY_*` name with or without the `KEY_` prefix. Named keys are case-insensitive. `PAGEUP` and `PAGEDOWN` are aliases for `PPAGE` and `NPAGE`. `ENTER` and `BACKSPACE` include the terminal-dependent forms of those keys.
