"""Dependency research agent runner (called in a background thread)."""


def run_research(component_id: int) -> dict:
    """Run the research agent and return summary + recommendations.

    Re-entrant: can be called multiple times. Already-accepted dependencies
    are passed as existing_deps so the agent won't recommend them again.
    """
    from backend.db import get_session
    from backend.db.models import Component

    with get_session() as session:
        comp = session.query(Component).filter_by(id=component_id).first()
        if not comp:
            raise ValueError(f"Component {component_id} not found")

        # Capture all needed values inside the session
        comp_name = comp.name
        comp_description = comp.description or ""

        hlrs = [
            {"id": h.id, "description": h.description}
            for h in comp.high_level_requirements
        ]

        language = repr(comp.language) if comp.language else "C++"

        # Collect existing deps from the dependency manager
        existing_deps = []
        if comp.language:
            for dm in comp.language.dependency_managers:
                for d in dm.dependencies:
                    existing_deps.append(d.name)

    from backend.ticketing_agent.design.research_dependencies import research_dependencies
    return research_dependencies(
        component_name=comp_name,
        component_description=comp_description,
        hlrs=hlrs,
        language=language,
        existing_deps=existing_deps,
    )
