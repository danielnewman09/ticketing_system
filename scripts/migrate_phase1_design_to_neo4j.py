#!/usr/bin/env python
"""DEPRECATED: Phase 1 SQLite → Neo4j migration.

This script was used for the initial migration from SQLAlchemy ontology
tables to Neo4j. The ORM models (OntologyNode, OntologyTriple, Predicate)
have been removed in Phase 4. This script is kept for reference only.

For label migration (:Design → :Compound/:Member/:Namespace), use:
    python scripts/migrate_design_labels.py
"""

import sys

print("DEPRECATED: This script requires the removed OntologyNode/OntologyTriple/Predicate ORM models.")
print("Use: python scripts/migrate_design_labels.py")
sys.exit(1)