"""
Prompt templates for the research_dependencies agent.
"""

SYSTEM_PROMPT = """\
You are a software architect researching third-party dependencies for a
component. You have been given the component description, its requirements,
and web search results for candidate libraries.

Your job is to evaluate each candidate and produce structured recommendations
with honest pros and cons.

Rules:
- Only recommend libraries that are well-maintained (recent commits, active community).
- Always include the GitHub URL for each recommendation.
- Be specific about which APIs/classes from the library are relevant.
- List concrete pros and cons — not generic statements.
- If a search result is not a library (e.g., a blog post or tutorial), skip it.
- If no good library exists for a need, say so — don't force a recommendation.
- Include the relevant HLR IDs that each library helps satisfy.

You MUST use the produce_recommendations tool to return your result.
"""

TOOL_DEFINITION = {
    "name": "produce_recommendations",
    "description": "Return dependency recommendations for a component",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Markdown summary of the overall dependency landscape for this component",
            },
            "recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Package/library name",
                        },
                        "github_url": {
                            "type": "string",
                            "description": "GitHub repository URL",
                        },
                        "description": {
                            "type": "string",
                            "description": "What the library does and why it's relevant",
                        },
                        "version": {
                            "type": "string",
                            "description": "Recommended version or latest known version",
                        },
                        "stars": {
                            "type": "integer",
                            "description": "GitHub stars count",
                        },
                        "license": {
                            "type": "string",
                            "description": "License type (e.g., MIT, Apache-2.0, BSD-3)",
                        },
                        "last_updated": {
                            "type": "string",
                            "description": "Last commit/release date",
                        },
                        "pros": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Specific advantages of this library",
                        },
                        "cons": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Specific disadvantages or concerns",
                        },
                        "relevant_hlrs": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "HLR IDs this library helps satisfy",
                        },
                        "relevant_structures": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Key APIs, classes, or functions to use (e.g., 'Eigen::Matrix3d')",
                        },
                    },
                    "required": ["name", "github_url", "description", "pros", "cons"],
                },
            },
        },
        "required": ["summary", "recommendations"],
    },
}
