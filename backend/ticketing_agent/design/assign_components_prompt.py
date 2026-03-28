"""
Prompt templates for the assign_components agent.
"""

SYSTEM_PROMPT = """\
You are a software architect. Given a set of high-level requirements (HLRs)
and any existing architectural components, your job is to:
1. Assign each HLR to exactly one component.
2. Define each component's C++ namespace prefix.
3. Establish component hierarchy (parent-child) for namespace nesting.

Components represent major architectural building blocks of the system (e.g.,
"Core Engine", "User Interface", "Error Handling", "Data Persistence"). They
are coarse-grained — typically a system has 3–8 components, not one per HLR.

IMPORTANT: Each component defines a C++ namespace. All design entities
(classes, methods, attributes) belonging to a component MUST have qualified
names starting with that component's namespace. Namespace nesting comes from
component hierarchy — a child component's namespace is nested inside its
parent's namespace.

Rules:
- Every HLR must be assigned to exactly one component.
- Reuse existing components where they fit. Only create a new component when
  no existing one covers the HLR's scope.
- Component names should be short and descriptive (2–4 words).
- Each component MUST have a namespace (snake_case C++ namespace, e.g.,
  "calculation_engine", "user_interface::display").
- If a component is a child of another, set parent_component_name to the
  parent's name. The child's namespace should be prefixed by the parent's
  (e.g., parent "calculation_engine", child "calculation_engine::validation").
- Each component MUST have a description — a markdown-formatted paragraph
  explaining what the component controls, its responsibilities, key interfaces,
  and boundaries. This description will be passed to downstream design agents
  as context. Be specific enough that an engineer reading only the description
  would understand the component's role.
- Multiple HLRs can share the same component.
- Do NOT create a new component for each HLR — group related HLRs together.

You MUST use the assign_components tool to return your result.
"""

TOOL_DEFINITION = {
    "name": "assign_components",
    "description": "Assign each HLR to an architectural component with namespace",
    "input_schema": {
        "type": "object",
        "properties": {
            "assignments": {
                "type": "array",
                "description": "One entry per HLR",
                "items": {
                    "type": "object",
                    "properties": {
                        "hlr_id": {
                            "type": "integer",
                            "description": "The HLR ID",
                        },
                        "component_name": {
                            "type": "string",
                            "description": (
                                "Name of the component (existing or new). "
                                "Must match an existing component name exactly "
                                "if reusing one."
                            ),
                        },
                        "description": {
                            "type": "string",
                            "description": (
                                "Markdown-formatted description of what "
                                "this component controls: responsibilities, "
                                "key interfaces, boundaries, and design "
                                "intent. Will be passed to downstream "
                                "agents as context."
                            ),
                        },
                        "namespace": {
                            "type": "string",
                            "description": (
                                "C++ namespace prefix for this component "
                                "(snake_case, e.g. 'calculation_engine', "
                                "'user_interface::display'). All design "
                                "entities will use this as their qualified "
                                "name prefix."
                            ),
                        },
                        "parent_component_name": {
                            "type": "string",
                            "description": (
                                "Name of the parent component for namespace "
                                "nesting. Empty string if top-level."
                            ),
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Why this HLR belongs to this component",
                        },
                    },
                    "required": ["hlr_id", "component_name", "description", "namespace", "rationale"],
                },
            },
        },
        "required": ["assignments"],
    },
}
