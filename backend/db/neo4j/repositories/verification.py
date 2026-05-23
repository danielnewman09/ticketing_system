"""Verification repository — Neo4j-primary CRUD for verification nodes.

All verification data access goes through this class. Phase 3 replaces
the SQLAlchemy VerificationMethod/VerificationCondition/VerificationAction
models with full Neo4j-native nodes and typed operand edges.

Node labels and edge types:
  (:LLR)-[:VERIFIES]->(:VerificationMethod)
  (:VerificationMethod)-[:HAS_CONDITION]->(:Condition)
  (:Condition)-[:LEFT_OPERAND]->(:Design)   (subject of assertion)
  (:Condition)-[:RIGHT_OPERAND]->(:Design)  (reference value)
  (:VerificationMethod)-[:HAS_ACTION]->(:Action)
  (:Action)-[:CALLER]->(:Design)            (object performing action)
  (:Action)-[:CALLEE]->(:Design)            (method being invoked)
"""

from __future__ import annotations

import logging

from neo4j import Session as Neo4jSession

from backend.db.neo4j.repositories.models.verification import (
    ActionNode,
    ConditionNode,
    VerificationMethodNode,
)

log = logging.getLogger(__name__)


class VerificationRepository:
    """CRUD operations for :VerificationMethod, :Condition, :Action nodes in Neo4j.

    VerificationMethod nodes use an `id` property (integer) as their unique
    identifier, consistent with the Phase 2 id pattern for HLR/LLR.
    """

    def __init__(self, session: Neo4jSession) -> None:
        self._session = session

    # -----------------------------------------------------------------------
    # VerificationMethod operations
    # -----------------------------------------------------------------------

    def create_verification(
        self,
        llr_id: int,
        method: str,
        test_name: str = "",
        description: str = "",
    ) -> VerificationMethodNode:
        """Create a :VerificationMethod node linked to :LLR via :VERIFIES edge."""
        next_id = self._next_vm_id()
        self._session.run(
            """
            MATCH (l:LLR {id: $llr_id})
            CREATE (vm:VerificationMethod {id: $id, method: $method, test_name: $test_name, description: $desc})
            CREATE (l)-[:VERIFIES]->(vm)
            """,
            {
                "llr_id": llr_id,
                "id": next_id,
                "method": method,
                "test_name": test_name,
                "desc": description,
            },
        )
        return VerificationMethodNode(
            id=next_id,
            llr_id=llr_id,
            method=method,
            test_name=test_name,
            description=description,
        )

    def get_verification(self, vm_id: int) -> VerificationMethodNode | None:
        """Fetch a single :VerificationMethod node by id. Returns None if not found."""
        result = self._session.run(
            "MATCH (vm:VerificationMethod {id: $id}) RETURN vm",
            {"id": vm_id},
        )
        record = result.single()
        if record is None:
            return None
        props = dict(record["vm"])
        # Resolve llr_id from VERIFIES edge
        llr_result = self._session.run(
            "MATCH (l:LLR)-[:VERIFIES]->(vm:VerificationMethod {id: $id}) RETURN l.id AS llr_id",
            {"id": vm_id},
        )
        llr_rec = llr_result.single()
        llr_id = llr_rec["llr_id"] if llr_rec else 0
        return VerificationMethodNode(
            id=props["id"],
            llr_id=llr_id,
            method=props["method"],
            test_name=props.get("test_name", ""),
            description=props.get("description", ""),
        )

    def update_verification(self, vm_id: int, **kwargs) -> VerificationMethodNode | None:
        """Update a :VerificationMethod node's properties. Returns the updated node or None."""
        if not kwargs:
            return self.get_verification(vm_id)

        allowed = {"method", "test_name", "description"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return self.get_verification(vm_id)

        set_clauses = ", ".join(f"vm.{k} = ${k}" for k in updates)
        params = {"id": vm_id, **updates}
        self._session.run(
            f"MATCH (vm:VerificationMethod {{id: $id}}) SET {set_clauses}",
            params,
        )
        return self.get_verification(vm_id)

    def delete_verification(self, vm_id: int) -> bool:
        """Delete a :VerificationMethod node and cascade-delete all :Condition/:Action nodes.

        Returns True if the node was deleted, False if not found.
        """
        # Find and delete child conditions and actions first
        cond_ids = [
            r["id"]
            for r in self._session.run(
                "MATCH (vm:VerificationMethod {id: $id})-[:HAS_CONDITION]->(c:Condition) RETURN c.id AS id",
                {"id": vm_id},
            )
        ]
        for cid in cond_ids:
            self._session.run(
                "MATCH (c:Condition {id: $id}) DETACH DELETE c",
                {"id": cid},
            )

        action_ids = [
            r["id"]
            for r in self._session.run(
                "MATCH (vm:VerificationMethod {id: $id})-[:HAS_ACTION]->(a:Action) RETURN a.id AS id",
                {"id": vm_id},
            )
        ]
        for aid in action_ids:
            self._session.run(
                "MATCH (a:Action {id: $id}) DETACH DELETE a",
                {"id": aid},
            )

        result = self._session.run(
            "MATCH (vm:VerificationMethod {id: $id}) DETACH DELETE vm RETURN count(vm) AS cnt",
            {"id": vm_id},
        )
        record = result.single()
        return record is not None and record["cnt"] > 0

    def list_verifications(self, llr_id: int) -> list[VerificationMethodNode]:
        """List all :VerificationMethod nodes linked to a specific :LLR via :VERIFIES."""
        result = self._session.run(
            """
            MATCH (l:LLR {id: $llr_id})-[:VERIFIES]->(vm:VerificationMethod)
            RETURN vm ORDER BY vm.id
            """,
            {"llr_id": llr_id},
        )
        vms = []
        for record in result:
            props = dict(record["vm"])
            vms.append(
                VerificationMethodNode(
                    id=props["id"],
                    llr_id=llr_id,
                    method=props["method"],
                    test_name=props.get("test_name", ""),
                    description=props.get("description", ""),
                )
            )
        return vms

    # -----------------------------------------------------------------------
    # Condition operations
    # -----------------------------------------------------------------------

    def add_condition(
        self,
        vm_id: int,
        phase: str,
        order: int = 0,
        operator: str = "==",
        expected_value: str = "",
        subject_qualified_name: str = "",
        object_qualified_name: str = "",
    ) -> ConditionNode:
        """Create a :Condition node with :HAS_CONDITION edge and optional operand edges.

        If subject_qualified_name references an existing :Design node, a
        :LEFT_OPERAND edge is created. Similarly for object_qualified_name
        with a :RIGHT_OPERAND edge. If the :Design node doesn't exist yet,
        the qualified name is stored as a property but no edge is created
        (call augment_missing_design_nodes() first if needed).
        """
        next_id = self._next_condition_id()

        # Create the :Condition node and :HAS_CONDITION edge
        self._session.run(
            """
            MATCH (vm:VerificationMethod {id: $vm_id})
            CREATE (c:Condition {
                id: $id, phase: $phase, `order`: $order,
                operator: $operator, expected_value: $expected_value,
                subject_qualified_name: $sqn, object_qualified_name: $oqn
            })
            CREATE (vm)-[:HAS_CONDITION]->(c)
            """,
            {
                "vm_id": vm_id,
                "id": next_id,
                "phase": phase,
                "order": order,
                "operator": operator,
                "expected_value": expected_value,
                "sqn": subject_qualified_name,
                "oqn": object_qualified_name,
            },
        )

        # Create :LEFT_OPERAND edge if subject :Design node exists
        if subject_qualified_name:
            self._session.run(
                """
                MATCH (c:Condition {id: $cid})
                MATCH (d:Design {qualified_name: $qn})
                MERGE (c)-[:LEFT_OPERAND]->(d)
                """,
                {"cid": next_id, "qn": subject_qualified_name},
            )

        # Create :RIGHT_OPERAND edge if object :Design node exists
        if object_qualified_name:
            self._session.run(
                """
                MATCH (c:Condition {id: $cid})
                MATCH (d:Design {qualified_name: $qn})
                MERGE (c)-[:RIGHT_OPERAND]->(d)
                """,
                {"cid": next_id, "qn": object_qualified_name},
            )

        return ConditionNode(
            id=next_id,
            verification_method_id=vm_id,
            phase=phase,
            order=order,
            subject_qualified_name=subject_qualified_name,
            operator=operator,
            expected_value=expected_value,
            object_qualified_name=object_qualified_name,
        )

    def list_conditions(self, vm_id: int, phase: str | None = None) -> list[ConditionNode]:
        """List :Condition nodes for a :VerificationMethod, optionally filtered by phase."""
        if phase is not None:
            result = self._session.run(
                """
                MATCH (vm:VerificationMethod {id: $vm_id})-[:HAS_CONDITION]->(c:Condition {phase: $phase})
                RETURN c ORDER BY c.`order`
                """,
                {"vm_id": vm_id, "phase": phase},
            )
        else:
            result = self._session.run(
                """
                MATCH (vm:VerificationMethod {id: $vm_id})-[:HAS_CONDITION]->(c:Condition)
                RETURN c ORDER BY c.`order`
                """,
                {"vm_id": vm_id},
            )
        conditions = []
        for record in result:
            props = dict(record["c"])
            conditions.append(
                ConditionNode(
                    id=props["id"],
                    verification_method_id=vm_id,
                    phase=props["phase"],
                    order=props.get("order", 0),
                    subject_qualified_name=props.get("subject_qualified_name", ""),
                    operator=props.get("operator", "=="),
                    expected_value=props.get("expected_value", ""),
                    object_qualified_name=props.get("object_qualified_name", ""),
                )
            )
        return conditions

    # -----------------------------------------------------------------------
    # Action operations
    # -----------------------------------------------------------------------

    def add_action(
        self,
        vm_id: int,
        order: int = 0,
        description: str = "",
        caller_qualified_name: str = "",
        callee_qualified_name: str = "",
    ) -> ActionNode:
        """Create an :Action node with :HAS_ACTION edge and optional edges to :Design.

        If caller_qualified_name references an existing :Design node, a
        :CALLER edge is created. If callee_qualified_name references an
        existing :Design node, a :CALLEE edge is created.
        """
        next_id = self._next_action_id()

        self._session.run(
            """
            MATCH (vm:VerificationMethod {id: $vm_id})
            CREATE (a:Action {
                id: $id, `order`: $order, description: $desc,
                caller_qualified_name: $caller_qn, callee_qualified_name: $callee_qn
            })
            CREATE (vm)-[:HAS_ACTION]->(a)
            """,
            {
                "vm_id": vm_id,
                "id": next_id,
                "order": order,
                "desc": description,
                "caller_qn": caller_qualified_name,
                "callee_qn": callee_qualified_name,
            },
        )

        # Create :CALLER edge if referenced :Design node exists
        if caller_qualified_name:
            self._session.run(
                """
                MATCH (a:Action {id: $aid})
                MATCH (d:Design {qualified_name: $qn})
                MERGE (a)-[:CALLER]->(d)
                """,
                {"aid": next_id, "qn": caller_qualified_name},
            )

        # Create :CALLEE edge if referenced :Design node exists
        if callee_qualified_name:
            self._session.run(
                """
                MATCH (a:Action {id: $aid})
                MATCH (d:Design {qualified_name: $qn})
                MERGE (a)-[:CALLEE]->(d)
                """,
                {"aid": next_id, "qn": callee_qualified_name},
            )

        return ActionNode(
            id=next_id,
            verification_method_id=vm_id,
            order=order,
            description=description,
            caller_qualified_name=caller_qualified_name,
            callee_qualified_name=callee_qualified_name,
        )

    def list_actions(self, vm_id: int) -> list[ActionNode]:
        """List :Action nodes for a :VerificationMethod, ordered by action order."""
        result = self._session.run(
            """
            MATCH (vm:VerificationMethod {id: $vm_id})-[:HAS_ACTION]->(a:Action)
            RETURN a ORDER BY a.`order`
            """,
            {"vm_id": vm_id},
        )
        actions = []
        for record in result:
            props = dict(record["a"])
            actions.append(
                ActionNode(
                    id=props["id"],
                    verification_method_id=vm_id,
                    order=props.get("order", 0),
                    description=props.get("description", ""),
                    caller_qualified_name=props.get("caller_qualified_name", ""),
                    callee_qualified_name=props.get("callee_qualified_name", ""),
                )
            )
        return actions

    # -----------------------------------------------------------------------
    # Design node augmentation and validation
    # -----------------------------------------------------------------------

    def augment_missing_design_nodes(self, qualified_names: list[str]) -> list[str]:
        """Create missing :Design stub nodes for unresolved verification references.

        For each qualified_name that doesn't match an existing :Design node,
        creates a stub with source_type="verification" (marks it as auto-created).
        Returns the list of qualified_names that were created.
        """
        if not qualified_names:
            return []

        created = []
        for qn in qualified_names:
            if not qn:
                continue
            # Check if :Design node already exists
            result = self._session.run(
                "MATCH (d:Design {qualified_name: $qn}) RETURN count(d) AS cnt",
                {"qn": qn},
            )
            if result.single()["cnt"] > 0:
                continue

            # Parse parent and member name for stub creation
            name = qn.rsplit("::", 1)[-1] if "::" in qn else qn

            # Create the stub :Design node
            self._session.run(
                """
                MERGE (d:Design {qualified_name: $qn})
                SET d.name = $name, d.kind = 'member', d.source_type = 'verification',
                    d.description = 'Auto-created from verification reference'
                """,
                {"qn": qn, "name": name},
            )
            created.append(qn)
            log.info("augment: created verification stub :Design node %s", qn)

        return created

    def validate_references(self, qualified_names: list[str]) -> tuple[list[str], list[str]]:
        """Check which qualified_names exist as :Design nodes in Neo4j.

        Returns (resolved, unresolved) lists.
        """
        resolved = []
        unresolved = []
        for qn in qualified_names:
            if not qn:
                continue
            result = self._session.run(
                "MATCH (d:Design {qualified_name: $qn}) RETURN count(d) AS cnt",
                {"qn": qn},
            )
            if result.single()["cnt"] > 0:
                resolved.append(qn)
            else:
                unresolved.append(qn)
        return resolved, unresolved

    # -----------------------------------------------------------------------
    # ID generation
    # -----------------------------------------------------------------------

    def _next_vm_id(self) -> int:
        """Generate the next VerificationMethod id by finding the current max + 1."""
        result = self._session.run(
            "MATCH (vm:VerificationMethod) RETURN coalesce(max(vm.id), 0) AS max_id"
        )
        record = result.single()
        return (record["max_id"] + 1) if record else 1

    def _next_condition_id(self) -> int:
        """Generate the next Condition id by finding the current max + 1."""
        result = self._session.run(
            "MATCH (c:Condition) RETURN coalesce(max(c.id), 0) AS max_id"
        )
        record = result.single()
        return (record["max_id"] + 1) if record else 1

    def _next_action_id(self) -> int:
        """Generate the next Action id by finding the current max + 1."""
        result = self._session.run(
            "MATCH (a:Action) RETURN coalesce(max(a.id), 0) AS max_id"
        )
        record = result.single()
        return (record["max_id"] + 1) if record else 1
