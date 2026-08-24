# Repository Instructions

## Implementation

- Keep changes small and direct. Follow the style of the surrounding code.
- Stamm requires Python 3.12 or later and must use only the Python standard library at runtime.
- Do not add dependencies without explicit approval.
- Do not add speculative abstractions, compatibility layers, or unrelated refactors.
- Reuse existing helpers and conventions before introducing new ones.
- Fix the reported behavior, not a simplified approximation of it.

## Code comments

- Do not add comments or docstrings that only restate the code.
- Comments could be added if they contain important information not obvious from code.
- If unsure ask if it's ok to add a particular comment.

## Tests

- Do not add shallow tests with excessive monkeypatching.

## Verification

Before reporting completion, run:

```sh
make lint
pytest -q
```
