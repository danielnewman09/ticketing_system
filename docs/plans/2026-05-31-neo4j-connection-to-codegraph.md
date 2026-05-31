# Neo4j Connection to Codegraph — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the Neo4j driver/connection module from the ticketing system to the shared `codegraph` library, keeping ticketing-specific constraint DDL in the ticketing system.

**Architecture:** `codegraph` gains a `neo4j` subpackage (`connection.py` + `__init__.py`) with the `Neo4jConnection` class and standalone driver functions. Ticketing imports from `codegraph.neo4j` instead of owning the connection module. Generic constraint DDL runs via codegraph's `CONSTRAINTS_AND_INDEXES`; ticketing-specific DDL lives in a new `backend/db/neo4j/constraints.py`.

**Tech Stack:** Python 3.12+, neo4j driver via codegraph (new dep), pydantic.

---

## Task 1: Update codegraph constants and dependencies

**Files:**
- Modify: `src/codegraph/constants.py`
- Modify: `pyproject.toml` (in codegraph repo)

- [ ] **Step 1: Add `namespace_qualified` index to CONSTRAINTS_AND_INDEXES**

In `src/codegraph/constants.py`, add after the `namespace_name` line:

```python
    # (existing line: "CREATE INDEX namespace_name IF NOT EXISTS FOR (n:Namespace) ON (n.name)",)
    "CREATE INDEX namespace_qualified IF NOT EXISTS FOR (n:Namespace) ON (n.qualified_name)",
```

Run: `grep -n "namespace_name" /Users/danielnewman/dev/codegraph/src/codegraph/constants.py` to find the exact line.

- [ ] **Step 2: Add `neo4j` dependency to pyproject.toml**

In `/Users/danielnewman/dev/codegraph/pyproject.toml`, add `"neo4j"` to the `dependencies` list:

```toml
dependencies = [
    "pydantic>=2.0",
    "neo4j",
]
```

- [ ] **Step 3: Commit codegraph changes**

```bash
cd /Users/danielnewman/dev/codegraph
git add src/codegraph/constants.py pyproject.toml
git commit -m "feat: add namespace_qualified index + neo4j dependency for connection module"
```

---

## Task 2: Create codegraph neo4j subpackage

**Files:**
- Create: `src/codegraph/neo4j/__init__.py`
- Create: `src/codegraph/neo4j/connection.py`

- [ ] **Step 1: Create `src/codegraph/neo4j/connection.py`**

This is a copy of the ticketing system's `backend/db/neo4j/connection.py` with:
- `ensure_constraints()`, `ensure_design_constraints()`, `ensure_requirement_constraints()` removed
- A new `ensure_constraints()` added that runs `CONSTRAINTS_AND_INDEXES` from `codegraph.constants`

```python
"""Neo4j driver management — shared connection singleton and standalone driver."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager

from neo4j import GraphDatabase

from codegraph.constants import CONSTRAINTS_AND_INDEXES

log = logging.getLogger(__name__)

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")


class Neo4jConnection:
    """Manages a Neo4j driver singleton with session helpers."""

    def __init__(self) -> None:
        self._uri = NEO4J_URI
        self._user = NEO4J_USER
        self._password = NEO4J_PASSWORD
        self._driver = None
        log.info("Neo4jConnection created (uri=%s, user=%s)", self._uri, self._user)

    def get_driver(self):
        if self._driver is None:
            self._driver = GraphDatabase.driver(self._uri, auth=(self._user, self._password))
            log.info("Neo4j driver created (uri=%s)", self._uri)
        return self._driver

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None
            log.info("Neo4j driver closed")

    @contextmanager
    def session(self, database: str = "neo4j"):
        driver = self.get_driver()
        neo4j_session = driver.session(database=database)
        try:
            yield neo4j_session
        finally:
            neo4j_session.close()

    def verify_connectivity(self) -> bool:
        try:
            self.get_driver().verify_connectivity()
            log.debug("Neo4j connectivity verified")
            return True
        except Exception as e:
            log.warning("Neo4j connection failed: %s", e)
            return False

    def ensure_constraints(self):
        """Create indexes and constraints for the shared codegraph data model."""
        if not self.verify_connectivity():
            log.warning("Neo4j not reachable — skipping constraint setup")
            return False
        with self.session() as session:
            for stmt in CONSTRAINTS_AND_INDEXES:
                try:
                    session.run(stmt)
                except Exception as e:
                    log.debug("Index/constraint may already exist: %s", e)
        log.info("Neo4j constraints and indexes ensured")
        return True


# Standalone driver (not bound to any app framework)
_standalone_driver = None


def get_standalone_driver():
    """Get or create the standalone Neo4j driver singleton."""
    global _standalone_driver
    if _standalone_driver is None:
        _standalone_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        log.info("Standalone Neo4j driver created")
    return _standalone_driver


def close_standalone_driver():
    global _standalone_driver
    if _standalone_driver is not None:
        _standalone_driver.close()
        _standalone_driver = None
        log.info("Standalone Neo4j driver closed")


@contextmanager
def get_standalone_session(database: str = "neo4j"):
    driver = get_standalone_driver()
    session = driver.session(database=database)
    try:
        yield session
    finally:
        session.close()
```

- [ ] **Step 2: Create `src/codegraph/neo4j/__init__.py`**

```python
"""Neo4j driver and connection management."""

from codegraph.neo4j.connection import (
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    Neo4jConnection,
    close_standalone_driver,
    get_standalone_driver,
    get_standalone_session,
)

__all__ = [
    "Neo4jConnection",
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "get_standalone_driver",
    "get_standalone_session",
    "close_standalone_driver",
]
```

- [ ] **Step 3: Commit codegraph neo4j package**

```bash
cd /Users/danielnewman/dev/codegraph
git add src/codegraph/neo4j/
git commit -m "feat: add neo4j connection subpackage"
```

---

## Task 3: Update codegraph __init__.py exports

**Files:**
- Modify: `src/codegraph/__init__.py`

- [ ] **Step 1: Add neo4j exports to codegraph __init__.py**

After the existing `from codegraph.graph import ...` block, add:

```python
from codegraph.neo4j import (
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    Neo4jConnection,
    close_standalone_driver,
    get_standalone_driver,
    get_standalone_session,
)
```

In the `__all__` list, add these names. The exact insertion point is before the closing `]` of `__all__`:

```python
    "Neo4jConnection",
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "get_standalone_driver",
    "get_standalone_session",
    "close_standalone_driver",
```

- [ ] **Step 2: Install codegraph with new deps and run tests**

```bash
cd /Users/danielnewman/dev/codegraph
source .venv/bin/activate
pip install -e .
pytest -v
```

Expected: all existing tests pass.

- [ ] **Step 3: Commit**

```bash
cd /Users/danielnewman/dev/codegraph
git add src/codegraph/__init__.py
git commit -m "feat: add neo4j connection exports to codegraph public API"
```

---

## Task 4: Create ticketing constraints module

**Files:**
- Create: `backend/db/neo4j/constraints.py`

- [ ] **Step 1: Create `backend/db/neo4j/constraints.py`**

Consolidates `ensure_design_constraints()` + `ensure_requirement_constraints()` plus the ticketing-specific indexes from `ensure_constraints()` into one function. Takes a `Neo4jConnection` instance since it's no longer a method on the class.

```python
"""Ticketing-system-specific Neo4j constraint and index DDL."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codegraph.neo4j import Neo4jConnection

log = logging.getLogger(__name__)


def ensure_ticketing_constraints(conn: Neo4jConnection) -> bool:
    """Create ticketing-specific constraints and indexes.

    Covers HLR, LLR, VerificationMethod, Condition, Action labels plus
    ticketing-only Compound indexes (component_id, implementation_status).
    Also handles Phase 2 migration cleanup (dropping sqlite_id constraints).
    """
    if not conn.verify_connectivity():
        log.warning("Neo4j not reachable — skipping ticketing constraint setup")
        return False

    with conn.session() as session:
        # Unique constraints
        for stmt in [
            "CREATE CONSTRAINT hlr_id IF NOT EXISTS FOR (n:HLR) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT llr_id IF NOT EXISTS FOR (n:LLR) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT verification_method_id IF NOT EXISTS FOR (n:VerificationMethod) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT condition_id IF NOT EXISTS FOR (n:Condition) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT action_id IF NOT EXISTS FOR (n:Action) REQUIRE n.id IS UNIQUE",
        ]:
            try:
                session.run(stmt)
            except Exception as e:
                log.debug("Constraint may already exist: %s", e)

        # Ticketing-specific indexes
        for stmt in [
            "CREATE INDEX compound_component_id IF NOT EXISTS FOR (n:Compound) ON (n.component_id)",
            "CREATE INDEX compound_implementation_status IF NOT EXISTS FOR (n:Compound) ON (n.implementation_status)",
        ]:
            try:
                session.run(stmt)
            except Exception as e:
                log.debug("Index may already exist: %s", e)

        # Phase 2 migration cleanup
        for old_constraint in ["hlr_sqlite_id", "llr_sqlite_id"]:
            try:
                session.run(f"DROP CONSTRAINT {old_constraint} IF EXISTS")
            except Exception:
                log.debug("Constraint %s did not exist, skipping drop", old_constraint)

        # Remove sqlite_id properties
        for label in ["HLR", "LLR"]:
            try:
                session.run(f"MATCH (n:{label}) REMOVE n.sqlite_id")
            except Exception:
                log.debug("No %s nodes with sqlite_id to remove", label)

    log.info("Ticketing-specific Neo4j constraints and indexes ensured")
    return True
```

- [ ] **Step 2: Commit**

```bash
cd /Users/danielnewman/dev/ticketing_system
git add backend/db/neo4j/constraints.py
git commit -m "feat: extract ticketing-specific Neo4j constraint DDL into constraints.py"
```

---

## Task 5: Update backend/db/neo4j/__init__.py imports

**Files:**
- Modify: `backend/db/neo4j/__init__.py`

- [ ] **Step 1: Update imports in __init__.py**

Change the import from `backend.db.neo4j.connection` to `codegraph.neo4j`. Also add the new `ensure_ticketing_constraints` export.

Old:
```python
from backend.db.neo4j.connection import (
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    Neo4jConnection,
    close_standalone_driver,
    get_standalone_driver,
    get_standalone_session,
)
```

New:
```python
from codegraph.neo4j import (
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    Neo4jConnection,
    close_standalone_driver,
    get_standalone_driver,
    get_standalone_session,
)
```

Add to the `__all__` list:
```python
    "ensure_ticketing_constraints",
```

And add the import for it:
```python
from backend.db.neo4j.constraints import ensure_ticketing_constraints
```

- [ ] **Step 2: Commit**

```bash
cd /Users/danielnewman/dev/ticketing_system
git add backend/db/neo4j/__init__.py
git commit -m "refactor: import Neo4j connection from codegraph library"
```

---

## Task 6: Update all consumer import paths

**Files (22 import sites across 17 files, grouped by import type):**

### Group A: `from backend.db.neo4j.connection import Neo4jConnection`
→ `from codegraph.neo4j import Neo4jConnection`

| # | File | Line |
|---|------|------|
| 1 | `nicegui_app.py` | 45 |
| 2 | `backend/ticketing_agent/mcp_server.py` | 191 |
| 3 | `scripts/02_setup_project.py` | 28 |
| 4 | `scripts/05a_build_and_index.py` | 45 |
| 5 | `scripts/05_benchmark_calculator.py` | 22 |
| 6 | `scripts/05_generate_skeleton.py` | 43 |
| 7 | `scripts/migrate_design_labels.py` | 29 |

### Group B: `    from backend.db.neo4j.connection import Neo4jConnection` (indented, inside function)
→ `    from codegraph.neo4j import Neo4jConnection`

| # | File | Line |
|---|------|------|
| 8 | `frontend/data/hlr.py` | 119 |
| 9 | `scripts/01_flush_db.py` | 29 |
| 10 | `scripts/import_fixtures.py` | 123 |
| 11 | `scripts/export_fixtures.py` | 142 |
| 12 | `services/dependencies.py` | 19 |

### Group C: Multiple indented imports in one file

| # | File | Line | Old import |
|---|------|------|-----------|
| 13 | `services/dependencies.py` | 49 | `        from backend.db.neo4j.connection import Neo4jConnection` |
| 14 | `services/dependencies.py` | 79 | `        from backend.db.neo4j.connection import Neo4jConnection` |

### Group D: `        from backend.db.neo4j.connection import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD`
→ `        from codegraph.neo4j import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD`

| # | File | Line |
|---|------|------|
| 15 | `backend/ticketing_agent/mcp_server.py` | 280 |

### Group E: `    from backend.db.neo4j.connection import get_standalone_driver` (indented)
→ `    from codegraph.neo4j import get_standalone_driver`

| # | File | Line |
|---|------|------|
| 16 | `tests/test_verification_repository.py` | 18 |
| 17 | `tests/test_graph_tags.py` | 15 |
| 18 | `tests/test_requirement_repository.py` | 18 |
| 19 | `tests/integration/test_design_repository_graph.py` | 21 |
| 20 | `tests/test_persistence.py` | 20 |
| 21 | `tests/test_design_data_repository.py` | 18 |

- [ ] **Step 1: Update Group A (top-level imports, Neo4jConnection)**

For each file, change:
```
from backend.db.neo4j.connection import Neo4jConnection
```
to:
```
from codegraph.neo4j import Neo4jConnection
```

Files: `nicegui_app.py:45`, `backend/ticketing_agent/mcp_server.py:191`, `scripts/02_setup_project.py:28`, `scripts/05a_build_and_index.py:45`, `scripts/05_benchmark_calculator.py:22`, `scripts/05_generate_skeleton.py:43`, `scripts/migrate_design_labels.py:29`

- [ ] **Step 2: Update Group B (indented imports, Neo4jConnection)**

For each file, change:
```
    from backend.db.neo4j.connection import Neo4jConnection
```
to:
```
    from codegraph.neo4j import Neo4jConnection
```

Files: `frontend/data/hlr.py:119`, `scripts/01_flush_db.py:29`, `scripts/import_fixtures.py:123`, `scripts/export_fixtures.py:142`, `services/dependencies.py:19`

- [ ] **Step 3: Update Group C (services/dependencies.py additional imports)**

In `services/dependencies.py`, also change line 49 and line 79:
```
        from backend.db.neo4j.connection import Neo4jConnection
```
to:
```
        from codegraph.neo4j import Neo4jConnection
```

- [ ] **Step 4: Update Group D (MCP server NEO4J constants)**

In `backend/ticketing_agent/mcp_server.py`, change line 280:
```
        from backend.db.neo4j.connection import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
```
to:
```
        from codegraph.neo4j import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
```

- [ ] **Step 5: Update Group E (test files, get_standalone_driver)**

For each file, change:
```
    from backend.db.neo4j.connection import get_standalone_driver
```
to:
```
    from codegraph.neo4j import get_standalone_driver
```

Files: `tests/test_verification_repository.py:18`, `tests/test_graph_tags.py:15`, `tests/test_requirement_repository.py:18`, `tests/integration/test_design_repository_graph.py:21`, `tests/test_persistence.py:20`, `tests/test_design_data_repository.py:18`

- [ ] **Step 6: Commit import path changes**

```bash
cd /Users/danielnewman/dev/ticketing_system
git add .
git commit -m "refactor: update all Neo4j connection imports to use codegraph.neo4j"
```

---

## Task 7: Update constraint callers

**Files:**
- Modify: `backend/ticketing_agent/mcp_server.py` (~line 193)
- Modify: `frontend/data/hlr.py` (~line 121)
- Modify: `scripts/02_setup_project.py` (~lines 93-94)
- Modify: `scripts/05_benchmark_calculator.py` (~lines 41-42)
- Modify: `scripts/migrate_design_labels.py` (~lines 70-71)

- [ ] **Step 1: Update callers that use `ensure_requirement_constraints()`**

Each of these files calls `.ensure_requirement_constraints()` on a connection instance. Change to the standalone function call.

For **`frontend/data/hlr.py`** (around line 121-122):
```python
    from backend.db.neo4j.connection import Neo4jConnection
    neo4j_conn = Neo4jConnection()
    neo4j_conn.ensure_requirement_constraints()
```
→ becomes:
```python
    from codegraph.neo4j import Neo4jConnection
    from backend.db.neo4j.constraints import ensure_ticketing_constraints
    neo4j_conn = Neo4jConnection()
    ensure_ticketing_constraints(neo4j_conn)
```

For **`backend/ticketing_agent/mcp_server.py`** (around line 191-193):
```python
    from backend.db.neo4j.connection import Neo4jConnection
    neo4j_conn = Neo4jConnection()
    neo4j_conn.ensure_requirement_constraints()
```
→ becomes:
```python
    from codegraph.neo4j import Neo4jConnection
    from backend.db.neo4j.constraints import ensure_ticketing_constraints
    neo4j_conn = Neo4jConnection()
    ensure_ticketing_constraints(neo4j_conn)
```

For **`scripts/02_setup_project.py`** (around lines 93-94):
```python
    neo4j_conn.ensure_constraints()
    neo4j_conn.ensure_requirement_constraints()
```
→ becomes:
```python
    neo4j_conn.ensure_constraints()
    ensure_ticketing_constraints(neo4j_conn)
```
Add import at top: `from backend.db.neo4j.constraints import ensure_ticketing_constraints`

For **`scripts/05_benchmark_calculator.py`** (around lines 41-42):
```python
    neo4j_conn.ensure_constraints()
    neo4j_conn.ensure_requirement_constraints()
```
→ becomes:
```python
    neo4j_conn.ensure_constraints()
    ensure_ticketing_constraints(neo4j_conn)
```
Add import at top: `from backend.db.neo4j.constraints import ensure_ticketing_constraints`

- [ ] **Step 2: Update caller that uses `ensure_design_constraints()`**

For **`scripts/migrate_design_labels.py`** (around lines 70-71):
```python
    conn.ensure_constraints()
    conn.ensure_design_constraints()
```
→ becomes:
```python
    conn.ensure_constraints()
    ensure_ticketing_constraints(conn)
```
Add import at top: `from backend.db.neo4j.constraints import ensure_ticketing_constraints`

- [ ] **Step 3: Commit constraint caller changes**

```bash
cd /Users/danielnewman/dev/ticketing_system
git add .
git commit -m "refactor: use standalone ensure_ticketing_constraints() instead of connection methods"
```

---

## Task 8: Convert connection.py to re-export shim

**Files:**
- Modify: `backend/db/neo4j/connection.py`

- [ ] **Step 1: Replace connection.py contents with re-export shim**

Replace the entire file with:

```python
"""Re-export shim — imports actual connection from codegraph library."""
from codegraph.neo4j.connection import *  # noqa: F401, F403
```

- [ ] **Step 2: Commit**

```bash
cd /Users/danielnewman/dev/ticketing_system
git add backend/db/neo4j/connection.py
git commit -m "refactor: replace connection.py with re-export shim to codegraph.neo4j"
```

---

## Task 9: Run full test suite

- [ ] **Step 1: Run ticketing system tests**

```bash
cd /Users/danielnewman/dev/ticketing_system
source .venv/bin/activate
pytest -v
```

Expected: All tests pass. Import paths all resolve correctly.

- [ ] **Step 2: Run codegraph tests**

```bash
cd /Users/danielnewman/dev/codegraph
source .venv/bin/activate
pytest -v
```

Expected: All existing tests pass (constants changes are backward-compatible).

- [ ] **Step 3: Verify tests pass, report results**
