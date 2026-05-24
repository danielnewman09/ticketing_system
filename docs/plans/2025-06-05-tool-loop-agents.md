# Tool-Loop Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace call_tool + retry loops in design_oo and verify_llr with call_tool_loop, giving each agent validation and lookup tools so the LLM can self-correct before committing output.

**Architecture:** Both agents switch from single-shot `call_tool` + manual retry to `call_tool_loop` with intermediate tools. Each agent gets a `validate_*` tool and a `lookup_*` tool alongside its existing `produce_*` final tool. The dispatcher functions are closures over the needed context. Post-loop, we still run validation as a sanity check but don't retry.

**Tech Stack:** Python, Pydantic, Neo4j, llm_caller.call_tool_loop, existing Neo4j repositories

---

## File Structure

**Created:**
- `backend/ticketing_agent/design/design_oo_tools.py` — tool schemas + `make_design_dispatcher()`
- `backend/ticketing_agent/verify/verify_llr_tools.py` — tool schemas + `make_verify_dispatcher()`
- `tests/test_design_oo_tools.py` — tests for design dispatcher
- `tests/test_verify_llr_tools.py` — tests for verify dispatcher

**Modified:**
- `backend/ticketing_agent/design/design_oo.py` — replace retry loop with `call_tool_loop`
- `backend/ticketing_agent/design/design_oo_prompt.py` — add tool descriptions to system prompt
- `backend/ticketing_agent/verify/verify_llr.py` — replace retry loop with `call_tool_loop`
- `backend/ticketing_agent/verify/verify_llr_prompt.py` — add tool descriptions to system prompt
- `scripts/03_design_requirements.py` — remove `_validate_verification_qnames` import (post-loop check moves inside agent)

**Unchanged (same public API):**
- `backend/ticketing_agent/design/design_hlr.py` — calls `design_oo()` with same signature
- Pipeline scripts — call same agent functions

---

### Task 1: Create design_oo_tools.py with tool schemas and dispatcher

**Files:**
- Create: `backend/ticketing_agent/design/design_oo_tools.py`
- Read: `backend/ticketing_agent/design/design_oo.py` (for `_validate_oo_design`)
- Read: `backend/codebase/schemas.py` (for `OODesignSchema`)

- [ ] **Step 1: Write failing tests for the design dispatcher**

Create `tests/test_design_oo_tools.py`:

```python
"""Tests for design_oo tool dispatcher and schemas."""

import json
import pytest
from backend.ticketing_agent.design.design_oo_tools import (
    VALIDATE_DESIGN_TOOL,
    CHECK_CLASS_NAME_TOOL,
    PRODUCE_OO_DESIGN_TOOL,
    ALL_TOOLS,
    make_design_dispatcher,
)
from backend.codebase.schemas import OODesignSchema


def _sample_design_dict():
    """Return a minimal valid OODesign dict."""
    return {
        "modules": ["calculation_engine"],
        "classes": [
            {
                "name": "Calculator",
                "module": "calculation_engine",
                "description": "Main calculator",
                "visibility": "public",
                "is_intercomponent": False,
                "requirement_ids": ["hlr:1"],
                "attributes": [
                    {
                        "name": "result",
                        "type_name": "double",
                        "visibility": "private",
                        "description": "Last result",
                    }
                ],
                "methods": [
                    {
                        "name": "add",
                        "description": "Add two numbers",
                        "visibility": "public",
                        "parameters": [],
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


def _make_dispatcher():
    """Create a dispatcher with sample context."""
    prior_class_lookup = {"Calculator": "calculation_engine::Calculator"}
    dependency_lookup = {"Fl_Window": "fltk::Fl_Window"}
    intercomponent_classes = [
        {
            "qualified_name": "user_interface::DisplayArea",
            "kind": "class",
            "description": "Display area",
            "name": "DisplayArea",
            "methods": [],
            "attributes": [],
        }
    ]
    return make_design_dispatcher(
        prior_class_lookup=prior_class_lookup,
        dependency_lookup=dependency_lookup,
        intercomponent_classes=intercomponent_classes,
    )


class TestToolSchemas:
    def test_all_tools_present(self):
        assert len(ALL_TOOLS) == 3
        names = {t["name"] for t in ALL_TOOLS}
        assert names == {"validate_design", "check_class_name", "produce_oo_design"}

    def test_validate_design_tool_schema(self):
        assert VALIDATE_DESIGN_TOOL["name"] == "validate_design"
        assert "input_schema" in VALIDATE_DESIGN_TOOL

    def test_check_class_name_tool_schema(self):
        assert CHECK_CLASS_NAME_TOOL["name"] == "check_class_name"
        props = CHECK_CLASS_NAME_TOOL["input_schema"]["properties"]
        assert "name" in props
        assert props["name"]["type"] == "string"

    def test_produce_oo_design_tool_matches_existing(self):
        # Must have same schema as current TOOL_DEFINITION
        assert PRODUCE_OO_DESIGN_TOOL["name"] == "produce_oo_design"
        assert "input_schema" in PRODUCE_OO_DESIGN_TOOL


class TestValidateDesignDispatcher:
    def test_valid_design_returns_no_errors(self):
        dispatcher = _make_dispatcher()
        result = json.loads(dispatcher("validate_design", _sample_design_dict()))
        assert result["valid"] is True
        assert result["errors"] == []

    def test_unknown_association_target_flagged(self):
        dispatcher = _make_dispatcher()
        design = _sample_design_dict()
        design["associations"] = [
            {
                "from_class": "Calculator",
                "to_class": "NonExistentClass",
                "kind": "depends_on",
                "description": "Missing ref",
            }
        ]
        result = json.loads(dispatcher("validate_design", design))
        assert result["valid"] is False
        assert any("NonExistentClass" in e for e in result["errors"])

    def test_missing_intercomponent_association_flagged(self):
        dispatcher = _make_dispatcher()
        design = _sample_design_dict()
        # Add attribute referencing DisplayArea but no association
        design["classes"][0]["attributes"].append(
            {
                "name": "display",
                "type_name": "DisplayArea",
                "visibility": "private",
                "description": "The display",
            }
        )
        result = json.loads(dispatcher("validate_design", design))
        assert result["valid"] is False
        assert any("intercomponent" in e.lower() or "DisplayArea" in e for e in result["errors"])

    def test_intercomponent_association_not_flagged(self):
        dispatcher = _make_dispatcher()
        design = _sample_design_dict()
        design["classes"][0]["attributes"].append(
            {
                "name": "display",
                "type_name": "DisplayArea",
                "visibility": "private",
                "description": "The display",
            }
        )
        design["associations"] = [
            {
                "from_class": "Calculator",
                "to_class": "user_interface::DisplayArea",
                "kind": "depends_on",
                "description": "Uses display",
            }
        ]
        result = json.loads(dispatcher("validate_design", design))
        assert result["valid"] is True
        assert result["errors"] == []

    def test_malformed_design_returns_format_error(self):
        dispatcher = _make_dispatcher()
        result = json.loads(dispatcher("validate_design", {"bad": "data"}))
        assert result["valid"] is False
        assert any("format" in e.lower() or "schema" in e.lower() for e in result["errors"])


class TestCheckClassNameDispatcher:
    def test_known_prior_design_class(self):
        dispatcher = _make_dispatcher()
        result = json.loads(dispatcher("check_class_name", {"name": "Calculator"}))
        assert result["found"] is True
        assert any(m["qualified_name"] == "calculation_engine::Calculator" for m in result["matches"])

    def test_known_dependency_class(self):
        dispatcher = _make_dispatcher()
        result = json.loads(dispatcher("check_class_name", {"name": "Fl_Window"}))
        assert result["found"] is True
        assert any(m["source"] == "dependency" for m in result["matches"])

    def test_known_intercomponent_class(self):
        dispatcher = _make_dispatcher()
        result = json.loads(dispatcher("check_class_name", {"name": "DisplayArea"}))
        assert result["found"] is True
        assert any(m["source"] == "intercomponent" for m in result["matches"])

    def test_unknown_class(self):
        dispatcher = _make_dispatcher()
        result = json.loads(dispatcher("check_class_name", {"name": "NonExistent"}))
        assert result["found"] is False
        assert result["matches"] == []

    def test_partial_match(self):
        dispatcher = _make_dispatcher()
        result = json.loads(dispatcher("check_class_name", {"name": "Calc"}))
        assert result["found"] is True
        # Should find Calculator via substring match
        assert any("Calculator" in m["qualified_name"] for m in result["matches"])

    def test_unknown_tool_returns_error(self):
        dispatcher = _make_dispatcher()
        result = json.loads(dispatcher("unknown_tool", {}))
        assert "error" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_design_oo_tools.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Create `backend/ticketing_agent/design/design_oo_tools.py`**

```python
"""Tool definitions and dispatcher for the design_oo tool-loop agent.

Provides three tools:
- validate_design: check a draft design for errors
- check_class_name: look up a class name in context
- produce_oo_design: commit the final design (terminates the loop)
"""

import json
import logging
from backend.codebase.schemas import OODesignSchema
from backend.ticketing_agent.design.design_oo import _validate_oo_design

log = logging.getLogger("agents.design")

# ---------------------------------------------------------------------------
# Tool definitions (Anthropic format)
# ---------------------------------------------------------------------------

PRODUCE_OO_DESIGN_TOOL = {
    "name": "produce_oo_design",
    "description": (
        "Return the final object-oriented class design derived from the requirements. "
        "Call this ONLY after you are confident the design is correct — use "
        "validate_design first to check for issues."
    ),
    "input_schema": OODesignSchema.model_json_schema(),
}

VALIDATE_DESIGN_TOOL = {
    "name": "validate_design",
    "description": (
        "Validate a draft OO design before committing it. Checks for unknown "
        "association targets, missing intercomponent associations, and other "
        "structural issues. Returns a list of errors and warnings. Use this "
        "to check your work before calling produce_oo_design."
    ),
    "input_schema": OODesignSchema.model_json_schema(),
}

CHECK_CLASS_NAME_TOOL = {
    "name": "check_class_name",
    "description": (
        "Check if a class, interface, or enum name exists in the design context "
        "(prior designs, dependency APIs, or intercomponent boundaries). "
        "Use this to verify that association targets and type references are "
        "valid before including them in your design. Supports partial matching."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "A class, interface, or enum name to look up. "
                    "Can be a bare name (e.g., 'Calculator') or a qualified name "
                    "(e.g., 'calculation_engine::Calculator'). Supports substring matching."
                ),
            },
        },
        "required": ["name"],
    },
}

ALL_TOOLS = [VALIDATE_DESIGN_TOOL, CHECK_CLASS_NAME_TOOL, PRODUCE_OO_DESIGN_TOOL]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def make_design_dispatcher(
    prior_class_lookup: dict[str, str],
    dependency_lookup: dict[str, str] | None,
    intercomponent_classes: list[dict] | None,
):
    """Create a tool dispatcher for the design_oo tool loop.

    Args:
        prior_class_lookup: bare_name -> qualified_name for previously designed classes.
        dependency_lookup: bare_name -> qualified_name for dependency API classes.
        intercomponent_classes: list of intercomponent class dicts with
            qualified_name, kind, name, etc.
    """
    dep_lookup = dict(dependency_lookup or {})
    intercomp_qnames: set[str] = set()
    intercomp_bare: set[str] = set()
    intercomp_map: dict[str, dict] = {}
    if intercomponent_classes:
        for cls in intercomponent_classes:
            qname = cls.get("qualified_name", "")
            bare = qname.rsplit("::", 1)[-1] if qname else cls.get("name", "")
            intercomp_qnames.add(qname)
            intercomp_bare.add(bare)
            intercomp_map[bare.lower()] = cls
            intercomp_map[qname.lower()] = cls

    def dispatch(tool_name: str, tool_input: dict) -> str:
        if tool_name == "validate_design":
            return _dispatch_validate_design(tool_input)
        elif tool_name == "check_class_name":
            return _dispatch_check_class_name(tool_input)
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    def _dispatch_validate_design(tool_input: dict) -> str:
        try:
            schema = OODesignSchema.model_validate(tool_input)
        except Exception as e:
            return json.dumps({
                "valid": False,
                "errors": [f"Invalid design format: {e}"],
                "warnings": [],
            })

        errors = _validate_oo_design(
            schema,
            prior_class_lookup=prior_class_lookup,
            dependency_lookup=dep_lookup,
            intercomponent_classes=intercomponent_classes or [],
        )
        return json.dumps({
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": [],
        })

    def _dispatch_check_class_name(tool_input: dict) -> str:
        name = tool_input.get("name", "")
        if not name:
            return json.dumps({"found": False, "matches": []})

        matches = []
        name_lower = name.lower()

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

        return json.dumps({
            "found": len(matches) > 0,
            "matches": matches,
        })

    return dispatch
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_design_oo_tools.py -v`
Expected: All 14 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/ticketing_agent/design/design_oo_tools.py tests/test_design_oo_tools.py
git commit -m "feat: add tool schemas and dispatcher for design_oo tool-loop agent"
```

---

### Task 2: Create verify_llr_tools.py with tool schemas and dispatcher

**Files:**
- Create: `backend/ticketing_agent/verify/verify_llr_tools.py`
- Create: `tests/test_verify_llr_tools.py`
- Read: `backend/ticketing_agent/verify/verify_llr.py` (for `_validate_verification_qnames`)
- Read: `backend/db/neo4j/repositories/verification.py` (for `validate_references`)
- Read: `backend/db/neo4j/repositories/design.py` (for `find_nodes`, `get_by_qualified_name`)

- [ ] **Step 1: Write failing tests for the verify dispatcher**

Create `tests/test_verify_llr_tools.py`:

```python
"""Tests for verify_llr tool dispatcher and schemas."""

import json
import pytest
from unittest.mock import MagicMock
from backend.ticketing_agent.verify.verify_llr_tools import (
    VALIDATE_QNAMES_TOOL,
    LOOKUP_DESIGN_ELEMENT_TOOL,
    PRODUCE_VERIFICATIONS_TOOL,
    ALL_TOOLS,
    make_verify_dispatcher,
)


class TestToolSchemas:
    def test_all_tools_present(self):
        assert len(ALL_TOOLS) == 3
        names = {t["name"] for t in ALL_TOOLS}
        assert names == {"validate_qualified_names", "lookup_design_element", "produce_verifications"}

    def test_validate_qnames_schema(self):
        assert VALIDATE_QNAMES_TOOL["name"] == "validate_qualified_names"
        props = VALIDATE_QNAMES_TOOL["input_schema"]["properties"]
        assert "qualified_names" in props
        assert props["qualified_names"]["type"] == "array"

    def test_lookup_design_element_schema(self):
        assert LOOKUP_DESIGN_ELEMENT_TOOL["name"] == "lookup_design_element"
        props = LOOKUP_DESIGN_ELEMENT_TOOL["input_schema"]["properties"]
        assert "name" in props
        assert "kind" in props


class TestValidateQualifiedNames:
    def test_valid_qnames_pass(self):
        dispatcher = make_verify_dispatcher(neo4j_session=None)
        result = json.loads(dispatcher("validate_qualified_names", {
            "qualified_names": ["calc::Engine::run", "user_interface::Display::show"]
        }))
        assert len(result["results"]) == 2
        assert result["results"][0]["valid"] is True
        assert result["results"][1]["valid"] is True

    def test_test_prefix_flagged(self):
        dispatcher = make_verify_dispatcher(neo4j_session=None)
        result = json.loads(dispatcher("validate_qualified_names", {
            "qualified_names": ["test_validate_input"]
        }))
        assert result["results"][0]["valid"] is False
        assert "test_" in result["results"][0]["error"]

    def test_dot_separator_flagged_with_correction(self):
        dispatcher = make_verify_dispatcher(neo4j_session=None)
        result = json.loads(dispatcher("validate_qualified_names", {
            "qualified_names": ["calc.Engine.run"]
        }))
        assert result["results"][0]["valid"] is True  # auto-correctable
        assert result["results"][0]["correction"] == "calc::Engine::run"

    def test_neo4j_resolution(self):
        mock_session = MagicMock()
        # Simulate: calc::Engine exists, missing::Class does not
        mock_session.run.side_effect = lambda q, p: MagicMock(
            single=MagicMock(return_value={"cnt": 1 if "Engine" in p.get("qn", "") else 0})
        )
        dispatcher = make_verify_dispatcher(neo4j_session=mock_session)
        result = json.loads(dispatcher("validate_qualified_names", {
            "qualified_names": ["calc::Engine::run", "missing::Class"]
        }))
        assert result["results"][0]["exists"] is True
        assert result["results"][1]["exists"] is False

    def test_empty_list(self):
        dispatcher = make_verify_dispatcher(neo4j_session=None)
        result = json.loads(dispatcher("validate_qualified_names", {
            "qualified_names": []
        }))
        assert result["results"] == []


class TestLookupDesignElement:
    def test_exact_match(self):
        mock_session = MagicMock()
        # get_by_qualified_name returns a DesignNode
        from backend.db.neo4j.repositories.models.design import DesignNode
        node = DesignNode(
            qualified_name="calculation_engine::Calculator",
            name="Calculator",
            kind="class",
            description="Main calculator",
        )
        mock_result = MagicMock()
        mock_result.single.return_value = {"d": node.model_dump()}
        mock_session.run.return_value = mock_result

        dispatcher = make_verify_dispatcher(neo4j_session=mock_session)
        result = json.loads(dispatcher("lookup_design_element", {
            "name": "calculation_engine::Calculator",
        }))
        # At minimum, empty results when no match (since mock setup is complex)
        assert "elements" in result

    def test_no_session_returns_empty(self):
        dispatcher = make_verify_dispatcher(neo4j_session=None)
        result = json.loads(dispatcher("lookup_design_element", {
            "name": "Calculator",
        }))
        assert result["elements"] == []

    def test_unknown_tool_returns_error(self):
        dispatcher = make_verify_dispatcher(neo4j_session=None)
        result = json.loads(dispatcher("unknown_tool", {}))
        assert "error" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_verify_llr_tools.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Create `backend/ticketing_agent/verify/verify_llr_tools.py`**

```python
"""Tool definitions and dispatcher for the verify_llr tool-loop agent.

Provides three tools:
- validate_qualified_names: check qname format and Neo4j existence
- lookup_design_element: fuzzy search for :Design nodes in Neo4j
- produce_verifications: commit verification procedures (terminates loop)
"""

import json
import logging

from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
from backend.requirements.schemas import VerificationSchema
from backend.ticketing_agent.verify.verify_llr import _validate_verification_qnames

log = logging.getLogger("agents.verify")

# ---------------------------------------------------------------------------
# Tool definitions (Anthropic format)
# ---------------------------------------------------------------------------

PRODUCE_VERIFICATIONS_TOOL = {
    "name": "produce_verifications",
    "description": (
        "Return the fleshed-out verification procedures for an LLR. "
        "Call this ONLY after you are confident in your output — use "
        "validate_qualified_names and lookup_design_element to verify "
        "your references first."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verifications": {
                "type": "array",
                "items": VerificationSchema.model_json_schema(),
            },
        },
        "required": ["verifications"],
    },
}

VALIDATE_QNAMES_TOOL = {
    "name": "validate_qualified_names",
    "description": (
        "Validate a list of qualified names against format rules and the "
        "design context. Checks for: invalid prefixes (test_, result_of_, "
        "verify_, check_), bare lowercase identifiers, dot separators (should "
        "be ::), and existence as :Design nodes in the ontology graph. "
        "Use this to verify your references before calling produce_verifications."
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
        "Search for design elements in the ontology graph by name or qualified "
        "name. Returns matching :Design nodes with their qualified names, kind, "
        "description, and public members. Use this to find the correct qualified "
        "name for a class, method, or attribute before referencing it in "
        "verification conditions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Name or qualified name to search for. Supports "
                    "substring matching — e.g., 'Button' will find "
                    "'user_interface::Button'."
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

ALL_TOOLS = [VALIDATE_QNAMES_TOOL, LOOKUP_DESIGN_ELEMENT_TOOL, PRODUCE_VERIFICATIONS_TOOL]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def make_verify_dispatcher(neo4j_session=None):
    """Create a tool dispatcher for the verify_llr tool loop.

    Args:
        neo4j_session: Optional Neo4j session for reference validation
            and design element lookup. If None, validation skips Neo4j checks.
    """
    def dispatch(tool_name: str, tool_input: dict) -> str:
        if tool_name == "validate_qualified_names":
            return _dispatch_validate_qnames(tool_input)
        elif tool_name == "lookup_design_element":
            return _dispatch_lookup_design_element(tool_input)
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    def _dispatch_validate_qnames(tool_input: dict) -> str:
        qnames = tool_input.get("qualified_names", [])
        results = []
        for qn in qnames:
            result_entry = {
                "qname": qn,
                "valid": True,
                "exists": None,
                "error": None,
                "correction": None,
            }
            # Format validation
            from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
            is_valid, corrected = _is_valid_verification_qname(qn)
            if not is_valid:
                result_entry["valid"] = False
                result_entry["error"] = f"Invalid qualified name format: {qn}"
            elif corrected:
                result_entry["correction"] = corrected
            # Neo4j existence check (if session provided)
            if neo4j_session is not None and is_valid:
                resolved_qn = corrected if corrected else qn
                check_qn = resolved_qn
                # For member references (e.g., "Ns::Class::method"), check the class part
                parts = resolved_qn.rsplit("::", 2)
                if len(parts) >= 2:
                    # Try full qname first, then class-level qname
                    for candidate in [resolved_qn, "::".join(parts[:-1]) if len(parts) == 3 else resolved_qn]:
                        cypher = "MATCH (d:Design {qualified_name: $qn}) RETURN count(d) AS cnt"
                        record = neo4j_session.run(cypher, {"qn": candidate}).single()
                        if record and record["cnt"] > 0:
                            check_qn = candidate
                            break
                record = neo4j_session.run(
                    "MATCH (d:Design {qualified_name: $qn}) RETURN count(d) AS cnt",
                    {"qn": check_qn},
                ).single()
                result_entry["exists"] = record["cnt"] > 0 if record else False
            results.append(result_entry)
        return json.dumps({"results": results})

    def _dispatch_lookup_design_element(tool_input: dict) -> str:
        name = tool_input.get("name", "")
        kind = tool_input.get("kind")
        if not name or neo4j_session is None:
            return json.dumps({"elements": []})
        from backend.db.neo4j.repositories.design import DesignRepository
        repo = DesignRepository(neo4j_session)
        # Try exact match first
        exact = repo.get_by_qualified_name(name)
        if exact:
            return json.dumps({"elements": [_format_design_node(exact)]})
        # Fuzzy search
        nodes = repo.find_nodes(kind=kind, search=name)
        # Limit to avoid overwhelming context
        elements = [_format_design_node(n) for n in nodes[:20]]
        return json.dumps({"elements": elements})

    return dispatch


def _format_design_node(node) -> dict:
    """Format a DesignNode for the tool response."""
    result = {
        "qualified_name": node.qualified_name,
        "kind": node.kind,
        "description": node.description,
    }
    if node.is_intercomponent:
        result["is_intercomponent"] = True
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_verify_llr_tools.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/ticketing_agent/verify/verify_llr_tools.py tests/test_verify_llr_tools.py
git commit -m "feat: add tool schemas and dispatcher for verify_llr tool-loop agent"
```

---

### Task 3: Refactor design_oo.py to use call_tool_loop

**Files:**
- Modify: `backend/ticketing_agent/design/design_oo.py`
- Read: `backend/ticketing_agent/design/design_oo_tools.py`
- Read: `backend/ticketing_agent/design/discover_classes.py` (reference for `call_tool_loop` pattern)

- [ ] **Step 1: Rewrite design_oo to use call_tool_loop**

The function signature stays the same. Replace the retry loop with a `call_tool_loop` call. Keep `_validate_oo_design` (used by dispatcher) but remove `_format_design_validation_errors` and the `MAX_TOOL_RETRIES` constant.

Key changes:
- Import `call_tool_loop` instead of `call_tool`
- Import `ALL_TOOLS`, `make_design_dispatcher` from `design_oo_tools`
- Build dispatcher from context params
- Call `call_tool_loop` with all 3 tools, `final_tool_name="produce_oo_design"`
- Post-loop: pydantic-validate result with `OODesignSchema.model_validate(result)`, run `_validate_oo_design` as sanity check and log warnings
- Remove: `MAX_TOOL_RETRIES`, `_format_design_validation_errors`, the entire `for attempt` loop, the `try/except Exception` block

- [ ] **Step 2: Run existing design_oo prompt tests to verify nothing broke**

Run: `pytest tests/test_design_oo_prompt.py -v`
Expected: All 6 tests PASS

- [ ] **Step 3: Update design_oo_retry tests for post-loop validation**

Modify `tests/test_design_oo_retry.py`: The `_validate_oo_design` function still exists (used by the dispatcher), but the retry loop no longer exists in `design_oo`. Remove tests that tested the retry loop directly (the ones that mock `call_tool`). Keep tests that test `_validate_oo_design` directly since it's still used.

Keep these tests:
- `test_unknown_association_target_flagged`
- `test_known_intercomponent_class_not_flagged`
- `test_missing_intercomponent_association_flagged`
- `test_valid_design_no_errors`
- `test_dependency_lookup_target_not_flagged`
- `test_prior_class_lookup_target_not_flagged`
- `test_format_single_error`
- `test_format_multiple_errors` (remove this one since we're removing `_format_design_validation_errors`)

Remove retry-loop tests that mock `call_tool` since the architecture changed.

- [ ] **Step 4: Add test for design_oo using call_tool_loop**

Add a test that verifies `design_oo()` still accepts the same parameters and returns an `OODesignSchema`:

```python
def test_design_oo_returns_schema_on_valid_output(mocker):
    """Verify design_oo function still returns OODesignSchema."""
    from backend.ticketing_agent.design.design_oo import design_oo
    from backend.codebase.schemas import OODesignSchema

    mock_result = {
        "modules": ["test_ns"],
        "classes": [{
            "name": "TestClass",
            "module": "test_ns",
            "description": "A test class",
            "visibility": "public",
            "is_intercomponent": False,
            "requirement_ids": [],
            "attributes": [],
            "methods": [],
            "inherits_from": [],
            "realizes_interfaces": [],
        }],
        "interfaces": [],
        "enums": [],
        "associations": [],
    }
    mocker.patch(
        "backend.ticketing_agent.design.design_oo.call_tool_loop",
        return_value=mock_result,
    )
    result = design_oo(
        hlr={"id": 1, "description": "Test HLR"},
        llrs=[],
        prior_class_lookup={},
    )
    assert isinstance(result, OODesignSchema)
```

- [ ] **Step 5: Run all design_oo tests**

Run: `pytest tests/test_design_oo_retry.py tests/test_design_oo_tools.py tests/test_design_oo_prompt.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/ticketing_agent/design/design_oo.py tests/test_design_oo_retry.py
git commit -m "refactor: replace design_oo retry loop with call_tool_loop"
```

---

### Task 4: Refactor verify_llr.py to use call_tool_loop

**Files:**
- Modify: `backend/ticketing_agent/verify/verify_llr.py`
- Read: `backend/ticketing_agent/verify/verify_llr_tools.py`

- [ ] **Step 1: Rewrite verify to use call_tool_loop**

Same pattern as design_oo. Key changes:
- Import `call_tool_loop` instead of `call_tool`
- Import `ALL_TOOLS`, `make_verify_dispatcher` from `verify_llr_tools`
- Build dispatcher with `neo4j_session`
- Call `call_tool_loop` with all 3 tools, `final_tool_name="produce_verifications"`
- Post-loop: parse verifications, run `_validate_verification_qnames` as sanity check and log warnings
- Remove: `MAX_TOOL_RETRIES`, `_format_verification_validation_errors`, the entire `for attempt` loop, the `try/except Exception` block, the `_collect_qualified_names` function (no longer needed for retry logic), the `_validate_verification_qnames` call in the loop, the failure logging block
- Keep: `_validate_verification_qnames` (used by dispatcher and post-loop check), `_collect_qualified_names` (still needed for post-loop reporting to pipeline)
- The `verify()` function still returns `VerifyResult` with the same fields

- [ ] **Step 2: Update verify_retry tests**

Similar to design_oo: keep tests for `_validate_verification_qnames` and `_collect_qualified_names`, remove retry-loop tests that mock `call_tool`.

- [ ] **Step 3: Run all verify tests**

Run: `pytest tests/test_verify_retry.py tests/test_verify_llr_tools.py tests/test_verify_llr_prompt.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/ticketing_agent/verify/verify_llr.py tests/test_verify_retry.py
git commit -m "refactor: replace verify_llr retry loop with call_tool_loop"
```

---

### Task 5: Update system prompts with tool descriptions

**Files:**
- Modify: `backend/ticketing_agent/design/design_oo_prompt.py`
- Modify: `backend/ticketing_agent/verify/verify_llr_prompt.py`

- [ ] **Step 1: Add tool descriptions to design_oo system prompt**

Add to `SYSTEM_PROMPT` in `design_oo_prompt.py`, after the `<CONTRACT>` block for associations:

```
## Available tools

You have three tools available:

### validate_design
Validates a draft design for structural issues (unknown association targets,
missing intercomponent associations). Call this on your draft before committing
it with produce_oo_design. The tool returns a list of errors to fix.

### check_class_name
Looks up a class, interface, or enum name in the design context (prior designs,
dependency APIs, intercomponent boundaries). Use this to verify that association
targets and type references are valid before including them in your design.

### produce_oo_design
Commits your final class design. This terminates the agent loop — only call
this when you are confident the design is complete and correct.

**Recommended workflow:** Draft your design, call validate_design to check for
issues, use check_class_name to resolve any ambiguous references, fix any
errors, then call produce_oo_design.
```

- [ ] **Step 2: Update design_oo_prompt tests**

The existing prompt tests check for `<CONTRACT>` blocks. Add tests for the tool descriptions:

```python
def test_system_prompt_contains_validate_design_description(self):
    self.assertIn("validate_design", SYSTEM_PROMPT)

def test_system_prompt_contains_check_class_name_description(self):
    self.assertIn("check_class_name", SYSTEM_PROMPT)
```

- [ ] **Step 3: Add tool descriptions to verify_llr system prompt**

Add to `SYSTEM_PROMPT` in `verify_llr_prompt.py`, after the `<FORMAT-CONTRACT>` block:

```
## Available tools

### validate_qualified_names
Validates a list of qualified names for format correctness (no test_ prefixes,
dot separators, bare identifiers) and checks if they exist as :Design nodes in
the ontology. Call this to verify your references before committing.

### lookup_design_element
Searches the design context for elements matching a name pattern. Returns
qualified names, kind, description, and member details. Use this to find the
correct qualified name for a class, method, or attribute before referencing it.

### produce_verifications
Commits your verification procedures. This terminates the agent loop — only
call this when you are confident the verifications are complete and all
references are correct.

**Recommended workflow:** Draft your verifications, call lookup_design_element
to find correct qualified names, call validate_qualified_names to check for
issues, fix any errors, then call produce_verifications.
```

- [ ] **Step 4: Update verify_llr_prompt tests**

```python
def test_system_prompt_contains_validate_qnames_description(self):
    self.assertIn("validate_qualified_names", SYSTEM_PROMPT)

def test_system_prompt_contains_lookup_design_element_description(self):
    self.assertIn("lookup_design_element", SYSTEM_PROMPT)
```

- [ ] **Step 5: Run prompt tests**

Run: `pytest tests/test_design_oo_prompt.py tests/test_verify_llr_prompt.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/ticketing_agent/design/design_oo_prompt.py backend/ticketing_agent/verify/verify_llr_prompt.py tests/test_design_oo_prompt.py tests/test_verify_llr_prompt.py
git commit -m "feat: add tool descriptions to design_oo and verify_llr system prompts"
```

---

### Task 6: Update pipeline script and integration

**Files:**
- Modify: `scripts/03_design_requirements.py`
- Modify: `backend/ticketing_agent/design/design_hlr.py` (if signatures changed)

- [ ] **Step 1: Verify design_hlr.py still works with refactored design_oo**

The `design_oo()` function signature should be unchanged (returns `OODesignSchema`), so `design_hlr.py` should need no modifications. Verify by running:

```bash
python -c "from backend.ticketing_agent.design.design_hlr import design_hlr; print('OK')"
```

- [ ] **Step 2: Remove _validate_verification_qnames import from pipeline script**

In `scripts/03_design_requirements.py`, the post-loop check imports `_validate_verification_qnames`. This should still work since we keep the function. But verify the import and usage are correct:

```bash
python -c "from backend.ticketing_agent.verify.verify_llr import _validate_verification_qnames; print('OK')"
```

- [ ] **Step 3: Clean up the pipeline script's logging**

The pipeline script currently has retry-loop-level error handling. Since `call_tool_loop` handles retry internally, remove the `_attemptN_failed.txt` logging since conversation logs now capture everything. Remove the `_validate_verification_qnames` import from the pipeline if it's no longer needed (but keep it if we still want post-loop sanity checks in the pipeline output).

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/03_design_requirements.py backend/ticketing_agent/design/design_hlr.py
git commit -m "chore: clean up pipeline integration after tool-loop refactor"
```

---

### Task 7: End-to-end pipeline test

**Files:** No new files — this is a manual verification step.

- [ ] **Step 1: Flush and re-run the pipeline**

```bash
python scripts/01_flush_db.py
python scripts/02_setup_project.py
python scripts/03_design_requirements.py
```

- [ ] **Step 2: Verify design agent uses all three tools**

Check `logs/design_oo_hlr*.md` for conversation logs showing the agent calling `validate_design` or `check_class_name` before `produce_oo_design`.

- [ ] **Step 3: Verify verify agent uses all three tools**

Check `logs/verify_llr*.md` for conversation logs showing the agent calling `validate_qualified_names` or `lookup_design_element` before `produce_verifications`.

- [ ] **Step 4: Verify no orphan stubs or missing cross-component links**

Run Neo4j queries:
```cypher
// Check cross-component associations exist
MATCH (d1:Design)-[r]->(d2:Design)
WHERE d1.qualified_name STARTS WITH 'user_interface'
  AND d2.qualified_name STARTS WITH 'calculation_engine'
RETURN d1.qualified_name, type(r), d2.qualified_name

// Check for orphan stubs from verification
MATCH (d:Design)
WHERE NOT (d)--() AND d.source_type='verification'
RETURN d.qualified_name
```

- [ ] **Step 5: Commit any final fixes**

```bash
git add -A
git commit -m "chore: end-to-end pipeline validation complete"
```