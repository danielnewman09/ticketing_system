"""
Agent that derives an ontology design (classes, relationships) from
a set of decomposed requirements.

Takes the existing HLRs and LLRs and produces:
- Ontology nodes (classes, structs, enums, etc.) with fully qualified names
- Triples (subject --predicate--> object) between nodes
- Links mapping each requirement to its associated triples

Can be used standalone (CLI) or imported by Django views/management commands.
"""

import json

from llm_caller import call_tool
from backend.db.models import Predicate
from backend.db.models.ontology import NODE_KIND_VALUES
from backend.codebase.schemas import DesignSchema
from backend.db.models.requirements import format_hlrs_for_prompt

from backend.ticketing_agent.design.design_ontology_prompt import (
    SYSTEM_PROMPT,
    build_specializations_section,
)

TOOL_DEFINITION = {
    "name": "produce_design",
    "description": "Return the ontology design derived from the requirements",
    "input_schema": DesignSchema.model_json_schema(),
}


def design(
    hlrs: list[dict],
    llrs: list[dict],
    language: str = "",
    model: str = "",
    prompt_log_file: str = "",
) -> DesignSchema:
    """
    Takes lists of HLR/LLR dicts and returns an ontology design.

    Each HLR dict: {id, description}
    Each LLR dict: {id, hlr_id, description}
    """
    requirements_text = format_hlrs_for_prompt(hlrs, llrs)

    # Build system prompt with allowed predicates from DB
    predicate_names = list(Predicate.objects.values_list("name", flat=True))
    if not predicate_names:
        Predicate.ensure_defaults()
        predicate_names = list(Predicate.objects.values_list("name", flat=True))
    system_prompt = SYSTEM_PROMPT.format(
        predicates=", ".join(predicate_names),
        node_kinds=", ".join(f'"{k}"' for k in sorted(NODE_KIND_VALUES)),
        specializations_section=build_specializations_section(language),
    )

    result = call_tool(
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": (
                    "Derive an ontology design from these requirements:\n\n"
                    f"{requirements_text}"
                ),
            }
        ],
        tools=[TOOL_DEFINITION],
        tool_name="produce_design",
        model=model,
        prompt_log_file=prompt_log_file,
    )

    return DesignSchema.model_validate(result)


if __name__ == "__main__":
    import os
    import sys

    from backend.db import init_db, get_session
    from backend.db.models import HighLevelRequirement, LowLevelRequirement

    init_db()

    with get_session() as session:
        hlrs = [{"id": h.id, "description": h.description} for h in session.query(HighLevelRequirement).all()]
        llrs = [
            {"id": l.id, "description": l.description, "hlr_id": l.high_level_requirement_id}
            for l in session.query(LowLevelRequirement).all()
        ]

    if not hlrs:
        print("No requirements found. Run the demo or create some first.")
        sys.exit(1)

    result = design(hlrs, llrs)
    print(json.dumps(result.model_dump(), indent=2))
