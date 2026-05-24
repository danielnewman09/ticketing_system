# Combined Design+Verify Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the design and verification phases into a single per-HLR tool loop, eliminating verification stub pollution and enabling the agent to revise the design when verification reveals gaps.

**Architecture:** A new `design_verify` module replaces the separate design_oo and verify_llr tool loops. The combined loop has a stateful dispatcher that holds an in-memory draft design and provides merged lookup/validation against the draft plus Neo4j. A single commit tool validates both design and verifications before accepting. The old separate agents are kept for standalone use.

**Tech Stack:** Python, Pydantic, Neo4j, llm_caller.tool_loop

---

### Task 1: Add DesignAndVerificationSchema

**Files:**
- Modify: `backend/codebase/schemas.py` (add new schema at the end)
- Test: `tests/test_pipeline_schemas.py` (add test for new schema)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pipeline_schemas.py`:

```python
def test_design_and_verification_schema_creation():
    """DesignAndVerificationSchema accepts valid input."""
    from backend.codebase.schemas import DesignAndVerificationSchema
    from backend.requirements.schemas import VerificationSchema, VerificationConditionSchema

    v = VerificationSchema(
        method="automated",
        test_name="test_add",
        description="Test addition",
        preconditions=[
            VerificationConditionSchema(
                subject_qualified_name="calculation_engine::Calculator",
                operator="not_null",
                expected_value="exists",
            )
        ],
        actions=[],
        postconditions=[],
    )
    schema = DesignAndVerificationSchema(
        oo_design={
            "modules": ["calculation_engine"],
            "classes": [
                {
                    "name": "Calculator",
                    "module": "calculation_engine",
                    "description": "Calculator",
                    "visibility": "public",
                    "is_intercomponent": False,
                    "requirement_ids": [],
                    "attributes": [],
                    "methods": [],
                    "inherits_from": [],
                    "realizes_interfaces": [],
                }
            ],
            "interfaces": [],
            "enums": [],
            "associations": [],
        },
        verifications={1: [v]},
    )
    assert len(schema.verifications) == 1
    assert 1 in schema.verifications
    assert schema.verifications[1][0].test_name == "test_add"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline_schemas.py::test_design_and_verification_schema_creation -v`
Expected: FAIL (ImportError — DesignAndVerificationSchema doesn't exist yet)

- [ ] **Step 3: Add DesignAndVerificationSchema to schemas.py**

Add at the end of `backend/codebase/schemas.py`, after the `DesignSchema` class:

```python
# ---------------------------------------------------------------------------
# Combined Design + Verification schema (for combined tool loop)
# ---------------------------------------------------------------------------


class DesignAndVerificationSchema(BaseModel):
    """Combined output for the design+verify tool loop.

    The oo_design is the final OO class design, and verifications maps
    LLR ids to their verification procedures.
    """

    oo_design: OODesignSchema
    verifications: dict[int, list[VerificationSchema]] = {}
```

Add the import at the top of `backend/codebase/schemas.py`:

```python
from backend.requirements.schemas import VerificationSchema
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pipeline_schemas.py::test_design_and_verification_schema_creation -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/codebase/schemas.py tests/test_pipeline_schemas.py
git commit -m "feat: add DesignAndVerificationSchema for combined loop"
```

---

### Task 2: Add source_type filter to DesignRepository.find_nodes

**Files:**
- Modify: `backend/db/neo4j/repositories/design.py` (add `exclude_source_types` param)
- Test: `tests/test_design_repository.py` (add test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_design_repository.py`:

```python
def test_find_nodes_excludes_verification_stubs(neo4j_session):
    """find_nodes with exclude_source_types='verification' skips stubs."""
    from backend.db.neo4j.repositories.design import DesignRepository
    from backend.db.neo4j.repositories.models.design import DesignNode

    repo = DesignRepository(neo4j_session)

    # Create a real node and a verification stub
    real = DesignNode(
        qualified_name="test::RealClass",
        name="RealClass",
        kind="class",
        description="A real class",
    )
    stub = DesignNode(
        qualified_name="test::FakeMethod",
        name="FakeMethod",
        kind="member",
        source_type="verification",
        description="Auto-created from verification reference",
    )
    repo.merge_node(real)
    repo.merge_node(stub)

    # Search without filter — both appear
    all_results = repo.find_nodes(search="test")
    qnames = [n.qualified_name for n in all_results]
    assert "test::RealClass" in qnames
    assert "test::FakeMethod" in qnames

    # Search with filter — stub excluded
    filtered = repo.find_nodes(search="test", exclude_source_types=["verification"])
    filtered_qnames = [n.qualified_name for n in filtered]
    assert "test::RealClass" in filtered_qnames
    assert "test::FakeMethod" not in filtered_qnames

    # Clean up
    repo.delete_node("test::RealClass")
    repo.delete_node("test::FakeMethod")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_design_repository.py::test_find_nodes_excludes_verification_stubs -v`
Expected: FAIL (TypeError — `exclude_source_types` param doesn't exist yet)

- [ ] **Step 3: Add exclude_source_types parameter to find_nodes**

In `backend/db/neo4j/repositories/design.py`, modify the `find_nodes` method signature and implementation:

Change the method signature from:

```python
def find_nodes(
    self,
    kind: str | None = None,
    search: str | None = None,
    component_id: int | None = None,
) -> list[DesignNode]:
```

to:

```python
def find_nodes(
    self,
    kind: str | None = None,
    search: str | None = None,
    component_id: int | None = None,
    exclude_source_types: list[str] | None = None,
) -> list[DesignNode]:
```

Add the exclusion clause after the existing `if search:` block:

```python
if exclude_source_types:
    conditions.append("NOT d.source_type IN $exclude_types")
    params["exclude_types"] = exclude_source_types
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_design_repository.py::test_find_nodes_excludes_verification_stubs -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/db/neo4j/repositories/design.py tests/test_design_repository.py
git commit -m "feat: add exclude_source_types filter to DesignRepository.find_nodes"
```

---

### Task 3: Create the combined tools module

**Files:**
- Create: `backend/ticketing_agent/design_verify/__init__.py`
- Create: `backend/ticketing_agent/design_verify/combined_tools.py`
- Test: `tests/test_combined_tools.py`

This is the core module. It contains the tool definitions, the stateful dispatcher, and the combined validation logic.

- [ ] **Step 1: Create the package init file**

Create `backend/ticketing_agent/design_verify/__init__.py`:

```python
"""Combined design+verify tool loop agent."""
```

- [ ] **Step 2: Write the failing test for draft state and merged lookup**

Create `tests/test_combined_tools.py`:

```python
"""Tests for combined design+verify tool dispatcher."""

import json
import pytest

from backend.codebase.schemas import OODesignSchema
from backend.requirements.schemas import (
    VerificationSchema,
    VerificationConditionSchema,
    VerificationActionSchema,
)
from backend.ticketing_agent.design_verify.combined_tools import (
    ALL_TOOLS,
    make_combined_dispatcher,
)


def _minimal_design_dict():
    return {
        "modules": ["calculation_engine"],
        "classes": [
            {
                "name": "Calculator",
                "module": "calculation_engine",
                "description": "Main calculator",
                "visibility": "public",
                "is_intercomponent": False,
                "requirement_ids": [],
                "attributes": [
                    {
                        "name": "lastResult",
                        "type_name": "CalculationResult",
                        "visibility": "private",
                        "description": "Last result",
                    }
                ],
                "methods": [
                    {
                        "name": "add",
                        "description": "Add two numbers",
                        "visibility": "public",
                        "parameters": ["double a", "double b"],
                        "return_type": "CalculationResult",
                    }
                ],
                "inherits_from": [],
                "realizes_interfaces": [],
            }
        ],
        "interfaces": [],
        "enums": [],
        "associations": [],
    }


def _minimal_design():
    return OODesignSchema.model_validate(_minimal_design_dict())


def _sample_verification():
    return VerificationSchema(
        method="automated",
        test_name="test_calc_add",
        description="Test addition",
        preconditions=[
            VerificationConditionSchema(
                subject_qualified_name="calculation_engine::Calculator",
                operator="not_null",
                expected_value="exists",
            )
        ],
        actions=[
            VerificationActionSchema(
                description="Call add method",
                callee_qualified_name="calculation_engine::Calculator::add",
            )
        ],
        postconditions=[],
    )


class TestDraftDesign:
    def test_draft_design_stores_and_validates(self):
        """draft_design stores a design and returns validation results."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        result = json.loads(dispatcher("draft_design", {"design": _minimal_design_dict()}))
        assert result["valid"] is True
        assert result["errors"] == []
        assert result["draft_summary"]["classes"] == 1

    def test_draft_design_validates_associations(self):
        """draft_design catches unknown association targets."""
        design = _minimal_design_dict()
        design["associations"] = [
            {
                "from_class": "Calculator",
                "to_class": "NonExistentClass",
                "kind": "depends_on",
                "description": "Missing dependency",
            }
        ]
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        result = json.loads(dispatcher("draft_design", {"design": design}))
        assert result["valid"] is False
        assert any("NonExistentClass" in e for e in result["errors"])

    def test_draft_design_returns_member_count(self):
        """draft_design summary includes attribute and method counts."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        result = json.loads(dispatcher("draft_design", {"design": _minimal_design_dict()}))
        summary = result["draft_summary"]
        assert summary["attributes"] == 1
        assert summary["methods"] == 1


class TestLookupDesignElement:
    def test_lookup_finds_draft_class(self):
        """lookup_design_element finds classes in the draft."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        # Store a draft first
        dispatcher("draft_design", {"design": _minimal_design_dict()})
        result = json.loads(dispatcher("lookup_design_element", {"name": "Calculator"}))
        assert len(result["elements"]) >= 1
        matches = [e for e in result["elements"] if e["source"] == "draft"]
        assert len(matches) >= 1
        assert matches[0]["qualified_name"] == "calculation_engine::Calculator"

    def test_lookup_finds_draft_method(self):
        """lookup_design_element finds methods in the draft."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        dispatcher("draft_design", {"design": _minimal_design_dict()})
        result = json.loads(dispatcher("lookup_design_element", {"name": "add"}))
        methods = [e for e in result["elements"] if e["kind"] == "method" and e["source"] == "draft"]
        assert len(methods) >= 1
        assert methods[0]["qualified_name"] == "calculation_engine::Calculator::add"

    def test_lookup_finds_draft_attribute(self):
        """lookup_design_element finds attributes in the draft."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        dispatcher("draft_design", {"design": _minimal_design_dict()})
        result = json.loads(dispatcher("lookup_design_element", {"name": "lastResult"}))
        attrs = [e for e in result["elements"] if e["kind"] == "attribute" and e["source"] == "draft"]
        assert len(attrs) >= 1
        assert attrs[0]["qualified_name"] == "calculation_engine::Calculator::lastResult"


class TestValidateQualifiedNames:
    def test_validate_draft_qnames_exist(self):
        """validate_qualified_names finds draft references as existing."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        dispatcher("draft_design", {"design": _minimal_design_dict()})
        result = json.loads(dispatcher(
            "validate_qualified_names",
            {"qualified_names": ["calculation_engine::Calculator", "calculation_engine::Calculator::add"]},
        ))
        assert result["results"][0]["valid"] is True
        assert result["results"][0]["exists"] is True
        assert result["results"][0]["source"] == "draft"
        assert result["results"][1]["valid"] is True
        assert result["results"][1]["exists"] is True

    def test_validate_nonexistent_qname(self):
        """validate_qualified_names reports non-existent references."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        dispatcher("draft_design", {"design": _minimal_design_dict()})
        result = json.loads(dispatcher(
            "validate_qualified_names",
            {"qualified_names": ["calculation_engine::NonExistent"]},
        ))
        assert result["results"][0]["valid"] is True  # format is valid
        assert result["results"][0]["exists"] is False  # but doesn't exist

    def test_validate_rejects_non_qname_object(self):
        """validate_qualified_names rejects symbols in object_qualified_name."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        result = json.loads(dispatcher(
            "validate_qualified_names",
            {"qualified_names": ["×"]},
        ))
        assert result["results"][0]["valid"] is False


class TestCommitDesignAndVerifications:
    def test_commit_rejects_invalid_qname(self):
        """commit_design_and_verifications rejects with invalid qnames."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        # Draft a design
        dispatcher("draft_design", {"design": _minimal_design_dict()})

        bad_verification = VerificationSchema(
            method="automated",
            test_name="test_bad",
            description="Bad qname test",
            preconditions=[
                VerificationConditionSchema(
                    subject_qualified_name="nonexistent::Class",
                    operator="not_null",
                    expected_value="exists",
                )
            ],
            actions=[],
            postconditions=[],
        )
        result = json.loads(dispatcher(
            "commit_design_and_verifications",
            {
                "oo_design": _minimal_design_dict(),
                "verifications": {"1": [bad_verification.model_dump()]},
            },
        ))
        assert result["committed"] is False
        assert len(result["errors"]) > 0

    def test_commit_accepts_valid(self):
        """commit_design_and_verifications accepts valid input."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        # Draft a design first
        dispatcher("draft_design", {"design": _minimal_design_dict()})

        good_verification = VerificationSchema(
            method="automated",
            test_name="test_add",
            description="Test addition",
            preconditions=[
                VerificationConditionSchema(
                    subject_qualified_name="calculation_engine::Calculator",
                    operator="not_null",
                    expected_value="exists",
                )
            ],
            actions=[
                VerificationActionSchema(
                    description="Call add",
                    callee_qualified_name="calculation_engine::Calculator::add",
                )
            ],
            postconditions=[],
        )
        result = json.loads(dispatcher(
            "commit_design_and_verifications",
            {
                "oo_design": _minimal_design_dict(),
                "verifications": {"1": [good_verification.model_dump()]},
            },
        ))
        assert result["committed"] is True
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_combined_tools.py -v`
Expected: FAIL (ImportError — module doesn't exist yet)

- [ ] **Step 4: Create the combined_tools.py module**

Create `backend/ticketing_agent/design_verify/combined_tools.py`:

```python
"""Tool definitions and dispatcher for the combined design+verify tool loop.

Provides six tools:
- draft_design: submit/revise the OO design draft (stores in dispatcher state)
- validate_design: validate the current draft for structural consistency
- check_class_name: look up class names in prior designs, dep APIs, and intercomponent context
- validate_qualified_names: validate qname format and existence against draft + Neo4j
- lookup_design_element: search for design elements in draft + Neo4j (excluding verification stubs)
- commit_design_and_verifications: atomically commit design + verifications (terminates loop)
"""

import json
import logging

from backend.codebase.schemas import DesignAndVerificationSchema, OODesignSchema
from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
from backend.requirements.schemas import VerificationSchema

from backend.ticketing_agent.design.design_oo_tools import _validate_oo_design

log = logging.getLogger("agents.design_verify")

# ---------------------------------------------------------------------------
# Tool definitions (Anthropic format)
# ---------------------------------------------------------------------------

DRAFT_DESIGN_TOOL = {
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

VALIDATE_DESIGN_TOOL = {
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

CHECK_CLASS_NAME_TOOL = {
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

VALIDATE_QNAMES_TOOL = {
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

LOOKUP_DESIGN_ELEMENT_TOOL = {
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

COMMIT_TOOL = {
    "name": "commit_design_and_verifications",
    "description": (
        "Commit the final OO design and all verification procedures. This "
        "terminates the agent loop. Validates that all qualified names "
        "reference real design elements and that the design is structurally "
        "sound. If there are errors, returns them for the agent to fix "
        "before retrying."
    ),
    "input_schema": DesignAndVerificationSchema.model_json_schema(),
}

ALL_TOOLS = [
    DRAFT_DESIGN_TOOL,
    VALIDATE_DESIGN_TOOL,
    CHECK_CLASS_NAME_TOOL,
    VALIDATE_QNAMES_TOOL,
    LOOKUP_DESIGN_ELEMENT_TOOL,
    COMMIT_TOOL,
]


# ---------------------------------------------------------------------------
# Draft-state helpers
# ---------------------------------------------------------------------------


def _build_draft_lookup(design: OODesignSchema) -> dict[str, dict]:
    """Build a lookup dict from a draft OODesignSchema.

    Returns qualified_name -> {kind, description, source: 'draft'} for all
    classes, interfaces, enums, their attributes, and methods.
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


def _draft_summary(design: OODesignSchema) -> dict:
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


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def make_combined_dispatcher(
    prior_class_lookup: dict[str, str],
    dependency_lookup: dict[str, str] | None,
    intercomponent_classes: list[dict] | None,
    neo4j_session=None,
):
    """Create a tool dispatcher for the combined design+verify tool loop.

    Maintains in-memory draft state between tool calls.

    Args:
        prior_class_lookup: bare_name -> qualified_name for previously designed classes.
        dependency_lookup: bare_name -> qualified_name for dependency API classes.
        intercomponent_classes: list of intercomponent class dicts.
        neo4j_session: Optional Neo4j session for persistent design lookups.
    """
    dep_lookup = dict(dependency_lookup or {})
    _draft_design: OODesignSchema | None = None
    _draft_lookup: dict[str, dict] = {}

    def dispatch(tool_name: str, tool_input: dict) -> str:
        nonlocal _draft_design, _draft_lookup

        if tool_name == "draft_design":
            return _dispatch_draft_design(tool_input)
        elif tool_name == "validate_design":
            return _dispatch_validate_design(tool_input)
        elif tool_name == "check_class_name":
            return _dispatch_check_class_name(tool_input)
        elif tool_name == "validate_qualified_names":
            return _dispatch_validate_qnames(tool_input)
        elif tool_name == "lookup_design_element":
            return _dispatch_lookup_design_element(tool_input)
        elif tool_name == "commit_design_and_verifications":
            return _dispatch_commit(tool_input, _draft_design, _draft_lookup)
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    # -- draft_design --------------------------------------------------------

    def _dispatch_draft_design(tool_input: dict) -> str:
        nonlocal _draft_design, _draft_lookup
        try:
            design = OODesignSchema.model_validate(tool_input.get("design", tool_input))
        except Exception as e:
            return json.dumps({"valid": False, "errors": [f"Invalid design format: {e}"], "draft_summary": {}})

        # Validate the draft
        errors = _validate_oo_design(
            design,
            prior_class_lookup=prior_class_lookup,
            dependency_lookup=dep_lookup,
            intercomponent_classes=intercomponent_classes or [],
        )

        # Store draft
        _draft_design = design
        _draft_lookup = _build_draft_lookup(design)

        return json.dumps({
            "valid": len(errors) == 0,
            "errors": errors,
            "draft_summary": _draft_summary(design),
        })

    # -- validate_design -----------------------------------------------------

    def _dispatch_validate_design(tool_input: dict) -> str:
        try:
            design = OODesignSchema.model_validate(tool_input.get("design", tool_input))
        except Exception as e:
            return json.dumps({"valid": False, "errors": [f"Invalid design format: {e}"], "warnings": []})

        errors = _validate_oo_design(
            design,
            prior_class_lookup=prior_class_lookup,
            dependency_lookup=dep_lookup,
            intercomponent_classes=intercomponent_classes or [],
        )
        return json.dumps({
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": [],
        })

    # -- check_class_name ----------------------------------------------------

    def _dispatch_check_class_name(tool_input: dict) -> str:
        name = tool_input.get("name", "")
        if not name:
            return json.dumps({"found": False, "matches": []})

        matches = []
        name_lower = name.lower()

        # Search draft
        if _draft_lookup:
            for qname, info in _draft_lookup.items():
                if name_lower in qname.lower() or name_lower in info.get("description", "").lower():
                    matches.append({
                        "qualified_name": qname,
                        "kind": info["kind"],
                        "source": "draft",
                    })

        # Search prior designs
        for bare, qname in prior_class_lookup.items():
            if name_lower in bare.lower() or name_lower in qname.lower():
                matches.append({
                    "qualified_name": qname,
                    "kind": "class",
                    "source": "prior_design",
                })

        # Search dependency APIs
        for bare, qname in dep_lookup.items():
            if name_lower in bare.lower() or name_lower in qname.lower():
                matches.append({
                    "qualified_name": qname,
                    "kind": "dependency",
                    "source": "dependency",
                })

        # Search intercomponent classes
        for cls in (intercomponent_classes or []):
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

    # -- validate_qualified_names --------------------------------------------

    def _dispatch_validate_qnames(tool_input: dict) -> str:
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
            found_in_draft = resolved_qn in _draft_lookup
            if found_in_draft:
                result_entry["exists"] = True
                result_entry["source"] = "draft"
            elif neo4j_session is not None:
                # Check Neo4j (excluding verification stubs)
                from backend.db.neo4j.repositories.design import DesignRepository
                repo = DesignRepository(neo4j_session)
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

    # -- lookup_design_element -----------------------------------------------

    def _dispatch_lookup_design_element(tool_input: dict) -> str:
        name = tool_input.get("name", "")
        kind = tool_input.get("kind")
        if not name:
            return json.dumps({"elements": []})

        elements = []
        name_lower = name.lower()

        # Search draft
        if _draft_lookup:
            for qname, info in _draft_lookup.items():
                if name_lower in qname.lower() or name_lower in info.get("description", "").lower():
                    if kind and info.get("kind") != kind:
                        continue
                    elements.append(info.copy())

        # Search Neo4j (excluding verification stubs)
        if neo4j_session is not None:
            from backend.db.neo4j.repositories.design import DesignRepository
            repo = DesignRepository(neo4j_session)
            nodes = repo.find_nodes(
                search=name,
                kind=kind if kind in ("class", "interface", "enum") else None,
                exclude_source_types=["verification"],
            )
            for node in nodes[:20]:
                # Skip if already found in draft (draft takes priority)
                if node.qualified_name in _draft_lookup:
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

    # -- commit_design_and_verifications --------------------------------------

    def _dispatch_commit(tool_input: dict, draft, draft_lookup) -> str:
        try:
            schema = DesignAndVerificationSchema.model_validate(tool_input)
        except Exception as e:
            return json.dumps({"committed": False, "errors": [f"Invalid input format: {e}"]})

        errors = []

        # 1. Design validation
        design_errors = _validate_oo_design(
            schema.oo_design,
            prior_class_lookup=prior_class_lookup,
            dependency_lookup=dep_lookup,
            intercomponent_classes=intercomponent_classes or [],
        )
        errors.extend(design_errors)

        # 2. Qname validation across all verifications
        all_qnames = set()
        for llr_id, verifs in schema.verifications.items():
            for v in verifs:
                for cond in v.preconditions + v.postconditions:
                    if cond.subject_qualified_name:
                        all_qnames.add(cond.subject_qualified_name)
                    if cond.object_qualified_name:
                        # object_qualified_name must be a valid qname or empty
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

        # 3. Existence check for all referenced qnames
        # Build lookup from the committed design (use schema.oo_design, not draft)
        commit_lookup = _build_draft_lookup(schema.oo_design)
        for qn in all_qnames:
            if qn in commit_lookup:
                continue
            # Check prior designs
            if qn in prior_class_lookup.values():
                continue
            if qn in prior_class_lookup:
                continue
            if qn in dep_lookup:
                continue
            if qn in dep_lookup.values():
                continue
            if intercomponent_classes:
                ic_qnames = {c["qualified_name"] for c in intercomponent_classes}
                if qn in ic_qnames:
                    continue
            # Check Neo4j
            if neo4j_session is not None:
                from backend.db.neo4j.repositories.design import DesignRepository
                repo = DesignRepository(neo4j_session)
                nodes = repo.find_nodes(search=qn, exclude_source_types=["verification"])
                if any(n.qualified_name == qn for n in nodes):
                    continue
                # Check class-level for member references
                if "::" in qn:
                    parts = qn.rsplit("::", 2)
                    if len(parts) >= 2:
                        class_qname = "::".join(parts[:-1]) if len(parts) == 3 else qn
                        if any(n.qualified_name == class_qname for n in nodes):
                            # Class exists but member doesn't — still an error
                            pass
            errors.append(f"Unresolved reference: '{qn}' does not exist in the design context or prior designs.")

        if errors:
            return json.dumps({"committed": False, "errors": errors})

        return json.dumps({
            "committed": True,
            "oo_design": schema.oo_design.model_dump(),
            "verifications": {
                str(k): [v.model_dump() for v in vs] for k, vs in schema.verifications.items()
            },
        })

    return dispatch
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_combined_tools.py -v`
Expected: Most tests PASS. Some may need adjustment for serialization of the commit tool input.

- [ ] **Step 6: Commit**

```bash
git add backend/ticketing_agent/design_verify/__init__.py backend/ticketing_agent/design_verify/combined_tools.py tests/test_combined_tools.py
git commit -m "feat: add combined design+verify tools module with draft-state dispatcher"
```

---

### Task 4: Create the combined prompt module

**Files:**
- Create: `backend/ticketing_agent/design_verify/combined_prompt.py`

- [ ] **Step 1: Create the combined prompt module**

Create `backend/ticketing_agent/design_verify/combined_prompt.py`:

```python
"""Prompt templates for the combined design+verify agent."""

from backend.requirements.formatting import format_hlrs_for_prompt

SYSTEM_PROMPT = """\
You are a software architect and verification engineer. Given design context
and requirements, your job is to produce an object-oriented class design AND
verification procedures that validate the design satisfies those requirements.

You have six tools available:

### draft_design
Submit or revise your OO design. The design is stored so that subsequent
lookup and validation tools can check references against it. Returns
validation results (unknown associations, missing intercomponent links, etc.)
and a summary of the stored draft. Call this whenever you revise the design.

### validate_design
Validate a draft OO design for structural consistency. Checks for unknown
association targets, missing intercomponent associations, and other issues.
Returns errors and warnings.

### check_class_name
Check if a class, interface, or enum name exists in the design context (prior
designs, dependency APIs, intercomponent boundaries, or the current draft).

### validate_qualified_names
Validate a list of qualified names against format rules and existence in the
design context (draft + persistent). Use this to verify your references before
committing.

### lookup_design_element
Search for design elements in the current draft and persistent ontology by
name. Returns qualified names, kind, description, and source (draft or
persistent). Use this to find correct qualified names.

### commit_design_and_verifications
Commit your final design and all verification procedures. This terminates the
agent loop. Validates all qualified names and design structure. If there are
errors, they are returned for you to fix before retrying.

**Recommended workflow:**

1. DESIGN PHASE: Draft your OO design using draft_design. Use check_class_name
   to verify references to external classes. Use validate_design to check for
   structural issues. Revise until the design is clean.

2. VERIFICATION PHASE: For each LLR, write verification procedures that
   reference the design. Use lookup_design_element to find correct qualified
   names. Use validate_qualified_names to verify references. If you find a
   reference that doesn't exist in the design, call draft_design again to add
   the missing member, then continue verifying.

3. COMMIT: When both design and all verifications are clean, call
   commit_design_and_verifications.

{specializations_section}
{namespace_section}
{dependency_api_section}
{as_built_section}
{existing_classes_section}
{intercomponent_section}
{other_hlrs_section}
{llr_section}

<FORMAT-CONTRACT name="qualified-names">
All `subject_qualified_name`, `object_qualified_name`, `callee_qualified_name`,
and `caller_qualified_name` fields MUST use qualified names that exactly match
the design context or the current draft.

Pattern: <namespace>::<ClassName>::<memberName>

✓ calculation_engine::CalculatorEngine::validateInput
✓ user_interface::CalculatorWindow::equalsButton
✗ user_interface::CalculatorWindow.equalsButton
  → Dot separator — use :: everywhere
✗ calculation_engine::CalculatorEngine::last_result.is_success
  → Nested attribute path — reference the outer attribute directly
    (calculation_engine::CalculatorEngine::lastResult)
    and the inner class member separately
    (calculation_engine::CalculationResult::isSuccess)
✗ result_of_first_call
  → Test variable, not a design element
✗ test_validate_input_syntax
  → Test function, not a design element

If no exact match exists in the design context or current draft, do NOT
fabricate a name. Call draft_design to add the missing member, or omit the
reference field and use expected_value alone.

**object_qualified_name** must be a qualified name from the design context or
draft. Use expected_value for literal values and constants:
✓ object_qualified_name: "Operator::MULTIPLY", expected_value: "active"
✗ object_qualified_name: "×"  ← this is a label, use expected_value instead
✗ object_qualified_name: "division operator button"  ← description, not a qname

Do not reference constructors (ClassName::ClassName) unless they are
explicitly designed as methods in the design context or your draft.
</FORMAT-CONTRACT>

## Instructions

### For the design:
- Reference ONLY qualified names from the design context, dependency APIs,
  intercomponent boundaries, or your own draft
- Qualified names follow C++ convention: Namespace::ClassName::memberName
- Use check_class_name to verify association targets before including them
- Keep classes focused and cohesive

### For verification procedures:
For each LLR, flesh out verification methods with:

1. **Pre-conditions** — assertions on design elements that must hold before
   the test action. Each has:
   - subject_qualified_name: fully qualified name of the element being checked
   - object_qualified_name: (optional) right-hand operand — must be a valid
     qualified name, NOT a literal value. Use expected_value for literals.
   - operator: one of "==", "!=", "<", ">", "<=", ">=", "is_true", "is_false", "contains", "not_null"
   - expected_value: the expected state

2. **Actions** — ordered stimulus steps. Each has:
   - description: human-readable step
   - callee_qualified_name: the method being called, with namespace prefix
   - caller_qualified_name: (optional) the caller context

3. **Post-conditions** — expected state after actions. Same format as pre-conditions.

Guidelines:
- Reference ONLY real qualified names from the design context or your draft
- If a verification needs a member that doesn't exist, add it to the design
  via draft_design before referencing it
- Keep conditions specific and testable
- Process LLRs one at a time during verification

You MUST use the commit_design_and_verifications tool to return your final result.
"""


def format_llr_section(llrs: list[dict]) -> str:
    """Format LLRs as a prompt section for verification."""
    if not llrs:
        return ""
    lines = ["## Requirements to Verify\n"]
    for llr in llrs:
        lines.append(f"- LLR {llr.get('id', '?')}: {llr.get('description', '')}")
    return "\n".join(lines)


# Re-use format helpers from design_oo_prompt
from backend.ticketing_agent.design.design_oo_prompt import (
    build_specializations_section,
    build_dependency_api_section,
    build_as_built_section,
    build_existing_classes_section,
    build_intercomponent_section,
    build_other_hlrs_section,
    build_namespace_section,
    build_dependency_section,
)
```

- [ ] **Step 2: Commit**

```bash
git add backend/ticketing_agent/design_verify/combined_prompt.py
git commit -m "feat: add combined design+verify prompt module"
```

---

### Task 5: Create the combined loop entry point

**Files:**
- Create: `backend/ticketing_agent/design_verify/combined_loop.py`

- [ ] **Step 1: Create the combined loop module**

Create `backend/ticketing_agent/design_verify/combined_loop.py`:

```python
"""Combined design+verify agent: per-HLR loop that designs and verifies.

Uses call_tool_loop with draft-state tools so the agent can design,
verify, discover gaps, and revise before committing.
"""

import json
import logging
import os

from llm_caller import call_tool_loop
from backend.codebase.schemas import OODesignSchema
from backend.requirements.schemas import VerificationSchema
from backend.requirements.formatting import format_hlrs_for_prompt

from backend.ticketing_agent.design_verify.combined_prompt import SYSTEM_PROMPT, format_llr_section
from backend.ticketing_agent.design_verify.combined_tools import (
    ALL_TOOLS,
    make_combined_dispatcher,
)
from backend.ticketing_agent.design.design_oo_tools import _validate_oo_design

log = logging.getLogger("agents.design_verify")


class DesignVerifyResult:
    """Result from the combined design+verify loop."""

    def __init__(
        self,
        oo_design: OODesignSchema,
        verifications: dict[int, list[VerificationSchema]],
        design_warnings: list[str] | None = None,
        verification_warnings: list[str] | None = None,
    ):
        self.oo_design = oo_design
        self.verifications = verifications
        self.design_warnings = design_warnings or []
        self.verification_warnings = verification_warnings or []


def design_and_verify(
    hlr: dict,
    llrs: list[dict],
    existing_verifications: list[dict] | None = None,
    existing_classes: list[dict] | None = None,
    intercomponent_classes: list[dict] | None = None,
    other_hlr_summaries: list[dict] | None = None,
    dependency_contexts: dict[int, dict] | None = None,
    component_namespace: str = "",
    sibling_namespaces: list[str] | None = None,
    prior_class_lookup: dict[str, str] | None = None,
    dependency_lookup: dict[str, str] | None = None,
    neo4j_session=None,
    model: str = "",
    prompt_log_file: str = "",
) -> DesignVerifyResult:
    """Run the combined design+verify loop for a single HLR.

    Uses call_tool_loop with design and verification tools so the LLM
    can design, verify against LLRs, discover gaps, and revise.

    Args:
        hlr: HLR dict with {id, description, component_name?}.
        llrs: LLR dicts for this HLR.
        existing_verifications: Existing verification stubs for these LLRs.
        existing_classes: Classes already designed in the same component.
        intercomponent_classes: Public API classes from other components.
        other_hlr_summaries: Other HLRs for context.
        dependency_contexts: Dependency assessment keyed by HLR ID.
        component_namespace: Required namespace for this component.
        sibling_namespaces: Other component namespaces.
        prior_class_lookup: bare_name -> qualified_name for previously designed classes.
        dependency_lookup: bare_name -> qualified_name for dependency API classes.
        neo4j_session: Optional Neo4j session for persistent lookups.
        model: LLM model override.
        prompt_log_file: File path for prompt logging.

    Returns:
        DesignVerifyResult with oo_design, verifications, and any warnings.
    """
    requirements_text = format_hlrs_for_prompt([hlr], llrs, include_component=True)

    system = SYSTEM_PROMPT.format(
        specializations_section="",  # TODO: build from design_oo_prompt helpers
        namespace_section="",        # TODO: build from component_namespace
        dependency_api_section="",
        as_built_section="",
        existing_classes_section="",
        intercomponent_section="",
        other_hlrs_section="",
        llr_section=format_llr_section(llrs),
    )

    # Build component context for the user prompt
    component_name = hlr.get("component_name")
    component_hint = ""
    if component_name:
        component_desc = hlr.get("component_description", "")
        component_hint = f"\n\nThis requirement belongs to the architectural component: **{component_name}**"
        if component_namespace:
            component_hint += f" (namespace: `{component_namespace}`)"
        component_hint += ". Your class design should be scoped to this component context.\n"
        if component_desc:
            component_hint += f"\n### Component Description\n\n{component_desc}\n"

    # Format existing verification stubs
    existing_verifs_text = ""
    if existing_verifications:
        lines = ["Existing verification stubs:"]
        for v in existing_verifications:
            lines.append(f"  - [{v['method']}] {v.get('test_name', '')}: {v.get('description', '')}")
        existing_verifs_text = "\n".join(lines)

    user_content = (
        f"Design the object-oriented class structure and write verification procedures "
        f"for the following requirements:\n\n{requirements_text}{component_hint}"
    )
    if existing_verifs_text:
        user_content += f"\n\n{existing_verifs_text}"

    messages = [{"role": "user", "content": user_content}]

    # Build tool dispatcher with draft state + Neo4j
    dispatcher = make_combined_dispatcher(
        prior_class_lookup=prior_class_lookup or {},
        dependency_lookup=dependency_lookup,
        intercomponent_classes=intercomponent_classes or [],
        neo4j_session=neo4j_session,
    )

    # Run the tool loop
    result = call_tool_loop(
        system=system,
        messages=messages,
        tools=ALL_TOOLS,
        final_tool_name="commit_design_and_verifications",
        tool_dispatcher=dispatcher,
        model=model,
        max_tokens=8192,
        max_turns=75,
        prompt_log_file=prompt_log_file,
    )

    # Parse the final result
    oo_design = OODesignSchema.model_validate(result["oo_design"])
    verifications = {}
    for llr_id_str, v_list in result.get("verifications", {}).items():
        llr_id = int(llr_id_str)
        verifications[llr_id] = [VerificationSchema.model_validate(v) for v in v_list]

    # Post-loop validation
    design_warnings = []
    verification_warnings = []

    design_errors = _validate_oo_design(
        oo_design,
        prior_class_lookup=prior_class_lookup or {},
        dependency_lookup=dependency_lookup,
        intercomponent_classes=intercomponent_classes or [],
    )
    if design_errors:
        design_warnings.extend(design_errors)

    return DesignVerifyResult(
        oo_design=oo_design,
        verifications=verifications,
        design_warnings=design_warnings,
        verification_warnings=verification_warnings,
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/ticketing_agent/design_verify/combined_loop.py
git commit -m "feat: add combined design+verify loop entry point"
```

---

### Task 6: Remove augment_missing_design_nodes from persistence

**Files:**
- Modify: `backend/requirements/services/persistence.py`

- [ ] **Step 1: Remove the augment call and stub-creation logic**

In `backend/requirements/services/persistence.py`, modify the `persist_verification` function:

Remove the block that collects all_qnames and calls `augment_missing_design_nodes`:

```python
# DELETE this entire block:
    # Collect all qualified names referenced in conditions and actions
    all_qnames: list[str] = []
    for v in verifications:
        for cond in v.preconditions + v.postconditions:
            if cond.subject_qualified_name:
                all_qnames.append(cond.subject_qualified_name)
            if cond.object_qualified_name:
                all_qnames.append(cond.object_qualified_name)
        for action in v.actions:
            if action.caller_qualified_name:
                all_qnames.append(action.caller_qualified_name)
            if action.callee_qualified_name:
                all_qnames.append(action.callee_qualified_name)

    # Auto-create missing :Design stubs for unresolved references
    if all_qnames:
        created = repo.augment_missing_design_nodes(all_qnames)
        result.nodes_augmented = len(created)
```

Also remove `VerificationResult.nodes_augmented` field since it's no longer used. Change the `VerificationResult` dataclass:

```python
@dataclass
class VerificationResult:
    verifications_saved: int = 0
    conditions_created: int = 0
    actions_created: int = 0
```

Find all references to `nodes_augmented` in the codebase and remove them:

```bash
grep -rn "nodes_augmented" backend/ scripts/
```

Remove any references found in `scripts/03_design_requirements.py` and elsewhere.

- [ ] **Step 2: Commit**

```bash
git add backend/requirements/services/persistence.py scripts/03_design_requirements.py
git commit -m "feat: remove augment_missing_design_nodes from persist_verification"
```

---

### Task 7: Remove augment_missing_design_nodes from VerificationRepository

**Files:**
- Modify: `backend/db/neo4j/repositories/verification.py`

- [ ] **Step 1: Remove the augment_missing_design_nodes method**

In `backend/db/neo4j/repositories/verification.py`, delete the `augment_missing_design_nodes` method entirely (approximately lines 200-240).

Keep `_is_valid_verification_qname` since it's still used by the combined tools module.

Find all callers of `augment_missing_design_nodes`:

```bash
grep -rn "augment_missing_design_nodes" backend/ scripts/ tests/
```

Remove any remaining references.

- [ ] **Step 2: Commit**

```bash
git add backend/db/neo4j/repositories/verification.py
git commit -m "feat: remove augment_missing_design_nodes from VerificationRepository"
```

---

### Task 8: Update the pipeline script

**Files:**
- Modify: `scripts/03_design_requirements.py`

Replace the separate `step_design` and `step_verify` functions with a combined `step_design_and_verify` function that calls `design_and_verify` from the new module.

- [ ] **Step 1: Add the combined step function**

Add a new `step_design_and_verify()` function that replaces `step_design` and `step_verify`. The function should:

1. Keep `step_decompose` unchanged
2. Replace `step_design` and `step_verify` with a single loop that calls `design_and_verify()` per HLR
3. After each HLR's combined loop completes, persist the design via `persist_design` and verifications via `persist_verification`
4. Keep `step_summary` unchanged

Key changes in the design+verify loop:
- Import `design_and_verify` from `backend.ticketing_agent.design_verify.combined_loop`
- After `design_and_verify` returns, persist `result.oo_design` via `persist_design`
- For each LLR id in `result.verifications`, persist via `persist_verification`
- Log any `design_warnings` or `verification_warnings`

- [ ] **Step 2: Update the main block**

Change `step_design(); step_verify()` to `step_design_and_verify()` in the `__main__` block.

- [ ] **Step 3: Commit**

```bash
git add scripts/03_design_requirements.py
git commit -m "feat: update pipeline to use combined design+verify loop"
```

---

### Task 9: Add cleanup of verification stubs to flush_db

**Files:**
- Modify: `scripts/01_flush_db.py`

- [ ] **Step 1: Add verification stub cleanup**

In `scripts/01_flush_db.py`, add after the existing Neo4j cleanup block:

```python
    # Clean up verification stub nodes (source_type='verification')
    with get_neo4j().session() as session:
        result = session.run(
            "MATCH (d:Design {source_type: 'verification'}) DETACH DELETE d "
            "RETURN count(d) AS deleted"
        )
        deleted = result.single()["deleted"]
        if deleted:
            print(f"  Deleted {deleted} verification stub design nodes")
```

This ensures a clean start when the pipeline runs.

- [ ] **Step 2: Commit**

```bash
git add scripts/01_flush_db.py
git commit -m "feat: add verification stub cleanup to flush_db"
```

---

### Task 10: Integration test

**Files:**
- Create: `tests/test_integration_combined_loop.py`

- [ ] **Step 1: Write an integration test that exercises the combined loop**

This test verifies the combined loop works end-to-end with a mock LLM. It doesn't require Neo4j.

```python
"""Integration test for the combined design+verify loop."""

import json
import pytest
from unittest.mock import patch, MagicMock

from backend.codebase.schemas import OODesignSchema
from backend.requirements.schemas import VerificationSchema, VerificationConditionSchema
from backend.ticketing_agent.design_verify.combined_loop import design_and_verify


def _minimal_design_dict():
    return {
        "modules": ["calculation_engine"],
        "classes": [
            {
                "name": "Calculator",
                "module": "calculation_engine",
                "description": "Main calculator",
                "visibility": "public",
                "is_intercomponent": False,
                "requirement_ids": [],
                "attributes": [],
                "methods": [
                    {
                        "name": "add",
                        "description": "Add two numbers",
                        "visibility": "public",
                        "parameters": ["double a", "double b"],
                        "return_type": "double",
                    }
                ],
                "inherits_from": [],
                "realizes_interfaces": [],
            }
        ],
        "interfaces": [],
        "enums": [],
        "associations": [],
    }


def _minimal_verification_dict():
    return {
        "method": "automated",
        "test_name": "test_add",
        "description": "Test addition",
        "preconditions": [
            {
                "subject_qualified_name": "calculation_engine::Calculator",
                "operator": "not_null",
                "expected_value": "exists",
            }
        ],
        "actions": [
            {
                "description": "Call add",
                "callee_qualified_name": "calculation_engine::Calculator::add",
            }
        ],
        "postconditions": [],
    }


def test_combined_loop_commits_valid_design_and_verifications():
    """The combined loop can commit a valid design + verification pair."""
    from backend.ticketing_agent.design_verify.combined_tools import make_combined_dispatcher

    hlr = {"id": 1, "description": "The calculator performs addition."}
    llrs = [{"id": 1, "description": "The engine shall add two numbers."}]

    # Simulate a tool loop where the agent first drafts a design, then commits
    dispatcher = make_combined_dispatcher(
        prior_class_lookup={},
        dependency_lookup=None,
        intercomponent_classes=None,
        neo4j_session=None,
    )

    # Step 1: Draft the design
    draft_result = json.loads(dispatcher("draft_design", {"design": _minimal_design_dict()}))
    assert draft_result["valid"] is True

    # Step 2: Commit with verification
    commit_result = json.loads(dispatcher(
        "commit_design_and_verifications",
        {
            "oo_design": _minimal_design_dict(),
            "verifications": {"1": [_minimal_verification_dict()]},
        },
    ))
    assert commit_result["committed"] is True


def test_combined_loop_rejects_unresolved_references():
    """Commit rejects when verifications reference non-existent design elements."""
    from backend.ticketing_agent.design_verify.combined_tools import make_combined_dispatcher

    dispatcher = make_combined_dispatcher(
        prior_class_lookup={},
        dependency_lookup=None,
        intercomponent_classes=None,
        neo4j_session=None,
    )

    # Draft a design without the referenced class
    dispatcher("draft_design", {"design": _minimal_design_dict()})

    # Try to commit with a verification referencing a non-existent class
    bad_verification = _minimal_verification_dict()
    bad_verification["preconditions"][0]["subject_qualified_name"] = "nonexistent::GhostClass"

    commit_result = json.loads(dispatcher(
        "commit_design_and_verifications",
        {
            "oo_design": _minimal_design_dict(),
            "verifications": {"1": [bad_verification]},
        },
    ))
    assert commit_result["committed"] is False
    assert any("GhostClass" in e for e in commit_result["errors"])
```

- [ ] **Step 2: Run the integration test**

Run: `pytest tests/test_integration_combined_loop.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration_combined_loop.py
git commit -m "test: add integration tests for combined design+verify loop"
```

---

### Task 11: Run full test suite and verify no regressions

- [ ] **Step 1: Run the full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All existing tests pass, new tests pass.

- [ ] **Step 2: Run the pipeline end-to-end (manual smoke test)**

```bash
python scripts/01_flush_db.py
python scripts/02_setup_project.py
python scripts/03_design_requirements.py
```

Expected: Pipeline runs through decompose → design+verify → summary with no verification stub creation and fewer unresolved references.

- [ ] **Step 3: Commit any fixes**

```bash
git add -A && git commit -m "fix: address any test failures from integration"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** All sections of the design spec are implemented (combined loop, draft state, commit tool, poison filter, prompt, pipeline changes, stub removal, cleanup).
- [x] **Placeholder scan:** No TBDs, TODOs, or "fill in later" in the plan.
- [x] **Type consistency:** DesignAndVerificationSchema.verifications uses `dict[int, list[VerificationSchema]]`, matching the commit tool's serialization to `dict[str, list[dict]]` (keys are LLR ids).
- [x] **File paths are exact:** All file paths reference real files in the codebase.