# Combined Tools Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `combined_tools.py` (1148 lines) into a per-tool file structure with a class-based dispatcher, extracting shared helpers into reusable modules.

**Architecture:** One file per tool (`SCHEMA` + `handle()`), a `ToolDispatcher` base class for registry/dispatch, a `CombinedDispatcher` subclass holding shared state, and shared helpers in `tools/helpers/`. Existing callers (`combined_loop.py`, `design_oo_tools.py`) get minimal 3-line import changes.

**Tech Stack:** Python 3.12, pytest, existing NiceGUI/Neo4j/llm_caller stack

---

## File Structure

**Create:**
- `backend/ticketing_agent/tools/__init__.py` — ToolDispatcher base class
- `backend/ticketing_agent/tools/helpers/__init__.py` — re-exports
- `backend/ticketing_agent/tools/helpers/qname.py` — qname_resolves, suggest_qname
- `backend/ticketing_agent/tools/helpers/draft_state.py` — build_draft_lookup, draft_summary, check_enum_collisions
- `backend/ticketing_agent/tools/helpers/commit_schema.py` — commit_tool_schema
- `backend/ticketing_agent/tools/helpers/design_validation.py` — validate_oo_design, extract_type_refs
- `backend/ticketing_agent/tools/helpers/discovery.py` — discover_tool_dispatch, slim_compound, DISCOVERY_METHOD_MAP
- `backend/ticketing_agent/tools/design_verify/__init__.py` — exports CombinedDispatcher
- `backend/ticketing_agent/tools/design_verify/dispatcher.py` — CombinedDispatcher class
- `backend/ticketing_agent/tools/design_verify/draft_design.py` — SCHEMA + handle()
- `backend/ticketing_agent/tools/design_verify/validate_design.py` — SCHEMA + handle()
- `backend/ticketing_agent/tools/design_verify/check_class_name.py` — SCHEMA + handle()
- `backend/ticketing_agent/tools/design_verify/find_mechanism.py` — SCHEMA + handle()
- `backend/ticketing_agent/tools/design_verify/validate_qualified_names.py` — SCHEMA + handle()
- `backend/ticketing_agent/tools/design_verify/lookup_design_element.py` — SCHEMA + handle()
- `backend/ticketing_agent/tools/design_verify/draft_verifications.py` — SCHEMA + handle()
- `backend/ticketing_agent/tools/design_verify/commit.py` — SCHEMA + handle()
- `backend/ticketing_agent/tools/utilities/__init__.py`
- `backend/ticketing_agent/tools/utilities/list_sources.py` — SCHEMA
- `backend/ticketing_agent/tools/utilities/search_symbols.py` — SCHEMA
- `backend/ticketing_agent/tools/utilities/get_compound.py` — SCHEMA
- `backend/ticketing_agent/tools/utilities/browse_namespace.py` — SCHEMA
- `backend/ticketing_agent/tools/utilities/find_inheritance.py` — SCHEMA
- `tests/test_tool_dispatcher.py` — unit tests for ToolDispatcher
- `tests/test_combined_handlers.py` — unit tests for handler functions

**Modify:**
- `backend/ticketing_agent/design_verify/combined_loop.py` — 3-line import change
- `backend/ticketing_agent/design/design_oo_tools.py` — import change for validate_oo_design

**Delete:**
- `backend/ticketing_agent/design_verify/combined_tools.py` — replaced entirely

---

### Task 1: ToolDispatcher base class

**Files:**
- Create: `backend/ticketing_agent/tools/__init__.py`
- Test: `tests/test_tool_dispatcher.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tool_dispatcher.py
"""Tests for ToolDispatcher base class."""

import json


def test_register_and_dispatch():
    """Register a handler and dispatch to it."""
    from backend.ticketing_agent.tools import ToolDispatcher

    dispatcher = ToolDispatcher()

    def my_handler(tool_input: dict) -> str:
        return json.dumps({"result": tool_input["value"] * 2})

    dispatcher.register("my_tool", {"name": "my_tool"}, my_handler)

    result = dispatcher.dispatch("my_tool", {"value": 5})
    assert json.loads(result) == {"result": 10}


def test_dispatch_unknown_tool():
    """Dispatching an unknown tool returns an error JSON."""
    from backend.ticketing_agent.tools import ToolDispatcher

    dispatcher = ToolDispatcher()

    result = dispatcher.dispatch("nonexistent", {})
    parsed = json.loads(result)
    assert parsed["error"] == "Unknown tool: nonexistent"


def test_all_tool_schemas():
    """all_tool_schemas returns schemas in registration order."""
    from backend.ticketing_agent.tools import ToolDispatcher

    dispatcher = ToolDispatcher()

    schema_a = {"name": "tool_a", "description": "A"}
    schema_b = {"name": "tool_b", "description": "B"}
    dispatcher.register("tool_a", schema_a, lambda inp: "")
    dispatcher.register("tool_b", schema_b, lambda inp: "")

    schemas = dispatcher.all_tool_schemas
    assert schemas == [schema_a, schema_b]


def test_duplicate_registration_raises():
    """Registering the same tool name twice raises ValueError."""
    from backend.ticketing_agent.tools import ToolDispatcher

    dispatcher = ToolDispatcher()
    dispatcher.register("tool_a", {}, lambda inp: "")

    try:
        dispatcher.register("tool_a", {}, lambda inp: "")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Duplicate tool handler: tool_a" in str(e)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/danielnewman/dev/Doxygen-Dependency-Parser && python -m pytest tests/test_tool_dispatcher.py -v`
Expected: FAILS — `backend.ticketing_agent.tools` module doesn't exist yet

- [ ] **Step 3: Write the ToolDispatcher implementation**

```python
# backend/ticketing_agent/tools/__init__.py
"""Tool dispatcher infrastructure for agent tool loops."""

import json
from collections.abc import Callable


class ToolDispatcher:
    """Base class for tool dispatchers.

    Registers handler functions by tool name alongside their JSON schemas
    and dispatches calls to the appropriate handler.

    Usage::

        class MyDispatcher(ToolDispatcher):
            def __init__(self, ...):
                super().__init__()
                self.register("my_tool", MY_TOOL_SCHEMA, self._handle_my_tool)

        d = MyDispatcher(...)
        result = d.dispatch("my_tool", {"arg": "value"})
        schemas = d.all_tool_schemas  # for LLM tools parameter
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[dict], str]] = {}
        self._schemas: dict[str, dict] = {}

    def register(self, name: str, schema: dict, handler: Callable[[dict], str]) -> None:
        """Register a handler and its JSON schema for a tool name.

        Args:
            name: Tool name (must be unique).
            schema: Anthropic-format tool definition dict.
            handler: Callable that takes a tool_input dict and returns a JSON string.

        Raises:
            ValueError: If a handler is already registered for this tool name.
        """
        if name in self._handlers:
            raise ValueError(f"Duplicate tool handler: {name}")
        self._handlers[name] = handler
        self._schemas[name] = schema

    def dispatch(self, tool_name: str, tool_input: dict) -> str:
        """Dispatch a tool call to the registered handler.

        Returns JSON string result. Unknown tool names return
        an error JSON.
        """
        handler = self._handlers.get(tool_name)
        if handler is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        return handler(tool_input)

    @property
    def all_tool_schemas(self) -> list[dict]:
        """Return all registered tool schemas (for LLM tools parameter)."""
        return list(self._schemas.values())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/danielnewman/dev/Doxygen-Dependency-Parser && python -m pytest tests/test_tool_dispatcher.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/ticketing_agent/tools/__init__.py tests/test_tool_dispatcher.py
git commit -m "feat: add ToolDispatcher base class with registry and dispatch"
```

---

### Task 2: Extract shared helpers — qname.py

**Files:**
- Create: `backend/ticketing_agent/tools/helpers/__init__.py`
- Create: `backend/ticketing_agent/tools/helpers/qname.py`

- [ ] **Step 1: Create the helpers package init**

```python
# backend/ticketing_agent/tools/helpers/__init__.py
"""Shared helpers for agent tool dispatchers."""
```

- [ ] **Step 2: Create qname.py**

Extract `_qname_resolves` and `_suggest_qname` from `combined_tools.py` lines 473–567. Drop `_` prefix, make them public. Logic is identical — just renamed and with docstrings updated.

```python
# backend/ticketing_agent/tools/helpers/qname.py
"""Qualified-name resolution and suggestion helpers."""


def qname_resolves(
    qname: str,
    draft_lookup: dict[str, dict] | None = None,
    prior_class_lookup: dict[str, str] | None = None,
    dep_lookup: dict[str, str] | None = None,
    intercomponent_classes: list[dict] | None = None,
    neo4j_session=None,
) -> bool:
    """Check whether a qualified name exists in the design context.

    Checks draft lookup, prior class lookup, dependency lookup,
    intercomponent classes, and (optionally) Neo4j persistent store.
    """
    if draft_lookup and qname in draft_lookup:
        return True
    if prior_class_lookup:
        if qname in prior_class_lookup.values():
            return True
        if qname in prior_class_lookup:
            return True
    if dep_lookup:
        if qname in dep_lookup:
            return True
        if qname in dep_lookup.values():
            return True
    if intercomponent_classes:
        ic_qnames = {c["qualified_name"] for c in intercomponent_classes}
        if qname in ic_qnames:
            return True
    if neo4j_session is not None:
        from backend.db.neo4j.repositories.design import DesignRepository
        repo = DesignRepository(neo4j_session)
        nodes = repo.find_nodes(search=qname, exclude_source_types=["verification"])
        if any(n.qualified_name == qname for n in nodes):
            return True
    return False


def suggest_qname(
    unresolved: str,
    draft_lookup: dict[str, dict],
    prior_class_lookup: dict[str, str],
    dep_lookup: dict[str, str],
    intercomponent_classes: list[dict],
) -> str | None:
    """Find the closest matching qualified name for an unresolved reference.

    Searches by bare name, member name, substring matching.
    Strips common stub suffixes (.output, .result, .return_value).

    Does NOT query Neo4j — only in-memory lookups for speed.
    """
    # Strip common stub suffixes
    cleaned = unresolved
    for suffix in (".output", ".result", ".return_value"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]

    # Strategy 1: bare name match in prior/dep lookups
    bare = cleaned.rsplit("::", 1)[-1].rsplit(".", 1)[-1]
    for name, qname in {**prior_class_lookup, **dep_lookup}.items():
        if name == bare or name.lower() == bare.lower():
            return qname

    # Strategy 2: member name match in draft
    for qname, info in draft_lookup.items():
        kind = info.get("kind", "")
        if kind in ("method", "attribute") and qname.endswith(f"::{bare}"):
            return qname

    # Strategy 3: class/interface/enum name match in draft
    for qname, info in draft_lookup.items():
        kind = info.get("kind", "")
        if kind in ("class", "interface", "enum"):
            class_name = qname.rsplit("::", 1)[-1]
            if class_name == bare or class_name.lower() == bare.lower():
                return qname

    # Strategy 4: substring match in draft and dep lookups
    cleaned_lower = cleaned.lower()
    for qname in draft_lookup:
        if cleaned_lower in qname.lower():
            return qname
    for qname in dep_lookup.values():
        if cleaned_lower in qname.lower():
            return qname

    return None
```

- [ ] **Step 3: Commit**

```bash
git add backend/ticketing_agent/tools/helpers/
git commit -m "feat: extract qname_resolves and suggest_qname into helpers/qname.py"
```

---

### Task 3: Extract shared helpers — draft_state.py

**Files:**
- Create: `backend/ticketing_agent/tools/helpers/draft_state.py`

- [ ] **Step 1: Create draft_state.py**

Extract `_build_draft_lookup`, `_draft_summary`, and the inline enum collision check from `combined_tools.py`. Lines 392–455, 454–470, and the duplication in `_dispatch_draft_design` and `_dispatch_validate_design`.

```python
# backend/ticketing_agent/tools/helpers/draft_state.py
"""Draft design state helpers."""

from backend.codebase.schemas import OODesignSchema


def build_draft_lookup(design: OODesignSchema) -> dict[str, dict]:
    """Build a lookup dict from a draft OODesignSchema.

    Returns qualified_name -> {qualified_name, kind, description, source: 'draft'}
    for all classes, interfaces, enums, their attributes, and methods.
    """
    lookup: dict[str, dict] = {}

    for cls in design.classes:
        qname = f"{cls.module}::{cls.name}" if cls.module else cls.name
        lookup[qname] = {
            "qualified_name": qname,
            "kind": "class",
            "description": cls.description,
            "source": "draft",
        }
        for attr in cls.attributes:
            attr_qname = f"{qname}::{attr.name}"
            lookup[attr_qname] = {
                "qualified_name": attr_qname,
                "kind": "attribute",
                "description": attr.description,
                "source": "draft",
            }
        for method in cls.methods:
            method_qname = f"{qname}::{method.name}"
            lookup[method_qname] = {
                "qualified_name": method_qname,
                "kind": "method",
                "description": method.description,
                "source": "draft",
            }

    for iface in design.interfaces:
        qname = f"{iface.module}::{iface.name}" if iface.module else iface.name
        lookup[qname] = {
            "qualified_name": qname,
            "kind": "interface",
            "description": iface.description,
            "source": "draft",
        }
        for method in iface.methods:
            method_qname = f"{qname}::{method.name}"
            lookup[method_qname] = {
                "qualified_name": method_qname,
                "kind": "method",
                "description": method.description,
                "source": "draft",
            }

    for enum in design.enums:
        qname = f"{enum.module}::{enum.name}" if enum.module else enum.name
        lookup[qname] = {
            "qualified_name": qname,
            "kind": "enum",
            "description": enum.description,
            "source": "draft",
        }

    return lookup


def draft_summary(design: OODesignSchema) -> dict:
    """Return a summary dict of the draft design for tool responses."""
    total_attrs = sum(len(cls.attributes) for cls in design.classes)
    total_methods = sum(len(cls.methods) for cls in design.classes)
    return {
        "classes": len(design.classes),
        "interfaces": len(design.interfaces),
        "enums": len(design.enums),
        "associations": len(design.associations),
        "attributes": total_attrs,
        "methods": total_methods,
    }


def check_enum_collisions(design: OODesignSchema, prior_class_lookup: dict[str, str]) -> list[str]:
    """Warn if enum names collide with prior designs.

    Returns a list of warning strings. Empty list means no collisions.
    """
    warnings = []
    for enum in design.enums:
        enum_qname = f"{enum.module}::{enum.name}" if enum.module else enum.name
        if enum.name in prior_class_lookup:
            existing_qname = prior_class_lookup[enum.name]
            if existing_qname != enum_qname:
                warnings.append(
                    f"Enum '{enum.name}' already exists as '{existing_qname}' in a "
                    f"prior design. Consider referencing the existing enum or "
                    f"renaming yours to avoid confusion."
                )
    return warnings
```

- [ ] **Step 2: Commit**

```bash
git add backend/ticketing_agent/tools/helpers/draft_state.py
git commit -m "feat: extract build_draft_lookup, draft_summary, check_enum_collisions into helpers"
```

---

### Task 4: Extract shared helpers — commit_schema.py

**Files:**
- Create: `backend/ticketing_agent/tools/helpers/commit_schema.py`

- [ ] **Step 1: Create commit_schema.py**

Extract `_commit_tool_schema` from `combined_tools.py` lines 42–56.

```python
# backend/ticketing_agent/tools/helpers/commit_schema.py
"""Schema builder for the commit_design_and_verifications tool."""

from backend.codebase.schemas import DesignAndVerificationSchema


def commit_tool_schema() -> dict:
    """Build the JSON schema for commit_design_and_verifications.

    Customizes the verifications field to explicitly describe the LLR ID key
    format, which LLMs frequently get wrong.
    """
    schema = DesignAndVerificationSchema.model_json_schema()
    if "properties" in schema and "verifications" in schema["properties"]:
        schema["properties"]["verifications"]["description"] = (
            "Map of LLR ID (integer string) to list of verification procedures. "
            "Keys MUST be LLR IDs like \"1\", \"2\" — NOT test names. "
            "Example: {\"1\": [...], \"2\": [...]}"
        )
    return schema
```

- [ ] **Step 2: Commit**

```bash
git add backend/ticketing_agent/tools/helpers/commit_schema.py
git commit -m "feat: extract commit_tool_schema into helpers/commit_schema.py"
```

---

### Task 5: Extract shared helpers — design_validation.py

**Files:**
- Create: `backend/ticketing_agent/tools/helpers/design_validation.py`
- Modify: `backend/ticketing_agent/design/design_oo_tools.py`

- [ ] **Step 1: Create design_validation.py**

Extract `_validate_oo_design` and `_extract_type_refs` from `backend/ticketing_agent/design/design_oo_tools.py` lines 260–455. Drop `_` prefix.

```python
# backend/ticketing_agent/tools/helpers/design_validation.py
"""OO design structural validation."""

import re

from backend.codebase.schemas import OODesignSchema


def extract_type_refs(type_string: str, known_names: set[str], out: set[str]) -> None:
    """Extract references to known design entity names from a type string.

    Handles types like `CalculatorResult`, `const CalculatorResult&`,
    `vector<CalculatorResult>`, `std::unique_ptr<Operator>`, etc.
    Only adds names that appear in *known_names*.
    """
    for token in re.findall(r'\b([A-Z][A-Za-z0-9_]*)\b', type_string):
        if token in known_names:
            out.add(token)


def validate_oo_design(
    oo: OODesignSchema,
    prior_class_lookup: dict[str, str],
    dependency_lookup: dict[str, str] | None,
    intercomponent_classes: list[dict] | None,
) -> list[str]:
    """Validate an OO design for association target resolution and intercomponent coverage.

    Returns a list of error strings. Empty list means valid.
    """
    errors = []

    # Build set of known names
    design_class_names = {cls.name for cls in oo.classes}
    design_iface_names = {iface.name for iface in oo.interfaces}
    design_enum_names = {enum.name for enum in oo.enums}
    all_design_names = design_class_names | design_iface_names | design_enum_names

    # Set of intercomponent qualified names for lookup
    intercomp_qnames: set[str] = set()
    intercomp_bare: set[str] = set()
    if intercomponent_classes:
        intercomp_qnames = {c["qualified_name"] for c in intercomponent_classes}
        intercomp_bare = {qname.rsplit("::", 1)[-1] for qname in intercomp_qnames}

    # Build dependency lookup
    dep_lookup = dict(dependency_lookup or {})

    # Check 1: Unknown association targets
    for assoc in oo.associations:
        for ref in [assoc.from_class, assoc.to_class]:
            if ref in all_design_names:
                continue
            if ref in prior_class_lookup.values():
                continue
            if ref in prior_class_lookup:
                continue
            if ref in dep_lookup:
                continue
            if ref in intercomp_qnames or ref in intercomp_bare:
                continue
            errors.append(
                f'Unknown class reference: "{ref}" in association '
                f'({assoc.from_class} -[{assoc.kind}]-> {assoc.to_class}). '
                f'"{ref}" is not defined in this design or the provided context.'
            )

    # Check 2: aggregates must have a mechanism; references recommended
    for assoc in oo.associations:
        if assoc.kind == "aggregates" and not assoc.mechanism:
            errors.append(
                f"Association {assoc.from_class} -[aggregates]-> {assoc.to_class} "
                f"has no mechanism. Use find_mechanism to discover the container "
                f"type (e.g., std::vector, std::map) and specify it in the mechanism field."
            )
        if assoc.kind == "aggregates" and assoc.mechanism:
            mechanism = assoc.mechanism
            if mechanism not in all_design_names and mechanism not in prior_class_lookup and mechanism not in dep_lookup:
                errors.append(
                    f"Association {assoc.from_class} -[aggregates]-> {assoc.to_class} "
                    f"has mechanism '{mechanism}' which is not a known class or dependency. "
                    f"Use find_mechanism to search for the correct container name."
                )

    # Check 3: Missing intercomponent associations
    if intercomponent_classes:
        for cls in oo.classes:
            referenced_intercomp: set[str] = set()
            for attr in cls.attributes:
                for ic in intercomponent_classes:
                    ic_bare = ic["qualified_name"].rsplit("::", 1)[-1]
                    if attr.type_name and (ic_bare in attr.type_name or ic["qualified_name"] in attr.type_name):
                        referenced_intercomp.add(ic["qualified_name"])
            for method in cls.methods:
                if method.return_type:
                    for ic in intercomponent_classes:
                        ic_bare = ic["qualified_name"].rsplit("::", 1)[-1]
                        if ic_bare in method.return_type or ic["qualified_name"] in method.return_type:
                            referenced_intercomp.add(ic["qualified_name"])

            if referenced_intercomp:
                assoc_targets = {assoc.to_class for assoc in oo.associations} | {assoc.from_class for assoc in oo.associations}
                for ic_qname in referenced_intercomp:
                    if ic_qname not in assoc_targets:
                        ic_bare = ic_qname.rsplit("::", 1)[-1]
                        if ic_bare not in assoc_targets:
                            errors.append(
                                f"Missing intercomponent association: {cls.name} references "
                                f"{ic_qname} in attributes/methods but has no association to it."
                            )

    # Check 4: Disconnected design entities
    inbound: dict[str, set[str]] = {name: set() for name in all_design_names}
    outbound: dict[str, set[str]] = {name: set() for name in all_design_names}

    for assoc in oo.associations:
        if assoc.from_class in all_design_names:
            if assoc.to_class in all_design_names:
                inbound[assoc.to_class].add(assoc.from_class)
            outbound[assoc.from_class].add(assoc.to_class)
        elif assoc.to_class in all_design_names:
            inbound[assoc.to_class].add(assoc.from_class)

    for cls in oo.classes:
        for attr in cls.attributes:
            if attr.type_name:
                extract_type_refs(attr.type_name, all_design_names, outbound[cls.name])
        for method in cls.methods:
            if method.return_type:
                extract_type_refs(method.return_type, all_design_names, outbound[cls.name])
            for param in (method.parameters or []):
                if isinstance(param, str):
                    extract_type_refs(param, all_design_names, outbound[cls.name])
        for parent in (cls.inherits_from or []):
            if parent in all_design_names:
                outbound[cls.name].add(parent)
                inbound[parent].add(cls.name)
        for iface in (cls.realizes_interfaces or []):
            if iface in all_design_names:
                outbound[cls.name].add(iface)
                inbound[iface].add(cls.name)

    for iface in oo.interfaces:
        for method in iface.methods:
            if method.return_type:
                extract_type_refs(method.return_type, all_design_names, outbound[iface.name])
            for param in (method.parameters or []):
                if isinstance(param, str):
                    extract_type_refs(param, all_design_names, outbound[iface.name])

    for entity_name, refs in outbound.items():
        for ref_name in refs:
            if ref_name in inbound and ref_name != entity_name:
                inbound[ref_name].add(entity_name)

    if len(all_design_names) > 1:
        disconnected = []
        for cls in oo.classes:
            if not inbound[cls.name] and not outbound[cls.name]:
                disconnected.append((cls.name, "class"))
        for iface in oo.interfaces:
            if not inbound[iface.name] and not outbound[iface.name]:
                disconnected.append((iface.name, "interface"))
        for enum in oo.enums:
            if not inbound[enum.name] and not outbound[enum.name]:
                disconnected.append((enum.name, "enum"))

        for name, kind in disconnected:
            errors.append(
                f"Disconnected {kind} \"{name}\" is not referenced by any association, "
                f"attribute type, method parameter/return type, inheritance, or interface, "
                f"and does not itself reference any other design entity. "
                f"Either remove it or connect it to the design."
            )

    return errors
```

- [ ] **Step 2: Update design_oo_tools.py to import from new location**

In `backend/ticketing_agent/design/design_oo_tools.py`, replace the local definitions of `_extract_type_refs` and `_validate_oo_design` with imports:

```python
# Replace lines 260-455 (the _extract_type_refs and _validate_oo_design definitions)
# with:
from backend.ticketing_agent.tools.helpers.design_validation import validate_oo_design, extract_type_refs
```

And update all internal references:
- `_validate_oo_design(` → `validate_oo_design(`
- `_extract_type_refs(` → `extract_type_refs(`

- [ ] **Step 3: Run existing tests to verify nothing broke**

Run: `cd /Users/danielnewman/dev/Doxygen-Dependency-Parser && python -m pytest tests/ -k "design" -v`
Expected: All passing

- [ ] **Step 4: Commit**

```bash
git add backend/ticketing_agent/tools/helpers/design_validation.py backend/ticketing_agent/design/design_oo_tools.py
git commit -m "feat: extract validate_oo_design and extract_type_refs into helpers/design_validation.py"
```

---

### Task 6: Extract shared helpers — discovery.py

**Files:**
- Create: `backend/ticketing_agent/tools/helpers/discovery.py`

- [ ] **Step 1: Create discovery.py**

Extract `_slim_compound` and `_dispatch_discovery` logic from `combined_tools.py`. Replace the per-handler dispatch with a reusable `discover_tool_dispatch` function.

```python
# backend/ticketing_agent/tools/helpers/discovery.py
"""Discovery tool dispatch helpers.

Routes discovery tool calls (list_sources, search_symbols, etc.)
to a DependencyGraphTools instance (doxygen_index).
"""

import json
import logging

log = logging.getLogger("agents.tools.discovery")

# Maps our tool names -> DependencyGraphTools method names
DISCOVERY_METHOD_MAP = {
    "list_sources": "list_sources",
    "search_symbols": "search_symbols",
    "get_compound": "get_compound",
    "browse_namespace": "browse_namespace",
    "find_inheritance": "find_inheritance",
}

# Tools whose results should be slimmed
_SLIM_FN = {}


def slim_compound(records: list[dict]) -> list[dict]:
    """Strip heavyweight fields from get_compound results."""
    drop = {"detailed", "member_refid", "member_brief"}
    return [{k: v for k, v in r.items() if k not in drop} for r in records]


_SLIM_FN["get_compound"] = slim_compound


def discover_tool_dispatch(
    tool_name: str,
    tool_input: dict,
    toolset,
) -> str:
    """Dispatch a discovery tool call to the DependencyGraphTools instance.

    Args:
        tool_name: One of the discovery tool names (list_sources, etc.).
        tool_input: Dict of tool arguments.
        toolset: A DependencyGraphTools instance, or None if unavailable.

    Returns:
        JSON string result.
    """
    if toolset is None:
        return json.dumps({
            "error": "Codebase index not available. Proceed with your design using general knowledge and note the gap.",
        })
    method_name = DISCOVERY_METHOD_MAP.get(tool_name)
    method = getattr(toolset, method_name, None) if toolset else None
    if not method:
        return json.dumps({"error": f"Discovery tool {tool_name} not available"})
    try:
        result = method(**tool_input)
        slim = _SLIM_FN.get(tool_name)
        if slim:
            result = slim(result)
        return json.dumps(result, default=str)
    except Exception as e:
        log.warning("Discovery tool %s failed: %s", tool_name, e)
        return json.dumps({"error": str(e)})
```

- [ ] **Step 2: Commit**

```bash
git add backend/ticketing_agent/tools/helpers/discovery.py
git commit -m "feat: extract discover_tool_dispatch and slim_compound into helpers/discovery.py"
```

---

### Task 7: Create utility tool schema files

**Files:**
- Create: `backend/ticketing_agent/tools/utilities/__init__.py`
- Create: `backend/ticketing_agent/tools/utilities/list_sources.py`
- Create: `backend/ticketing_agent/tools/utilities/search_symbols.py`
- Create: `backend/ticketing_agent/tools/utilities/get_compound.py`
- Create: `backend/ticketing_agent/tools/utilities/browse_namespace.py`
- Create: `backend/ticketing_agent/tools/utilities/find_inheritance.py`

- [ ] **Step 1: Create all five utility schema files + init**

```python
# backend/ticketing_agent/tools/utilities/__init__.py
"""Discovery tool schemas for codebase indexing."""
```

```python
# backend/ticketing_agent/tools/utilities/list_sources.py
"""list_sources tool: list indexed dependency sources."""

from backend.ticketing_agent.tools.helpers.discovery import discover_tool_dispatch

SCHEMA = {
    "name": "list_sources",
    "description": (
        "List all indexed dependency sources and their symbol counts. "
        "Call this first to see which dependencies are available before "
        "searching for specific classes."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def handle(ctx, tool_input: dict) -> str:
    """Delegate to the discovery toolset."""
    return discover_tool_dispatch("list_sources", tool_input, ctx.toolset)
```

```python
# backend/ticketing_agent/tools/utilities/search_symbols.py
"""search_symbols tool: full-text search across indexed symbol names."""

from backend.ticketing_agent.tools.helpers.discovery import discover_tool_dispatch

SCHEMA = {
    "name": "search_symbols",
    "description": (
        "Full-text search across indexed symbol names and documentation. "
        "Use this to discover dependency or project classes relevant to "
        "the requirements when designing. Supports natural-language terms "
        "(e.g. 'window create', 'font rendering'). Returns matches with "
        "qualified_name, kind, source, and relevance score."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search terms (supports Lucene syntax — AND, OR, quotes).",
            },
            "source": {
                "type": "string",
                "description": "Optional dependency name to restrict results (e.g. 'fltk', 'boost').",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results.",
                "default": 20,
            },
        },
        "required": ["query"],
    },
}


def handle(ctx, tool_input: dict) -> str:
    """Delegate to the discovery toolset."""
    return discover_tool_dispatch("search_symbols", tool_input, ctx.toolset)
```

```python
# backend/ticketing_agent/tools/utilities/get_compound.py
"""get_compound tool: get full details of a class, struct, or enum."""

from backend.ticketing_agent.tools.helpers.discovery import discover_tool_dispatch

SCHEMA = {
    "name": "get_compound",
    "description": (
        "Get full details of a class, struct, or enum and its members from "
        "the indexed codebase. Use this after search_symbols identifies a "
        "compound of interest. Returns the compound metadata plus all of "
        "its members with signatures. Essential for understanding the API "
        "of a class you plan to inherit from or reference."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Exact or qualified name (e.g. 'Fl_Window', 'boost::gregorian::date').",
            },
            "source": {
                "type": "string",
                "description": "Optional dependency name filter.",
            },
        },
        "required": ["name"],
    },
}


def handle(ctx, tool_input: dict) -> str:
    """Delegate to the discovery toolset."""
    return discover_tool_dispatch("get_compound", tool_input, ctx.toolset)
```

```python
# backend/ticketing_agent/tools/utilities/browse_namespace.py
"""browse_namespace tool: list classes and symbols within a namespace."""

from backend.ticketing_agent.tools.helpers.discovery import discover_tool_dispatch

SCHEMA = {
    "name": "browse_namespace",
    "description": (
        "List classes, free functions, and other symbols within a namespace "
        "in the indexed codebase. Returns both nested compounds and "
        "namespace-level members. Use this to explore a dependency's top-level "
        "types when you don't know exact class names."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Namespace name (e.g. 'Fl', 'boost::asio').",
            },
            "source": {
                "type": "string",
                "description": "Optional dependency name filter.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results.",
                "default": 50,
            },
        },
        "required": ["name"],
    },
}


def handle(ctx, tool_input: dict) -> str:
    """Delegate to the discovery toolset."""
    return discover_tool_dispatch("browse_namespace", tool_input, ctx.toolset)
```

```python
# backend/ticketing_agent/tools/utilities/find_inheritance.py
"""find_inheritance tool: explore class inheritance hierarchies."""

from backend.ticketing_agent.tools.helpers.discovery import discover_tool_dispatch

SCHEMA = {
    "name": "find_inheritance",
    "description": (
        "Explore the inheritance hierarchy of a class in the indexed codebase. "
        "Use this to understand parent classes and derived classes — if a class "
        "is relevant, its base classes may also be. Essential for determining "
        "the correct inherits_from list in your design."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Exact or qualified class name.",
            },
            "direction": {
                "type": "string",
                "enum": ["up", "down", "both"],
                "description": 'Direction: "up" (base classes), "down" (derived), or "both".',
                "default": "both",
            },
            "max_depth": {
                "type": "integer",
                "description": "Maximum inheritance depth to traverse.",
                "default": 5,
            },
        },
        "required": ["name"],
    },
}


def handle(ctx, tool_input: dict) -> str:
    """Delegate to the discovery toolset."""
    return discover_tool_dispatch("find_inheritance", tool_input, ctx.toolset)
```

- [ ] **Step 2: Commit**

```bash
git add backend/ticketing_agent/tools/utilities/
git commit -m "feat: add discovery utility tool schemas and handlers"
```

---

### Task 8: Create design_verify tool handler files

**Files:**
- Create: `backend/ticketing_agent/tools/design_verify/draft_design.py`
- Create: `backend/ticketing_agent/tools/design_verify/validate_design.py`
- Create: `backend/ticketing_agent/tools/design_verify/check_class_name.py`
- Create: `backend/ticketing_agent/tools/design_verify/find_mechanism.py`

- [ ] **Step 1: Create draft_design.py**

```python
# backend/ticketing_agent/tools/design_verify/draft_design.py
"""draft_design tool: submit or revise the OO design draft."""

import json

from backend.codebase.schemas import OODesignSchema
from backend.ticketing_agent.tools.helpers.draft_state import (
    build_draft_lookup,
    check_enum_collisions,
    draft_summary,
)
from backend.ticketing_agent.tools.helpers.design_validation import validate_oo_design

SCHEMA = {
    "name": "draft_design",
    "description": (
        "Submit or revise the current OO design draft. The design is stored "
        "in the tool loop state so that subsequent validate_qualified_names "
        "and lookup_design_element calls can check references against it. "
        "Returns validation results and a summary of the stored draft."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "design": OODesignSchema.model_json_schema(),
        },
        "required": ["design"],
    },
}


def handle(ctx, tool_input: dict) -> str:
    """Parse, validate, and store the draft design."""
    try:
        design = OODesignSchema.model_validate(tool_input.get("design", tool_input))
    except Exception as e:
        return json.dumps({
            "valid": False,
            "errors": [f"Invalid design format: {e}"],
            "draft_summary": {},
        })

    errors = validate_oo_design(
        design,
        prior_class_lookup=ctx.prior_class_lookup,
        dependency_lookup=ctx.dep_lookup,
        intercomponent_classes=ctx.intercomponent_classes,
    )

    warnings = check_enum_collisions(design, ctx.prior_class_lookup)

    # Store draft — mutable state on ctx
    ctx.draft_design = design
    ctx.draft_lookup = build_draft_lookup(design)

    return json.dumps({
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "draft_summary": draft_summary(design),
    })
```

- [ ] **Step 2: Create validate_design.py**

```python
# backend/ticketing_agent/tools/design_verify/validate_design.py
"""validate_design tool: validate draft design for structural consistency."""

import json

from backend.codebase.schemas import OODesignSchema
from backend.ticketing_agent.tools.helpers.draft_state import check_enum_collisions
from backend.ticketing_agent.tools.helpers.design_validation import validate_oo_design

SCHEMA = {
    "name": "validate_design",
    "description": (
        "Validate the current draft OO design for structural consistency. "
        "Checks for unknown association targets, missing intercomponent "
        "associations, and other issues. Uses the design currently stored "
        "via draft_design. Returns errors and warnings."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "design": OODesignSchema.model_json_schema(),
        },
        "required": ["design"],
    },
}


def handle(ctx, tool_input: dict) -> str:
    """Validate the provided design draft."""
    try:
        design = OODesignSchema.model_validate(tool_input.get("design", tool_input))
    except Exception as e:
        return json.dumps({
            "valid": False,
            "errors": [f"Invalid design format: {e}"],
            "warnings": [],
        })

    errors = validate_oo_design(
        design,
        prior_class_lookup=ctx.prior_class_lookup,
        dependency_lookup=ctx.dep_lookup,
        intercomponent_classes=ctx.intercomponent_classes,
    )

    warnings = check_enum_collisions(design, ctx.prior_class_lookup)

    return json.dumps({
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    })
```

- [ ] **Step 3: Create check_class_name.py**

```python
# backend/ticketing_agent/tools/design_verify/check_class_name.py
"""check_class_name tool: look up class/interface/enum names across design contexts."""

import json

SCHEMA = {
    "name": "check_class_name",
    "description": (
        "Check if a class, interface, or enum name exists in the design "
        "context (prior designs, dependency APIs, intercomponent boundaries, "
        "or the current draft). Use this to verify that association targets "
        "and type references are valid. Supports partial matching."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "A class, interface, or enum name to look up. Can be a "
                    "bare name or qualified name. Supports substring matching."
                ),
            },
        },
        "required": ["name"],
    },
}


def handle(ctx, tool_input: dict) -> str:
    """Search draft, prior designs, dependency APIs, and intercomponent
    classes for matching names."""
    name = tool_input.get("name", "")
    if not name:
        return json.dumps({"found": False, "matches": []})

    matches = []
    name_lower = name.lower()

    # Search draft
    if ctx.draft_lookup:
        for qname, info in ctx.draft_lookup.items():
            if name_lower in qname.lower() or name_lower in info.get("description", "").lower():
                matches.append({
                    "qualified_name": qname,
                    "kind": info["kind"],
                    "source": "draft",
                })

    # Search prior designs
    for bare, qname in ctx.prior_class_lookup.items():
        if name_lower in bare.lower() or name_lower in qname.lower():
            matches.append({
                "qualified_name": qname,
                "kind": "class",
                "source": "prior_design",
            })

    # Search dependency APIs
    for bare, qname in ctx.dep_lookup.items():
        if name_lower in bare.lower() or name_lower in qname.lower():
            matches.append({
                "qualified_name": qname,
                "kind": "dependency",
                "source": "dependency",
            })

    # Search intercomponent classes
    for cls in ctx.intercomponent_classes:
        qname = cls.get("qualified_name", "")
        bare = qname.rsplit("::", 1)[-1] if qname else ""
        cls_name = cls.get("name", bare)
        if name_lower in cls_name.lower() or name_lower in qname.lower():
            matches.append({
                "qualified_name": qname,
                "kind": cls.get("kind", "class"),
                "source": "intercomponent",
            })

    return json.dumps({"found": len(matches) > 0, "matches": matches})
```

- [ ] **Step 4: Create find_mechanism.py**

```python
# backend/ticketing_agent/tools/design_verify/find_mechanism.py
"""find_mechanism tool: search for container/smart-pointer types in the dependency graph."""

import json
import logging

log = logging.getLogger("agents.tools.find_mechanism")

SCHEMA = {
    "name": "find_mechanism",
    "description": (
        "Search the dependency graph for container or smart-pointer types "
        "(e.g., std::vector, std::map, boost::unordered_map). "
        "Returns matching types with their qualified_name, kind, source, "
        "and brief description. Use this to discover the correct mechanism "
        "name for aggregates and references associations. Common containers "
        "(std::vector, std::map, etc.) are pre-loaded in the dependency "
        "context and available without a search."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Container or smart-pointer name to search for "
                    "(e.g., 'vector', 'unordered_map', 'shared_ptr')"
                ),
            },
            "library": {
                "type": "string",
                "description": "Optional library source to restrict search (e.g., 'cppreference', 'boost')",
            },
        },
        "required": ["query"],
    },
}


def handle(ctx, tool_input: dict) -> str:
    """Search dep_lookup and Neo4j for container/smart-pointer types."""
    query = tool_input.get("query", "")
    library = tool_input.get("library")
    if not query:
        return json.dumps({"containers": []})

    matches = []
    query_lower = query.lower()

    # Search dep_lookup (includes pre-seeded containers)
    for bare, qname in ctx.dep_lookup.items():
        if query_lower in bare.lower() or query_lower in qname.lower():
            matches.append({
                "qualified_name": qname,
                "name": bare,
                "kind": "class",
                "source": "dependency",
                "brief": "",
            })

    # Search Neo4j if session is available
    if ctx.neo4j_session is not None:
        try:
            result = ctx.neo4j_session.run(
                "MATCH (n:Compound) "
                "WHERE n.qualified_name CONTAINS $query "
                "AND n.kind IN ['class', 'struct'] "
                "AND (n.source = 'cppreference' OR n.source = 'boost' OR n.source IS NOT NULL) "
                "RETURN n.qualified_name AS qn, n.name AS name, "
                "n.kind AS kind, n.source AS source, n.brief AS brief "
                "LIMIT 20",
                query=query,
            )
            for record in result:
                qn = record["qn"]
                if any(m["qualified_name"] == qn for m in matches):
                    continue
                if library and record["source"] != library:
                    continue
                matches.append({
                    "qualified_name": qn,
                    "name": record["name"] or qn.rsplit("::", 1)[-1],
                    "kind": record["kind"] or "class",
                    "source": record["source"] or "dependency",
                    "brief": record["brief"] or "",
                })
        except Exception:
            log.warning("find_mechanism: Neo4j query failed", exc_info=True)

    # Deduplicate by qualified_name
    seen = set()
    deduped = []
    for m in matches:
        if m["qualified_name"] not in seen:
            seen.add(m["qualified_name"])
            deduped.append(m)

    return json.dumps({"containers": deduped[:20]})
```

- [ ] **Step 5: Commit**

```bash
git add backend/ticketing_agent/tools/design_verify/
git commit -m "feat: add draft_design, validate_design, check_class_name, find_mechanism handlers"
```

---

### Task 9: Create remaining design_verify tool handler files

**Files:**
- Create: `backend/ticketing_agent/tools/design_verify/validate_qualified_names.py`
- Create: `backend/ticketing_agent/tools/design_verify/lookup_design_element.py`

- [ ] **Step 1: Create validate_qualified_names.py**

```python
# backend/ticketing_agent/tools/design_verify/validate_qualified_names.py
"""validate_qualified_names tool: validate qname format and existence."""

import json

from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
from backend.ticketing_agent.tools.helpers.qname import qname_resolves

SCHEMA = {
    "name": "validate_qualified_names",
    "description": (
        "Validate a list of qualified names against format rules and the "
        "design context (draft + persistent). Checks for: invalid prefixes, "
        "bare lowercase identifiers, dot separators, and existence. Use this "
        "to verify your references before calling commit_design_and_verifications."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "qualified_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of qualified names to validate.",
            },
        },
        "required": ["qualified_names"],
    },
}


def handle(ctx, tool_input: dict) -> str:
    """Validate qualified name format and existence against draft + Neo4j."""
    qnames = tool_input.get("qualified_names", [])
    results = []
    for qn in qnames:
        result_entry = {
            "qname": qn,
            "valid": True,
            "exists": None,
            "source": None,
            "error": None,
            "correction": None,
        }

        # Format validation
        is_valid, corrected = _is_valid_verification_qname(qn)
        if not is_valid:
            result_entry["valid"] = False
            result_entry["error"] = f"Invalid qualified name format: {qn}"
            results.append(result_entry)
            continue
        elif corrected:
            result_entry["correction"] = corrected

        resolved_qn = corrected if corrected else qn

        # Check draft first
        found_in_draft = resolved_qn in ctx.draft_lookup
        if found_in_draft:
            result_entry["exists"] = True
            result_entry["source"] = "draft"
        elif ctx.neo4j_session is not None:
            from backend.db.neo4j.repositories.design import DesignRepository
            repo = DesignRepository(ctx.neo4j_session)
            nodes = repo.find_nodes(search=resolved_qn, exclude_source_types=["verification"])
            found = any(n.qualified_name == resolved_qn for n in nodes)
            # Also check parent class for member references
            if not found and "::" in resolved_qn:
                parts = resolved_qn.rsplit("::", 2)
                if len(parts) >= 2:
                    class_qname = "::".join(parts[:-1]) if len(parts) == 3 else resolved_qn
                    found = any(n.qualified_name == class_qname for n in nodes)
            result_entry["exists"] = found
            result_entry["source"] = "persistent" if found else None
        else:
            result_entry["exists"] = found_in_draft
            result_entry["source"] = "draft" if found_in_draft else None

        results.append(result_entry)
    return json.dumps({"results": results})
```

- [ ] **Step 2: Create lookup_design_element.py**

```python
# backend/ticketing_agent/tools/design_verify/lookup_design_element.py
"""lookup_design_element tool: search for design elements in draft + Neo4j."""

import json

SCHEMA = {
    "name": "lookup_design_element",
    "description": (
        "Search for design elements in the current draft and persistent "
        "ontology graph by name or qualified name. Returns matching elements "
        "with their qualified names, kind, description, and source (draft or "
        "persistent). Use this to find the correct qualified name for a class, "
        "method, or attribute before referencing it in conditions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Name or qualified name to search for. Supports "
                    "substring matching."
                ),
            },
            "kind": {
                "type": "string",
                "description": "Optional kind filter: 'class', 'interface', 'enum', 'method', 'attribute'.",
            },
        },
        "required": ["name"],
    },
}


def handle(ctx, tool_input: dict) -> str:
    """Search draft and Neo4j (excluding verification stubs) for matching elements."""
    name = tool_input.get("name", "")
    kind = tool_input.get("kind")
    if not name:
        return json.dumps({"elements": []})

    elements = []
    name_lower = name.lower()

    # Search draft
    if ctx.draft_lookup:
        for qname, info in ctx.draft_lookup.items():
            if name_lower in qname.lower() or name_lower in info.get("description", "").lower():
                if kind and info.get("kind") != kind:
                    continue
                elements.append(info.copy())

    # Search Neo4j (excluding verification stubs)
    if ctx.neo4j_session is not None:
        from backend.db.neo4j.repositories.design import DesignRepository
        repo = DesignRepository(ctx.neo4j_session)
        nodes = repo.find_nodes(
            search=name,
            kind=kind if kind in ("class", "interface", "enum") else None,
            exclude_source_types=["verification"],
        )
        for node in nodes[:20]:
            # Skip if already found in draft (draft takes priority)
            if node.qualified_name in ctx.draft_lookup:
                continue
            elements.append({
                "qualified_name": node.qualified_name,
                "kind": node.kind,
                "description": node.description or "",
                "source": "persistent",
                **({"is_intercomponent": True} if node.is_intercomponent else {}),
            })

    # Deduplicate by qualified name and limit
    seen = set()
    deduped = []
    for e in elements:
        qn = e["qualified_name"]
        if qn not in seen:
            seen.add(qn)
            deduped.append(e)
    return json.dumps({"elements": deduped[:20]})
```

- [ ] **Step 3: Commit**

```bash
git add backend/ticketing_agent/tools/design_verify/validate_qualified_names.py backend/ticketing_agent/tools/design_verify/lookup_design_element.py
git commit -m "feat: add validate_qualified_names and lookup_design_element handlers"
```

---

### Task 10: Create draft_verifications and commit handlers

**Files:**
- Create: `backend/ticketing_agent/tools/design_verify/draft_verifications.py`
- Create: `backend/ticketing_agent/tools/design_verify/commit.py`

- [ ] **Step 1: Create draft_verifications.py**

```python
# backend/ticketing_agent/tools/design_verify/draft_verifications.py
"""draft_verifications tool: submit/revise verification procedures with reference validation."""

import json

from backend.requirements.schemas import VerificationSchema
from backend.ticketing_agent.tools.helpers.qname import qname_resolves, suggest_qname

SCHEMA = {
    "name": "draft_verifications",
    "description": (
        "Submit or revise verification procedures for LLRs. Validates all "
        "qualified name references against the current design draft and "
        "design context (prior classes, dependency APIs, intercomponent). "
        "Returns a validation report showing which references resolved and "
        "which didn't, with suggestions for corrections. Use this after "
        "drafting your design to iteratively resolve verification stub "
        "references before committing."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verifications": {
                "type": "object",
                "description": (
                    "Map of LLR ID (integer string) to list of verification "
                    "procedures. Keys MUST be LLR IDs like \"1\", \"2\" \u2014 "
                    "NOT test names."
                ),
                "additionalProperties": {
                    "type": "array",
                    "items": VerificationSchema.model_json_schema(),
                },
            },
        },
        "required": ["verifications"],
    },
}


def handle(ctx, tool_input: dict) -> str:
    """Parse, validate, and store drafted verifications."""
    verifs_input = tool_input.get("verifications", {})
    if not verifs_input:
        return json.dumps({"valid": False, "errors": ["No verifications provided"]})

    parsed: dict[int, list[VerificationSchema]] = {}
    parse_errors = []
    for llr_id_str, v_list in verifs_input.items():
        try:
            llr_id = int(llr_id_str)
        except (ValueError, TypeError):
            parse_errors.append(f"Non-integer LLR ID key: '{llr_id_str}'")
            continue
        parsed[llr_id] = []
        for v in v_list:
            try:
                parsed[llr_id].append(VerificationSchema.model_validate(v))
            except Exception as e:
                parse_errors.append(f"LLR {llr_id_str}: invalid verification: {e}")

    if parse_errors:
        return json.dumps({"valid": False, "errors": parse_errors})

    # Validate all qname references
    warnings = []
    unresolved_details = []
    verification_summary = {}

    # Warn if no design draft exists
    if not ctx.draft_design:
        warnings.append(
            "No design draft exists. Verification references cannot be "
            "validated against design elements. Call draft_design first."
        )

    for llr_id, verifs in parsed.items():
        llr_key = str(llr_id)
        resolved = 0
        total = 0
        for v in verifs:
            test_label = v.test_name or v.method
            for cond in v.preconditions + v.postconditions:
                if cond.subject_qualified_name:
                    total += 1
                    if qname_resolves(
                        cond.subject_qualified_name,
                        ctx.draft_lookup, ctx.prior_class_lookup,
                        ctx.dep_lookup, ctx.intercomponent_classes,
                        ctx.neo4j_session,
                    ):
                        resolved += 1
                    else:
                        suggestion = suggest_qname(
                            cond.subject_qualified_name,
                            ctx.draft_lookup, ctx.prior_class_lookup,
                            ctx.dep_lookup, ctx.intercomponent_classes,
                        )
                        detail = {
                            "llr_id": llr_key,
                            "verification": test_label,
                            "field": "subject_qualified_name",
                            "value": cond.subject_qualified_name,
                        }
                        if suggestion:
                            detail["suggestion"] = suggestion
                        unresolved_details.append(detail)
                if cond.object_qualified_name:
                    total += 1
                    if qname_resolves(
                        cond.object_qualified_name,
                        ctx.draft_lookup, ctx.prior_class_lookup,
                        ctx.dep_lookup, ctx.intercomponent_classes,
                        ctx.neo4j_session,
                    ):
                        resolved += 1
                    else:
                        suggestion = suggest_qname(
                            cond.object_qualified_name,
                            ctx.draft_lookup, ctx.prior_class_lookup,
                            ctx.dep_lookup, ctx.intercomponent_classes,
                        )
                        detail = {
                            "llr_id": llr_key,
                            "verification": test_label,
                            "field": "object_qualified_name",
                            "value": cond.object_qualified_name,
                        }
                        if suggestion:
                            detail["suggestion"] = suggestion
                        unresolved_details.append(detail)
                # Warn about missing operator
                if not cond.operator or cond.operator == "":
                    warnings.append(
                        f"LLR {llr_key} '{test_label}': condition on "
                        f"'{cond.subject_qualified_name}' has no operator \u2014 "
                        f"will default to '=='"
                    )
                # Warn about expected_value that looks like a qname
                if cond.expected_value and "::" in cond.expected_value:
                    warnings.append(
                        f"LLR {llr_key} '{test_label}': expected_value "
                        f"'{cond.expected_value}' contains '::' \u2014 if this "
                        f"references a design member, move it to "
                        f"object_qualified_name and use the display text "
                        f"as expected_value instead"
                    )
            for action in v.actions:
                if action.callee_qualified_name:
                    total += 1
                    if qname_resolves(
                        action.callee_qualified_name,
                        ctx.draft_lookup, ctx.prior_class_lookup,
                        ctx.dep_lookup, ctx.intercomponent_classes,
                        ctx.neo4j_session,
                    ):
                        resolved += 1
                    else:
                        suggestion = suggest_qname(
                            action.callee_qualified_name,
                            ctx.draft_lookup, ctx.prior_class_lookup,
                            ctx.dep_lookup, ctx.intercomponent_classes,
                        )
                        detail = {
                            "llr_id": llr_key,
                            "verification": test_label,
                            "field": "callee_qualified_name",
                            "value": action.callee_qualified_name,
                        }
                        if suggestion:
                            detail["suggestion"] = suggestion
                        unresolved_details.append(detail)
                # Warn about unqualified caller references
                if action.caller_qualified_name and "::" not in action.caller_qualified_name:
                    warnings.append(
                        f"LLR {llr_key} '{test_label}': caller "
                        f"'{action.caller_qualified_name}' is not a "
                        f"qualified name \u2014 leave empty if the caller is "
                        f"the test harness"
                    )

        verification_summary[llr_key] = {
            "methods": len(verifs),
            "resolved_references": resolved,
            "unresolved_references": total - resolved,
        }

    # Store drafted verifications
    ctx.draft_verifications = parsed

    errors = [
        f"Unresolved reference: '{d['value']}'"
        + (f" Did you mean '{d['suggestion']}'?" if "suggestion" in d else "")
        for d in unresolved_details
    ]

    return json.dumps({
        "valid": len(unresolved_details) == 0 and len(parse_errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "verification_summary": verification_summary,
        "unresolved_details": unresolved_details,
    })
```

- [ ] **Step 2: Create commit.py**

```python
# backend/ticketing_agent/tools/design_verify/commit.py
"""commit_design_and_verifications tool: atomically commit design + verifications."""

import json

from backend.codebase.schemas import DesignAndVerificationSchema
from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
from backend.ticketing_agent.tools.helpers.commit_schema import commit_tool_schema
from backend.ticketing_agent.tools.helpers.design_validation import validate_oo_design
from backend.ticketing_agent.tools.helpers.draft_state import build_draft_lookup
from backend.ticketing_agent.tools.helpers.qname import qname_resolves, suggest_qname

SCHEMA = commit_tool_schema()


def handle(ctx, tool_input: dict) -> str:
    """Validate and commit the final design + verifications."""
    try:
        schema = DesignAndVerificationSchema.model_validate(tool_input)
    except Exception as e:
        return json.dumps({"committed": False, "errors": [f"Invalid input format: {e}"]})

    errors = []

    # 1. Design validation
    design_errors = validate_oo_design(
        schema.oo_design,
        prior_class_lookup=ctx.prior_class_lookup,
        dependency_lookup=ctx.dep_lookup,
        intercomponent_classes=ctx.intercomponent_classes,
    )
    errors.extend(design_errors)

    # 2. QName validation across all verifications
    all_qnames = _collect_verification_qnames(schema, errors)

    # 3. Existence check for all referenced qnames
    commit_lookup = build_draft_lookup(schema.oo_design)
    for qn in all_qnames:
        if qname_resolves(qn, commit_lookup, ctx.prior_class_lookup, ctx.dep_lookup, ctx.intercomponent_classes, ctx.neo4j_session):
            continue
        suggestion = suggest_qname(qn, commit_lookup, ctx.prior_class_lookup, ctx.dep_lookup, ctx.intercomponent_classes)
        error_msg = f"Unresolved reference: '{qn}' does not exist in the design context."
        if suggestion:
            error_msg += f" Did you mean '{suggestion}'?"
        errors.append(error_msg)

    if errors:
        return json.dumps({"committed": False, "errors": errors})

    return json.dumps({
        "committed": True,
        "oo_design": schema.oo_design.model_dump(),
        "verifications": {
            str(k): [v.model_dump() for v in vs] for k, vs in schema.verifications.items()
        },
    })


def _collect_verification_qnames(schema, errors: list[str]) -> set[str]:
    """Collect all qname references from verifications and validate object_qualified_name format."""
    all_qnames = set()
    for llr_id, verifs in schema.verifications.items():
        for v in verifs:
            for cond in v.preconditions + v.postconditions:
                if cond.subject_qualified_name:
                    all_qnames.add(cond.subject_qualified_name)
                if cond.object_qualified_name:
                    is_valid, _ = _is_valid_verification_qname(cond.object_qualified_name)
                    if not is_valid:
                        errors.append(
                            f"LLR {llr_id}: Invalid object_qualified_name "
                            f"in condition: '{cond.object_qualified_name}'. "
                            f"Use expected_value for literal values."
                        )
            for action in v.actions:
                if action.caller_qualified_name:
                    all_qnames.add(action.caller_qualified_name)
                if action.callee_qualified_name:
                    all_qnames.add(action.callee_qualified_name)
    return all_qnames
```

- [ ] **Step 3: Commit**

```bash
git add backend/ticketing_agent/tools/design_verify/draft_verifications.py backend/ticketing_agent/tools/design_verify/commit.py
git commit -m "feat: add draft_verifications and commit handlers"
```

---

### Task 11: Create the CombinedDispatcher and package init

**Files:**
- Create: `backend/ticketing_agent/tools/design_verify/__init__.py`
- Create: `backend/ticketing_agent/tools/design_verify/dispatcher.py`

- [ ] **Step 1: Create dispatcher.py**

```python
# backend/ticketing_agent/tools/design_verify/dispatcher.py
"""Combined design+verify tool dispatcher.

Creates a ToolDispatcher with all design, verification, and discovery
tools registered. Maintains in-memory draft state between tool calls.
"""

from backend.codebase.schemas import OODesignSchema
from backend.requirements.schemas import VerificationSchema
from backend.ticketing_agent.tools import ToolDispatcher

# Handler imports
from backend.ticketing_agent.tools.design_verify.draft_design import (
    SCHEMA as DRAFT_DESIGN_SCHEMA, handle as handle_draft_design,
)
from backend.ticketing_agent.tools.design_verify.validate_design import (
    SCHEMA as VALIDATE_DESIGN_SCHEMA, handle as handle_validate_design,
)
from backend.ticketing_agent.tools.design_verify.check_class_name import (
    SCHEMA as CHECK_CLASS_NAME_SCHEMA, handle as handle_check_class_name,
)
from backend.ticketing_agent.tools.design_verify.find_mechanism import (
    SCHEMA as FIND_MECHANISM_SCHEMA, handle as handle_find_mechanism,
)
from backend.ticketing_agent.tools.design_verify.validate_qualified_names import (
    SCHEMA as VALIDATE_QNAMES_SCHEMA, handle as handle_validate_qualified_names,
)
from backend.ticketing_agent.tools.design_verify.lookup_design_element import (
    SCHEMA as LOOKUP_DESIGN_ELEMENT_SCHEMA, handle as handle_lookup_design_element,
)
from backend.ticketing_agent.tools.design_verify.draft_verifications import (
    SCHEMA as DRAFT_VERIFICATIONS_SCHEMA, handle as handle_draft_verifications,
)
from backend.ticketing_agent.tools.design_verify.commit import (
    SCHEMA as COMMIT_SCHEMA, handle as handle_commit,
)

# Discovery handler
from backend.ticketing_agent.tools.helpers.discovery import discover_tool_dispatch

# Discovery schemas
from backend.ticketing_agent.tools.utilities.list_sources import SCHEMA as LIST_SOURCES_SCHEMA
from backend.ticketing_agent.tools.utilities.search_symbols import SCHEMA as SEARCH_SYMBOLS_SCHEMA
from backend.ticketing_agent.tools.utilities.get_compound import SCHEMA as GET_COMPOUND_SCHEMA
from backend.ticketing_agent.tools.utilities.browse_namespace import SCHEMA as BROWSE_NAMESPACE_SCHEMA
from backend.ticketing_agent.tools.utilities.find_inheritance import SCHEMA as FIND_INHERITANCE_SCHEMA


class CombinedDispatcher(ToolDispatcher):
    """Tool dispatcher for the combined design+verify agent loop.

    Maintains in-memory draft state between tool calls and provides
    access to shared context (prior classes, dependencies, Neo4j).

    Usage::

        dispatcher = CombinedDispatcher(
            prior_class_lookup=cls_lookup,
            dependency_lookup=dep_lookup,
            neo4j_session=session,
        )
        result = call_tool_loop(
            ...,
            tools=dispatcher.all_tool_schemas,
            tool_dispatcher=dispatcher.dispatch,
        )
    """

    def __init__(
        self,
        prior_class_lookup: dict[str, str],
        dependency_lookup: dict[str, str] | None = None,
        intercomponent_classes: list[dict] | None = None,
        neo4j_session=None,
        toolset=None,
    ):
        super().__init__()
        # --- Immutable context ---
        self.prior_class_lookup = prior_class_lookup
        self.dep_lookup = dict(dependency_lookup or {})
        self.intercomponent_classes = intercomponent_classes or []
        self.neo4j_session = neo4j_session
        self.toolset = toolset

        # --- Mutable draft state ---
        self.draft_design: OODesignSchema | None = None
        self.draft_lookup: dict[str, dict] = {}
        self.draft_verifications: dict[int, list[VerificationSchema]] = {}

        # --- Register all handlers ---
        self._register_design_tools()
        self._register_verification_tools()
        self._register_discovery_tools()

    def _register_design_tools(self):
        self.register("draft_design", DRAFT_DESIGN_SCHEMA,
                       lambda inp: handle_draft_design(self, inp))
        self.register("validate_design", VALIDATE_DESIGN_SCHEMA,
                       lambda inp: handle_validate_design(self, inp))
        self.register("check_class_name", CHECK_CLASS_NAME_SCHEMA,
                       lambda inp: handle_check_class_name(self, inp))
        self.register("find_mechanism", FIND_MECHANISM_SCHEMA,
                       lambda inp: handle_find_mechanism(self, inp))

    def _register_verification_tools(self):
        self.register("validate_qualified_names", VALIDATE_QNAMES_SCHEMA,
                       lambda inp: handle_validate_qualified_names(self, inp))
        self.register("lookup_design_element", LOOKUP_DESIGN_ELEMENT_SCHEMA,
                       lambda inp: handle_lookup_design_element(self, inp))
        self.register("draft_verifications", DRAFT_VERIFICATIONS_SCHEMA,
                       lambda inp: handle_draft_verifications(self, inp))
        self.register("commit_design_and_verifications", COMMIT_SCHEMA,
                       lambda inp: handle_commit(self, inp))

    def _register_discovery_tools(self):
        self.register("list_sources", LIST_SOURCES_SCHEMA,
                       lambda inp: discover_tool_dispatch("list_sources", inp, self.toolset))
        self.register("search_symbols", SEARCH_SYMBOLS_SCHEMA,
                       lambda inp: discover_tool_dispatch("search_symbols", inp, self.toolset))
        self.register("get_compound", GET_COMPOUND_SCHEMA,
                       lambda inp: discover_tool_dispatch("get_compound", inp, self.toolset))
        self.register("browse_namespace", BROWSE_NAMESPACE_SCHEMA,
                       lambda inp: discover_tool_dispatch("browse_namespace", inp, self.toolset))
        self.register("find_inheritance", FIND_INHERITANCE_SCHEMA,
                       lambda inp: discover_tool_dispatch("find_inheritance", inp, self.toolset))
```

- [ ] **Step 2: Create __init__.py**

```python
# backend/ticketing_agent/tools/design_verify/__init__.py
"""Combined design+verify tool dispatcher package."""

from backend.ticketing_agent.tools.design_verify.dispatcher import CombinedDispatcher

__all__ = ["CombinedDispatcher"]
```

- [ ] **Step 3: Commit**

```bash
git add backend/ticketing_agent/tools/design_verify/dispatcher.py backend/ticketing_agent/tools/design_verify/__init__.py
git commit -m "feat: add CombinedDispatcher with all tool registrations"
```

---

### Task 12: Update callers — combined_loop.py and design_oo_tools.py

**Files:**
- Modify: `backend/ticketing_agent/design_verify/combined_loop.py`
- Modify: `backend/ticketing_agent/design/design_oo_tools.py`

- [ ] **Step 1: Update combined_loop.py imports**

In `backend/ticketing_agent/design_verify/combined_loop.py`, change the import and usage lines:

**Before:**
```python
from backend.ticketing_agent.design_verify.combined_tools import (
    ALL_TOOLS,
    make_combined_dispatcher,
)
```

**After:**
```python
from backend.ticketing_agent.tools.design_verify import CombinedDispatcher
```

**Before:**
```python
    dispatcher = make_combined_dispatcher(
        prior_class_lookup=prior_class_lookup or {},
        dependency_lookup=dep_lookup,
        intercomponent_classes=intercomponent_classes or [],
        neo4j_session=neo4j_session,
        toolset=toolset,
    )
```

**After:**
```python
    dispatcher = CombinedDispatcher(
        prior_class_lookup=prior_class_lookup or {},
        dependency_lookup=dep_lookup,
        intercomponent_classes=intercomponent_classes or [],
        neo4j_session=neo4j_session,
        toolset=toolset,
    )
```

**Before:**
```python
    result = call_tool_loop(
        system=system,
        messages=messages,
        tools=ALL_TOOLS,
        final_tool_name="commit_design_and_verifications",
        tool_dispatcher=dispatcher,
```

**After:**
```python
    result = call_tool_loop(
        system=system,
        messages=messages,
        tools=dispatcher.all_tool_schemas,
        final_tool_name="commit_design_and_verifications",
        tool_dispatcher=dispatcher.dispatch,
```

Also remove the import of `_validate_oo_design` from `design_oo_tools`:

**Before:**
```python
from backend.ticketing_agent.design.design_oo_tools import _validate_oo_design
```

**After:**
```python
from backend.ticketing_agent.tools.helpers.design_validation import validate_oo_design
```

And update all references in this file from `_validate_oo_design` to `validate_oo_design`.

- [ ] **Step 2: Update design_oo_tools.py imports**

In `backend/ticketing_agent/design/design_oo_tools.py`, replace the local `_validate_oo_design` and `_extract_type_refs` definitions with imports from the new location. Remove the full function definitions (approximately lines 260–455) and add:

**After existing imports, add:**
```python
from backend.ticketing_agent.tools.helpers.design_validation import validate_oo_design, extract_type_refs
```

**Then replace all references:**
- `_validate_oo_design(` → `validate_oo_design(`
- `_extract_type_refs(` → `extract_type_refs(`

- [ ] **Step 3: Run tests to verify nothing broke**

Run: `cd /Users/danielnewman/dev/Doxygen-Dependency-Parser && python -m pytest tests/ -k "design_oo or combined" -v`
Expected: All tests that reference the old paths should pass (some might need import updates)

- [ ] **Step 4: Commit**

```bash
git add backend/ticketing_agent/design_verify/combined_loop.py backend/ticketing_agent/design/design_oo_tools.py
git commit -m "feat: update callers to use new CombinedDispatcher and shared helpers"
```

---

### Task 13: Delete combined_tools.py and add handler unit tests

**Files:**
- Delete: `backend/ticketing_agent/design_verify/combined_tools.py`
- Create: `tests/test_combined_handlers.py`

- [ ] **Step 1: Delete combined_tools.py**

```bash
rm backend/ticketing_agent/design_verify/combined_tools.py
```

- [ ] **Step 2: Write handler unit tests**

```python
# tests/test_combined_handlers.py
"""Unit tests for individual tool handlers in the design_verify package."""

import json
import pytest
from unittest.mock import MagicMock

from backend.codebase.schemas import OODesignSchema, ClassDefinition, AttributeDefinition


class MockContext:
    """Lightweight mock of CombinedDispatcher for testing individual handlers."""
    def __init__(
        self,
        prior_class_lookup=None,
        dep_lookup=None,
        intercomponent_classes=None,
        neo4j_session=None,
        toolset=None,
        draft_lookup=None,
        draft_design=None,
    ):
        self.prior_class_lookup = prior_class_lookup or {}
        self.dep_lookup = dep_lookup or {}
        self.intercomponent_classes = intercomponent_classes or []
        self.neo4j_session = neo4j_session
        self.toolset = toolset
        self.draft_lookup = draft_lookup or {}
        self.draft_design = draft_design
        self.draft_verifications = {}


class TestCheckClassName:
    def test_empty_name_returns_not_found(self):
        from backend.ticketing_agent.tools.design_verify.check_class_name import handle
        ctx = MockContext()
        result = json.loads(handle(ctx, {"name": ""}))
        assert result["found"] is False
        assert result["matches"] == []

    def test_finds_in_prior_class_lookup(self):
        from backend.ticketing_agent.tools.design_verify.check_class_name import handle
        ctx = MockContext(prior_class_lookup={"Calculator": "calc::Calculator"})
        result = json.loads(handle(ctx, {"name": "Calculator"}))
        assert result["found"] is True
        assert any(m["source"] == "prior_design" for m in result["matches"])

    def test_finds_in_dep_lookup(self):
        from backend.ticketing_agent.tools.design_verify.check_class_name import handle
        ctx = MockContext(dep_lookup={"Fl_Window": "fltk::Fl_Window"})
        result = json.loads(handle(ctx, {"name": "Fl_Window"}))
        assert result["found"] is True
        assert any(m["source"] == "dependency" for m in result["matches"])

    def test_finds_in_draft_lookup(self):
        from backend.ticketing_agent.tools.design_verify.check_class_name import handle
        ctx = MockContext(draft_lookup={
            "calc::Calculator": {"qualified_name": "calc::Calculator", "kind": "class", "description": "", "source": "draft"},
        })
        result = json.loads(handle(ctx, {"name": "Calculator"}))
        assert result["found"] is True
        assert any(m["source"] == "draft" for m in result["matches"])


class TestFindMechanism:
    def test_empty_query_returns_empty(self):
        from backend.ticketing_agent.tools.design_verify.find_mechanism import handle
        ctx = MockContext()
        result = json.loads(handle(ctx, {"query": ""}))
        assert result == {"containers": []}

    def test_finds_in_dep_lookup(self):
        from backend.ticketing_agent.tools.design_verify.find_mechanism import handle
        ctx = MockContext(dep_lookup={"vector": "std::vector"})
        result = json.loads(handle(ctx, {"query": "vector"}))
        assert len(result["containers"]) == 1
        assert result["containers"][0]["qualified_name"] == "std::vector"


class TestDraftDesign:
    def test_invalid_schema_returns_error(self):
        from backend.ticketing_agent.tools.design_verify.draft_design import handle
        ctx = MockContext()
        result = json.loads(handle(ctx, {"design": {}}))
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_valid_design_stores_draft(self):
        from backend.ticketing_agent.tools.design_verify.draft_design import handle
        ctx = MockContext()
        design = {
            "classes": [
                {
                    "name": "Calculator",
                    "module": "calc",
                    "description": "Calculator class",
                    "attributes": [],
                    "methods": [],
                },
            ],
            "interfaces": [],
            "enums": [],
            "associations": [],
        }
        result = json.loads(handle(ctx, {"design": design}))
        assert result["valid"] is True
        assert ctx.draft_design is not None
        assert ctx.draft_lookup != {}


class TestToolDispatcher:
    def test_dispatch_unknown_returns_error(self):
        from backend.ticketing_agent.tools import ToolDispatcher
        d = ToolDispatcher()
        result = json.loads(d.dispatch("nonexistent", {}))
        assert "error" in result

    def test_register_and_dispatch(self):
        from backend.ticketing_agent.tools import ToolDispatcher
        d = ToolDispatcher()
        d.register("test", {"name": "test"}, lambda inp: json.dumps({"ok": True, "input": inp}))
        result = json.loads(d.dispatch("test", {"x": 1}))
        assert result["ok"] is True
        assert result["input"] == {"x": 1}

    def test_all_tool_schemas(self):
        from backend.ticketing_agent.tools import ToolDispatcher
        d = ToolDispatcher()
        d.register("a", {"name": "a"}, lambda inp: "")
        d.register("b", {"name": "b"}, lambda inp: "")
        assert [s["name"] for s in d.all_tool_schemas] == ["a", "b"]
```

- [ ] **Step 3: Run the new tests**

Run: `cd /Users/danielnewman/dev/Doxygen-Dependency-Parser && python -m pytest tests/test_tool_dispatcher.py tests/test_combined_handlers.py -v`
Expected: All pass

- [ ] **Step 4: Run full test suite**

Run: `cd /Users/danielnewman/dev/Doxygen-Dependency-Parser && python -m pytest tests/ -v --tb=short`
Expected: All existing tests pass. No import errors from removed `combined_tools.py`.

- [ ] **Step 5: Commit**

```bash
git rm backend/ticketing_agent/design_verify/combined_tools.py
git add tests/test_tool_dispatcher.py tests/test_combined_handlers.py
git commit -m "feat: delete combined_tools.py, add handler unit tests"
```

---

### Task 14: Final integration test

- [ ] **Step 1: Run the full test suite**

Run: `cd /Users/danielnewman/dev/Doxygen-Dependency-Parser && python -m pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 2: Verify imports work correctly**

Run: `cd /Users/danielnewman/dev/Doxygen-Dependency-Parser && python -c "from backend.ticketing_agent.tools.design_verify import CombinedDispatcher; print('CombinedDispatcher imported OK')"`
Expected: `CombinedDispatcher imported OK`

- [ ] **Step 3: Verify ALL_TOOLS equivalent**

Run: `cd /Users/danielnewman/dev/Doxygen-Dependency-Parser && python -c "
from backend.ticketing_agent.tools.design_verify import CombinedDispatcher
d = CombinedDispatcher(prior_class_lookup={})
schemas = d.all_tool_schemas
names = sorted(s['name'] for s in schemas)
expected = sorted([
    'list_sources', 'search_symbols', 'get_compound', 'browse_namespace', 'find_inheritance',
    'draft_design', 'validate_design', 'check_class_name', 'find_mechanism',
    'validate_qualified_names', 'lookup_design_element', 'draft_verifications',
    'commit_design_and_verifications',
])
assert names == expected, f'Mismatch: got {names}, expected {expected}'
print(f'All {len(names)} tools registered correctly: {names}')
"`
Expected: All 13 tools registered correctly

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: integration fixes from final testing"
```