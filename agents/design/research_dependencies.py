"""
Agent that researches third-party dependencies for a component.

Searches the web for candidate libraries, enriches with GitHub metrics,
and produces structured recommendations with pros/cons for human review.

Runs after assign_components so each component has HLRs and a description.
"""

import logging

from agents.llm_client import call_tool
from agents.search.web_search import search_and_enrich

log = logging.getLogger(__name__)


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


def _build_search_queries(component_desc: str, hlrs: list[dict]) -> list[str]:
    """Derive search queries from component description and HLRs."""
    queries = []
    # Extract key themes from HLR descriptions
    for hlr in hlrs:
        desc = hlr.get("description", "")
        # Take meaningful noun phrases from HLR descriptions
        if len(desc) > 20:
            queries.append(desc[:100])
    # Add component-level query
    if component_desc:
        # Take the first sentence/line
        first_line = component_desc.split("\n")[0].strip("# ").strip()
        if first_line:
            queries.append(first_line)
    return queries[:5]  # Limit to avoid too many searches


def research_dependencies(
    component_name: str,
    component_description: str,
    hlrs: list[dict],
    language: str,
    existing_deps: list[str] | None = None,
    model: str = "",
    prompt_log_file: str = "",
) -> dict:
    """Research dependencies for a component.

    Args:
        component_name: Name of the component.
        component_description: Markdown description of the component.
        hlrs: HLR dicts with 'id' and 'description'.
        language: Target language (e.g., "C++", "Python").
        existing_deps: Names of already-installed dependencies.
        model: LLM model override.
        prompt_log_file: Optional prompt log path.

    Returns:
        Dict with 'summary' (str) and 'recommendations' (list of dicts).
    """
    existing_deps = existing_deps or []

    # Step 1: Search for candidate libraries
    queries = _build_search_queries(component_description, hlrs)
    all_candidates = []
    seen_urls = set()

    for query in queries:
        candidates = search_and_enrich(query, language, max_results=3)
        for c in candidates:
            if c["github_url"] not in seen_urls:
                seen_urls.add(c["github_url"])
                all_candidates.append(c)

    log.info(
        "Found %d candidate libraries for %s from %d queries",
        len(all_candidates), component_name, len(queries),
    )

    # Step 2: Format search results for the LLM
    if all_candidates:
        candidates_text = []
        for i, c in enumerate(all_candidates, 1):
            gh = c.get("github", {})
            candidates_text.append(
                f"### Candidate {i}: {gh.get('name', c['title'])}\n"
                f"- GitHub: {c['github_url']}\n"
                f"- Stars: {gh.get('stars', '?')}\n"
                f"- License: {gh.get('license', '?')}\n"
                f"- Language: {gh.get('language', '?')}\n"
                f"- Last pushed: {gh.get('last_pushed', '?')}\n"
                f"- Description: {gh.get('description', c.get('snippet', ''))}\n"
            )
        search_section = "\n".join(candidates_text)
    else:
        search_section = "(No candidates found via web search)"

    hlr_text = "\n".join(
        f"- HLR {h['id']}: {h['description']}" for h in hlrs
    )

    existing_text = (
        "\n".join(f"- {d}" for d in existing_deps)
        if existing_deps else "(none)"
    )

    user_message = (
        f"## Component: {component_name}\n\n"
        f"{component_description}\n\n"
        f"## Language: {language}\n\n"
        f"## Existing Dependencies\n\n{existing_text}\n\n"
        f"## Requirements\n\n{hlr_text}\n\n"
        f"## Web Search Results\n\n{search_section}\n\n"
        f"Evaluate the candidates and produce recommendations. Include any "
        f"well-known libraries from your training data that the search may "
        f"have missed. Always include GitHub URLs."
    )

    # Step 3: LLM evaluation
    result = call_tool(
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        tools=[TOOL_DEFINITION],
        tool_name="produce_recommendations",
        model=model,
        prompt_log_file=prompt_log_file,
    )

    # Backfill GitHub metrics from search results into recommendations
    gh_by_url = {c["github_url"]: c.get("github", {}) for c in all_candidates}
    for rec in result.get("recommendations", []):
        url = rec.get("github_url", "")
        if url in gh_by_url:
            gh = gh_by_url[url]
            if not rec.get("stars"):
                rec["stars"] = gh.get("stars", 0)
            if not rec.get("license"):
                rec["license"] = gh.get("license", "")
            if not rec.get("last_updated"):
                rec["last_updated"] = gh.get("last_pushed", "")

    return {
        "summary": result.get("summary", ""),
        "recommendations": result.get("recommendations", []),
    }
