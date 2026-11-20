# AGENTS.md

## Python Environment

- Use the repository's `.venv` for all Python commands and package management.
- In PowerShell, activate it with `\.venv\Scripts\Activate.ps1` before running Python or pip commands.
- Install packages with `python -m pip install <package>` after activation; do not install into the global Python environment.

## Lint Check After Commit

After every commit, run the following lint check on modified Python files:

```bash
ruff check blueprints/python_strategy.py gunicorn.conf.py
```

If ruff reports errors, fix them before pushing. For auto-fixable issues, use:

```bash
ruff check --fix blueprints/python_strategy.py gunicorn.conf.py
```

## Project-Specific Rules

- All Python code must pass `ruff check` before committing
- Do not introduce new bare `except:` clauses (E722)
- Do not leave unused variables (F841)
- Match existing code style in the file you're editing
