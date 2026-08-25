# AGENTS.md

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
