#!/usr/bin/env python
"""Migrate :Design nodes to :Compound/:Member/:Namespace labels with layer property.

This script:
1. Adds the correct label (:Compound, :Member, or :Namespace) to each :Design node
2. Sets the `layer` property based on `source_type`:
   - source_type='dependency' → layer='dependency'
   - source_type='compound' and refid is non-empty → layer='as-built'
   - source_type='compound' and refid is empty → layer='design'
   - source_type='member' → inherits from parent compound's layer
   - source_type='namespace' → layer='design'
   - missing/empty source_type → layer='design'
3. Removes the `source_type` property
4. Removes the `:Design` label

Usage:
    python scripts/migrate_design_labels.py [--dry-run]
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from codegraph.neo4j import Neo4jConnection


COMPOUND_KINDS = {"class", "struct", "template_class", "interface", "abstract_class", "enum", "enum_class"}
MEMBER_KINDS = {"method", "attribute", "constant", "enum_value"}
NAMESPACE_KINDS = {"namespace", "module", "package"}


def determine_layer(source_type: str | None, refid: str | None) -> str:
    """Determine the layer value from legacy source_type and refid."""
    if source_type == "dependency":
        return "dependency"
    elif source_type == "compound":
        if refid:
            return "as-built"
        return "design"
    elif source_type == "namespace":
        return "design"
    elif source_type == "member":
        # Members inherit their parent's layer; default to design
        return "design"
    else:
        # Empty or missing source_type → design
        return "design"


def determine_label(kind: str) -> str:
    """Determine the Neo4j label for a node based on its kind."""
    if kind in COMPOUND_KINDS:
        return "Compound"
    elif kind in MEMBER_KINDS:
        return "Member"
    elif kind in NAMESPACE_KINDS:
        return "Namespace"
    else:
        # Default to Compound for unknown kinds
        return "Compound"


def migrate(dry_run: bool = False):
    conn = Neo4jConnection()
    conn.ensure_constraints()
    conn.ensure_design_constraints()

    driver = conn.get_driver()
    with driver.session(database="neo4j") as session:
        # Step 1: Get all Design nodes
        result = session.run("MATCH (d:Design) RETURN d")
        nodes = [dict(record["d"]) for record in result]
        print(f"Found {len(nodes)} :Design nodes")

        if dry_run:
            print("\n--- DRY RUN ---")
            for props in nodes[:10]:
                kind = props.get("kind", "unknown")
                source_type = props.get("source_type", "")
                refid = props.get("refid", "")
                label = determine_label(kind)
                layer = determine_layer(source_type, refid)
                qname = props.get("qualified_name", "?")
                print(f"  {qname}: kind={kind}, source_type={source_type!r} → :{label} {{layer: '{layer}'}}")
            if len(nodes) > 10:
                print(f"  ... and {len(nodes) - 10} more")
            return

        # Step 2: Add new labels and set layer property
        label_counts = {"Compound": 0, "Member": 0, "Namespace": 0}
        for props in nodes:
            kind = props.get("kind", "unknown")
            source_type = props.get("source_type", "")
            refid = props.get("refid", "")
            qname = props.get("qualified_name", "")
            label = determine_label(kind)
            layer = determine_layer(source_type, refid)

            session.run(
                f"MATCH (d:Design {{qualified_name: $qn}}) SET d:{label}, d.layer = $layer",
                {"qn": qname, "layer": layer},
            )
            label_counts[label] += 1

        print(f"Labeled nodes: {label_counts}")

        # Step 3: For member nodes, update layer based on parent compound
        # Members that are children of as-built compounds should be as-built
        session.run("""
            MATCH (parent:Compound {layer: 'as-built'})-[:COMPOSES]->(member:Member {layer: 'design'})
            SET member.layer = 'as-built'
        """)
        print("Updated member layers based on parent compounds")

        # Step 4: Remove source_type property from all nodes
        # (Both labels exist on nodes at this point)
        session.run("MATCH (n) WHERE n.source_type IS NOT NULL REMOVE n.source_type")
        print("Removed source_type property from all nodes")

        # Step 5: Remove :Design label (nodes now have specific labels)
        session.run("MATCH (d:Design) REMOVE d:Design")
        print("Removed :Design label from all nodes")

        # Step 6: Drop legacy indexes
        for stmt in [
            "DROP INDEX design_kind IF EXISTS",
            "DROP INDEX design_source_type IF EXISTS",
            "DROP INDEX design_component_id IF EXISTS",
            "DROP INDEX design_implementation_status IF EXISTS",
            "DROP CONSTRAINT design_qualified_name IF EXISTS",
        ]:
            try:
                session.run(stmt)
            except Exception:
                pass
        print("Dropped legacy :Design indexes (if they existed)")

        # Step 7: Verify
        result = session.run("MATCH (c:Compound) RETURN count(c) AS count")
        compound_count = result.single()["count"]
        result = session.run("MATCH (m:Member) RETURN count(m) AS count")
        member_count = result.single()["count"]
        result = session.run("MATCH (n:Namespace) RETURN count(n) AS count")
        namespace_count = result.single()["count"]
        result = session.run("MATCH (d:Design) RETURN count(d) AS count")
        design_count = result.single()["count"]
        print(f"\nVerification:")
        print(f"  :Compound nodes: {compound_count}")
        print(f"  :Member nodes: {member_count}")
        print(f"  :Namespace nodes: {namespace_count}")
        print(f"  :Design nodes remaining: {design_count}")

    conn.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Migrate :Design nodes to typed labels with layer property")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without making changes")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)


if __name__ == "__main__":
    main()