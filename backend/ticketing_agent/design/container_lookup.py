"""Utility for seeding container/smart-pointer types from the dependency graph.

Queries Neo4j for a curated set of standard C++ containers so they can be
pre-loaded into the design agent's dependency context.  This ensures that
``aggregates`` mechanism values like ``std::vector`` resolve to real Neo4j
nodes instead of disconnected stubs.
"""

import logging

log = logging.getLogger(__name__)

# Curated qualified names for standard containers used as ``aggregates``
# mechanism values.  These are always available from the cppreference index.
_AGGREGATE_CONTAINER_QNAMES = [
    "std::vector",
    "std::list",
    "std::deque",
    "std::array",
    "std::set",
    "std::map",
    "std::unordered_set",
    "std::unordered_map",
    "std::stack",
    "std::queue",
    "std::priority_queue",
]


def seed_container_lookup(
    neo4j_session,
    container_qnames: list[str] | None = None,
) -> dict[str, str]:
    """Query Neo4j for container nodes and return a bare-name -> qualified-name mapping.

    For each container found in the dependency graph, two entries are added:
    ``bare_name -> qualified_name`` and ``qualified_name -> qualified_name``.
    This allows the design agent and ``map_to_ontology`` to resolve either
    ``"vector"`` or ``"std::vector"`` to the real node.

    Args:
        neo4j_session: An active Neo4j session for querying.
        container_qnames: Override list of qualified names to look up.
            Defaults to ``_AGGREGATE_CONTAINER_QNAMES``.

    Returns:
        Dict mapping bare names and qualified names to qualified names.
        E.g. ``{"vector": "std::vector", "std::vector": "std::vector"}``
    """
    if container_qnames is None:
        container_qnames = _AGGREGATE_CONTAINER_QNAMES

    lookup: dict[str, str] = {}

    try:
        result = neo4j_session.run(
            "MATCH (n:Compound) "
            "WHERE n.qualified_name IN $names "
            "RETURN n.qualified_name AS qn, n.name AS name",
            names=container_qnames,
        )
        for record in result:
            qn = record["qn"]
            bare = record["name"] or qn.rsplit("::", 1)[-1]
            lookup[bare] = qn
            lookup[qn] = qn
    except Exception:
        log.warning("Failed to query Neo4j for container lookup", exc_info=True)

    return lookup


def get_container_class_info(
    neo4j_session,
    container_qnames: list[str] | None = None,
) -> list[dict]:
    """Return class-info dicts for the curated container set.

    Each dict has ``qualified_name``, ``name``, ``kind``, ``source``, and
    ``description`` keys - suitable for inclusion in the design prompt's dependency
    API section.

    Args:
        neo4j_session: An active Neo4j session for querying.
        container_qnames: Override list of qualified names to look up.

    Returns:
        List of dicts suitable for ``build_dependency_api_section``.
    """
    if container_qnames is None:
        container_qnames = _AGGREGATE_CONTAINER_QNAMES

    containers: list[dict] = []

    try:
        result = neo4j_session.run(
            "MATCH (n:Compound) "
            "WHERE n.qualified_name IN $names "
            "RETURN n.qualified_name AS qn, n.name AS name, "
            "n.kind AS kind, n.source AS source, n.brief AS brief",
            names=container_qnames,
        )
        for record in result:
            containers.append({
                "qualified_name": record["qn"],
                "name": record["name"] or record["qn"].rsplit("::", 1)[-1],
                "kind": record["kind"] or "class",
                "source": record["source"] or "cppreference",
                "description": record["brief"] or f"Standard library container: {record['qn']}",
            })
    except Exception:
        log.warning("Failed to query Neo4j for container class info", exc_info=True)

    return containers
