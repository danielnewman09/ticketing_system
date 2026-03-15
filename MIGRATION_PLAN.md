# Migration Plan: Django → SQLAlchemy + NiceGUI

## Context

The project started as a Django app but has evolved: the frontend is migrating to NiceGUI, persistence logic has been extracted to a service layer, and data shapes are defined by Pydantic schemas. Django is now overhead — providing auth, admin, template rendering, and middleware that aren't used. This migration removes Django entirely, keeping SQLAlchemy for ORM + Alembic for migrations + NiceGUI for the UI.

## New Project Structure

```
ticketing_system/
  db/
    __init__.py              # init_db(), get_session(), get_codebase_session()
    base.py                  # DeclarativeBase, naming conventions
    models/
      __init__.py            # re-exports all models
      associations.py        # M2M junction tables
      tickets.py             # Ticket, TicketAcceptanceCriteria, TicketFile, TicketReference
      requirements.py        # HighLevelRequirement, LowLevelRequirement, TicketRequirement
      verification.py        # VerificationMethod, VerificationCondition, VerificationAction
      components.py          # Component, Language, BuildSystem, TestFramework, DependencyManager, Dependency
      ontology.py            # OntologyNode, Predicate, OntologyTriple
      codebase.py            # Reflected read-only models (Compound, Member, etc.)
    events.py                # SQLAlchemy event listeners (replaces Django signals)
    vec.py                   # sqlite-vec loading + virtual table setup
  alembic/
    env.py
    versions/
  alembic.ini
  agents/                    # unchanged structure, updated imports
  requirements/
    schemas.py               # unchanged (Pydantic)
    agents/                  # unchanged
    services/
      persistence.py         # updated: session-based instead of Django ORM
  codebase/
    schemas.py               # unchanged (Pydantic)
  search/
    embeddings.py            # updated: use db.get_raw_connection() instead of django.db.connection
  nicegui_app.py             # updated: db.init_db() instead of django.setup()
  demo.py                    # updated
  pyproject.toml             # django → sqlalchemy + alembic
```

### What Gets Deleted
- `config/` (settings.py, urls.py, wsgi.py, asgi.py)
- `manage.py`
- All `views/`, `forms/`, `urls.py`, `admin.py`, `apps.py` files
- All `templates/` and `static/` directories
- All `migrations/` directories
- `ai_assist/` app entirely
- `components/signals.py`, `search/signals.py`, `search/apps.py`
- `codebase/routers.py`

## Existing Table Names (must match exactly to preserve data)

```
components, languages, build_systems, test_frameworks,
dependency_managers, dependencies,
tickets, ticket_acceptance_criteria, ticket_files,
ticket_references, tickets_components, tickets_languages,
high_level_requirements, high_level_requirements_triples,
low_level_requirements, low_level_requirements_components,
low_level_requirements_triples, ticket_requirements,
verification_methods, verification_conditions, verification_actions,
ontology_nodes, ontology_predicates, ontology_triples
```

## Implementation Phases

### Phase 1: Database Layer (`db/`)

**1a. Base + associations** — `db/base.py`, `db/models/associations.py`
- `DeclarativeBase` with SQLAlchemy 2.0 `Mapped[]` annotations
- All 6 M2M junction tables as explicit `Table()` objects using exact Django table names
- Naming convention for constraints (needed by Alembic)

**1b. Models** — one file per domain, matching existing `__tablename__`s
- Port each Django model preserving column names, types, constraints
- Key translations:
  - `CharField(max_length=N)` → `String(N)`
  - `JSONField` → `JSON`
  - `ForeignKey(on_delete=SET_NULL)` → `ForeignKey(...), nullable=True`
  - `ManyToManyField` → `relationship(secondary=junction_table)`
  - `unique_together` → `UniqueConstraint` in `__table_args__`
- Keep `to_prompt_text()` methods on models
- Move constants (`NODE_KINDS`, `VERIFICATION_METHODS`, etc.) into the SQLAlchemy model files

**1c. Codebase models** — `db/models/codebase.py`
- Reflected models from `codebase.sqlite3` using `autoload_with=codebase_engine`
- Never migrated by Alembic

**1d. Session management** — `db/__init__.py`
- Two engines: main (`db.sqlite3`) + codebase (`codebase.sqlite3`)
- `init_db(main_url, codebase_url)` creates engines + session factories
- `get_session() → Session` (context manager pattern)
- `get_codebase_session() → Session`
- sqlite-vec loaded via `@event.listens_for(engine, "connect")`

**1e. Event listeners** — `db/events.py`
- `after_insert`/`after_update` on `Ticket` → update embedding
- `after_insert` on `Language` → create Environment component

**1f. Alembic setup**
- `alembic init alembic`
- Configure `env.py` with `target_metadata = Base.metadata`
- Exclude codebase models via `include_object` filter
- Generate initial migration, then `alembic stamp head` (DB already has the tables)

### Phase 2: Update Consumers

**2a. `requirements/services/persistence.py`**
- Accept `session: Session` parameter on all functions
- `Model.objects.create(...)` → `session.add(Model(...)); session.flush()`
- `Model.objects.get_or_create(...)` → helper `get_or_create(session, Model, ...)`
- `Model.objects.filter(...)` → `session.query(Model).filter(...)`
- `req.triples.add(triple)` → `req.triples.append(triple)`
- `transaction.atomic()` → caller manages `session.commit()`

**2b. `agents/mcp_server.py`**
- Replace `django.setup()` with `db.init_db()`
- Each tool: `with get_session() as session: ...`
- Pass `session` to persistence functions

**2c. `nicegui_app.py`**
- Replace `django.setup()` with `db.init_db()`
- `_fetch_*` functions use `with get_session() as session:`
- Keep `sync_to_async` / `asyncio.to_thread` pattern

**2d. `demo.py`**
- Replace `django.setup()` with `db.init_db()`
- Replace `call_command("flush")` with `Base.metadata.drop_all(); Base.metadata.create_all()`
- Update ORM calls

**2e. Agent imports**
- `requirements/schemas.py` imports `VERIFICATION_METHODS` → update path to `db.models.verification`
- `codebase/schemas.py` imports `NODE_KINDS`, `VISIBILITY_CHOICES` → update path to `db.models.ontology`
- `requirements/agents/decompose_hlr.py` imports `format_hlr_dict` → update path
- `agents/llm_client.py` — no Django imports, unchanged

**2f. `search/embeddings.py`**
- Replace `from django.db import connection` with `from db import get_main_engine`
- `_raw_conn()` → `get_main_engine().raw_connection()`

### Phase 3: Cleanup

- Delete all Django files (listed above)
- Update `pyproject.toml`: remove `django`, `pytest-django`; add `sqlalchemy>=2.0`, `alembic`
- Update `CLAUDE.md` with new setup/run instructions
- Update tests: replace Django test infrastructure with plain pytest + in-memory SQLite

## Utility: `get_or_create` Helper

```python
def get_or_create(session, model, defaults=None, **kwargs):
    instance = session.query(model).filter_by(**kwargs).first()
    if instance:
        return instance, False
    params = {**kwargs, **(defaults or {})}
    instance = model(**params)
    session.add(instance)
    session.flush()
    return instance, True
```

## Verification

1. **Existing data preserved**: After migration, run `python -c "from db import init_db, get_session; init_db(); s = get_session(); print(s.query(HighLevelRequirement).count())"` and verify counts match pre-migration
2. **NiceGUI works**: `python nicegui_app.py` → visit http://127.0.0.1:8081, verify all pages render
3. **MCP server works**: `python -m agents.mcp_server` starts without errors
4. **Demo pipeline**: `python demo.py` runs end-to-end
5. **Tests pass**: `pytest`
6. **Search works**: Create a ticket, verify embedding is generated and search returns results
