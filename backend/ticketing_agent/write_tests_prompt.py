"""Prompt engineering for the test writer agent.

Generates pytest unit tests that map 1:1 to VerificationMethod specs
(preconditions, actions, postconditions). Each test includes a docstring
referencing the LLR ID for traceability.
"""

SYSTEM_PROMPT = """\
You are a test writer agent. Your job is to write pytest unit tests that
directly implement the verification procedures defined for low-level
requirements.

## Input
For each verification method you receive:
- test_name: the exact function name to generate
- method: verification type ("automated" = unit test)
- description: what the test verifies
- preconditions: member state assertions before the stimulus
- actions: ordered steps/stimuli to apply
- postconditions: expected member state after the stimulus

## Rules
1. Generate ONE test function per verification method, named exactly
   as the `test_name` field.
2. The test docstring MUST include: "LLR {id}: {description}" for traceability.
3. Use the standard pytest pattern: arrange-act-assert.
   - Arrange: set up preconditions (create objects, set member state)
   - Act: execute the actions (call the method being tested)
   - Assert: verify postconditions using assert statements
4. Use `pytest.raises(ExpectedError)` when postconditions indicate an error.
5. Use `pytest.approx()` for float comparisons with tolerance.
6. Import the class under test from the skeleton module path.
   Path format: `from src.<module>.<module> import <ClassName>`
7. If a verification references multiple classes, import all of them.
8. Tests MUST be valid Python that passes `pytest --collect-only`.
9. Do NOT use `unittest.TestCase` — use plain pytest functions.

## Output
Produce test files via the available tool. Each file includes:
- file_path: the full path under tests/
- content: the complete pytest test file source
- test_names: list of test function names in the file
"""

TOOL_DEFINITION = {
    "name": "produce_test_files",
    "description": (
        "Generate pytest test files that implement the verification procedures."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "content": {"type": "string"},
                        "test_names": {
                            "type": "array", "items": {"type": "string"},
                        },
                    },
                    "required": ["file_path", "content", "test_names"],
                },
            },
        },
        "required": ["files"],
    },
}


def build_test_context(
    verifications: list[dict],
    skeleton_code: str = "",
    skeleton_files: list[str] | None = None,
    llr_id: int = 0,
    llr_description: str = "",
    module_path: str = "",
) -> str:
    """Build context text for the test writer prompt."""
    lines = [f"## Requirement\n", f"LLR {llr_id}: {llr_description}\n"]

    if module_path:
        lines.append(f"Module path: `{module_path}`\n")

    if skeleton_files:
        lines.append("## Skeleton Files (import targets)\n")
        for f in skeleton_files:
            lines.append(f"- `{f}`")
        lines.append("")

    lines.append("## Verification Methods\n")
    for i, v in enumerate(verifications, 1):
        lines.append(f"### Verification {i}")
        lines.append(f"test_name: `{v.get('test_name', 'unnamed')}`")
        lines.append(f"method: {v.get('method', 'automated')}")
        lines.append(f"description: {v.get('description', '')}")

        if v.get('preconditions'):
            lines.append("preconditions:")
            for pc in v['preconditions']:
                lines.append(f"  - {pc}")
        if v.get('actions'):
            lines.append("actions:")
            for a in v['actions']:
                lines.append(f"  - {a}")
        if v.get('postconditions'):
            lines.append("postconditions:")
            for pc in v['postconditions']:
                lines.append(f"  - {pc}")
        lines.append("")

    if skeleton_code:
        lines.append(f"## Skeleton Source Code\n")
        lines.append(f"```python\n{skeleton_code}\n```\n")

    return "\n".join(lines)
