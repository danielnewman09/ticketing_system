# Ticketing System

Django-based ticket management with requirements traceability and semantic search.

## Python Environment

- Python 3.12+ (installed via Homebrew on macOS)
- Virtual environment at `.venv/` (git-ignored)
- Dependencies declared in `pyproject.toml`

### Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Adding dependencies

Add to `pyproject.toml` under `[project] dependencies` (or `[project.optional-dependencies] dev` for dev-only), then reinstall:

```bash
pip install -e ".[dev]"
```

## Running

```bash
source .venv/bin/activate
python manage.py runserver
```

## Tests

```bash
pytest
```

Settings module: `config.settings` (configured in `pyproject.toml`).
