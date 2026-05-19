"""Prompt engineering for task generation agent."""

SYSTEM_PROMPT = """\
You are a task generation agent. Your job is to break down an object-oriented
class design into discrete, independently-implementable tasks.

## Input
- OO class design (classes, methods, attributes, inheritance, associations)
- Verification methods tied to low-level requirements
- Existing codebase context (classes already implemented)

## Rules
1. Each task must implement ONE coherent unit of work (usually: one class or
   one method cluster with its associated verification methods).
2. Each task MUST list: which design nodes it covers, which verification tests
   it must satisfy, which files it creates/modifies.
3. Tasks should be ordered by dependency -- base classes and interfaces before
   derived classes. Utility classes before consumers.
4. The task's source_files and test_files must be explicit, valid paths.
5. For Python projects, use:
   - Source: `src/<package>/<module>.py`
   - Tests: `tests/<package>/test_<module>.py`

## Output
Produce a list of tasks via the available tool. Each task must include:
- title: short descriptive name
- description: what to build
- design_node_qualified_names: specific nodes from the design this task implements
- verification_test_names: specific test names from the verification methods
  that this task's implementation must satisfy
- source_files: files this task will create or modify
- test_files: test files this task will create
- dependencies: titles of other tasks this depends on
- estimated_complexity: low, medium, or high
"""

TOOL_DEFINITION = {
    "name": "generate_tasks",
    "description": (
        "Generate implementation tasks from the OO design and verification methods."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "design_node_qualified_names": {
                            "type": "array", "items": {"type": "string"},
                        },
                        "verification_test_names": {
                            "type": "array", "items": {"type": "string"},
                        },
                        "source_files": {"type": "array", "items": {"type": "string"}},
                        "test_files": {"type": "array", "items": {"type": "string"}},
                        "dependencies": {"type": "array", "items": {"type": "string"}},
                        "estimated_complexity": {
                            "type": "string", "enum": ["low", "medium", "high"],
                        },
                    },
                    "required": ["title", "description"],
                },
            },
            "component_name": {"type": "string"},
            "dependency_graph": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2, "maxItems": 2,
                },
            },
        },
        "required": ["tasks"],
    },
}


def build_task_context(
    classes: list[dict],
    verifications: list[dict],
    existing_classes: list[dict],
) -> str:
    """Build context text for the task generation prompt."""
    lines = ["## OO Class Design\n"]
    for cls in classes:
        lines.append(f"### {cls['name']}")
        if cls.get('module'):
            lines.append(f"Module: {cls['module']}")
        if cls.get('description'):
            lines.append(f"Description: {cls['description']}")
        if cls.get('attributes'):
            lines.append("Attributes:")
            for a in cls['attributes']:
                vis = a.get('visibility', 'public')
                lines.append(
                    f"  - {a['name']}: {a.get('type_name', 'any')} ({vis})"
                )
        if cls.get('methods'):
            lines.append("Methods:")
            for m in cls['methods']:
                params = ", ".join(m.get('parameters', []))
                ret = m.get('return_type', 'void')
                vis = m.get('visibility', 'public')
                lines.append(f"  - {m['name']}({params}) -> {ret} ({vis})")
        if cls.get('inherits_from'):
            lines.append(f"Inherits: {', '.join(cls['inherits_from'])}")
        if cls.get('requirement_ids'):
            lines.append(f"Requirements: {', '.join(cls['requirement_ids'])}")
        lines.append("")

    lines.append("## Verification Methods\n")
    for v in verifications:
        tn = v.get('test_name', 'unnamed')
        desc = v.get('description', '')
        lines.append(f"- [{v['method']}] {tn}: {desc}")
        if v.get('preconditions'):
            lines.append("  Pre-conditions:")
            for pc in v['preconditions']:
                lines.append(f"    - {pc}")
        if v.get('actions'):
            lines.append("  Actions:")
            for a in v['actions']:
                lines.append(f"    - {a}")
        if v.get('postconditions'):
            lines.append("  Post-conditions:")
            for pc in v['postconditions']:
                lines.append(f"    - {pc}")
        lines.append("")

    if existing_classes:
        lines.append("## Existing Classes (do NOT recreate)\n")
        for c in existing_classes:
            qn = c.get('qualified_name', c.get('name', '?'))
            lines.append(f"- {qn}")
        lines.append("")

    return "\n".join(lines)
