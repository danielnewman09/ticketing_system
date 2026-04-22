# Decouple Frontend from Agentic Layer

**Date:** 2026-04-18  
**Project:** ticketing_system  
**Status:** Draft

---

## Goal

Separate the NiceGUI frontend from the backend agentic logic to enable independent testing, deployment, and iteration.

## Current State

The frontend (`frontend/pages/`) directly imports and calls:
- **5 agent functions**: `decompose_hlr`, `design_single_hlr`, `integrate_dependency`, `scaffold_project`, `research_dependencies`
- **ORM models**: `HighLevelRequirement`, `LowLevelRequirement`, `OntologyNode`, etc.
- **Session management**: `get_session()` called from `frontend/data/*.py`
- **Neo4j queries**: `fetch_graph`, `fetch_node_detail`, `fetch_neighbourhood_graph`

Zero frontend tests exist.

## Proposed Approach

### Step 1: Define a Service Layer API

Create `backend/services/` with a clean Python API that the frontend calls instead of reaching into `backend.db` and `backend.ticketing_agent` directly:

| Service | Methods |
|---------|---------|
| `RequirementsService` | `list_hlrs()`, `get_hlr()`, `create_hlr()`, `decompose_hlr()`, `design_hlr()` |
| `OntologyService` | `list_nodes()`, `get_graph()`, `get_node_detail()` |
| `DependencyService` | `list_dependencies()`, `research()`, `accept_recommendation()` |
| `ProjectService` | `get_meta()`, `scaffold()`, `integrate_dependency()` |

### Step 2: Move Data Modules

Migrate `frontend/data/*.py` logic into the service layer. Frontend pages only import from `backend.services`.

### Step 3: Add Integration Tests

With the service layer as the seam, write pytest tests against services without needing NiceGUI.

### Step 4: (Optional) REST API

If we want the frontend to be a separate process later, the service layer becomes the basis for a FastAPI REST endpoint.

## Files to Change

| File | Change |
|------|--------|
| `backend/services/__init__.py` | **New** — Service layer |
| `backend/services/requirements.py` | **New** — HLR/LLR service |
| `backend/services/ontology.py` | **New** — Ontology service |
| `backend/services/dependencies.py` | **New** — Dependency service |
| `frontend/pages/requirements.py` | Update imports to use services |
| `frontend/pages/hlr_detail.py` | Update imports |
| `frontend/pages/project/route.py` | Update imports |
| `frontend/data/*.py` | Deprecate, move logic to services |
| `tests/test_services.py` | **New** — Service layer tests |

## Risks

- NiceGUI's reactive model may make it hard to fully abstract data fetching
- Neo4j query patterns are tightly coupled to graph visualization in the frontend
- The MCP server already duplicates some of this logic — need to decide if services should be shared

## Open Questions

1. Should the service layer async or sync? (NiceGUI supports both)
2. Do we share the service layer with the MCP server, or keep them separate?
3. How do we handle the Neo4j dual-write pattern?