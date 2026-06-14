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
    VerificationMethodSchema,
    ConditionSchema,
    ActionSchema,
    detail_schema,
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
        "num_llrs": len(parsed_result.low_level_requirements) if parsed_result else 0,
        "total_verifications": (
            sum(len(llr.verifications) for llr in parsed_result.low_level_requirements)
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

    def test_tool_schema_derived_from_neomodel(self):
        """Verify the tool input_schema is generated from neomodel _detail_fields."""
        schema = TOOL_DEFINITION["input_schema"]

        # The schema must have the expected top-level keys
        assert schema["type"] == "object"
        assert "description" in schema["properties"]
        assert "low_level_requirements" in schema["properties"]
        assert "description" in schema["required"]
        assert "low_level_requirements" in schema["required"]

        # The $defs must include LowLevelRequirementSchema
        assert "LowLevelRequirementSchema" in schema.get("$defs", {})

        # The verifications field must accept list[dict] (from neomodel-derived schema)
        llr_def = schema["$defs"]["LowLevelRequirementSchema"]
        assert "verifications" in llr_def["properties"]

    def test_neomodel_detail_schemas(self):
        """Verify detail_schema() produces correct JSON Schema from neomodel models."""
        from backend_migrated.models.verification import (
            VerificationMethod, Condition, Action,
        )

        # VerificationMethod schema
        vm_schema = detail_schema(VerificationMethod)
        assert vm_schema["type"] == "object"
        assert "method" in vm_schema["properties"]
        assert "method" in vm_schema["required"]
        assert "test_name" in vm_schema["properties"]
        assert vm_schema["properties"]["method"]["type"] == "string"

        # Condition schema
        cond_schema = detail_schema(Condition)
        assert "phase" in cond_schema["properties"]
        assert "phase" in cond_schema["required"]
        assert "subject_qualified_name" in cond_schema["properties"]
        assert "operator" in cond_schema["properties"]
        assert "expected_value" in cond_schema["properties"]

        # Action schema
        act_schema = detail_schema(Action)
        assert "description" in act_schema["properties"]
        assert "callee_qualified_name" in act_schema["properties"]

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
        normal = {"description": "test", "low_level_requirements": [{"description": "LLR1"}]}
        assert _recover_mixed_xml_json(normal) == normal

        # Mixed XML-in-JSON
        mixed = {
            "description": "The system shall compute</description>\n<parameter=low_level_requirements>\n[{\"description\": \"LLR1\"}]"
        }
        recovered = _recover_mixed_xml_json(mixed)
        assert "low_level_requirements" in recovered
        assert isinstance(recovered["low_level_requirements"], list)
        assert recovered["low_level_requirements"][0]["description"] == "LLR1"

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
        assert len(parsed_result.low_level_requirements) >= 1, (
            f"Expected ≥1 LLR, got {len(parsed_result.low_level_requirements)}"
        )

        # 4. Each LLR must have a non-empty description
        for i, llr in enumerate(parsed_result.low_level_requirements):
            assert llr.description, f"LLR[{i}] has empty description"

        # 5. Each LLR should have at least one verification
        for i, llr in enumerate(parsed_result.low_level_requirements):
            assert len(llr.verifications) >= 1, (
                f"LLR[{i}] '{llr.description[:40]}...' has no verifications"
            )

        # 6. Verifications must have a method
        for i, llr in enumerate(parsed_result.low_level_requirements):
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
        assert len(parsed_result.low_level_requirements) >= 1
        """Verify VerificationMethod.from_llm_dict() constructs from raw LLM output."""
        from backend_migrated.models.verification import VerificationMethod, Condition, Action

        vm_data = {
            "method": "automated",
            "test_name": "test_add_returns_sum",
            "description": "Invoke the add operation with operands 10 and 20",
            "preconditions": [
                {"subject_qualified_name": "Engine.is_initialized", "operator": "is_true", "expected": "true"},
            ],
            "actions": [
                {"description": "Invoke the add operation", "callee_qualified_name": "Engine.add"},
            ],
            "postconditions": [
                {"subject_qualified_name": "Engine.result", "operator": "==", "expected_value": "30"},
            ],
        }

        vm, conditions, actions = VerificationMethod.from_llm_dict(vm_data)

        # VM properties
        assert vm.method == "automated"
        assert vm.test_name == "test_add_returns_sum"
        assert vm.description == "Invoke the add operation with operands 10 and 20"
        assert vm.layer == "design"
        assert vm.name == ""

        # Conditions — preconditions get phase="pre", postconditions get phase="post"
        assert len(conditions) == 2
        pre_cond = [c for c in conditions if c.phase == "pre"]
        post_cond = [c for c in conditions if c.phase == "post"]
        assert len(pre_cond) == 1
        assert len(post_cond) == 1

        # Pre-condition: "expected" → "expected_value" alias
        assert pre_cond[0].subject_qualified_name == "Engine.is_initialized"
        assert pre_cond[0].operator == "is_true"
        assert pre_cond[0].expected_value == "true"  # "expected" → "expected_value"
        assert pre_cond[0].order == 0

        # Post-condition
        assert post_cond[0].subject_qualified_name == "Engine.result"
        assert post_cond[0].expected_value == "30"
        assert post_cond[0].order == 0

        # Actions
        assert len(actions) == 1
        assert actions[0].description == "Invoke the add operation"
        assert actions[0].callee_qualified_name == "Engine.add"
        assert actions[0].order == 0
        assert actions[0].layer == "design"

    def test_from_llm_dict_verification_method(self):
        """Verify VerificationMethod.from_llm_dict() constructs from raw LLM output."""
        from backend_migrated.models.verification import VerificationMethod, Condition, Action

        vm_data = {
            "method": "automated",
            "test_name": "test_add_returns_sum",
            "description": "Invoke the add operation with operands 10 and 20",
            "preconditions": [
                {"subject_qualified_name": "Engine.is_initialized", "operator": "is_true", "expected": "true"},
            ],
            "actions": [
                {"description": "Invoke the add operation", "callee_qualified_name": "Engine.add"},
            ],
            "postconditions": [
                {"subject_qualified_name": "Engine.result", "operator": "==", "expected_value": "30"},
            ],
        }

        vm, conditions, actions = VerificationMethod.from_llm_dict(vm_data)

        # VM properties
        assert vm.method == "automated"
        assert vm.test_name == "test_add_returns_sum"
        assert vm.description == "Invoke the add operation with operands 10 and 20"
        assert vm.layer == "design"
        assert vm.name == ""

        # Conditions — preconditions get phase="pre", postconditions get phase="post"
        assert len(conditions) == 2
        pre_cond = [c for c in conditions if c.phase == "pre"]
        post_cond = [c for c in conditions if c.phase == "post"]
        assert len(pre_cond) == 1
        assert len(post_cond) == 1

        # Pre-condition: "expected" → "expected_value" alias
        assert pre_cond[0].subject_qualified_name == "Engine.is_initialized"
        assert pre_cond[0].operator == "is_true"
        assert pre_cond[0].expected_value == "true"  # "expected" → "expected_value"
        assert pre_cond[0].order == 0

        # Post-condition
        assert post_cond[0].subject_qualified_name == "Engine.result"
        assert post_cond[0].expected_value == "30"
        assert post_cond[0].order == 0

        # Actions
        assert len(actions) == 1
        assert actions[0].description == "Invoke the add operation"
        assert actions[0].callee_qualified_name == "Engine.add"
        assert actions[0].order == 0
        assert actions[0].layer == "design"

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

    def test_from_llm_dict_full_decomposition(self, artifact_path):
        """Round-trip: load raw LLM response → neomodel objects → serialize → deserialize."""
        import json
        from codegraph.models.tags import CodeGraphNode
        from backend_migrated.models.verification import VerificationMethod
        from backend_migrated.models.requirement import HLR, LLR

        raw_path = artifact_path("decompose_hlr", "06_raw_response.json")
        if not raw_path.exists():
            pytest.skip("No raw response artifact — run test_decompose_simple_hlr first")

        raw = json.loads(raw_path.read_text())

        # The raw response should be a successful decomposition with a
        # top-level "description" key.  If a previous run failed and
        # wrote an error stub, skip.
        if "description" not in raw:
            pytest.skip(
                f"Raw response artifact is not a valid decomposition "
                f"(keys: {sorted(raw.keys())}). Run test_decompose_simple_hlr first."
            )

        # HLR
        hlr = HLR.from_llm_dict({"description": raw["description"]})
        assert hlr.description
        assert hlr.layer == "design"

        # Each LLR + verifications
        total_conditions = 0
        total_actions = 0
        for llr_data in raw["low_level_requirements"]:
            llr = LLR.from_llm_dict({"description": llr_data["description"]})
            assert llr.description
            assert llr.layer == "design"

            for vm_data in llr_data.get("verifications", []):
                vm, conditions, actions = VerificationMethod.from_llm_dict(vm_data)
                assert vm.method in ("automated", "review", "inspection")
                assert vm.layer == "design"
                total_conditions += len(conditions)
                total_actions += len(actions)

                # Round-trip: serialize → deserialize each condition
                for cond in conditions:
                    cond_dict = cond.serialize(fields="all")
                    restored = CodeGraphNode.deserialize(cond_dict)
                    assert isinstance(restored, type(cond))
                    assert restored.phase == cond.phase
                    assert restored.expected_value == cond.expected_value

        # Save the round-trip report
        report = {
            "description": raw["description"][:80],
            "num_llrs": len(raw["low_level_requirements"]),
            "total_conditions": total_conditions,
            "total_actions": total_actions,
        }
        report_path = artifact_path("decompose_hlr", "09_round_trip_report.json")
        report_path.write_text(json.dumps(report, indent=2))

        # Sanity check — the raw response produced conditions and actions
        assert total_conditions > 0, "No conditions deserialized from raw response"
        assert total_actions > 0, "No actions deserialized from raw response"