# Stage 1: Neo4j Infrastructure Setup

This guide sets up Neo4j as the graph database backend for codebase data (replacing `codebase.sqlite3`).

---

## 1. Docker Compose

Create `docker-compose.yml` in the project root:

```yaml
services:
  neo4j:
    image: neo4j:5-community
    ports:
      - "7474:7474"   # Browser UI
      - "7687:7687"   # Bolt protocol
    environment:
      NEO4J_AUTH: neo4j/msd-local-dev
      NEO4J_PLUGINS: '[]'
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
    restart: unless-stopped

volumes:
  neo4j_data:
  neo4j_logs:
```

Start it:

```bash
docker compose up -d
```

Verify at http://localhost:7474 (login: `neo4j` / `msd-local-dev`).

---

## 2. Python Dependency

Add `neo4j` to `pyproject.toml` dependencies:

```toml
dependencies = [
    # ... existing deps ...
    "neo4j>=5.0",
]
```

Then reinstall:

```bash
pip install -e ".[dev]"
```

---

## 3. Connection Module

Create `db/neo4j.py`:

```python
"""Neo4j connection management for codebase graph data."""

import os
from contextlib import contextmanager

from neo4j import GraphDatabase

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "msd-local-dev")

_driver = None


def get_driver():
    """Get or create the Neo4j driver singleton."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver


def close_driver():
    """Close the Neo4j driver."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


@contextmanager
def get_neo4j_session(database="neo4j"):
    """Context manager for Neo4j sessions."""
    driver = get_driver()
    session = driver.session(database=database)
    try:
        yield session
    finally:
        session.close()


def verify_connection():
    """Verify Neo4j is reachable. Returns True on success."""
    try:
        driver = get_driver()
        driver.verify_connectivity()
        return True
    except Exception as e:
        print(f"Neo4j connection failed: {e}")
        return False
```

---

## 4. Verification

After completing steps 1-3:

```bash
# Start Neo4j
docker compose up -d

# Verify from Python
python -c "from db.neo4j import verify_connection; print('OK' if verify_connection() else 'FAILED')"
```

---

## What's Next

Once this infrastructure is in place, Stage 2 (in the MSD-CPP repo) will create `scripts/doxygen_to_neo4j.py` to ingest Doxygen XML directly into this Neo4j instance.
