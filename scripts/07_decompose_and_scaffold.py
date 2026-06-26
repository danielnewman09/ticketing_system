#!/usr/bin/env python
"""Run HLR decomposition and persist scaffold nodes to Neo4j.

Standalone script that:
1. Decomposes an HLR into LLRs with verification stubs (LLM call)
2. Persists the decomposition to Neo4j via ``decompose_and_persist_hlr``
   (creates LLRs, verification methods, conditions, actions, and scaffold
   CodeGraphNodes from notional references)
3. Queries Neo4j to show the scaffold nodes that were created

Usage::

    # Decompose a fresh description (creates an HLR first)
    python scripts/07_decompose_and_scaffold.py "The Calculation Engine shall..."

    # Decompose an existing HLR by refid
    python scripts/07_decompose_and_scaffold.py --refid 2c3463b2...

Environment:
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD — Neo4j connection
    LLM_BACKEND, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL — LLM config
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

# Load .env
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("decompose_and_scaffold")


def main() -> None:
    from backend_migrated.connection import init_neo4j, close_neo4j
    from codegraph_requirements.models import HLR
    from backend_migrated.agents.decompose_hlr import decompose_and_persist_hlr

    init_neo4j()

    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    if args[0] == "--refid":
        refid = args[1]
        hlr = HLR.nodes.get_or_none(refid=refid)
        if hlr is None:
            print(f"HLR with refid '{refid}' not found")
            sys.exit(1)
        description = hlr.description
        print(f"Decomposing existing HLR {refid[:8]}: {description[:80]}...")
    else:
        description = " ".join(args)
        # Create a new HLR
        hlr = HLR(description=description, layer="design", tags=["design"])
        hlr.save()
        refid = hlr.refid
        print(f"Created HLR {refid[:8]}: {description[:80]}...")

    # --- Step 1+2: Decompose and persist (single call) ---
    print("\n=== Decomposing and persisting to Neo4j ===")
    model = os.environ.get("LLM_MODEL", "")
    log_dir = os.path.join("logs")
    os.makedirs(log_dir, exist_ok=True)

    result = decompose_and_persist_hlr(
        refid=refid,
        model=model,
        log_dir=log_dir,
    )

    print(f"  HLR refid:                  {result['hlr_refid'][:8]}")
    print(f"  LLRs created:               {result['llrs_created']}")
    print(f"  Verification methods:       {result['verifications_created']}")
    print(f"  Conditions:                 {result['conditions_created']}")
    print(f"  Actions:                    {result['actions_created']}")
    print(f"  Scaffold classes:           {result['scaffold_classes']}")
    print(f"  Scaffold attributes:        {result['scaffold_attributes']}")
    print(f"  Typed edges (operand/caller): {result['operand_edges']}")

    if result.get("scaffold_map"):
        print(f"\n  Scaffold map (notional → qualified):")
        for notional, scaffold_qn in result["scaffold_map"].items():
            print(f"    {notional} → {scaffold_qn}")

    # --- Step 3: Query Neo4j to show scaffold nodes ---
    print("\n=== Scaffold nodes in Neo4j ===")
    from neomodel import db

    with db.driver.session() as session:
        # Scaffold class nodes
        records = session.run(
            """
            MATCH (c:ClassNode)
            WHERE 'scaffold' IN c.tags
            RETURN c.qualified_name AS qname, c.name AS name, c.kind AS kind
            ORDER BY c.qualified_name
            """
        )
        classes = [(r["qname"], r["name"], r["kind"]) for r in records]
        print(f"\n  Scaffold ClassNodes ({len(classes)}):")
        for qname, name, kind in classes:
            print(f"    {qname} (kind={kind})")

        # Scaffold attribute nodes
        records = session.run(
            """
            MATCH (a:AttributeNode)
            WHERE 'scaffold' IN a.tags
            RETURN a.qualified_name AS qname, a.name AS name, a.kind AS kind
            ORDER BY a.qualified_name
            """
        )
        attrs = [(r["qname"], r["name"], r["kind"]) for r in records]
        print(f"\n  Scaffold AttributeNodes ({len(attrs)}):")
        for qname, name, kind in attrs:
            print(f"    {qname} (kind={kind})")

        # COMPOSES edges between scaffold nodes
        records = session.run(
            """
            MATCH (c:ClassNode)-[:COMPOSES]->(a:AttributeNode)
            WHERE 'scaffold' IN c.tags AND 'scaffold' IN a.tags
            RETURN c.qualified_name AS class_qn, a.qualified_name AS attr_qn
            ORDER BY c.qualified_name, a.qualified_name
            """
        )
        composes = [(r["class_qn"], r["attr_qn"]) for r in records]
        print(f"\n  COMPOSES edges (class → attribute): {len(composes)}")
        for class_qn, attr_qn in composes:
            print(f"    {class_qn} → {attr_qn}")

        # Typed edges from verification nodes to scaffold nodes
        records = session.run(
            """
            MATCH (v)-[r]->(s)
            WHERE 'scaffold' IN s.tags
              AND (v:Condition OR v:Action)
              AND type(r) IN ['LEFT_OPERAND', 'RIGHT_OPERAND', 'CALLER', 'CALLEE']
            RETURN type(r) AS edge_type,
                   s.qualified_name AS scaffold_qn,
                   labels(s) AS target_labels
            ORDER BY edge_type, scaffold_qn
            """
        )
        typed_edges = [
            (r["edge_type"], r["scaffold_qn"], list(r["target_labels"] or []))
            for r in records
        ]
        print(f"\n  Typed edges (verification → scaffold): {len(typed_edges)}")
        for edge_type, scaffold_qn, target_labels in typed_edges:
            label_str = ", ".join(target_labels) if target_labels else ""
            print(f"    -[:{edge_type}]-> {scaffold_qn} ({label_str})")

    print("\n=== Done ===")
    print(f"  HLR refid: {refid}")

    close_neo4j()


if __name__ == "__main__":
    main()