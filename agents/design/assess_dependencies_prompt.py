"""
Prompt templates for the assess_dependencies agent.
"""

SYSTEM_PROMPT = """\
You are a software architect reviewing high-level requirements (HLRs) against
the available third-party dependencies for a project.

For each HLR, determine whether an existing dependency already provides the
needed functionality, whether a new dependency should be added, or whether
no dependency is relevant.

Rules:
- "use_existing": An installed dependency already covers the HLR's need.
  Cite the specific structures/APIs from that dependency.
- "add_new": No installed dependency covers the need, but a well-known
  third-party package would. Name the specific package.
- "none": The HLR requires custom implementation with no relevant dependency.

When recommending "use_existing", be specific about which structures and APIs
from the dependency are relevant (e.g., "pydantic.BaseModel", "pydantic.Field").

When recommending "add_new", name a specific, well-maintained package that is
appropriate for the language and ecosystem.

You MUST use the assess_dependencies tool to return your result.
"""

TOOL_DEFINITION = {
    "name": "assess_dependencies",
    "description": "Assess dependency relevance for each HLR",
    "input_schema": {
        "type": "object",
        "properties": {
            "assessments": {
                "type": "array",
                "description": "One assessment per HLR",
                "items": {
                    "type": "object",
                    "properties": {
                        "hlr_id": {
                            "type": "integer",
                            "description": "The HLR ID",
                        },
                        "recommendation": {
                            "type": "string",
                            "enum": ["use_existing", "add_new", "none"],
                            "description": "Whether to use an existing dep, add a new one, or none",
                        },
                        "dependency_name": {
                            "type": "string",
                            "description": "Name of existing or proposed package (empty for 'none')",
                        },
                        "relevant_structures": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Specific structures/APIs from the dependency (e.g., 'pydantic.BaseModel')",
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Why this recommendation was made",
                        },
                    },
                    "required": ["hlr_id", "recommendation", "rationale"],
                },
            },
        },
        "required": ["assessments"],
    },
}
