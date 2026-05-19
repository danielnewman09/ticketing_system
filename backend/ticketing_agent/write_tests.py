"""Agent: write pytest unit tests from verification methods and skeleton code.

Takes verification procedures (preconditions, actions, postconditions) and
generates pytest test files that map 1:1 to each verification method.

Usage:
    from backend.ticketing_agent.write_tests import write_tests

    results = write_tests(
        verifications=verifications_list,
        skeleton_files= skeleton_file_contents,
        module_path="src.calculator.engine",
    )
"""

import logging
from dataclasses import dataclass, field

from backend.ticketing_agent.write_tests_prompt import (
    SYSTEM_PROMPT,
    TOOL_DEFINITION,
    build_test_context,
)

log = logging.getLogger("agents.write_tests")


@dataclass
class TestFileOutput:
    """One generated test file."""
    file_path: str
    content: str
    test_names: list[str] = field(default_factory=list)


def write_tests(
    verifications: list[dict],
    skeleton_files: list[str] | None = None,
    skeleton_code: str = "",
    llr_id: int = 0,
    llr_description: str = "",
    module_path: str = "",
    model: str = "",
    prompt_log_file: str = "",
) -> list[TestFileOutput]:
    """Generate pytest test files from verification methods.

    Args:
        verifications: List of verification dicts with test_name, method,
            description, preconditions, actions, postconditions.
        skeleton_files: List of skeleton file paths (import targets).
        skeleton_code: Source code of the skeleton being tested.
        llr_id: LLR database ID for traceability.
        llr_description: LLR description text.
        module_path: Python module path for imports (e.g. "src.calculator.engine").
        model: LLM model override.
        prompt_log_file: Log path for prompt conversation.

    Returns:
        List of TestFileOutput with file paths and content.
    """
    context = build_test_context(
        verifications=verifications,
        skeleton_code=skeleton_code,
        skeleton_files=skeleton_files,
        llr_id=llr_id,
        llr_description=llr_description,
        module_path=module_path,
    )

    user_msg = f"Generate pytest test files for these verification methods:\n\n{context}"

    from llm_caller import call_tool

    result = call_tool(
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
        tools=[TOOL_DEFINITION],
        tool_name="produce_test_files",
        model=model,
        prompt_log_file=prompt_log_file,
    )

    return [
        TestFileOutput(
            file_path=f["file_path"],
            content=f["content"],
            test_names=f.get("test_names", []),
        )
        for f in result["files"]
    ]


# ---------------------------------------------------------------------------
# Deterministic test generator (fallback when LLM unavailable)
# ---------------------------------------------------------------------------

def generate_deterministic_tests(
    verifications: list[dict],
    module_path: str = "",
    llr_id: int = 0,
    llr_description: str = "",
) -> list[TestFileOutput]:
    """Generate basic pytest tests without LLM — arrange/act/assert skeleton.

    Useful as a fallback or bootstrapping path.  The generated tests are
    syntactically valid but contain placeholder assertions that the LLM
    or a human should refine.
    """
    if not verifications:
        return []

    imports = []
    if module_path:
        # Best-effort: try to extract class name from module path
        parts = module_path.split(".")
        if len(parts) >= 2:
            mod = parts[-1]
            imports.append(f"from {module_path} import {mod.title().replace('_', '')}")

    test_funcs: list[str] = []
    test_names: list[str] = []

    for v in verifications:
        test_name = v.get("test_name", "test_unnamed")
        desc = v.get("description", "")
        test_names.append(test_name)

        lines = [
            "",
            "",
            f"def {test_name}():",
            f'    """LLR {llr_id}: {desc}."""',
        ]

        preconditions = v.get("preconditions", [])
        actions = v.get("actions", [])
        postconditions = v.get("postconditions", [])

        if preconditions:
            lines.append("    # Arrange: preconditions")
            for pc in preconditions:
                lines.append(f"    # Pre: {pc}")
                lines.append(f"    pass  # TODO: set up {pc}")

        if actions:
            lines.append("")
            lines.append("    # Act")
            for a in actions:
                lines.append(f"    # Action: {a}")
                lines.append(f"    pass  # TODO: {a}")

        if postconditions:
            lines.append("")
            lines.append("    # Assert: postconditions")
            for pc in postconditions:
                lines.append(f"    # Post: {pc}")
                lines.append(f"    pass  # TODO: assert {pc}")
        else:
            lines.append("")
            lines.append("    # TODO: add assertions")

        test_funcs.append("\n".join(lines))

    header = [
        f'"""Tests for {module_path} — LLR {llr_id}."""',
        "",
    ]
    if "pytest" not in header[0]:
        header.insert(1, "import pytest")

    content = "\n".join(header + test_funcs + [""])
    file_path = f"tests/{module_path.replace('.', '/').replace('src/', '')}_test.py" if module_path else "tests/test_generated.py"

    return [TestFileOutput(
        file_path=file_path,
        content=content,
        test_names=test_names,
    )]
