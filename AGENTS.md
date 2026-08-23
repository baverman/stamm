# Repository Instructions

## Implementation

- Keep changes small and direct. Follow the style of the surrounding code.
- Stamm requires Python 3.12 or later and must use only the Python standard library at runtime.
- Do not add dependencies without explicit approval.
- Do not add speculative abstractions, compatibility layers, or unrelated refactors.
- Do not add comments or docstrings that only restate the code. Add a comment only when it explains a necessary, non-obvious constraint.
- Reuse existing helpers and conventions before introducing new ones.
- Fix the reported behavior, not a simplified approximation of it.

## Tests

- Do not add shallow tests with excessive monkeypatching.

## Verification

Before reporting completion, run:

```sh
make lint
pytest -q
```
