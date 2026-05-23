"""Requirement repository — Neo4j-primary CRUD for HLR/LLR nodes.

All HLR/LLR data access goes through this class. Phase 2 replaces
the sqlite_id-bridged stub approach with full Neo4j-native nodes.
"""

from __future__ import annotations

import logging
from typing import Sequence

from neo4j import Session as Neo4jSession

from backend.db.neo4j.repositories.models.requirement import HLRNode, LLRNode

log = logging.getLogger(__name__)


class RequirementRepository:
    """CRUD operations for :HLR and :LLR nodes in Neo4j.

    HLR and LLR nodes use an `id` property (integer) as their unique
    identifier. This replaces the `sqlite_id` bridge property from Phase 1.
    """

    def __init__(self, session: Neo4jSession) -> None:
        self._session = session

    # -----------------------------------------------------------------------
    # HLR operations
    # -----------------------------------------------------------------------

    def create_hlr(
        self,
        description: str,
        component_id: int | None = None,
        dependency_context: dict | None = None,
    ) -> HLRNode:
        """Create a new :HLR node. Returns the created HLRNode."""
        next_id = self._next_hlr_id()
        self._session.run(
            """
            CREATE (h:HLR {id: $id, description: $desc, component_id: $cid, dependency_context: $dep_ctx})
            """,
            {
                "id": next_id,
                "desc": description,
                "cid": component_id,
                "dep_ctx": dependency_context,
            },
        )
        return HLRNode(
            id=next_id,
            description=description,
            component_id=component_id,
            dependency_context=dependency_context,
        )

    def get_hlr(self, hlr_id: int) -> HLRNode | None:
        """Fetch a single :HLR node by id. Returns None if not found."""
        result = self._session.run(
            "MATCH (h:HLR {id: $id}) RETURN h",
            {"id": hlr_id},
        )
        record = result.single()
        if record is None:
            return None
        props = dict(record["h"])
        return HLRNode(
            id=props["id"],
            description=props["description"],
            component_id=props.get("component_id"),
            dependency_context=props.get("dependency_context"),
        )

    def update_hlr(self, hlr_id: int, **kwargs) -> HLRNode | None:
        """Update an :HLR node's properties. Returns the updated HLRNode or None."""
        if not kwargs:
            return self.get_hlr(hlr_id)

        allowed = {"description", "component_id", "dependency_context"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return self.get_hlr(hlr_id)

        set_clauses = ", ".join(f"h.{k} = ${k}" for k in updates)
        params = {"id": hlr_id, **updates}
        self._session.run(
            f"MATCH (h:HLR {{id: $id}}) SET {set_clauses}",
            params,
        )
        return self.get_hlr(hlr_id)

    def delete_hlr(self, hlr_id: int) -> bool:
        """Delete an :HLR node and all its relationships (including child :LLR nodes).

        Returns True if the node was deleted, False if not found.
        """
        # First, find and delete child LLRs
        llr_ids = [
            r["id"]
            for r in self._session.run(
                "MATCH (h:HLR {id: $id})-[:DECOMPOSES_INTO]->(l:LLR) RETURN l.id AS id",
                {"id": hlr_id},
            )
        ]
        for llr_id in llr_ids:
            self.delete_llr(llr_id)

        # Then delete HLR
        result = self._session.run(
            "MATCH (h:HLR {id: $id}) DETACH DELETE h RETURN count(h) AS cnt",
            {"id": hlr_id},
        )
        record = result.single()
        return record is not None and record["cnt"] > 0

    def list_hlrs(self, component_id: int | None = None) -> list[HLRNode]:
        """List all :HLR nodes, optionally filtered by component_id."""
        if component_id is not None:
            result = self._session.run(
                "MATCH (h:HLR {component_id: $cid}) RETURN h ORDER BY h.id",
                {"cid": component_id},
            )
        else:
            result = self._session.run(
                "MATCH (h:HLR) RETURN h ORDER BY h.id",
            )
        hlrs = []
        for record in result:
            props = dict(record["h"])
            hlrs.append(
                HLRNode(
                    id=props["id"],
                    description=props["description"],
                    component_id=props.get("component_id"),
                    dependency_context=props.get("dependency_context"),
                )
            )
        return hlrs

    # -----------------------------------------------------------------------
    # LLR operations
    # -----------------------------------------------------------------------

    def create_llr(self, hlr_id: int, description: str) -> LLRNode:
        """Create a new :LLR node linked to :HLR via DECOMPOSES_INTO.

        Returns the created LLRNode.
        """
        next_id = self._next_llr_id()
        self._session.run(
            """
            MATCH (h:HLR {id: $hid})
            CREATE (l:LLR {id: $id, description: $desc, high_level_requirement_id: $hid})
            CREATE (h)-[:DECOMPOSES_INTO]->(l)
            """,
            {"hid": hlr_id, "id": next_id, "desc": description},
        )
        return LLRNode(id=next_id, description=description, high_level_requirement_id=hlr_id)

    def get_llr(self, llr_id: int) -> LLRNode | None:
        """Fetch a single :LLR node by id. Returns None if not found."""
        result = self._session.run(
            "MATCH (l:LLR {id: $id}) RETURN l",
            {"id": llr_id},
        )
        record = result.single()
        if record is None:
            return None
        props = dict(record["l"])
        return LLRNode(
            id=props["id"],
            description=props["description"],
            high_level_requirement_id=props["high_level_requirement_id"],
        )

    def update_llr(self, llr_id: int, **kwargs) -> LLRNode | None:
        """Update a :LLR node's properties. Returns the updated LLRNode or None."""
        if not kwargs:
            return self.get_llr(llr_id)

        allowed = {"description", "high_level_requirement_id"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return self.get_llr(llr_id)

        # If re-parenting, also update the DECOMPOSES_INTO edge
        if "high_level_requirement_id" in updates:
            new_hlr_id = updates["high_level_requirement_id"]
            old_llr = self.get_llr(llr_id)
            if old_llr and old_llr.high_level_requirement_id != new_hlr_id:
                # Delete old edge, create new one
                self._session.run(
                    """
                    MATCH (h:HLR {id: $old_hid})-[r:DECOMPOSES_INTO]->(l:LLR {id: $lid})
                    DELETE r
                    """,
                    {"old_hid": old_llr.high_level_requirement_id, "lid": llr_id},
                )
                self._session.run(
                    """
                    MATCH (h:HLR {id: $new_hid})
                    MATCH (l:LLR {id: $lid})
                    CREATE (h)-[:DECOMPOSES_INTO]->(l)
                    """,
                    {"new_hid": new_hlr_id, "lid": llr_id},
                )

        set_clauses = ", ".join(f"l.{k} = ${k}" for k in updates)
        params = {"id": llr_id, **updates}
        self._session.run(
            f"MATCH (l:LLR {{id: $id}}) SET {set_clauses}",
            params,
        )
        return self.get_llr(llr_id)

    def delete_llr(self, llr_id: int) -> bool:
        """Delete a :LLR node and all its relationships.

        Returns True if the node was deleted, False if not found.
        """
        result = self._session.run(
            "MATCH (l:LLR {id: $id}) DETACH DELETE l RETURN count(l) AS cnt",
            {"id": llr_id},
        )
        record = result.single()
        return record is not None and record["cnt"] > 0

    def list_llrs(self, hlr_id: int | None = None) -> list[LLRNode]:
        """List all :LLR nodes, optionally filtered by parent HLR id."""
        if hlr_id is not None:
            result = self._session.run(
                """
                MATCH (h:HLR {id: $hid})-[:DECOMPOSES_INTO]->(l:LLR)
                RETURN l ORDER BY l.id
                """,
                {"hid": hlr_id},
            )
        else:
            result = self._session.run(
                "MATCH (l:LLR) RETURN l ORDER BY l.id",
            )
        llrs = []
        for record in result:
            props = dict(record["l"])
            llrs.append(
                LLRNode(
                    id=props["id"],
                    description=props["description"],
                    high_level_requirement_id=props["high_level_requirement_id"],
                )
            )
        return llrs

    # -----------------------------------------------------------------------
    # Component link operations (replaces low_level_requirements_components M2M)
    # -----------------------------------------------------------------------

    def link_component(self, llr_id: int, component_id: int) -> None:
        """Store a component association on an :LLR node.

        Since :Component nodes don't yet exist in Neo4j (Phase 3+),
        we store component_ids as a list property on the LLR node.
        """
        # Get current component_ids list
        result = self._session.run(
            "MATCH (l:LLR {id: $lid}) RETURN l.component_ids AS cids",
            {"lid": llr_id},
        )
        record = result.single()
        cids = record["cids"] if record and record["cids"] else []
        if cids is None:
            cids = []
        if component_id not in cids:
            cids = cids + [component_id]  # create new list to satisfy Neo4j
            self._session.run(
                "MATCH (l:LLR {id: $lid}) SET l.component_ids = $cids",
                {"lid": llr_id, "cids": cids},
            )

    def unlink_component(self, llr_id: int, component_id: int) -> None:
        """Remove a component association from an :LLR node."""
        result = self._session.run(
            "MATCH (l:LLR {id: $lid}) RETURN l.component_ids AS cids",
            {"lid": llr_id},
        )
        record = result.single()
        cids = record["cids"] if record and record["cids"] else []
        if cids is None:
            cids = []
        if component_id in cids:
            cids = [c for c in cids if c != component_id]
            self._session.run(
                "MATCH (l:LLR {id: $lid}) SET l.component_ids = $cids",
                {"lid": llr_id, "cids": cids},
            )

    def get_llr_components(self, llr_id: int) -> list[int]:
        """Get the component IDs associated with an :LLR node."""
        result = self._session.run(
            "MATCH (l:LLR {id: $lid}) RETURN l.component_ids AS cids",
            {"lid": llr_id},
        )
        record = result.single()
        cids = record["cids"] if record and record["cids"] else []
        return cids or []

    # -----------------------------------------------------------------------
    # TRACES_TO edge operations (moved from DesignRepository)
    # -----------------------------------------------------------------------

    def trace_to_design(self, hlr_id: int | None = None, llr_id: int | None = None, design_qualified_name: str = "") -> None:
        """Create a TRACES_TO edge from an :HLR or :LLR node to a :Design node."""
        if hlr_id is not None:
            self._session.run(
                """
                MATCH (h:HLR {id: $id})
                MATCH (d:Design {qualified_name: $qn})
                MERGE (h)-[:TRACES_TO]->(d)
                """,
                {"id": hlr_id, "qn": design_qualified_name},
            )
        elif llr_id is not None:
            self._session.run(
                """
                MATCH (l:LLR {id: $id})
                MATCH (d:Design {qualified_name: $qn})
                MERGE (l)-[:TRACES_TO]->(d)
                """,
                {"id": llr_id, "qn": design_qualified_name},
            )

    def untrace_from_design(self, hlr_id: int | None = None, llr_id: int | None = None, design_qualified_name: str = "") -> None:
        """Remove a TRACES_TO edge from an :HLR or :LLR node to a :Design node."""
        if hlr_id is not None:
            self._session.run(
                """
                MATCH (h:HLR {id: $id})-[r:TRACES_TO]->(d:Design {qualified_name: $qn})
                DELETE r
                """,
                {"id": hlr_id, "qn": design_qualified_name},
            )
        elif llr_id is not None:
            self._session.run(
                """
                MATCH (l:LLR {id: $id})-[r:TRACES_TO]->(d:Design {qualified_name: $qn})
                DELETE r
                """,
                {"id": llr_id, "qn": design_qualified_name},
            )

    # -----------------------------------------------------------------------
    # ID generation
    # -----------------------------------------------------------------------

    def _next_hlr_id(self) -> int:
        """Generate the next HLR id by finding the current max + 1."""
        result = self._session.run("MATCH (h:HLR) RETURN coalesce(max(h.id), 0) AS max_id")
        record = result.single()
        return (record["max_id"] + 1) if record else 1

    def _next_llr_id(self) -> int:
        """Generate the next LLR id by finding the current max + 1."""
        result = self._session.run("MATCH (l:LLR) RETURN coalesce(max(l.id), 0) AS max_id")
        record = result.single()
        return (record["max_id"] + 1) if record else 1