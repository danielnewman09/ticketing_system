"""Sync remaining data from SQLite to Neo4j.

Phase 1 note: Design node/triple sync has been replaced by DesignRepository
(direct writes during persistence). This module only handles:
- Implementation status sync (Design node properties from SQLAlchemy)
- Task sync (Task sqlite_id + IMPLEMENTING edges)
- Full design sync (cross-layer IMPLEMENTED_BY links only)
- clear_design_graph (utility)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import Session as Neo4jSession
    from sqlalchemy.orm import Session as SqlSession

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Clear all design-intent nodes
# ---------------------------------------------------------------------------


def clear_design_graph():
    """Delete all design graph nodes (and their relationships) from Neo4j."""
    from services.dependencies import get_neo4j
    from backend.db.neo4j.repositories.design import DesignRepository

    try:
        with get_neo4j().session() as session:
            repo = DesignRepository(session)
            repo.clear_design_graph()
        return True
    except Exception:
        log.warning("Neo4j clear failed", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Cross-layer link
# ---------------------------------------------------------------------------


def link_implemented_nodes(neo4j_session: Neo4jSession) -> int:
    """Match Design nodes to as-built Compound/Member/Namespace by qualified_name or refid.

    Returns the number of IMPLEMENTED_BY relationships created.
    """
    result = neo4j_session.run("""
    MATCH (d:Compound)
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
    MATCH (d:Compound)
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
# Bulk sync — now only handles IMPLEMENTED_BY links
# ---------------------------------------------------------------------------


def sync_full_design(neo4j_session: Neo4jSession, sql_session: SqlSession) -> dict:
    """Sync cross-layer IMPLEMENTED_BY links.

    In Phase 1, design nodes and triples are written directly to Neo4j
    via DesignRepository during persistence. This function only handles
    the IMPLEMENTED_BY linking between Design and Compound nodes.
    """
    stats = {
        "nodes": 0,
        "triples": 0,
        "implemented_by": 0,
    }

    # Cross-layer links
    stats["implemented_by"] = link_implemented_nodes(neo4j_session)

    return stats


# ---------------------------------------------------------------------------
# Task sync (Task nodes are lightweight cross-references, not full
# requirement data)
# ---------------------------------------------------------------------------


def sync_task(neo4j_session, task):
    """MERGE a Task node in Neo4j with its design links.

    Phase 1: TaskDesignNode links use qualified_name string instead of
    FK to ontology_nodes table.
    """
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

    # Delete existing IMPLEMENTING edges before re-creating
    neo4j_session.run(
        "MATCH (t:Task {sqlite_id: $tid})-[r:IMPLEMENTING]->() DELETE r",
        {"tid": task.id},
    )

    for td in task.design_nodes:
        # Phase 1: use qualified_name string (no FK to ontology_nodes)
        qname = getattr(td, "ontology_node_qualified_name", None)
        if qname is None:
            # Fallback: try the old FK-based relationship
            qname = getattr(td.ontology_node, "qualified_name", None) if hasattr(td, "ontology_node") and td.ontology_node else None
        if not qname:
            continue
        neo4j_session.run(
            """
        MATCH (t:Task {sqlite_id: $tid})
        MATCH (d:Compound {qualified_name: $qname})
        MERGE (t)-[:IMPLEMENTING]->(d)
        """,
            {"tid": task.id, "qname": qname},
        )


def sync_implementation_status(neo4j_session, node):
    """Update a Design node's implementation status in Neo4j.

    Phase 1: accepts either an OntologyNode (with .qualified_name,
    .implementation_status, .source_file, .test_file) or a
    (qualified_name, status, source_file, test_file) tuple.
    """
    # Handle both ORM objects and simple dicts/tuples
    if hasattr(node, "qualified_name"):
        qname = node.qualified_name
        status = node.implementation_status
        source_file = getattr(node, "source_file", "") or ""
        test_file = getattr(node, "test_file", "") or ""
    elif isinstance(node, dict):
        qname = node["qualified_name"]
        status = node["implementation_status"]
        source_file = node.get("source_file", "")
        test_file = node.get("test_file", "")
    else:
        log.warning("sync_implementation_status: unrecognised node type %s", type(node))
        return

    neo4j_session.run(
        """
    MATCH (d:Compound {qualified_name: $qname})
    SET d.implementation_status = $status,
        d.source_file = $source_file,
        d.test_file = $test_file
    """,
        {
            "qname": qname,
            "status": status,
            "source_file": source_file,
            "test_file": test_file,
        },
    )