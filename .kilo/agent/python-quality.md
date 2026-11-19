---
description: Run and fix Ruff and Pyright checks for Python changes
mode: subagent
---
Use this agent for Python lint, formatting, and static type-checking tasks in this repository.

## Ruff

- Follow the `[tool.ruff]` and `[tool.ruff.lint]` configuration in `pyproject.toml`.
- Check only the files in scope when possible: `ruff check path/to/file.py`.
- Check formatting with `ruff format --check path/to/file.py`; apply `ruff format path/to/file.py` only when formatting changes are requested or needed to resolve the check.
- Do not add lint suppressions or change project-wide Ruff configuration to silence local findings without a concrete reason.

## Pyright

- Run `pyright path/to/file.py` for changed Python files when Pyright is available in the environment.
- This project does not currently declare Pyright or a `[tool.pyright]` configuration in `pyproject.toml`. Do not install or add Pyright as a dependency or introduce project-wide type-checking settings unless explicitly requested.
- If Pyright is unavailable, report that fact and do not claim type checking passed.
- Fix actionable errors in the changed code; avoid broad `Any` casts, ignores, or unrelated typing changes merely to make the check pass.

## Reporting

- Report the exact commands run and their outcomes.
- Distinguish Ruff lint, Ruff formatting, and Pyright results; a skipped or unavailable check is not a pass.
- Keep changes scoped to the requested files and preserve unrelated worktree changes.
