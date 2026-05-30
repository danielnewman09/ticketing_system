"""CodebaseEdge — a directed relationship between codebase graph nodes.

Stored in Neo4j as a typed relationship with the predicate name
uppercased (e.g. 'composes' → COMPOSES). Identified by subject +
predicate + object.

Re-exports from ``codegraph`` shared library.
"""

from codegraph.edges import CodebaseEdge
from codegraph.constants import PREDICATES

__all__ = ["CodebaseEdge", "PREDICATES"]
