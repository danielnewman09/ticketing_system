# Ticketing System

Ticket management with requirements traceability and semantic search.

## Stack

- **ORM**: SQLAlchemy 2.0 with `Mapped[]` annotations
- **Migrations**: Alembic
- **Frontend**: NiceGUI
- **Search**: sqlite-vec + sentence-transformers
- **AI agents**: Anthropic API + MCP server

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
python nicegui_app.py
```

Then visit http://127.0.0.1:8081

## MCP Server

```bash
python -m agents.mcp_server
```

## Demo Pipeline

```bash
python demo.py
```

## Tests

```bash
pytest
```

## Database

- Main DB: `db.sqlite3` (SQLAlchemy models in `db/models/`)
- Codebase DB: `codebase.sqlite3` read-only (external, populated by Doxygen)
- Session management: `from db import init_db, get_session`
- Migrations: `alembic upgrade head` / `alembic revision --autogenerate -m "description"`

## Project Structure

```
db/                    # SQLAlchemy models, session management, events
  models/              # One file per domain (components, tickets, etc.)
  base.py              # DeclarativeBase
  events.py            # Event listeners (replaces Django signals)
  vec.py               # sqlite-vec virtual table setup
alembic/               # Alembic migration config
agents/                # AI agents (design, review, verify)
requirements/          # Schemas, services, agents for requirements
  schemas.py           # Pydantic schemas
  services/            # Persistence service layer
  agents/              # Decomposition agent
codebase/              # Pydantic schemas for design pipeline
search/                # Embedding generation and vector search
```
