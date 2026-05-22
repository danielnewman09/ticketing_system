#!/usr/bin/env python
"""Import JSON fixtures into a fresh database, recreating the full state.

Usage:
    source .venv/bin/activate
    python scripts/import_fixtures.py

This will:
  1. Wipe and recreate SQLite tables (via Alembic or init_db)
  2. Load sqlite_fixtures.json into SQLite
  3. Sync design nodes and triples to Neo4j

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
    """Load SQLite fixture data into the database."""
    from backend.db import init_db, get_session
    from backend.db.models import (
        Component,
        Dependency,
        DependencyManager,
        HighLevelRequirement,
        Language,
        LowLevelRequirement,
        OntologyNode,
        OntologyTriple,
        Predicate,
        VerificationAction,
        VerificationCondition,
        VerificationMethod,
        dependency_components,
    )

    with open(SQLITE_FIXTURE) as f:
        data = json.load(f)

    init_db()

    with get_session() as session:
        # Delete in dependency order (reverse of creation)
        session.query(VerificationAction).delete()
        session.query(VerificationCondition).delete()
        session.query(VerificationMethod).delete()
        session.execute(dependency_components.delete())
        session.query(Dependency).delete()
        session.query(DependencyManager).delete()
        session.query(OntologyTriple).delete()
        session.query(OntologyNode).delete()
        session.query(LowLevelRequirement).delete()
        session.query(HighLevelRequirement).delete()
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

        # --- Requirements ---
        for row in data.get("high_level_requirements", []):
            hlr = HighLevelRequirement(
                id=row["id"],
                description=row["description"],
                component_id=row.get("component_id"),
            )
            # dependency_context is stored separately
            dep_ctx = next(
                (d for d in data.get("hlr_dependency_contexts", []) if d["hlr_id"] == row["id"]),
                None,
            )
            if dep_ctx:
                hlr.dependency_context = dep_ctx["dependency_context"]
            session.add(hlr)

        for row in data.get("low_level_requirements", []):
            session.add(LowLevelRequirement(
                id=row["id"],
                description=row["description"],
                high_level_requirement_id=row["high_level_requirement_id"],
            ))

        session.flush()

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

        session.flush()

        # M2M relationships (now that nodes and triples have IDs)
        for row in data.get("hlr_triples", []):
            hlr = session.query(HighLevelRequirement).get(row["hlr_id"])
            triple = session.query(OntologyTriple).get(row["triple_id"])
            if hlr and triple:
                hlr.triples.append(triple)

        for row in data.get("hlr_nodes", []):
            hlr = session.query(HighLevelRequirement).get(row["hlr_id"])
            node = session.query(OntologyNode).get(row["node_id"])
            if hlr and node:
                hlr.nodes.append(node)

        for row in data.get("llr_nodes", []):
            llr = session.query(LowLevelRequirement).get(row["llr_id"])
            node = session.query(OntologyNode).get(row["node_id"])
            if llr and node:
                llr.nodes.append(node)

        # --- Verifications ---
        for row in data.get("verification_methods", []):
            session.add(VerificationMethod(
                id=row["id"],
                method=row["method"],
                test_name=row.get("test_name", ""),
                description=row.get("description", ""),
                low_level_requirement_id=row["low_level_requirement_id"],
            ))

        session.flush()

        for row in data.get("verification_conditions", []):
            session.add(VerificationCondition(
                id=row["id"],
                verification_id=row["verification_id"],
                phase=row.get("phase", "pre"),
                order=row.get("order", 0),
                member_qualified_name=row.get("member_qualified_name", ""),
                operator=row.get("operator", ""),
                expected_value=row.get("expected_value", ""),
                ontology_node_id=row.get("ontology_node_id"),
            ))

        for row in data.get("verification_actions", []):
            session.add(VerificationAction(
                id=row["id"],
                verification_id=row["verification_id"],
                order=row.get("order", 0),
                description=row.get("description", ""),
                member_qualified_name=row.get("member_qualified_name", ""),
                ontology_node_id=row.get("ontology_node_id"),
            ))

        # session commits on exit via context manager

    print(f"SQLite fixture loaded from {SQLITE_FIXTURE}")
    print(f"  {len(data.get('ontology_nodes', []))} nodes, {len(data.get('ontology_triples', []))} triples")
    print(f"  {len(data.get('high_level_requirements', []))} HLRs, {len(data.get('low_level_requirements', []))} LLRs")
    print(f"  {len(data.get('verification_methods', []))} verifications")


def import_neo4j():
    """Load Neo4j fixture data: design nodes and relationships."""
    from backend.db.neo4j.connection import Neo4jConnection

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
            # Can't parameterize labels in Cypher, so the kind label is interpolated
            # This is safe because kind values come from a fixed enum
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

    neo4j.close()

    print(f"\nNeo4j fixture loaded from {NEO4J_FIXTURE}")
    print(f"  {len(data.get('design_nodes', []))} Design nodes")
    print(f"  {len(data.get('design_relationships', []))} Design relationships")
    print(f"  {len(data.get('dependency_relationships', []))} dependency relationships")
    print(f"  {len(data.get('dependency_compound_nodes', []))} Compound dependency nodes")


if __name__ == "__main__":
    print("Importing SQLite fixtures...")
    import_sqlite()
    print()
    print("Importing Neo4j fixtures...")
    import_neo4j()