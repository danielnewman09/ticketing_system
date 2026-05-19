"""One-time migration: populate high_level_requirements_nodes and
low_level_requirements_nodes from existing triple associations.

For each HLR/LLR with linked triples, derive the subject and object nodes
from each triple and add them to the M2M node association.

Usage:
    python scripts/backfill_requirement_nodes.py
"""

from backend.db import init_db, get_session
from backend.db.models import (
    HighLevelRequirement,
    LowLevelRequirement,
)


def backfill():
    init_db()

    with get_session() as session:
        hlrs_processed = 0
        nodes_linked = 0

        for hlr in session.query(HighLevelRequirement).all():
            existing_node_ids = {n.id for n in hlr.nodes}
            for triple in hlr.triples:
                for node in [triple.subject, triple.object]:
                    if node.id not in existing_node_ids:
                        hlr.nodes.append(node)
                        existing_node_ids.add(node.id)
                        nodes_linked += 1
            hlrs_processed += 1

        llrs_processed = 0
        for llr in session.query(LowLevelRequirement).all():
            existing_node_ids = {n.id for n in llr.nodes}
            for triple in llr.triples:
                for node in [triple.subject, triple.object]:
                    if node.id not in existing_node_ids:
                        llr.nodes.append(node)
                        existing_node_ids.add(node.id)
                        nodes_linked += 1
            llrs_processed += 1

        session.flush()
        print(f"Backfill complete: {hlrs_processed} HLRs, {llrs_processed} LLRs, {nodes_linked} node links created")


if __name__ == "__main__":
    backfill()
