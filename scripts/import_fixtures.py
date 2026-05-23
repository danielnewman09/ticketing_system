#!/usr/bin/env python
"""Import JSON fixtures into a fresh database, recreating the full state.

Phase 3 notes:
  - HLR/LLR data lives in Neo4j (Phase 2)
  - Verification data lives in Neo4j (Phase 3)
  - SQLite fixture loader skips HLR/LLR and verification tables

Usage:
    source .venv/bin/activate
    python scripts/import_fixtures.py

This will:
  1. Wipe and recreate SQLite tables (via Alembic or init_db)
  2. Load sqlite_fixtures.json into SQLite (excluding HLR/LLR and verification tables)
  3. Sync design nodes and triples to Neo4j
  4. Sync verification data to Neo4j

WARNING: This replaces all data in both databases.
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


def import_sqlite():
    """Load SQLite fixture data into the database (excluding HLR/LLR and verification tables)."""
    from backend.db import init_db, get_session
    from backend.db.models import (
        Component,
        Dependency,
        DependencyManager,
        Language,
        OntologyNode,
        OntologyTriple,
        Predicate,
        dependency_components,
    )

    with open(SQLITE_FIXTURE) as f:
        data = json.load(f)

    init_db()

    with get_session() as session:
        # Delete in dependency order
        session.execute(dependency_components.delete())
        session.query(Dependency).delete()
        session.query(DependencyManager).delete()
        session.query(OntologyTriple).delete()
        session.query(OntologyNode).delete()
        session.query(Component).delete()
        session.query(Language).delete()
        session.query(Predicate).delete()
        session.flush()

        # --- Reference data ---
        for row in data.get("predicates", []):
            session.add(Predicate(id=row["id"], name=row["name"], description=row.get("description")))

        for row in data.get("languages", []):
            session.add(Language(id=row["id"], name=row["name"], version=row.get("version")))

        for row in data.get("dependency_managers", []):
            session.add(DependencyManager(
                id=row["id"], name=row["name"],
                language_id=row.get("language_id"),
                version=row.get("version", ""),
                lock_file=row.get("lock_file", ""),
            ))

        for row in data.get("components", []):
            session.add(Component(
                id=row["id"], name=row["name"],
                description=row.get("description", ""),
                language_id=row.get("language_id"),
                parent_id=row.get("parent_id"),
                namespace=row.get("namespace", ""),
            ))

        for row in data.get("dependencies", []):
            session.add(Dependency(
                id=row["id"], name=row["name"],
                version=row.get("version", ""),
                manager_id=row.get("manager_id"),
            ))

        session.flush()

        # M2M: dependency_components
        for row in data.get("dependency_components", []):
            session.execute(
                dependency_components.insert().values(
                    component_id=row["component_id"],
                    dependency_id=row["dependency_id"],
                )
            )

        # HLR/LLR data is now in Neo4j (Phase 2) — skip loading into SQLite

        # --- Ontology ---
        for row in data.get("ontology_nodes", []):
            session.add(OntologyNode(
                id=row["id"],
                qualified_name=row["qualified_name"],
                name=row.get("name", ""),
                kind=row.get("kind", ""),
                specialization=row.get("specialization", ""),
                visibility=row.get("visibility", ""),
                description=row.get("description", ""),
                refid=row.get("refid", ""),
                component_id=row.get("component_id"),
                is_intercomponent=row.get("is_intercomponent", False),
                source_type=row.get("source_type", ""),
                type_signature=row.get("type_signature", ""),
                argsstring=row.get("argsstring", ""),
                definition=row.get("definition", ""),
                file_path=row.get("file_path", ""),
                line_number=row.get("line_number"),
                is_static=row.get("is_static", False),
                is_const=row.get("is_const", False),
                is_virtual=row.get("is_virtual", False),
                is_abstract=row.get("is_abstract", False),
                is_final=row.get("is_final", False),
            ))

        session.flush()

        for row in data.get("ontology_triples", []):
            session.add(OntologyTriple(
                id=row["id"],
                subject_id=row["subject_id"],
                predicate_id=row["predicate_id"],
                object_id=row["object_id"],
            ))

        # Verification data is now in Neo4j (Phase 3) — skip loading into SQLite

    hlr_count = len(data.get("high_level_requirements", []))
    llr_count = len(data.get("low_level_requirements", []))
    vm_count = len(data.get("verification_methods", []))
    cond_count = len(data.get("verification_conditions", []))
    act_count = len(data.get("verification_actions", []))
    print(f"SQLite fixture loaded from {SQLITE_FIXTURE}")
    print(f"  {len(data.get('ontology_nodes', []))} nodes, {len(data.get('ontology_triples', []))} triples")
    if hlr_count or llr_count:
        print(f"  Skipping {hlr_count} HLRs and {llr_count} LLRs (Phase 2: in Neo4j)")
    if vm_count or cond_count or act_count:
        print(f"  Skipping {vm_count} verifications, {cond_count} conditions, {act_count} actions (Phase 3: in Neo4j)")


def import_neo4j():
    """Load Neo4j fixture data: design nodes, relationships, and verification data."""
    from backend.db.neo4j.connection import Neo4jConnection
    from backend.db.neo4j.repositories.verification import VerificationRepository

    with open(NEO4J_FIXTURE) as f:
        data = json.load(f)

    neo4j = Neo4jConnection()

    with neo4j.session() as session:
        # Clear existing Design nodes
        session.run("MATCH (n:Design) DETACH DELETE n")

        # Create design nodes
        for node in data.get("design_nodes", []):
            kind_label = (node.get("kind") or "Unknown").capitalize()
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
                n.type_signature = $type_signature,
                n.argsstring = $argsstring,
                n.definition = $definition,
                n.file_path = $file_path,
                n.line_number = $line_number,
                n.is_static = $is_static,
                n.is_const = $is_const,
                n.is_virtual = $is_virtual,
                n.is_abstract = $is_abstract,
                n.is_final = $is_final
            """
            params = {
                "qname": node["qname"],
                "name": node.get("name", ""),
                "kind": node.get("kind", ""),
                "specialization": node.get("specialization", ""),
                "visibility": node.get("visibility", ""),
                "description": node.get("description", ""),
                "refid": node.get("refid", ""),
                "source_type": node.get("source_type", ""),
                "component_id": node.get("component_id"),
                "is_intercomponent": node.get("is_intercomponent", False),
                "type_signature": node.get("type_signature", ""),
                "argsstring": node.get("argsstring", ""),
                "definition": node.get("definition", ""),
                "file_path": node.get("file_path", ""),
                "line_number": node.get("line_number"),
                "is_static": node.get("is_static", False),
                "is_const": node.get("is_const", False),
                "is_virtual": node.get("is_virtual", False),
                "is_abstract": node.get("is_abstract", False),
                "is_final": node.get("is_final", False),
            }
            session.run(cypher, params)

        # Create design→design relationships
        for rel in data.get("design_relationships", []):
            pred_name = rel["predicate"]
            cypher = f"""
            MATCH (s:Design {{qualified_name: $subj}})
            MATCH (o:Design {{qualified_name: $obj}})
            MERGE (s)-[r:{pred_name}]->(o)
            """
            session.run(cypher, {"subj": rel["subject"], "obj": rel["object"]})

        # Create/ensure dependency Compound nodes exist and link
        for cnode in data.get("dependency_compound_nodes", []):
            cypher = """
            MERGE (c:Compound {qualified_name: $qname})
            SET c.name = $name, c.kind = $kind, c.source = $source, c.refid = $refid
            """
            session.run(cypher, {
                "qname": cnode["qname"],
                "name": cnode.get("name", ""),
                "kind": cnode.get("kind", ""),
                "source": cnode.get("source", ""),
                "refid": cnode.get("refid", ""),
            })

        for rel in data.get("dependency_relationships", []):
            pred_name = rel["predicate"]
            cypher = f"""
            MATCH (s:Design {{qualified_name: $subj}})
            MATCH (c:Compound {{qualified_name: $obj}})
            MERGE (s)-[r:{pred_name}]->(c)
            """
            session.run(cypher, {"subj": rel["subject"], "obj": rel["object"]})

        # Import verification data from fixture
        ver_repo = VerificationRepository(session)
        vm_count = 0
        cond_count = 0
        act_count = 0
        for vm_row in data.get("verification_methods", []):
            vm = ver_repo.create_verification(
                llr_id=vm_row["low_level_requirement_id"],
                method=vm_row["method"],
                test_name=vm_row.get("test_name", ""),
                description=vm_row.get("description", ""),
            )
            vm_count += 1

            # Import conditions for this verification method
            for c_row in data.get("verification_conditions", []):
                if c_row["verification_id"] == vm_row["id"]:
                    # Map legacy member_qualified_name → subject_qualified_name
                    subject_qn = c_row.get("member_qualified_name", "") or c_row.get("subject_qualified_name", "")
                    object_qn = c_row.get("object_qualified_name", "") or c_row.get("ontology_node_qualified_name", "")
                    ver_repo.add_condition(
                        vm_id=vm.id,
                        phase=c_row.get("phase", "pre"),
                        order=c_row.get("order", 0),
                        operator=c_row.get("operator", "=="),
                        expected_value=c_row.get("expected_value", ""),
                        subject_qualified_name=subject_qn,
                        object_qualified_name=object_qn,
                    )
                    cond_count += 1

            # Import actions for this verification method
            for a_row in data.get("verification_actions", []):
                if a_row["verification_id"] == vm_row["id"]:
                    # Map legacy member_qualified_name → callee_qualified_name
                    callee_qn = a_row.get("member_qualified_name", "") or a_row.get("callee_qualified_name", "")
                    caller_qn = a_row.get("caller_qualified_name", "")
                    ver_repo.add_action(
                        vm_id=vm.id,
                        order=a_row.get("order", 0),
                        description=a_row.get("description", ""),
                        caller_qualified_name=caller_qn,
                        callee_qualified_name=callee_qn,
                    )
                    act_count += 1

    neo4j.close()

    print(f"\nNeo4j fixture loaded from {NEO4J_FIXTURE}")
    print(f"  {len(data.get('design_nodes', []))} Design nodes")
    print(f"  {len(data.get('design_relationships', []))} Design relationships")
    print(f"  {len(data.get('dependency_relationships', []))} dependency relationships")
    print(f"  {len(data.get('dependency_compound_nodes', []))} Compound dependency nodes")
    if vm_count:
        print(f"  {vm_count} VerificationMethods, {cond_count} Conditions, {act_count} Actions")


if __name__ == "__main__":
    print("Importing SQLite fixtures...")
    import_sqlite()
    print()
    print("Importing Neo4j fixtures...")
    import_neo4j()
