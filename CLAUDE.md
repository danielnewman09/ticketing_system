# Ticketing System

Ticket management with requirements traceability and semantic search.

## Stack

- **ORM**: SQLAlchemy 2.0 with `Mapped[]` annotations
- **Migrations**: Alembic
- **Frontend**: NiceGUI
- **Search**: sqlite-vec + sentence-transformers
- **AI agents**: llm_caller (multi-backend) + ticketing_agent (domain agents) + MCP server

## Python Environment

- Python 3.12+ (installed via Homebrew on macOS)
- Virtual environment at `.venv/` (git-ignored)
- Dependencies declared in `pyproject.toml`

### Setup

```bash
python -m venv .venv
source .venv/bin/activate
git clone https://github.com/danielnewman09/llm-caller.git ../llm-caller  # if not already cloned
pip install -e ../llm-caller -e ./ticketing_agent -e ".[dev]"
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
python -m ticketing_agent.mcp_server
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
llm_caller/            # Standalone LLM client library (separate package)
  llm_caller/
    backends/          # anthropic.py, openai.py, gemini.py
    tools/             # terminal.py (sandboxed file/command tools)
    client.py          # call_tool, call_text, call_reasoned_tool
    tool_loop.py       # call_tool_loop (multi-turn)
    skill_runner.py    # Generic skill runner
    config.py          # Env var configuration
ticketing_agent/       # Domain-specific agents (separate package)
  ticketing_agent/
    design/            # OO design, ontology, scaffolding, dependencies
    review/            # HLR review, challenge design, conflict detection
    verify/            # Verification procedure generation
    decompose/         # HLR → LLR decomposition
    search/            # Web search for dependency discovery
    mcp_server.py      # MCP server exposing persistence tools
db/                    # SQLAlchemy models, session management, events
  models/              # One file per domain (components, tickets, etc.)
  base.py              # DeclarativeBase
  events.py            # Event listeners (replaces Django signals)
  vec.py               # sqlite-vec virtual table setup
alembic/               # Alembic migration config
requirements/          # Schemas and services for requirements
  schemas.py           # Pydantic schemas
  services/            # Persistence service layer
codebase/              # Pydantic schemas for design pipeline
search/                # Embedding generation and vector search
```
