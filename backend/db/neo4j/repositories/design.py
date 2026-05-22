"""Design node and triple repository — Neo4j-primary data access.

All design graph CRUD goes through this class. No SQLAlchemy models
are used for design data.
"""

from __future__ import annotations

import logging
from typing import Sequence

from neo4j import Session as Neo4jSession

from backend.db.neo4j.repositories.constants import PREDICATE_TO_REL_TYPE
from backend.db.neo4j.repositories.models.design import (
    DesignNode,
    DesignTripleUpdate,
)

log = logging.getLogger(__name__)


class DesignRepository:
    """CRUD operations for :Design nodes and their relationships.

    Each method accepts a Neo4j session and performs Cypher queries
    directly. The caller is responsible for transaction management
    (the session context manager handles commit/rollback).
    """

    def __init__(self, session: Neo4jSession) -> None:
        self._session = session

    # -----------------------------------------------------------------------
    # Node operations
    # -----------------------------------------------------------------------

    def merge_node(self, node: DesignNode) -> DesignNode:
        """Create or update a :Design node by qualified_name.

        Dependency-reference stubs (source_type='dependency') are skipped
        because their real nodes exist as :Compound in Neo4j. Edges to
        them are created via merge_triple, which routes to Compounds.
        """
        if node.source_type == "dependency":
            log.debug("Skipping dependency stub %s in Neo4j merge", node.qualified_name)
            return node

        kind_label = node.kind.capitalize() if node.kind else "Unknown"

        cypher = f"""
        MERGE (d:Design {{qualified_name: $qn}})
        SET d:{kind_label},
            d.name = $name,
            d.kind = $kind,
            d.specialization = $specialization,
            d.visibility = $visibility,
            d.description = $description,
            d.refid = $refid,
            d.source_type = $source_type,
            d.component_id = $component_id,
            d.is_intercomponent = $is_intercomponent,
            d.file_path = $file_path,
            d.line_number = $line_number,
            d.type_signature = $type_signature,
            d.argsstring = $argsstring,
            d.definition = $definition,
            d.is_static = $is_static,
            d.is_const = $is_const,
            d.is_virtual = $is_virtual,
            d.is_abstract = $is_abstract,
            d.is_final = $is_final,
            d.implementation_status = $implementation_status,
            d.source_file = $source_file,
            d.test_file = $test_file
        """
        self._session.run(cypher, node.model_dump())
        return node

    def get_by_qualified_name(self, qualified_name: str) -> DesignNode | None:
        """Fetch a :Design node by qualified_name. Returns None if not found."""
        result = self._session.run(
            "MATCH (d:Design {qualified_name: $qn}) RETURN d",
            {"qn": qualified_name},
        )
        record = result.single()
        if record is None:
            return None
        props = dict(record["d"])
        return DesignNode(**props)

    def find_nodes(
        self,
        kind: str | None = None,
        search: str | None = None,
        component_id: int | None = None,
    ) -> list[DesignNode]:
        """Find :Design nodes matching optional filters."""
        conditions = ["d:Design"]
        params: dict = {}

        if kind:
            conditions.append("d.kind = $kind")
            params["kind"] = kind
        if component_id is not None:
            conditions.append("d.component_id = $comp_id")
            params["comp_id"] = component_id
        if search:
            conditions.append("(d.name CONTAINS $search OR d.qualified_name CONTAINS $search)")
            params["search"] = search

        where = " AND ".join(conditions)
        cypher = f"MATCH (d) WHERE {where} RETURN d"

        result = self._session.run(cypher, params)
        nodes = []
        for record in result:
            props = dict(record["d"])
            try:
                nodes.append(DesignNode(**props))
            except Exception:
                log.warning("Skipping Design node with invalid props: %s", props)
        return nodes

    def delete_node(self, qualified_name: str) -> bool:
        """Delete a :Design node and all its relationships. Returns True if deleted."""
        result = self._session.run(
            "MATCH (d:Design {qualified_name: $qn}) DETACH DELETE d RETURN count(d) AS cnt",
            {"qn": qualified_name},
        )
        record = result.single()
        return record is not None and record["cnt"] > 0

    # -----------------------------------------------------------------------
    # Triple / relationship operations
    # -----------------------------------------------------------------------

    def merge_triple(
        self,
        subject_qualified_name: str,
        predicate: str,
        object_qualified_name: str,
    ) -> None:
        """MERGE a typed relationship between two Design nodes.

        For dependency targets (object is a dependency stub), falls back
        to matching :Compound nodes.
        """
        rel_type = PREDICATE_TO_REL_TYPE.get(predicate)
        if not rel_type:
            log.warning("Unknown predicate %r — skipping triple", predicate)
            return

        cypher = f"""
        MATCH (s:Design {{qualified_name: $subj}})
        OPTIONAL MATCH (o_design:Design {{qualified_name: $obj}})
        OPTIONAL MATCH (o_compound:Compound {{qualified_name: $obj}})
        WITH s, coalesce(o_design, o_compound) AS target
        WHERE target IS NOT NULL
        MERGE (s)-[r:{rel_type}]->(target)
        """
        self._session.run(
            cypher,
            {"subj": subject_qualified_name, "obj": object_qualified_name},
        )

    # -----------------------------------------------------------------------
    # HLR/LLR stub operations (temporary bridge — Phase 1 only)
    # -----------------------------------------------------------------------

    def merge_hlr_stub(self, sqlite_id: int, description: str, component_id: int | None = None) -> None:
        """Create or update an :HLR stub node. Phase 1 bridge to SQLite HLRs.

        These stubs enable Cypher traversal from HLR→Design for requirement
        tagging while HLRs still live in SQLite. Phase 2 makes HLRs full
        Neo4j citizens and removes sqlite_id.
        """
        self._session.run(
            """
            MERGE (h:HLR {sqlite_id: $sid})
            SET h.description = $desc,
                h.component_id = $cid
            """,
            {"sid": sqlite_id, "desc": description, "cid": component_id},
        )

    def merge_llr_stub(self, sqlite_id: int, description: str) -> None:
        """Create or update an :LLR stub node. Phase 1 bridge."""
        self._session.run(
            """
            MERGE (l:LLR {sqlite_id: $sid})
            SET l.description = $desc
            """,
            {"sid": sqlite_id, "desc": description},
        )

    def trace_design_to_hlr(self, hlr_sqlite_id: int, design_qualified_name: str) -> None:
        """Create a TRACES_TO edge from an HLR stub to a Design node."""
        self._session.run(
            """
            MATCH (h:HLR {sqlite_id: $hid})
            MATCH (d:Design {qualified_name: $qn})
            MERGE (h)-[:TRACES_TO]->(d)
            """,
            {"hid": hlr_sqlite_id, "qn": design_qualified_name},
        )

    def trace_design_to_llr(self, llr_sqlite_id: int, design_qualified_name: str) -> None:
        """Create a TRACES_TO edge from an LLR stub to a Design node."""
        self._session.run(
            """
            MATCH (l:LLR {sqlite_id: $lid})
            MATCH (d:Design {qualified_name: $qn})
            MERGE (l)-[:TRACES_TO]->(d)
            """,
            {"lid": llr_sqlite_id, "qn": design_qualified_name},
        )

    def untrace_design_from_hlr(self, hlr_sqlite_id: int, design_qualified_name: str) -> None:
        """Remove a TRACES_TO edge from an HLR stub to a Design node."""
        self._session.run(
            """
            MATCH (h:HLR {sqlite_id: $hid})-[r:TRACES_TO]->(d:Design {qualified_name: $qn})
            DELETE r
            """,
            {"hid": hlr_sqlite_id, "qn": design_qualified_name},
        )

    # -----------------------------------------------------------------------
    # Bulk operations
    # -----------------------------------------------------------------------

    def clear_design_graph(self) -> bool:
        """Delete all :Design nodes and their relationships."""
        try:
            self._session.run("MATCH (n:Design) DETACH DELETE n")
            log.info("Cleared design graph from Neo4j")
            return True
        except Exception:
            log.warning("Neo4j clear failed", exc_info=True)
            return False

    def sync_implementation_status(self, qualified_name: str, status: str, source_file: str = "", test_file: str = "") -> None:
        """Update implementation_status on a :Design node."""
        self._session.run(
            """
            MATCH (d:Design {qualified_name: $qn})
            SET d.implementation_status = $status,
                d.source_file = $source_file,
                d.test_file = $test_file
            """,
            {
                "qn": qualified_name,
                "status": status,
                "source_file": source_file,
                "test_file": test_file,
            },
        )