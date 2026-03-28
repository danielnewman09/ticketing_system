"""Sync design-intent and requirement data from SQLite to Neo4j."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from backend.db.neo4j import get_neo4j_session, verify_connection

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
    """Delete all Design, HLR, and LLR nodes (and their relationships) from Neo4j."""
    if not verify_connection():
        log.warning("Neo4j unavailable — skipping clear")
        return False
    try:
        with get_neo4j_session() as session:
            session.run("MATCH (n) WHERE n:Design OR n:HLR OR n:LLR DETACH DELETE n")
        log.info("Cleared design graph from Neo4j")
        return True
    except Exception:
        log.warning("Neo4j clear failed", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Design nodes & triples
# ---------------------------------------------------------------------------

def sync_design_node(neo4j_session: Neo4jSession, node) -> None:
    """MERGE a Design node by qualified_name, setting all properties."""
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
    neo4j_session.run(cypher, {
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
    })


def sync_design_triple(neo4j_session: Neo4jSession, triple) -> None:
    """MATCH endpoints and MERGE the typed relationship."""
    pred_name = triple.predicate.name if hasattr(triple.predicate, "name") else triple.predicate
    rel_type = PREDICATE_TO_REL_TYPE.get(pred_name)
    if not rel_type:
        log.warning("Unknown predicate %r — skipping triple", pred_name)
        return

    subj_qname = triple.subject.qualified_name if hasattr(triple.subject, "qualified_name") else triple.subject
    obj_qname = triple.object.qualified_name if hasattr(triple.object, "qualified_name") else triple.object

    cypher = f"""
    MATCH (s:Design {{qualified_name: $subj}})
    MATCH (o:Design {{qualified_name: $obj}})
    MERGE (s)-[r:{rel_type}]->(o)
    """
    neo4j_session.run(cypher, {"subj": subj_qname, "obj": obj_qname})


# ---------------------------------------------------------------------------
# Requirement reference nodes
# ---------------------------------------------------------------------------

def sync_requirement_node(neo4j_session: Neo4jSession, req, label: str) -> None:
    """MERGE a lightweight HLR or LLR reference node by sqlite_id."""
    title = req.description[:200] if req.description else ""
    cypher = f"""
    MERGE (r:{label} {{sqlite_id: $sid}})
    SET r.title = $title,
        r.requirement_type = $rtype
    """
    neo4j_session.run(cypher, {
        "sid": req.id,
        "title": title,
        "rtype": label.lower(),
    })


def sync_requirement_links(neo4j_session: Neo4jSession, req, label: str) -> None:
    """Create TRACES_TO relationships from requirement to linked Design nodes."""
    for triple in req.triples:
        subj_qname = triple.subject.qualified_name
        obj_qname = triple.object.qualified_name
        # Link requirement to both subject and object of the triple
        cypher = f"""
        MATCH (r:{label} {{sqlite_id: $sid}})
        MATCH (d:Design {{qualified_name: $qname}})
        MERGE (r)-[:TRACES_TO]->(d)
        """
        neo4j_session.run(cypher, {"sid": req.id, "qname": subj_qname})
        neo4j_session.run(cypher, {"sid": req.id, "qname": obj_qname})


def sync_requirement_hierarchy(neo4j_session: Neo4jSession, hlr) -> None:
    """Create DECOMPOSES relationships from LLRs to their parent HLR."""
    for llr in hlr.low_level_requirements:
        cypher = """
        MATCH (l:LLR {sqlite_id: $llr_id})
        MATCH (h:HLR {sqlite_id: $hlr_id})
        MERGE (l)-[:DECOMPOSES]->(h)
        """
        neo4j_session.run(cypher, {"llr_id": llr.id, "hlr_id": hlr.id})


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
    """Bulk sync all design nodes, triples, requirement refs, and links."""
    from backend.db.models import (
        HighLevelRequirement,
        LowLevelRequirement,
        OntologyNode,
        OntologyTriple,
    )

    stats = {
        "nodes": 0,
        "triples": 0,
        "hlrs": 0,
        "llrs": 0,
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

    # HLR reference nodes + links
    for hlr in sql_session.query(HighLevelRequirement).all():
        sync_requirement_node(neo4j_session, hlr, "HLR")
        sync_requirement_links(neo4j_session, hlr, "HLR")
        sync_requirement_hierarchy(neo4j_session, hlr)
        stats["hlrs"] += 1

    # LLR reference nodes + links
    for llr in sql_session.query(LowLevelRequirement).all():
        sync_requirement_node(neo4j_session, llr, "LLR")
        sync_requirement_links(neo4j_session, llr, "LLR")
        stats["llrs"] += 1

    # Cross-layer links
    stats["implemented_by"] = link_implemented_nodes(neo4j_session)

    return stats


# ---------------------------------------------------------------------------
# Convenience: sync with graceful degradation
# ---------------------------------------------------------------------------

def try_sync_design_nodes_and_triples(nodes, triples):
    """Sync a batch of design nodes and triples to Neo4j.

    Logs a warning and returns False if Neo4j is unavailable.
    """
    if not verify_connection():
        log.warning("Neo4j unavailable — design sync deferred to migration script")
        return False

    try:
        with get_neo4j_session() as session:
            for node in nodes:
                sync_design_node(session, node)
            for triple in triples:
                sync_design_triple(session, triple)
        return True
    except Exception:
        log.warning("Neo4j sync failed — design sync deferred", exc_info=True)
        return False


def try_sync_requirement(req, label: str, hlr=None):
    """Sync a requirement reference node (and hierarchy if hlr given).

    Logs a warning and returns False if Neo4j is unavailable.
    """
    if not verify_connection():
        log.warning("Neo4j unavailable — requirement sync deferred to migration script")
        return False

    try:
        with get_neo4j_session() as session:
            sync_requirement_node(session, req, label)
            sync_requirement_links(session, req, label)
            if hlr is not None:
                sync_requirement_hierarchy(session, hlr)
        return True
    except Exception:
        log.warning("Neo4j sync failed — requirement sync deferred", exc_info=True)
        return False
