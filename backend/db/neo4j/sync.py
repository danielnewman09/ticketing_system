"""Sync design-intent data from SQLite to Neo4j.

Only **Design** nodes and triples are synced to Neo4j.  Requirements
(HLRs, LLRs), verifications, and tasks are relational data that lives
entirely in SQLite.  The graph views read requirement associations from
SQLite and join them to Neo4j Design nodes at query time.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from services.dependencies import get_neo4j

if TYPE_CHECKING:
    from neo4j import Session as Neo4jSession
    from sqlalchemy.orm import Session as SqlSession

log = logging.getLogger(__name__)

# Maps lowercase predicate names (SQLite) → UPPER_SNAKE_CASE Neo4j rel types
PREDICATE_TO_REL_TYPE = {
    "associates": "ASSOCIATES",
    "aggregates": "AGGREGATES",
    "composes": "COMPOSES",
    "depends_on": "DEPENDS_ON",
    "generalizes": "GENERALIZES",
    "realizes": "REALIZES",
    "invokes": "INVOKES",
}


# ---------------------------------------------------------------------------
# Clear all design-intent nodes
# ---------------------------------------------------------------------------


def clear_design_graph():
    """Delete all Design nodes (and their relationships) from Neo4j."""
    try:
        with get_neo4j().session() as session:
            session.run("MATCH (n:Design) DETACH DELETE n")
        log.info("Cleared design graph from Neo4j")
        return True
    except Exception:
        log.warning("Neo4j clear failed", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Design nodes & triples
# ---------------------------------------------------------------------------


def sync_design_node(neo4j_session: Neo4jSession, node) -> None:
    """MERGE a Design node by qualified_name, setting all properties.

    Skips dependency-reference stubs — their real nodes exist as
    Compound nodes in Neo4j. Edges to them are created via
    sync_design_triple which routes to Compounds directly.
    """
    if getattr(node, 'source_type', None) == 'dependency':
        log.debug("Skipping dependency stub %s in Neo4j sync", node.qualified_name)
        return

    kind_label = node.kind.capitalize() if node.kind else "Unknown"
    # Cypher doesn't allow parameterized labels, so we interpolate safely
    # (kind is from a known set of values)
    cypher = f"""
    MERGE (n:Design {{qualified_name: $qname}})
    SET n:{kind_label},
        n.name = $name,
        n.kind = $kind,
        n.specialization = $specialization,
        n.visibility = $visibility,
        n.description = $description,
        n.refid = $refid,
        n.source_type = $source_type,
        n.component_id = $component_id,
        n.is_intercomponent = $is_intercomponent,
        n.file_path = $file_path,
        n.line_number = $line_number,
        n.type_signature = $type_signature,
        n.argsstring = $argsstring,
        n.definition = $definition,
        n.is_static = $is_static,
        n.is_const = $is_const,
        n.is_virtual = $is_virtual,
        n.is_abstract = $is_abstract,
        n.is_final = $is_final
    """
    neo4j_session.run(
        cypher,
        {
            "qname": node.qualified_name,
            "name": node.name,
            "kind": node.kind,
            "specialization": node.specialization or "",
            "visibility": node.visibility or "",
            "description": node.description or "",
            "refid": node.refid or "",
            "source_type": node.source_type or "",
            "component_id": node.component_id,
            "is_intercomponent": node.is_intercomponent,
            "file_path": node.file_path or "",
            "line_number": node.line_number,
            "type_signature": node.type_signature or "",
            "argsstring": node.argsstring or "",
            "definition": node.definition or "",
            "is_static": node.is_static,
            "is_const": node.is_const,
            "is_virtual": node.is_virtual,
            "is_abstract": node.is_abstract,
            "is_final": node.is_final,
        },
    )


def sync_design_triple(neo4j_session: Neo4jSession, triple) -> None:
    """MATCH endpoints and MERGE the typed relationship."""
    pred_name = triple.predicate.name if hasattr(triple.predicate, "name") else triple.predicate
    rel_type = PREDICATE_TO_REL_TYPE.get(pred_name)
    if not rel_type:
        log.warning("Unknown predicate %r — skipping triple", pred_name)
        return

    subj_qname = (
        triple.subject.qualified_name
        if hasattr(triple.subject, "qualified_name")
        else triple.subject
    )
    obj_qname = (
        triple.object.qualified_name if hasattr(triple.object, "qualified_name") else triple.object
    )

    # Try Design→Design first; fall back to Design→Compound for dependency classes
    cypher = f"""
    MATCH (s:Design {{qualified_name: $subj}})
    OPTIONAL MATCH (o_design:Design {{qualified_name: $obj}})
    OPTIONAL MATCH (o_compound:Compound {{qualified_name: $obj}})
    WITH s, coalesce(o_design, o_compound) AS target
    WHERE target IS NOT NULL
    MERGE (s)-[r:{rel_type}]->(target)
    """
    log.debug("Cypher Query: {cypher}")
    neo4j_session.run(cypher, {"subj": subj_qname, "obj": obj_qname})


# ---------------------------------------------------------------------------
# Cross-layer link
# ---------------------------------------------------------------------------


def link_implemented_nodes(neo4j_session: Neo4jSession) -> int:
    """Match Design nodes to as-built Compound/Member/Namespace by qualified_name or refid.

    Returns the number of IMPLEMENTED_BY relationships created.
    """
    result = neo4j_session.run("""
    MATCH (d:Design)
    WHERE d.qualified_name IS NOT NULL AND d.qualified_name <> ''
    OPTIONAL MATCH (c:Compound {qualified_name: d.qualified_name})
    OPTIONAL MATCH (m:Member {qualified_name: d.qualified_name})
    OPTIONAL MATCH (ns:Namespace {name: d.qualified_name})
    WITH d, coalesce(c, m, ns) AS target
    WHERE target IS NOT NULL
    MERGE (d)-[:IMPLEMENTED_BY]->(target)
    RETURN count(*) AS cnt
    """)
    record = result.single()
    cnt = record["cnt"] if record else 0

    # Also try matching by refid
    result2 = neo4j_session.run("""
    MATCH (d:Design)
    WHERE d.refid IS NOT NULL AND d.refid <> ''
    AND NOT EXISTS { (d)-[:IMPLEMENTED_BY]->() }
    OPTIONAL MATCH (c:Compound {refid: d.refid})
    OPTIONAL MATCH (m:Member {refid: d.refid})
    WITH d, coalesce(c, m) AS target
    WHERE target IS NOT NULL
    MERGE (d)-[:IMPLEMENTED_BY]->(target)
    RETURN count(*) AS cnt
    """)
    record2 = result2.single()
    cnt += record2["cnt"] if record2 else 0

    return cnt


# ---------------------------------------------------------------------------
# Bulk sync
# ---------------------------------------------------------------------------


def sync_full_design(neo4j_session: Neo4jSession, sql_session: SqlSession) -> dict:
    """Bulk sync all design nodes and triples.  Requirements stay in SQLite."""
    from backend.db.models import (
        OntologyNode,
        OntologyTriple,
    )

    stats = {
        "nodes": 0,
        "triples": 0,
        "implemented_by": 0,
    }

    # Nodes
    for node in sql_session.query(OntologyNode).all():
        sync_design_node(neo4j_session, node)
        stats["nodes"] += 1

    # Triples
    for triple in sql_session.query(OntologyTriple).all():
        sync_design_triple(neo4j_session, triple)
        stats["triples"] += 1

    # Cross-layer links
    stats["implemented_by"] = link_implemented_nodes(neo4j_session)

    return stats


# ---------------------------------------------------------------------------
# Task sync (Task nodes are lightweight cross-references, not full
# requirement data)
# ---------------------------------------------------------------------------


def sync_task(neo4j_session, task):
    """MERGE a Task node in Neo4j with its design links."""
    neo4j_session.run(
        """
    MERGE (t:Task {sqlite_id: $tid})
    SET t.title = $title,
        t.description = $description,
        t.status = $status,
        t.component_id = $component_id,
        t.created_at = $created_at,
        t.updated_at = $updated_at
    """,
        {
            "tid": task.id,
            "title": task.title[:300],
            "description": task.description,
            "status": task.status,
            "component_id": task.component_id,
            "created_at": str(task.created_at),
            "updated_at": str(task.updated_at),
        },
    )

    for td in task.design_nodes:
        node_qname = td.ontology_node.qualified_name
        neo4j_session.run(
            """
        MATCH (t:Task {sqlite_id: $tid})
        MATCH (d:Design {qualified_name: $qname})
        MERGE (t)-[:IMPLEMENTING]->(d)
        """,
            {"tid": task.id, "qname": node_qname},
        )


def sync_implementation_status(neo4j_session, node):
    """Update a Design node's implementation status in Neo4j."""
    neo4j_session.run(
        """
    MATCH (d:Design {qualified_name: $qname})
    SET d.implementation_status = $status,
        d.source_file = $source_file,
        d.test_file = $test_file
    """,
        {
            "qname": node.qualified_name,
            "status": node.implementation_status,
            "source_file": node.source_file,
            "test_file": node.test_file,
        },
    )


# ---------------------------------------------------------------------------
# Convenience: sync with graceful degradation
# ---------------------------------------------------------------------------


def try_sync_design_nodes_and_triples(nodes, triples):
    """Sync a batch of design nodes and triples to Neo4j.

    Logs a warning and returns False if Neo4j is unavailable.
    """
    try:
        with get_neo4j().session() as session:
            for node in nodes:
                sync_design_node(session, node)
            for triple in triples:
                sync_design_triple(session, triple)
        return True
    except Exception:
        log.warning("Neo4j sync failed — design sync deferred", exc_info=True)
        return False