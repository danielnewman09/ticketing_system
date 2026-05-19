"""Prompt engineering for the implementation agent.

Generates real implementation code from skeleton stubs, design context,
and verification methods.
"""

SYSTEM_PROMPT = """\
You are an implementation agent. Your job is to fill in skeleton code with
working implementations that match the design and pass the verification tests.

## Input
For each implementation task you receive:
- task_title and task_description: what to build
- skeleton_code: the empty class/method stubs to fill in
- design_context: the OO design (classes, methods, attributes, relationships)
- verification_context: the verification methods (preconditions, actions, postconditions)
- test_code: the test file that must pass

## Rules
1. Fill in ONLY the method bodies -- do NOT change class names, method
   signatures, or attribute names from the skeleton.
2. The implementation MUST pass all provided tests.
3. Follow the design: if the design says a method takes (a, b) -> float,
   implement it that way.
4. Handle edge cases mentioned in verifications (e.g., division by zero,
   empty input, out-of-range values).
5. Use standard library only unless the design specifies external dependencies.
6. Keep implementations clean: short methods, descriptive variable names,
   no unnecessary comments.
7. If a method is not mentioned in any verification, implement the simplest
   reasonable behavior.
8. Return ONLY the complete file content -- do not wrap in markdown code
   fences. The output should be valid Python that can be written directly
   to a .py file.

## Output
Use the available tool to produce implementation files. Each file includes:
- file_path: the source file path (same as skeleton)
- content: the complete Python source with implementation filled in
- classes_modified: list of class names that were modified
"""

TOOL_DEFINITION = {
    "name": "produce_implementation",
    "description": (
        "Produce implementation files filling in the skeleton code."
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
                        "classes_modified": {
                            "type": "array", "items": {"type": "string"},
                        },
                    },
                    "required": ["file_path", "content"],
                },
            },
        },
        "required": ["files"],
    },
}


def build_implementation_context(
    task_title: str,
    task_description: str,
    skeleton_code: str = "",
    design_classes: list[dict] | None = None,
    verifications: list[dict] | None = None,
    test_code: str = "",
    llr_description: str = "",
) -> str:
    """Build context text for the implementation prompt."""
    lines = [
        f"## Task",
        f"title: {task_title}",
        f"description: {task_description}",
    ]

    if llr_description:
        lines.append(f"LLR context: {llr_description}")

    if skeleton_code:
        lines.append(f"\n## Skeleton Code (fill in method bodies)\n")
        lines.append(f"```python\n{skeleton_code}\n```")

    if design_classes:
        lines.append(f"\n## Design Context\n")
        for cls in design_classes:
            lines.append(f"### {cls.get('name', '?')}")
            if cls.get('description'):
                lines.append(f"Description: {cls['description']}")
            if cls.get('attributes'):
                lines.append("Attributes:")
                for a in cls['attributes']:
                    lines.append(f"  - {a['name']}: {a.get('type_name', 'any')}")
            if cls.get('methods'):
                lines.append("Methods:")
                for m in cls['methods']:
                    params = ", ".join(m.get('parameters', []))
                    lines.append(f"  - {m['name']}({params}) -> {m.get('return_type', 'void')}")
                    if m.get('description'):
                        lines.append(f"    {m['description']}")
            lines.append("")

    if verifications:
        lines.append(f"\n## Verification Methods\n")
        for v in verifications:
            lines.append(f"- {v.get('test_name', '?')}: {v.get('description', '')}")
            if v.get('postconditions'):
                for pc in v['postconditions']:
                    lines.append(f"  -> {pc}")
            lines.append("")

    if test_code:
        lines.append(f"\n## Test Code (must pass)\n")
        lines.append(f"```python\n{test_code}\n```")

    return "\n".join(lines)
