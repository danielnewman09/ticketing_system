# Implementation Plan: Migrate frontend to frontend_migrated/

**GitHub Issue:** #4
**Scope:** Create `frontend_migrated/` mirroring `frontend/` structure — working UI modules ported as-is, data layer and pages stubbed with full TypedDict return types. No `backend/` imports anywhere.

---

## Step 1: Create `frontend_migrated/__init__.py`

**What:** Package root init.

```python
"""Migrated frontend package — working UI modules + typed stubs for data/pages.

No imports from backend/. Data functions raise NotImplementedError until
reimplemented against the migrated backend.
"""
```

**Verification:** `python -c "import frontend_migrated"` succeeds.

---

## Step 2: Copy `frontend/theme.py` → `frontend_migrated/theme.py`

**What:** Copy verbatim. No `frontend.` imports to change — theme.py only imports from `nicegui` and stdlib.

**Verification:** `python -c "from frontend_migrated.theme import COLORS, apply_theme; print('OK')"` succeeds.

---

## Step 3: Copy `frontend/widgets.py` → `frontend_migrated/widgets.py`

**What:** Copy verbatim, then change `from frontend.theme import ...` to `from frontend_migrated.theme import ...`.

**Verification:** `python -c "from frontend_migrated.widgets import GraphState, GraphConfig; print('OK')"` succeeds.

---

## Step 4: Copy `frontend/layout.py` → `frontend_migrated/layout.py`

**What:** Copy verbatim, then change `from frontend.agent_log import agent_log` → `from frontend_migrated.agent_log import agent_log` and `from frontend.theme import BACKGROUNDS` → `from frontend_migrated.theme import BACKGROUNDS`.

**Verification:** `python -c "from frontend_migrated.layout import page_layout, stat_card; print('OK')"` succeeds.

---

## Step 5: Copy `frontend/agent_log.py` → `frontend_migrated/agent_log.py`

**What:** Copy verbatim. No `frontend.` imports — only depends on `llm_caller`, stdlib, and `nicegui` (not imported in this file). The only local reference is `_TRACE_DIR = Path(__file__).resolve().parent.parent / "logs"` which resolves correctly from either location.

**Verification:** `python -c "from frontend_migrated.agent_log import agent_log, install_hooks; print('OK')"` succeeds.

---

## Step 6: Create `frontend_migrated/graph/__init__.py`

**What:** Copy `frontend/graph/__init__.py`, change `from frontend.graph.format` → `from frontend_migrated.graph.format`.

```python
"""Frontend graph formatting — re-export layer_graph_to_cytoscape and filter helpers."""

from frontend_migrated.graph.format import (
    layer_graph_to_cytoscape,
    _filter_by_kind,
    _filter_by_search,
    _filter_by_component,
)

__all__ = [
    "layer_graph_to_cytoscape",
    "_filter_by_kind",
    "_filter_by_search",
    "_filter_by_component",
]
```

**Verification:** `python -c "from frontend_migrated.graph import layer_graph_to_cytoscape; print('OK')"` succeeds (may need codegraph installed).

---

## Step 7: Copy `frontend/graph/labels.py` → `frontend_migrated/graph/labels.py`

**What:** Copy verbatim. No `frontend.` imports — stdlib only module.

**Verification:** `python -c "from frontend_migrated.graph.labels import _build_uml_label; print('OK')"` succeeds.

---

## Step 8: Copy `frontend/graph/format.py` → `frontend_migrated/graph/format.py`

**What:** Copy verbatim, then change `from frontend.graph.labels import ...` → `from frontend_migrated.graph.labels import ...`. The `from codegraph.graph import ...` import stays as-is (not a `backend/` import).

**Verification:** `python -c "from frontend_migrated.graph.format import layer_graph_to_cytoscape; print('OK')"` succeeds.

---

## Step 9: Create `frontend_migrated/data/__init__.py`

**What:** Stub package init that re-exports all data functions (matching the original `frontend/data/__init__.py`). Each import will pull from the corresponding stub module.

```python
"""Data-fetching stubs for UI pages. Run in threads via asyncio.to_thread.

All functions raise NotImplementedError until reimplemented against the
migrated backend. Return types are documented via TypedDicts in each module.
"""

from frontend_migrated.data.components import (
    add_dependency,
    create_dependency_manager,
    delete_dependency,
    delete_dependency_manager,
    ensure_component_language,
    fetch_component_detail,
    fetch_components_data,
    fetch_components_options,
    update_dependency_index_config,
)
from frontend_migrated.data.dependencies import (
    accept_recommendation,
    add_manual_recommendation,
    fetch_design_dependency_links_data,
    fetch_pending_recommendations_summary,
    fetch_recommendations,
    reject_use_stdlib,
    save_recommendations,
    update_recommendation_status,
)
from frontend_migrated.data.hlr import (
    create_hlr,
    decompose_hlr,
    delete_hlr,
    design_single_hlr,
    fetch_hlr_detail,
    fetch_requirements_data,
    update_hlr,
)
from frontend_migrated.data.llr import (
    create_llr,
    delete_llr,
    fetch_llr_detail,
    update_llr,
)
from frontend_migrated.data.ontology import (
    fetch_graph_node_detail,
    fetch_hlr_graph_data,
    fetch_node_detail_full,
    fetch_ontology_data,
    fetch_ontology_graph_data,
    resolve_node_id_by_qualified_name,
    update_member_type,
)
from frontend_migrated.data.project import (
    fetch_environment_data,
    fetch_project_meta,
    update_project_meta,
)

__all__ = [
    # project
    "fetch_project_meta",
    "update_project_meta",
    "fetch_environment_data",
    # hlr
    "fetch_requirements_data",
    "fetch_hlr_detail",
    "create_hlr",
    "update_hlr",
    "delete_hlr",
    "decompose_hlr",
    "design_single_hlr",
    # llr
    "fetch_llr_detail",
    "create_llr",
    "update_llr",
    "delete_llr",
    # components
    "fetch_components_data",
    "fetch_component_detail",
    "fetch_components_options",
    "ensure_component_language",
    "create_dependency_manager",
    "add_dependency",
    "update_dependency_index_config",
    "delete_dependency",
    "delete_dependency_manager",
    # ontology
    "fetch_ontology_data",
    "fetch_ontology_graph_data",
    "fetch_hlr_graph_data",
    "fetch_graph_node_detail",
    "fetch_node_detail_full",
    "resolve_node_id_by_qualified_name",
    "update_member_type",
    # dependencies
    "fetch_design_dependency_links_data",
    "fetch_recommendations",
    "save_recommendations",
    "update_recommendation_status",
    "accept_recommendation",
    "add_manual_recommendation",
    "reject_use_stdlib",
    "fetch_pending_recommendations_summary",
]
```

**Verification:** Cannot import yet (stub modules don't exist). Will verify after stub modules are created.

---

## Step 10: Create `frontend_migrated/data/project.py` — stubs

**What:** 3 functions, 3 TypedDicts. Simplest data module — good first stub.

```python
"""Project metadata and environment data — stubs.

Return types are documented via TypedDicts. All functions raise
NotImplementedError until reimplemented against the migrated backend.
"""

from __future__ import annotations

from typing import TypedDict


class ProjectMeta(TypedDict):
    name: str
    description: str
    working_directory: str


class EnvironmentDependency(TypedDict):
    id: int
    name: str
    version: str
    github_url: str
    manager: str
    is_dev: bool
    index_file_patterns: str
    index_subdir: str
    index_exclude_patterns: str
    index_recursive: bool
    components: list[dict]  # {id: int, name: str}


class LanguageEnvironment(TypedDict):
    id: int
    name: str
    version: str
    build_systems: list[BuildSystemRow]       # defined in components.py
    test_frameworks: list[TestFrameworkRow]   # defined in components.py
    dependency_managers: list[str]
    dependencies: list[EnvironmentDependency]


# Forward-declared type references — these are defined in components.py.
# Imported at runtime to avoid circular imports.
class BuildSystemRow(TypedDict):
    name: str
    config_file: str | None
    version: str | None


class TestFrameworkRow(TypedDict):
    name: str
    config_file: str | None
    discovery_path: str | None


def fetch_project_meta() -> ProjectMeta:
    """Fetch project metadata (single row), creating defaults if missing."""
    raise NotImplementedError("fetch_project_meta — requires backend_migrated data layer")


def update_project_meta(name: str, description: str, working_directory: str) -> bool:
    """Update project metadata. Returns True on success."""
    raise NotImplementedError("update_project_meta — requires backend_migrated data layer")


def fetch_environment_data() -> list[LanguageEnvironment]:
    """Fetch languages with their build systems, test frameworks, and dependencies."""
    raise NotImplementedError("fetch_environment_data — requires backend_migrated data layer")
```

**Verification:** `python -c "from frontend_migrated.data.project import ProjectMeta, fetch_project_meta; print('OK')"` succeeds.

---

## Step 11: Create `frontend_migrated/data/components.py` — stubs

**What:** 9 functions, 8 TypedDicts. All `backend.db` references become stubs.

```python
"""Component CRUD, detail, options, and environment CRUD — stubs.

Return types are documented via TypedDicts. All functions raise
NotImplementedError until reimplemented against the migrated backend.
No imports from backend/ anywhere in this module.
"""

from __future__ import annotations

from typing import TypedDict


class ComponentRow(TypedDict):
    id: int
    name: str
    namespace: str
    language: str | None
    parent: str | None
    hlr_count: int
    node_count: int


class ComponentChild(TypedDict):
    id: int
    name: str
    namespace: str | None
    hlr_count: int
    node_count: int


class BuildSystemRow(TypedDict):
    name: str
    config_file: str | None
    version: str | None


class TestFrameworkRow(TypedDict):
    name: str
    config_file: str | None
    discovery_path: str | None


class DependencyInManager(TypedDict):
    id: int
    name: str
    version: str
    is_dev: bool


class DependencyManagerRow(TypedDict):
    id: int
    name: str
    manifest_file: str
    lock_file: str
    dependencies: list[DependencyInManager]


class ComponentEnvironment(TypedDict):
    language_id: int
    language: str
    build_systems: list[BuildSystemRow]
    test_frameworks: list[TestFrameworkRow]
    dependency_managers: list[DependencyManagerRow]


class ComponentDetail(TypedDict):
    id: int
    name: str
    description: str
    namespace: str
    parent: dict | None  # {id: int, name: str}
    children: list[ComponentChild]
    environment: ComponentEnvironment | None
    hlrs: list[dict]  # {id, description, llr_count}
    dependencies: list[dict]  # {id, name, version, is_dev}
    default_manager_id: int | None
    node_kinds: dict[str, int]
    nodes_sample: list[dict]
    node_count: int


class ComponentOption(TypedDict):
    id: int
    name: str


def fetch_components_data() -> list[ComponentRow]:
    """Fetch all data needed for the components page."""
    raise NotImplementedError("fetch_components_data — requires backend_migrated data layer")


def fetch_component_detail(component_id: int) -> ComponentDetail | None:
    """Fetch full component detail including children, environment, requirements, and nodes."""
    raise NotImplementedError("fetch_component_detail — requires backend_migrated data layer")


def fetch_components_options() -> list[ComponentOption]:
    """Return list of {id, name} for component dropdowns."""
    raise NotImplementedError("fetch_components_options — requires backend_migrated data layer")


def ensure_component_language(component_id: int, language_name: str, version: str = "") -> int:
    """Ensure a component has a language set, creating it if needed. Returns language id."""
    raise NotImplementedError("ensure_component_language — requires backend_migrated data layer")


def create_dependency_manager(
    language_id: int,
    name: str,
    manifest_file: str,
    lock_file: str = "",
) -> int:
    """Create a dependency manager. Returns the new id."""
    raise NotImplementedError("create_dependency_manager — requires backend_migrated data layer")


def add_dependency(
    manager_id: int,
    name: str,
    version: str = "",
    is_dev: bool = False,
    component_id: int | None = None,
) -> int:
    """Add a dependency to a manager. Returns the new id."""
    raise NotImplementedError("add_dependency — requires backend_migrated data layer")


def update_dependency_index_config(
    dep_id: int,
    file_patterns: str,
    subdir: str,
    exclude_patterns: str,
    recursive: bool,
) -> bool:
    """Update the Doxygen indexing config for a dependency."""
    raise NotImplementedError("update_dependency_index_config — requires backend_migrated data layer")


def delete_dependency(dep_id: int) -> bool:
    """Delete a dependency. Returns True on success."""
    raise NotImplementedError("delete_dependency — requires backend_migrated data layer")


def delete_dependency_manager(manager_id: int) -> bool:
    """Delete a dependency manager and its dependencies. Returns True on success."""
    raise NotImplementedError("delete_dependency_manager — requires backend_migrated data layer")
```

**Verification:** `python -c "from frontend_migrated.data.components import ComponentDetail, fetch_components_data; print('OK')"` succeeds.

---

## Step 12: Create `frontend_migrated/data/dependencies.py` — stubs

**What:** 8 functions, 3 TypedDicts (`DependencyRecommendation`, `PendingRecommendationSummary`, `ComponentDependency`). Plus `fetch_design_dependency_links_data` returning `dict` (Cytoscape format — nodes/edges).

```python
"""Dependency recommendations and dependency graph data — stubs.

Return types are documented via TypedDicts. All functions raise
NotImplementedError until reimplemented against the migrated backend.
No imports from backend/ anywhere in this module.
"""

from __future__ import annotations

from typing import TypedDict


class DependencyRecommendation(TypedDict):
    id: int
    name: str
    github_url: str
    description: str
    version: str
    stars: int
    license: str
    last_updated: str
    pros: list[str]
    cons: list[str]
    relevant_hlrs: list[str]
    relevant_structures: list[str]
    summary: str
    status: str


class PendingRecommendationSummary(TypedDict):
    component_id: int
    component_name: str
    pending_count: int


class ComponentDependency(TypedDict):
    id: int
    name: str
    version: str
    is_dev: bool


def fetch_design_dependency_links_data(design_qnames: list[str]) -> dict:
    """Fetch cross-layer links between Design nodes and dependency Compounds.

    Returns Cytoscape-format dict with 'nodes' and 'edges' keys.
    """
    raise NotImplementedError("fetch_design_dependency_links_data — requires backend_migrated data layer")


def fetch_recommendations(component_id: int) -> list[DependencyRecommendation]:
    """Fetch all dependency recommendations for a component."""
    raise NotImplementedError("fetch_recommendations — requires backend_migrated data layer")


def save_recommendations(component_id: int, summary: str, recommendations: list[dict]) -> None:
    """Save research results as pending recommendations, replacing all previous ones."""
    raise NotImplementedError("save_recommendations — requires backend_migrated data layer")


def update_recommendation_status(rec_id: int, status: str) -> bool:
    """Update a recommendation's status (accepted/rejected). Returns True on success."""
    raise NotImplementedError("update_recommendation_status — requires backend_migrated data layer")


def accept_recommendation(rec_id: int) -> bool:
    """Accept a recommendation: mark as accepted and add to dependency manager."""
    raise NotImplementedError("accept_recommendation — requires backend_migrated data layer")


def add_manual_recommendation(component_id: int, rec: dict) -> int:
    """Add a manually researched dependency recommendation. Returns the new record ID."""
    raise NotImplementedError("add_manual_recommendation — requires backend_migrated data layer")


def reject_use_stdlib(rec_id: int) -> bool:
    """Reject a recommendation with a note that stdlib will be used instead."""
    raise NotImplementedError("reject_use_stdlib — requires backend_migrated data layer")


def fetch_pending_recommendations_summary() -> list[PendingRecommendationSummary]:
    """Fetch components that have pending dependency recommendations."""
    raise NotImplementedError("fetch_pending_recommendations_summary — requires backend_migrated data layer")
```

**Verification:** `python -c "from frontend_migrated.data.dependencies import DependencyRecommendation, fetch_recommendations; print('OK')"` succeeds.

---

## Step 13: Create `frontend_migrated/data/hlr.py` — stubs

**What:** 7 functions, 6 TypedDicts (`LLRRow`, `HLRRow`, `RequirementsData`, `TripleRow`, `HLRDetail`, `DecompositionResult`).

```python
"""HLR CRUD, decomposition, and requirements dashboard data — stubs.

Return types are documented via TypedDicts. All functions raise
NotImplementedError until reimplemented against the migrated backend.
No imports from backend/ anywhere in this module.
"""

from __future__ import annotations

from typing import TypedDict


class LLRRow(TypedDict):
    id: int
    description: str
    methods: list[str]


class HLRRow(TypedDict):
    id: int
    description: str
    component: str | None
    llrs: list[LLRRow]


class RequirementsData(TypedDict):
    hlrs: list[HLRRow]
    unlinked_llrs: list[LLRRow]
    total_hlrs: int
    total_llrs: int
    total_verifications: int
    total_nodes: int
    total_triples: int


class TripleRow(TypedDict):
    subject: str
    predicate: str
    object: str


class HLRDetail(TypedDict):
    id: int
    description: str
    component: str | None
    component_id: int | None
    llrs: list[LLRRow]
    triples: list[TripleRow]


class DecompositionResult(TypedDict):
    llrs_created: int
    verifications_created: int


def fetch_requirements_data() -> RequirementsData:
    """Fetch all data needed for the requirements dashboard."""
    raise NotImplementedError("fetch_requirements_data — requires backend_migrated data layer")


def fetch_hlr_detail(hlr_id: int) -> HLRDetail | None:
    """Fetch all data needed for HLR detail page."""
    raise NotImplementedError("fetch_hlr_detail — requires backend_migrated data layer")


def create_hlr(description: str, component_id: int | None = None) -> int:
    """Create a new HLR in Neo4j. Returns the new HLR id."""
    raise NotImplementedError("create_hlr — requires backend_migrated data layer")


def update_hlr(hlr_id: int, description: str, component_id: int | None = None) -> bool:
    """Update an HLR's description and component in Neo4j. Returns True on success."""
    raise NotImplementedError("update_hlr — requires backend_migrated data layer")


def delete_hlr(hlr_id: int) -> bool:
    """Delete an HLR and its child LLRs from Neo4j. Returns True on success."""
    raise NotImplementedError("delete_hlr — requires backend_migrated data layer")


def decompose_hlr(hlr_id: int) -> DecompositionResult:
    """Run the decomposition agent on an HLR and persist results to Neo4j."""
    raise NotImplementedError("decompose_hlr — requires backend_migrated data layer")


def design_single_hlr(hlr_id: int) -> dict:
    """Run the design agent on an HLR and persist the ontology results."""
    raise NotImplementedError("design_single_hlr — requires backend_migrated data layer")
```

**Verification:** `python -c "from frontend_migrated.data.hlr import HLRDetail, fetch_requirements_data; print('OK')"` succeeds.

---

## Step 14: Create `frontend_migrated/data/llr.py` — stubs

**What:** 4 functions, 5 TypedDicts (`ConditionRow`, `ActionRow`, `VerificationDetail`, `HLRSummary`, `LLRDetail`).

```python
"""LLR CRUD and detail data — stubs.

Return types are documented via TypedDicts. All functions raise
NotImplementedError until reimplemented against the migrated backend.
No imports from backend/ anywhere in this module.
"""

from __future__ import annotations

from typing import TypedDict


class ConditionRow(TypedDict):
    subject_qualified_name: str
    operator: str
    expected_value: str


class ActionRow(TypedDict):
    order: int
    description: str
    callee_qualified_name: str | None
    caller_qualified_name: str | None


class VerificationDetail(TypedDict):
    id: int
    method: str
    test_name: str | None
    description: str | None
    preconditions: list[ConditionRow]
    actions: list[ActionRow]
    postconditions: list[ConditionRow]


class HLRSummary(TypedDict):
    id: int
    description: str
    component: str | None


class LLRDetail(TypedDict):
    id: int
    description: str
    hlr: HLRSummary | None
    verifications: list[VerificationDetail]
    components: list[str]
    triples: list[dict]  # TripleRow — reuse from hlr.py when cross-module import is needed


def fetch_llr_detail(llr_id: int) -> LLRDetail | None:
    """Fetch all data needed for LLR detail page."""
    raise NotImplementedError("fetch_llr_detail — requires backend_migrated data layer")


def create_llr(hlr_id: int, description: str) -> int:
    """Create a new LLR under an HLR in Neo4j. Returns the new LLR id."""
    raise NotImplementedError("create_llr — requires backend_migrated data layer")


def update_llr(llr_id: int, description: str) -> bool:
    """Update an LLR's description in Neo4j. Returns True on success."""
    raise NotImplementedError("update_llr — requires backend_migrated data layer")


def delete_llr(llr_id: int) -> bool:
    """Delete an LLR from Neo4j. Returns True on success."""
    raise NotImplementedError("delete_llr — requires backend_migrated data layer")
```

**Verification:** `python -c "from frontend_migrated.data.llr import LLRDetail, fetch_llr_detail; print('OK')"` succeeds.

---

## Step 15: Create `frontend_migrated/data/ontology.py` — stubs

**What:** 8 functions, 6 TypedDicts (`OntologyNodeRow`, `OntologyData`, `OutgoingRef`, `IncomingRef`, `NodeDetail`, `NodeDetailFull`). Plus `filter_cross_layer_elements` (pure function — also stubbed for consistency, will be trivially re-implementable later).

```python
"""Ontology data and graph queries — stubs.

Return types are documented via TypedDicts. All functions raise
NotImplementedError until reimplemented against the migrated backend.
No imports from backend/ anywhere in this module.
"""

from __future__ import annotations

from typing import TypedDict


class OntologyNodeRow(TypedDict):
    name: str
    kind: str
    qualified_name: str
    component: str


class OntologyData(TypedDict):
    nodes: list[OntologyNodeRow]
    kind_counts: dict[str, int]
    total_nodes: int
    total_triples: int
    total_predicates: int


class OutgoingRef(TypedDict):
    rel: str
    target_qn: str
    target_name: str
    target_labels: list[str]


class IncomingRef(TypedDict):
    rel: str
    source_qn: str
    source_name: str
    source_labels: list[str]


class NodeDetail(TypedDict):
    properties: dict
    outgoing: list[OutgoingRef]
    incoming: list[IncomingRef]
    implemented_by: list
    members: list[dict]
    codebase_members: list
    available_types: list


class NodeDetailFull(TypedDict):
    node: dict
    neo4j: NodeDetail
    requirements: list


def fetch_ontology_data() -> OntologyData:
    """Fetch all data needed for the ontology overview page via LayerGraph."""
    raise NotImplementedError("fetch_ontology_data — requires backend_migrated data layer")


def fetch_ontology_graph_data(
    layer: str = "design",
    kind_filter: str | None = None,
    search: str | None = None,
    component_id: int | None = None,
    source_filter: str | None = None,
    requirement_tags: str = "hlr",
    include_dependencies: bool = True,
) -> dict:
    """Fetch graph data for Cytoscape.js rendering via LayerGraph.

    Returns Cytoscape-format dict with 'nodes' and 'edges' keys.
    """
    raise NotImplementedError("fetch_ontology_graph_data — requires backend_migrated data layer")


def fetch_hlr_graph_data(
    hlr_id: int,
    component_id: int | None = None,
    requirement_tags: str = "hlr",
) -> dict:
    """Fetch the ontology subgraph around an HLR for Cytoscape.js.

    Returns Cytoscape-format dict with 'nodes' and 'edges' keys.
    """
    raise NotImplementedError("fetch_hlr_graph_data — requires backend_migrated data layer")


def fetch_graph_node_detail(qualified_name: str) -> NodeDetail | None:
    """Fetch node detail from LayerGraph (properties + relationships + members)."""
    raise NotImplementedError("fetch_graph_node_detail — requires backend_migrated data layer")


def fetch_node_detail_full(qualified_name: str) -> NodeDetailFull | None:
    """Fetch ontology node by qualified_name with all properties + Neo4j relationships."""
    raise NotImplementedError("fetch_node_detail_full — requires backend_migrated data layer")


def resolve_node_id_by_qualified_name(qualified_name: str) -> int | None:
    """Look up an identifier for an ontology node by qualified_name."""
    raise NotImplementedError("resolve_node_id_by_qualified_name — requires backend_migrated data layer")


def update_member_type(qualified_name: str, type_signature: str) -> bool:
    """Update type_signature on a design member node in Neo4j."""
    raise NotImplementedError("update_member_type — requires backend_migrated data layer")


def filter_cross_layer_elements(
    nodes: list[dict], edges: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Remove cross-layer nodes and edges (dependency and as-built).

    Used when include_dependencies=False to return a design-only graph.
    """
    raise NotImplementedError("filter_cross_layer_elements — requires backend_migrated data layer")
```

**Verification:** `python -c "from frontend_migrated.data.ontology import OntologyData, fetch_ontology_data; print('OK')"` succeeds.

---

## Step 16: Verify `frontend_migrated/data/__init__.py` imports

**What:** Now that all stub modules exist, verify the full data package imports.

**Verification:** `python -c "from frontend_migrated.data import fetch_components_data, fetch_requirements_data, fetch_ontology_data; print('OK')"` succeeds.

---

## Step 17: Create `frontend_migrated/pages/__init__.py` — stubs

**What:** Stub page registrations matching the original, with NotImplementedError bodies.

```python
"""Page definitions — stubs.

Importing this module registers all NiceGUI routes. Each page function
raises NotImplementedError until reimplemented against the migrated data layer.
"""

from frontend_migrated.pages.project import project_page
from frontend_migrated.pages.requirements import requirements_page
from frontend_migrated.pages.hlr_detail import hlr_detail_page
from frontend_migrated.pages.llr_detail import llr_detail_page
from frontend_migrated.pages.components import components_page
from frontend_migrated.pages.ontology import ontology_page
from frontend_migrated.pages.ontology_graph import ontology_graph_page
from frontend_migrated.pages.node_detail import node_detail_page
from frontend_migrated.pages.component_detail import component_detail_page
from frontend_migrated.pages.dependency_review import dependency_review_page

__all__ = [
    "project_page",
    "requirements_page",
    "hlr_detail_page",
    "llr_detail_page",
    "components_page",
    "component_detail_page",
    "dependency_review_page",
    "ontology_page",
    "ontology_graph_page",
    "node_detail_page",
]
```

**Verification:** Will verify after all page stubs are created.

---

## Step 18: Create page stubs — simple pages

**What:** Create stubs for `components.py`, `ontology.py` — these are the simplest pages.

`frontend_migrated/pages/components.py`:
```python
"""Components page — stub."""

from nicegui import ui

from frontend_migrated.theme import apply_theme
from frontend_migrated.layout import page_layout


@ui.page("/components")
async def components_page():
    """STUB: Components overview page."""
    raise NotImplementedError("components_page — requires data layer reimplementation")
```

`frontend_migrated/pages/ontology.py`:
```python
"""Ontology overview page — stub."""

from nicegui import ui

from frontend_migrated.theme import apply_theme
from frontend_migrated.layout import page_layout


@ui.page("/ontology")
async def ontology_page():
    """STUB: Ontology overview page."""
    raise NotImplementedError("ontology_page — requires data layer reimplementation")
```

**Verification:** `python -c "from frontend_migrated.pages.components import components_page; from frontend_migrated.pages.ontology import ontology_page; print('OK')"` succeeds.

---

## Step 19: Create page stubs — detail and graph pages

**What:** Create stubs for `hlr_detail.py`, `llr_detail.py`, `node_detail.py`, `component_detail.py`, `ontology_graph.py`, `requirements.py`.

Each preserves the `@ui.page()` decorator and function signature with the route path. Body is `raise NotImplementedError`.

Pattern (example for `hlr_detail.py`):
```python
"""HLR detail page — stub."""

from nicegui import ui


@ui.page("/hlr/{hlr_id}")
async def hlr_detail_page(hlr_id: int):
    """STUB: HLR detail page showing requirements, LLR table, and graph."""
    raise NotImplementedError(f"hlr_detail_page({hlr_id}) — requires data layer reimplementation")
```

All other detail pages follow the same pattern with their respective route paths:
- `llr_detail.py` → `@ui.page("/llr/{llr_id}")`
- `node_detail.py` → `@ui.page("/ontology/node/{qualified_name}")` (check original for exact route)
- `component_detail.py` → `@ui.page("/component/{component_id}")`
- `ontology_graph.py` → `@ui.page("/ontology/graph")`
- `requirements.py` → `@ui.page("/requirements")`

**Verification:** `python -c "from frontend_migrated.pages import hlr_detail_page, requirements_page; print('OK')"` succeeds.

---

## Step 20: Create `frontend_migrated/pages/dependency_review/` — working cards.py + stubs

**What:** Cards module is working code (no backend deps). Research and route are stubs.

`frontend_migrated/pages/dependency_review/__init__.py`:
```python
"""Dependency review page submodule — stub."""

from frontend_migrated.pages.dependency_review.route import dependency_review_page

__all__ = ["dependency_review_page"]
```

`frontend_migrated/pages/dependency_review/cards.py` — Copy verbatim from `frontend/pages/dependency_review/cards.py`, change `from frontend.theme` → `from frontend_migrated.theme`.

`frontend_migrated/pages/dependency_review/research.py`:
```python
"""Dependency research agent runner — stub."""


def run_research(component_id: int) -> dict:
    """Run the research agent and return summary + recommendations.

    STUB: Requires backend_migrated data layer and agent integration.
    """
    raise NotImplementedError(f"run_research({component_id}) — requires backend_migrated data layer and agent integration")
```

`frontend_migrated/pages/dependency_review/route.py` — Stub with route decorator.

**Verification:** `python -c "from frontend_migrated.pages.dependency_review import dependency_review_page; print('OK')"` succeeds.

---

## Step 21: Create `frontend_migrated/pages/project/` — working submodules + stubs

**What:** `file_tree.py` and `vscode.py` port as working code. `route.py` and `sections.py` are stubs.

`frontend_migrated/pages/project/__init__.py`:
```python
"""Project page submodule — stub."""

from frontend_migrated.pages.project.route import project_page

__all__ = ["project_page"]
```

`frontend_migrated/pages/project/vscode.py` — Copy verbatim. No `frontend.` imports to change (only `nicegui` and stdlib).

`frontend_migrated/pages/project/file_tree.py` — Copy verbatim, change `from frontend.pages.project.vscode import open_file` → `from frontend_migrated.pages.project.vscode import open_file`. The `from codegraph.connection import get_session` stays as-is.

`frontend_migrated/pages/project/route.py` — Stub with route decorator, imports from `frontend_migrated.layout` and `frontend_migrated.data.project`.

`frontend_migrated/pages/project/sections.py` — Stub. The original is ~577 lines; the stub just needs the route registration pattern and a NotImplementedError.

**Verification:** `python -c "from frontend_migrated.pages.project import project_page; print('OK')"` succeeds.

---

## Step 22: Full import verification

**What:** Run a comprehensive import check to verify every module in `frontend_migrated/` can be imported without errors and no `backend/` imports leak through.

```bash
python -c "
import frontend_migrated
import frontend_migrated.theme
import frontend_migrated.widgets
import frontend_migrated.layout
import frontend_migrated.agent_log
import frontend_migrated.graph
import frontend_migrated.graph.format
import frontend_migrated.graph.labels
import frontend_migrated.data
import frontend_migrated.data.components
import frontend_migrated.data.dependencies
import frontend_migrated.data.hlr
import frontend_migrated.data.llr
import frontend_migrated.data.ontology
import frontend_migrated.data.project
import frontend_migrated.pages
print('All frontend_migrated modules import successfully')
"
```

Then verify no `backend` imports:
```bash
grep -rn "from backend\|import backend" frontend_migrated/ && echo "FAIL: backend imports found" || echo "OK: no backend imports"
```

**Verification:** Both commands succeed — all modules import, zero backend imports found.

---

## Step 23: Verify working modules produce correct output

**What:** Confirm that working modules (theme, widgets, layout, agent_log, graph) produce correct runtime output, not just import successfully.

```bash
python -c "
from frontend_migrated.theme import COLORS, BACKGROUNDS, apply_theme, cytoscape_base_styles, KIND_COLORS
assert 'primary' in COLORS
assert 'base' in BACKGROUNDS
assert 'class' in KIND_COLORS
print('theme: OK')

from frontend_migrated.widgets import GraphState, GraphConfig, breadcrumb
gs = GraphState()
assert gs.graph_layer == 'design'
gc = GraphConfig(container_id='test')
assert gc.tap_event == 'test_tap'
print('widgets: OK')

from frontend_migrated.agent_log import AgentLog, agent_log
al = AgentLog()
al.push('test', 'hello')
assert al.version == 1
entries = al.entries()
assert len(entries) == 1
print('agent_log: OK')

from frontend_migrated.graph.labels import _build_uml_label, _CODEGRAPH_KIND_GROUP
assert 'method' in _CODEGRAPH_KIND_GROUP
print('graph/labels: OK')

from frontend_migrated.graph.format import layer_graph_to_cytoscape
print('graph/format: OK')
"
```

**Verification:** All assertions pass.

---

## Summary of Files Created

| # | File | Type | Lines (est.) |
|---|------|------|------|
| 1 | `frontend_migrated/__init__.py` | Package | ~6 |
| 2 | `frontend_migrated/theme.py` | Working | ~551 |
| 3 | `frontend_migrated/widgets.py` | Working | ~740 |
| 4 | `frontend_migrated/layout.py` | Working | ~122 |
| 5 | `frontend_migrated/agent_log.py` | Working | ~444 |
| 6 | `frontend_migrated/graph/__init__.py` | Working | ~15 |
| 7 | `frontend_migrated/graph/labels.py` | Working | ~412 |
| 8 | `frontend_migrated/graph/format.py` | Working | ~385 |
| 9 | `frontend_migrated/data/__init__.py` | Stub | ~95 |
| 10 | `frontend_migrated/data/project.py` | Stub | ~60 |
| 11 | `frontend_migrated/data/components.py` | Stub | ~130 |
| 12 | `frontend_migrated/data/dependencies.py` | Stub | ~80 |
| 13 | `frontend_migrated/data/hlr.py` | Stub | ~90 |
| 14 | `frontend_migrated/data/llr.py` | Stub | ~70 |
| 15 | `frontend_migrated/data/ontology.py` | Stub | ~100 |
| 16 | *(verify data imports)* | — | — |
| 17 | `frontend_migrated/pages/__init__.py` | Stub | ~35 |
| 18 | `frontend_migrated/pages/components.py` | Stub | ~15 |
| 19 | `frontend_migrated/pages/*.py` (6 files) | Stub | ~15 ea |
| 20 | `frontend_migrated/pages/dependency_review/` | Mixed | ~120 |
| 21 | `frontend_migrated/pages/project/` | Mixed | ~60 new + copied |
| 22 | *(full import verification)* | — | — |
| 23 | *(runtime verification)* | — | — |

**Total: ~3,500 lines** (~2,270 working code + ~785 stubs + ~445 stub pages/inits)