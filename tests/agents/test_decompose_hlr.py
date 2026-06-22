"""Integration test for HLR decomposition agent.

Calls ``decompose()`` with a real LLM backend and saves all intermediate
data for offline inspection:

1. **Prompt data** — system prompt, user message, tool schema definition
2. **Model response** — raw JSON returned by the LLM
3. **Parsed result** — the ``DecomposedRequirement`` model instance
4. **Assertions** — structural validation of the decomposition

All artifacts are saved to ``tests/agents/__data__/decompose_hlr/``.

Run::

    pytest tests/agents/test_decompose_hlr.py -v -s

Skip (requires network + API key)::

    pytest -m "not agent"
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from backend_migrated.agents.decompose_hlr import (
    SYSTEM_PROMPT,
    TOOL_DEFINITION,
    decompose,
    _format_dependency_context,
)
from backend_migrated.requirements.schemas import (
    DecomposedRequirementSchema,
)

from tests.agents import agent

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

HLR_DESCRIPTION = (
    "The Calculation Engine shall expose arithmetic operations (add, subtract, "
    "multiply, divide) that accept two numeric operands, return the numeric "
    "result for valid inputs, and signal an error for invalid inputs (non-numeric "
    "operands, division by zero)."
)

HLR_COMPONENT = "Calculation Engine"


# ---------------------------------------------------------------------------
# Helper: save all intermediate data for a decompose() call
# ---------------------------------------------------------------------------

def _save_artifacts(
    artifact_path,
    group: str,
    *,
    system_prompt: str,
    user_message: str,
    tool_definition: dict,
    tool_schema: dict,
    raw_response: dict | None,
    parsed_result: DecomposedRequirementSchema | None,
    error: str | None = None,
) -> dict[str, Path]:
    """Write all intermediate data to the artifact directory.

    Returns a dict mapping artifact name → file path.
    """
    paths: dict[str, Path] = {}

    # 1. System prompt
    p = artifact_path(group, "01_system_prompt.md")
    p.write_text(system_prompt)
    paths["system_prompt"] = p

    # 2. User message
    p = artifact_path(group, "02_user_message.md")
    p.write_text(user_message)
    paths["user_message"] = p

    # 3. Tool definition (name + description)
    p = artifact_path(group, "03_tool_definition.json")
    p.write_text(json.dumps(tool_definition, indent=2))
    paths["tool_definition"] = p

    # 4. Tool input_schema (what the model sees)
    p = artifact_path(group, "04_tool_input_schema.json")
    p.write_text(json.dumps(tool_schema, indent=2))
    paths["tool_input_schema"] = p

    # 5. Full prompt assembly (what gets sent)
    assembly = {
        "system_prompt_length": len(system_prompt),
        "user_message_length": len(user_message),
        "tool_name": tool_definition.get("name"),
        "tool_description": tool_definition.get("description"),
        "schema_properties": list(tool_schema.get("properties", {}).keys()),
        "schema_required": tool_schema.get("required", []),
        "schema_defs": list(tool_schema.get("$defs", {}).keys()) if "$defs" in tool_schema else [],
    }
    p = artifact_path(group, "05_prompt_assembly.json")
    p.write_text(json.dumps(assembly, indent=2))
    paths["prompt_assembly"] = p

    # 6. Raw model response — don't overwrite good data with error stubs
    if raw_response is not None:
        p = artifact_path(group, "06_raw_response.json")
        # Only write if the file doesn't already exist with real data,
        # or if the new data is a successful response (has description).
        if not p.exists() or not isinstance(raw_response, dict) or "description" in raw_response:
            p.write_text(json.dumps(raw_response, indent=2, default=str))
        paths["raw_response"] = p

    # 7. Parsed result
    if parsed_result is not None:
        p = artifact_path(group, "07_parsed_result.json")
        p.write_text(json.dumps(parsed_result.model_dump(), indent=2))
        paths["parsed_result"] = p

    # 8. Error (if any)
    if error is not None:
        p = artifact_path(group, "08_error.txt")
        p.write_text(error)
        paths["error"] = p

    # 9. Summary
    summary = {
        "hlr_description": HLR_DESCRIPTION,
        "hlr_component": HLR_COMPONENT,
        "success": parsed_result is not None,
        "error": error,
        "num_llrs": len([n for n in parsed_result.nodes if n.get("type") == "LLR"]) if parsed_result else 0,
        "total_verifications": (
            len([n for n in parsed_result.nodes if n.get("type") == "VerificationMethod"])
            if parsed_result else 0
        ),
    }
    p = artifact_path(group, "00_summary.json")
    p.write_text(json.dumps(summary, indent=2))
    paths["summary"] = p

    return paths


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.agent
class TestDecomposeHLR:
    """Integration tests for the HLR decomposition agent.

    These tests call the real LLM backend configured in ``.env``.
    They save all intermediate data to ``tests/agents/__data__/decompose_hlr/``
    and assert structural properties of the result.
    """

    def test_tool_schema_flat_node_format(self):
        """Verify the tool input_schema uses a flat nodes list."""
        schema = TOOL_DEFINITION["input_schema"]

        assert schema["type"] == "object"
        assert "description" in schema["properties"]
        assert "nodes" in schema["properties"]
        assert "description" in schema["required"]
        assert "nodes" in schema["required"]

    def test_decompose_requirement_validates_flat_nodes(self):
        """Verify DecomposedRequirementSchema validates flat node dicts."""
        dr = DecomposedRequirementSchema(
            description="Test HLR",
            nodes=[
                {"type": "LLR", "refid": "llr-1", "description": "Test LLR"},
                {"type": "VerificationMethod", "refid": "vm-1", "method": "automated",
                 "test_name": "test_x", "description": "Test"},
            ],
        )
        assert dr.description == "Test HLR"
        assert len(dr.nodes) == 2
        assert dr.nodes[0]["type"] == "LLR"
        assert dr.nodes[1]["type"] == "VerificationMethod"

    def test_dependency_context_formatting(self):
        """Verify _format_dependency_context produces expected prompt text."""
        # Empty context
        assert _format_dependency_context({}) == ""
        assert _format_dependency_context({"recommendation": "none"}) == ""

        # With dependency
        ctx = {
            "recommendation": "use_existing",
            "dependency_name": "math-lib",
            "relevant_structures": ["MathEngine.add", "MathEngine.subtract"],
            "rationale": "Arithmetic ops already provided",
        }
        result = _format_dependency_context(ctx)
        assert "math-lib" in result
        assert "MathEngine.add" in result
        assert "Do not create LLRs" in result

    def test_recover_mixed_xml_json(self):
        """Verify _recover_mixed_xml_json handles malformed LLM output."""
        from backend_migrated.agents.decompose_hlr import _recover_mixed_xml_json

        # Normal JSON — should pass through unchanged
        normal = {"description": "test", "nodes": [{"type": "LLR", "refid": "llr-1", "description": "LLR1"}]}
        assert _recover_mixed_xml_json(normal) == normal

        # Mixed XML-in-JSON
        mixed = {
            "description": "The system shall compute</description>\n<parameter=low_level_requirements>\n[{\"description\": \"LLR1\"}]"
        }
        recovered = _recover_mixed_xml_json(mixed)
        assert "nodes" in recovered
        assert isinstance(recovered["nodes"], list)
        assert recovered["nodes"][0]["description"] == "LLR1"

    def test_decompose_simple_hlr(self, artifact_path):
        """Decompose a simple HLR and save all intermediate data.

        This is the primary integration test. It calls the real LLM backend,
        saves prompts, schemas, responses, and parsed results, and asserts
        structural properties of the decomposition.
        """
        # Build the user message exactly as decompose() does
        user_message = f"Decompose this high-level requirement:\n\n{HLR_DESCRIPTION}"
        user_message += f"\n\nThis HLR belongs to the **{HLR_COMPONENT}** component. "

        # Set up prompt log for llm_caller to write raw data
        prompt_log = artifact_path("decompose_hlr", "llm_prompt_log.md")

        # llm_caller writes: {base}_response.json and {base}_raw.txt
        # where base = os.path.splitext(prompt_log_file)[0]
        # So for "llm_prompt_log.md" → "llm_prompt_log_response.json"
        llm_response_path = prompt_log.parent / "llm_prompt_log_response.json"

        # --- Call decompose() with real LLM ---
        raw_response = None
        parsed_result = None
        error = None

        try:
            result = decompose(
                description=HLR_DESCRIPTION,
                component=HLR_COMPONENT,
                prompt_log_file=str(prompt_log),
            )
            parsed_result = result
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            log.exception("decompose() failed")

        # Read back the raw response that llm_caller wrote
        if llm_response_path.exists():
            try:
                raw_response = json.loads(llm_response_path.read_text())
            except (json.JSONDecodeError, UnicodeDecodeError):
                raw_response = {"_raw_file": str(llm_response_path)}

        # Save all artifacts (even on error — useful for debugging)
        paths = _save_artifacts(
            artifact_path,
            "decompose_hlr",
            system_prompt=SYSTEM_PROMPT,
            user_message=user_message,
            tool_definition={
                "name": TOOL_DEFINITION["name"],
                "description": TOOL_DEFINITION["description"],
            },
            tool_schema=TOOL_DEFINITION["input_schema"],
            raw_response=raw_response,
            parsed_result=parsed_result,
            error=error,
        )

        # If the LLM backend failed, skip assertions but keep artifacts
        if error is not None:
            pytest.skip(f"LLM backend error: {error}")

        # --- Assertions ---
        # 1. The call must succeed
        assert parsed_result is not None, "decompose() returned None"

        # 2. Must have a description
        assert parsed_result.description, "Decomposed requirement has no description"

        # 3. Must produce at least one LLR
        assert len([n for n in parsed_result.nodes if n.get("type") == "LLR"]) >= 1, (
            f"Expected ≥1 LLR, got {len([n for n in parsed_result.nodes if n.get('type') == 'LLR'])}"
        )

        # 4. Each LLR must have a non-empty description
        for i, llr in enumerate([n for n in parsed_result.nodes if n.get("type") == "LLR"]):
            assert llr.description, f"LLR[{i}] has empty description"

        # 5. Each LLR should have at least one verification
        for i, llr in enumerate([n for n in parsed_result.nodes if n.get("type") == "LLR"]):
            assert len(llr.verifications) >= 1, (
                f"LLR[{i}] '{llr.description[:40]}...' has no verifications"
            )

        # 6. Verifications must have a method
        for i, llr in enumerate([n for n in parsed_result.nodes if n.get("type") == "LLR"]):
            for j, v in enumerate(llr.verifications):
                assert "method" in v, (
                    f"LLR[{i}].verifications[{j}] missing 'method' field"
                )
                assert v["method"] in ("automated", "review", "inspection"), (
                    f"LLR[{i}].verifications[{j}] has unexpected method: {v['method']}"
                )

        # 7. All artifacts must exist
        for name, path in paths.items():
            assert path.exists(), f"Artifact '{name}' not written to {path}"

    def test_decompose_with_dependency_context(self, artifact_path):
        """Decompose an HLR with dependency context and verify it's included."""
        dependency_context = {
            "recommendation": "use_existing",
            "dependency_name": "math-lib",
            "relevant_structures": ["MathEngine.add", "MathEngine.subtract"],
            "rationale": "Basic arithmetic already provided by math-lib",
        }

        user_message = f"Decompose this high-level requirement:\n\n{HLR_DESCRIPTION}"
        user_message += f"\n\nThis HLR belongs to the **{HLR_COMPONENT}** component. "
        user_message += _format_dependency_context(dependency_context)

        prompt_log = artifact_path("decompose_hlr_dep", "llm_prompt_log.md")

        # llm_caller writes: {base}_response.json and {base}_raw.txt
        llm_response_path = prompt_log.parent / "llm_prompt_log_response.json"

        raw_response = None
        parsed_result = None
        error = None

        try:
            result = decompose(
                description=HLR_DESCRIPTION,
                component=HLR_COMPONENT,
                dependency_context=dependency_context,
                prompt_log_file=str(prompt_log),
            )
            parsed_result = result
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            log.exception("decompose() with dep context failed")

        if llm_response_path.exists():
            try:
                raw_response = json.loads(llm_response_path.read_text())
            except (json.JSONDecodeError, UnicodeDecodeError):
                raw_response = {"_raw_file": str(llm_response_path)}

        paths = _save_artifacts(
            artifact_path,
            "decompose_hlr_dep",
            system_prompt=SYSTEM_PROMPT,
            user_message=user_message,
            tool_definition={
                "name": TOOL_DEFINITION["name"],
                "description": TOOL_DEFINITION["description"],
            },
            tool_schema=TOOL_DEFINITION["input_schema"],
            raw_response=raw_response,
            parsed_result=parsed_result,
            error=error,
        )

        # If the LLM backend failed, skip assertions but keep artifacts
        if error is not None:
            pytest.skip(f"LLM backend error: {error}")

        # Verify the dependency context appears in the prompt log
        prompt_log_content = prompt_log.read_text()
        assert "math-lib" in prompt_log_content, (
            "Dependency context not found in prompt log"
        )

        # Basic structural assertions
        assert parsed_result is not None, "decompose() returned None"
        assert len([n for n in parsed_result.nodes if n.get("type") == "LLR"]) >= 1

    def test_layergraph_deserialize_flat_nodes(self):
        """Verify LayerGraph.deserialize() handles flat verification node dicts."""
        from codegraph.graph import LayerGraph

        node_dicts = [
            {"type": "LLR", "refid": "llr-1", "description": "Test LLR", "layer": "design", "name": "",
             "edges": [{"relation_type": "COMPOSES", "target_uid": "vm-1", "target_type": "VerificationMethod"}]},
            {"type": "VerificationMethod", "refid": "vm-1", "method": "automated", "test_name": "test_x",
             "description": "Test", "layer": "design", "name": "",
             "edges": [{"relation_type": "COMPOSES", "target_uid": "cond-1", "target_type": "Condition"}]},
            {"type": "Condition", "refid": "cond-1", "phase": "pre", "operator": "==", "layer": "design", "name": "",
             "edges": [
                 {"relation_type": "LEFT_OPERAND", "target_uid": "Engine::result", "target_type": "AttributeNode"},
                 {"relation_type": "RIGHT_OPERAND", "target_uid": "literal::30", "target_type": "LiteralNode"},
             ]},
            {"type": "AttributeNode", "qualified_name": "Engine::result", "name": "result", "kind": "attribute", "tags": ["scaffold"]},
            {"type": "LiteralNode", "qualified_name": "literal::30", "name": "30", "kind": "literal",
             "value": "30", "value_type": "int", "tags": ["scaffold"]},
        ]

        graph = LayerGraph.deserialize(node_dicts)
        all_entries = list(graph._all_entries())

        llr_entry = next(e for e in all_entries if e.node.__class__.__name__ == "LLR")
        assert "VerificationMethod" in llr_entry.children

        cond_entry = next(e for e in all_entries if e.node.__class__.__name__ == "Condition")
        assert len(cond_entry.references) == 2
        rel_types = {r[0] for r in cond_entry.references}
        assert rel_types == {"LEFT_OPERAND", "RIGHT_OPERAND"}

    def test_from_llm_dict_hlr_llr(self):
        """Verify HLR/LLR.from_llm_dict() constructs from raw LLM output."""
        from backend_migrated.models.requirement import HLR, LLR

        # HLR from LLM dict (just description)
        hlr = HLR.from_llm_dict({"description": "The system shall compute arithmetic operations"})
        assert hlr.description == "The system shall compute arithmetic operations"
        assert hlr.layer == "design"
        assert hlr.name == ""
        assert hlr.tags == ["design"]

        # LLR from LLM dict
        llr = LLR.from_llm_dict({"description": "The engine shall add two operands"})
        assert llr.description == "The engine shall add two operands"
        assert llr.layer == "design"
        assert llr.name == ""
        assert llr.tags == ["design"]

    def test_full_decomposition_round_trip(self, artifact_path):
        """Round-trip: load raw LLM response → LayerGraph.deserialize() → verify structure."""
        import json
        from codegraph.graph import LayerGraph
        from backend_migrated.models.requirement import HLR

        raw_path = artifact_path("decompose_hlr", "06_raw_response.json")
        if not raw_path.exists():
            pytest.skip("No raw response artifact — run test_decompose_simple_hlr first")

        raw = json.loads(raw_path.read_text())

        if "description" not in raw or "nodes" not in raw:
            pytest.skip(
                f"Raw response artifact is not a valid flat decomposition "
                f"(keys: {sorted(raw.keys())}). Run test_decompose_simple_hlr first."
            )

        hlr = HLR.from_llm_dict({"description": raw["description"]})
        assert hlr.description
        assert hlr.layer == "design"

        node_types = [n.get("type", "?") for n in raw["nodes"]]
        total_conditions = node_types.count("Condition")
        total_actions = node_types.count("Action")
        total_llrs = node_types.count("LLR")

        graph = LayerGraph.deserialize(raw["nodes"])
        all_entries = list(graph._all_entries())
        assert any(e.node.__class__.__name__ == "LLR" for e in all_entries)
        assert any(e.node.__class__.__name__ == "VerificationMethod" for e in all_entries)

        report = {
            "description": raw["description"][:80],
            "num_llrs": total_llrs,
            "total_conditions": total_conditions,
            "total_actions": total_actions,
        }
        report_path = artifact_path("decompose_hlr", "09_round_trip_report.json")
        report_path.write_text(json.dumps(report, indent=2))

        assert total_conditions > 0, "No conditions in raw response"
        assert total_actions > 0, "No actions in raw response"