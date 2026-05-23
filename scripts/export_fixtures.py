#!/usr/bin/env python
"""Export current database state to JSON fixtures for integration tests.

Phase 2 note: HLR/LLR data is now in Neo4j, not SQLite. The SQLite
fixture includes verification data (with plain low_level_requirement_id)
but not HLR/LLR tables. HLR/LLR data should be created via scripts or
the dashboard and then exported from Neo4j separately if needed.

Usage:
    source .venv/bin/activate
    python scripts/export_fixtures.py

Outputs:
    tests/integration/sqlite_fixtures.json   — components, ontology, verifications
    tests/integration/neo4j_fixtures.json    — design nodes & relationships
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv

load_dotenv()

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests", "integration")
SQLITE_FIXTURE = os.path.join(FIXTURES_DIR, "sqlite_fixtures.json")
NEO4J_FIXTURE = os.path.join(FIXTURES_DIR, "neo4j_fixtures.json")


# ---------------------------------------------------------------------------
# SQLite export (no HLR/LLR — those are in Neo4j)
# ---------------------------------------------------------------------------


def export_sqlite():
    """Dump domain tables from db.sqlite3 to a JSON fixture (excluding HLR/LLR)."""
    from backend.db import init_db, get_session
    from backend.db.models import (
        Component,
        DependencyManager,
        Dependency,
        Language,
        OntologyNode,
        OntologyTriple,
        Predicate,
        VerificationAction,
        VerificationCondition,
        VerificationMethod,
    )
    from backend.db.models.components import dependency_components

    init_db()
    os.makedirs(FIXTURES_DIR, exist_ok=True)

    with get_session() as session:
        data = {}

        data["languages"] = [
            {"id": l.id, "name": l.name, "version": l.version}
            for l in session.query(Language).order_by(Language.id).all()
        ]

        data["components"] = [
            {
                "id": c.id, "name": c.name, "description": c.description,
                "language_id": c.language_id, "parent_id": c.parent_id,
                "namespace": c.namespace,
            }
            for c in session.query(Component).order_by(Component.id).all()
        ]

        data["dependency_managers"] = [
            {
                "id": dm.id, "name": dm.name, "language_id": dm.language_id,
                "version": dm.version, "lock_file": dm.lock_file,
            }
            for dm in session.query(DependencyManager).order_by(DependencyManager.id).all()
        ]

        data["dependencies"] = [
            {"id": d.id, "name": d.name, "version": d.version, "manager_id": d.manager_id}
            for d in session.query(Dependency).order_by(Dependency.id).all()
        ]

        data["dependency_components"] = [
            {"component_id": cd.component_id, "dependency_id": cd.dependency_id}
            for cd in session.query(dependency_components).all()
        ]

        data["predicates"] = [
            {"id": p.id, "name": p.name, "description": p.description}
            for p in session.query(Predicate).order_by(Predicate.id).all()
        ]

        # HLR/LLR data is in Neo4j (Phase 2) — not exported from SQLite

        data["ontology_nodes"] = [
            {
                "id": n.id, "qualified_name": n.qualified_name, "name": n.name or "",
                "kind": n.kind or "", "specialization": n.specialization or "",
                "visibility": n.visibility or "", "description": n.description or "",
                "refid": n.refid or "", "component_id": n.component_id,
                "is_intercomponent": getattr(n, "is_intercomponent", False),
                "source_type": n.source_type or "",
                "type_signature": getattr(n, "type_signature", "") or "",
                "argsstring": getattr(n, "argsstring", "") or "",
                "definition": getattr(n, "definition", "") or "",
                "file_path": getattr(n, "file_path", "") or "",
                "line_number": n.line_number,
                "is_static": getattr(n, "is_static", False),
                "is_const": getattr(n, "is_const", False),
                "is_virtual": getattr(n, "is_virtual", False),
                "is_abstract": getattr(n, "is_abstract", False),
                "is_final": getattr(n, "is_final", False),
            }
            for n in session.query(OntologyNode).order_by(OntologyNode.id).all()
        ]

        data["ontology_triples"] = [
            {
                "id": t.id, "subject_id": t.subject_id,
                "predicate_id": t.predicate_id, "object_id": t.object_id,
            }
            for t in session.query(OntologyTriple).order_by(OntologyTriple.id).all()
        ]

        # HLR/LLR M2M relationships removed (Phase 2: data in Neo4j via TRACES_TO)

        data["verification_methods"] = [
            {
                "id": v.id, "method": v.method, "test_name": v.test_name or "",
                "description": v.description or "",
                "low_level_requirement_id": v.low_level_requirement_id,
            }
            for v in session.query(VerificationMethod).order_by(VerificationMethod.id).all()
        ]

        data["verification_conditions"] = [
            {
                "id": c.id, "verification_id": c.verification_id, "phase": c.phase or "pre",
                "order": c.order or 0, "member_qualified_name": c.member_qualified_name or "",
                "operator": c.operator or "", "expected_value": c.expected_value or "",
                "ontology_node_id": c.ontology_node_id,
            }
            for c in session.query(VerificationCondition).order_by(VerificationCondition.id).all()
        ]

        data["verification_actions"] = [
            {
                "id": a.id, "verification_id": a.verification_id,
                "order": a.order or 0, "description": a.description or "",
                "member_qualified_name": a.member_qualified_name or "",
                "ontology_node_id": a.ontology_node_id,
            }
            for a in session.query(VerificationAction).order_by(VerificationAction.id).all()
        ]

    with open(SQLITE_FIXTURE, "w") as f:
        json.dump(data, f, indent=2)

    hlr_count = len(data.get("high_level_requirements", []))
    llr_count = len(data.get("low_level_requirements", []))
    print(f"SQLite fixture written to {SQLITE_FIXTURE}")
    print(f"  {len(data['ontology_nodes'])} nodes, {len(data['ontology_triples'])} triples")
    print(f"  HLR/LLR data not included (Phase 2: in Neo4j)")
    print(f"  {len(data['verification_methods'])} verifications")


# ---------------------------------------------------------------------------
# Neo4j export
# ---------------------------------------------------------------------------


def export_neo4j():
    """Dump Design nodes and their relationships from Neo4j to JSON."""
    from backend.db.neo4j.connection import Neo4jConnection

    neo4j = Neo4jConnection()
    os.makedirs(FIXTURES_DIR, exist_ok=True)

    with neo4j.session() as session:
        nodes_result = session.run(
            "MATCH (n:Design) "
            "RETURN n.qualified_name AS qname, n.name AS name, n.kind AS kind, "
            "n.specialization AS specialization, n.visibility AS visibility, "
            "n.description AS description, n.refid AS refid, "
            "n.source_type AS source_type, n.component_id AS component_id, "
            "n.is_intercomponent AS is_intercomponent, "
            "n.type_signature AS type_signature, n.argsstring AS argsstring, "
            "n.definition AS definition, n.file_path AS file_path, "
            "n.line_number AS line_number, "
            "n.is_static AS is_static, n.is_const AS is_const, "
            "n.is_virtual AS is_virtual, n.is_abstract AS is_abstract, "
            "n.is_final AS is_final "
            "ORDER BY n.qualified_name"
        )
        nodes = []
        for record in nodes_result:
            node = dict(record)
            for key, val in node.items():
                if val is None:
                    node[key] = None
                elif isinstance(val, (list,)):
                    node[key] = list(val)
            nodes.append(node)

        rels_result = session.run(
            "MATCH (s:Design)-[r]->(o:Design) "
            "RETURN s.qualified_name AS subject, type(r) AS predicate, "
            "o.qualified_name AS object "
            "ORDER BY subject, predicate, object"
        )
        design_rels = [dict(r) for r in rels_result]

        dep_rels_result = session.run(
            "MATCH (s:Design)-[r]->(c:Compound) "
            "WHERE NOT c.source STARTS WITH 'as-built' "
            "RETURN s.qualified_name AS subject, type(r) AS predicate, "
            "c.qualified_name AS object, c.source AS object_source "
            "ORDER BY subject, predicate, object"
        )
        dep_rels = [dict(r) for r in dep_rels_result]

        impl_result = session.run(
            "MATCH (d:Design)-[:IMPLEMENTED_BY]->(target) "
            "RETURN d.qualified_name AS design_qname, "
            "target.qualified_name AS target_qname, "
            "labels(target) AS target_labels "
            "ORDER BY design_qname"
        )
        impl_links = [dict(r) for r in impl_result]

        dep_compound_qnames = [r["object"] for r in dep_rels]
        compound_nodes = []
        if dep_compound_qnames:
            compound_result = session.run(
                "MATCH (c:Compound) WHERE c.qualified_name IN $qnames "
                "RETURN c.qualified_name AS qname, c.name AS name, c.kind AS kind, "
                "c.source AS source, c.refid AS refid "
                "ORDER BY c.qualified_name",
                qnames=dep_compound_qnames,
            )
            compound_nodes = [dict(r) for r in compound_result]

    neo4j.close()

    fixture = {
        "design_nodes": nodes,
        "design_relationships": design_rels,
        "dependency_relationships": dep_rels,
        "dependency_compound_nodes": compound_nodes,
        "implemented_by_links": impl_links,
    }

    with open(NEO4J_FIXTURE, "w") as f:
        json.dump(fixture, f, indent=2)

    print(f"\nNeo4j fixture written to {NEO4J_FIXTURE}")
    print(f"  {len(nodes)} Design nodes")
    print(f"  {len(design_rels)} Design→Design relationships")
    print(f"  {len(dep_rels)} Design→Compound dependency relationships")
    print(f"  {len(compound_nodes)} referenced Compound nodes")
    print(f"  {len(impl_links)} IMPLEMENTED_BY links")


if __name__ == "__main__":
    print("Exporting SQLite fixtures...")
    export_sqlite()
    print()
    print("Exporting Neo4j fixtures...")
    export_neo4j()