"""Design data repository — typed read queries against Neo4j.

Replaces ad-hoc graph querying patterns in design_per_hlr, draft_state,
persistence, and orchestrator with a single clean API returning typed
ClassDiagram models.
"""

from __future__ import annotations

import logging
from typing import Literal

from neo4j import Session as Neo4jSession

from backend.design_data.models import (
    Association,
    AttributeNode,
    ClassDiagram,
    ClassNode,
    EnumNode,
    EnumValueNode,
    InterfaceNode,
    MethodNode,
    ModuleNode,
)

log = logging.getLogger(__name__)

# Neo4j Design node kinds that map to ClassNode-like entities
_CLASS_KINDS = {"class", "struct", "template_class"}
_INTERFACE_KINDS = {"interface", "abstract_class"}
_ENUM_KINDS = {"enum", "enum_class"}
_MEMBER_KINDS = {"attribute", "method", "constant", "enum_value"}
_MODULE_KINDS = {"namespace", "module"}

# Predicates that become Association objects
_ASSOCIATION_PREDICATES = {
    "aggregates",
    "composes",
    "references",
    "depends_on",
    "associates",
    "invokes",
    "returns",
    "realizes",
    "inherits_from",
    "implements",
}


class DesignDataRepository:
    """Read-only repository returning typed models from Neo4j :Compound nodes with layer='design'.

    Each method accepts a Neo4j session and returns hydrated model objects
    suitable for agent prompts, verification context, or draft lookups.
    """

    def __init__(self, session: Neo4jSession) -> None:
        self._session = session

    # -----------------------------------------------------------------------
    # Full diagram queries
    # -----------------------------------------------------------------------

    def get_class_diagram(
        self,
        component_id: int | None = None,
        layer: Literal["design", "as-built", "dependency"] | None = None,
    ) -> ClassDiagram:
        """Fetch a complete ClassDiagram for a component and/or layer.

        Args:
            component_id: Optional component FK to filter by.
            layer: Optional layer filter ("design", "as-built", "dependency").

        Returns:
            A ClassDiagram with all matching entities and associations.
        """
        conditions = ["d:Compound", "d.layer = $layer"]
        params: dict = {"layer": layer or "design"}

        if component_id is not None:
            conditions.append("d.component_id = $comp_id")
            params["comp_id"] = component_id
        if layer is not None:
            conditions.append("d.source_type = $source_type OR d.source_type IS NULL")
            # Map layer to source_type values used in Neo4j
            layer_map = {"design": "member", "as-built": "compound", "dependency": "dependency"}
            # For design layer, include nodes without source_type too
            if layer == "design":
                conditions[-1] = "(d.source_type = 'member' OR d.source_type IS NULL OR d.source_type = '')"
            elif layer == "as-built":
                conditions[-1] = "d.source_type = 'compound'"
            else:
                conditions[-1] = "d.source_type = 'dependency'"
            params["source_type"] = layer

        where = " AND ".join(conditions)

        # Fetch top-level entities
        cypher = f"""
        MATCH (d)
        WHERE {where}
          AND d.kind IN ['class', 'struct', 'template_class', 'interface', 'abstract_class', 'enum', 'enum_class', 'namespace', 'module']
        OPTIONAL MATCH (d)-[:COMPOSES]->(member:Member)
        WITH d, collect(DISTINCT member) AS members
        RETURN d, members
        """
        result = self._session.run(cypher, params)

        classes: list[ClassNode] = []
        interfaces: list[InterfaceNode] = []
        enums: list[EnumNode] = []
        modules: list[ModuleNode] = []
        module_names: list[str] = []

        for record in result:
            d = dict(record["d"])
            members = record["members"] or []
            kind = d.get("kind", "")

            if kind in _CLASS_KINDS:
                cls = self._hydrate_class(d, members)
                classes.append(cls)
                if cls.module and cls.module not in module_names:
                    module_names.append(cls.module)
            elif kind in _INTERFACE_KINDS:
                iface = self._hydrate_interface(d, members)
                interfaces.append(iface)
                if iface.module and iface.module not in module_names:
                    module_names.append(iface.module)
            elif kind in _ENUM_KINDS:
                enum = self._hydrate_enum(d, members)
                enums.append(enum)
                if enum.module and enum.module not in module_names:
                    module_names.append(enum.module)
            elif kind in _MODULE_KINDS:
                mod = ModuleNode(
                    name=d.get("name", ""),
                    qualified_name=d.get("qualified_name", ""),
                    kind="module",
                    layer=_map_layer(d),
                    description=d.get("description", ""),
                )
                modules.append(mod)
                if mod.name and mod.name not in module_names:
                    module_names.append(mod.name)

        # Fetch associations
        associations = self._fetch_associations(conditions, params)

        return ClassDiagram(
            module_names=module_names,
            classes=classes,
            interfaces=interfaces,
            enums=enums,
            associations=associations,
        )

    def get_hlr_subgraph(
        self,
        hlr_id: int,
        component_id: int | None = None,
    ) -> ClassDiagram:
        """Fetch the class diagram for design nodes linked to an HLR.

        Args:
            hlr_id: HLR node ID in Neo4j.
            component_id: Optional component filter.

        Returns:
            A ClassDiagram containing only the entities relevant to this HLR.
        """
        params: dict = {"hlr_id": hlr_id}
        conditions = [
            "d:Compound", "d.layer = 'design'",
            "d.kind IN ['class', 'struct', 'template_class', 'interface', 'abstract_class', 'enum', 'enum_class']",
        ]
        if component_id is not None:
            conditions.append("d.component_id = $comp_id")
            params["comp_id"] = component_id

        where = " AND ".join(conditions)

        # Strategy: find entities that are directly linked to HLR
        # via TRACES_TO or that are in the same component
        cypher = f"""
        MATCH (hlr:HLR {{id: $hlr_id}})
        MATCH (d)
        WHERE {where}
          AND (
            EXISTS {{
              MATCH (hlr)-[:TRACES_TO]->(d)
            }}
            OR
            EXISTS {{
              MATCH (hlr)-[:TRACES_TO]->(parent:Compound)-[:COMPOSES]->(d)
            }}
            OR
            d.component_id = $comp_id
          )
        OPTIONAL MATCH (d)-[:COMPOSES]->(member:Member)
        WITH d, collect(DISTINCT member) AS members
        RETURN d, members
        """
        if component_id is not None:
            result = self._session.run(cypher, params)
        else:
            # Without component filter, just find entities linked to HLR
            cypher_simple = """
            MATCH (hlr:HLR {id: $hlr_id})-[:TRACES_TO]->(d:Compound)
            WHERE d.kind IN ['class', 'struct', 'template_class', 'interface', 'abstract_class', 'enum', 'enum_class']
            OPTIONAL MATCH (d)-[:COMPOSES]->(member:Member)
            WITH d, collect(DISTINCT member) AS members
            RETURN d, members
            """
            result = self._session.run(cypher_simple, params)

        classes: list[ClassNode] = []
        interfaces: list[InterfaceNode] = []
        enums: list[EnumNode] = []
        module_names: list[str] = []

        for record in result:
            d = dict(record["d"])
            members = record["members"] or []
            kind = d.get("kind", "")

            if kind in _CLASS_KINDS:
                cls = self._hydrate_class(d, members)
                classes.append(cls)
                if cls.module and cls.module not in module_names:
                    module_names.append(cls.module)
            elif kind in _INTERFACE_KINDS:
                iface = self._hydrate_interface(d, members)
                interfaces.append(iface)
                if iface.module and iface.module not in module_names:
                    module_names.append(iface.module)
            elif kind in _ENUM_KINDS:
                enum = self._hydrate_enum(d, members)
                enums.append(enum)
                if enum.module and enum.module not in module_names:
                    module_names.append(enum.module)

        return ClassDiagram(
            module_names=module_names,
            classes=classes,
            interfaces=interfaces,
            enums=enums,
            associations=[],
        )

    # -----------------------------------------------------------------------
    # Single-entity queries
    # -----------------------------------------------------------------------

    def get_class(self, qualified_name: str) -> ClassNode | None:
        """Fetch a single class with hydrated members."""
        cypher = """
        MATCH (d:Compound {qualified_name: $qn})
        WHERE d.kind IN ['class', 'struct', 'template_class']
        AND d.layer = 'design'
        OPTIONAL MATCH (d)-[:COMPOSES]->(member:Member)
        RETURN d, collect(DISTINCT member) AS members
        """
        result = self._session.run(cypher, {"qn": qualified_name})
        record = result.single()
        if record is None:
            return None
        d = dict(record["d"])
        members = record["members"] or []
        return self._hydrate_class(d, members)

    def get_interface(self, qualified_name: str) -> InterfaceNode | None:
        """Fetch a single interface with hydrated methods."""
        cypher = """
        MATCH (d:Compound {qualified_name: $qn})
        WHERE d.kind IN ['interface', 'abstract_class']
        AND d.layer = 'design'
        OPTIONAL MATCH (d)-[:COMPOSES]->(member:Member)
        RETURN d, collect(DISTINCT member) AS members
        """
        result = self._session.run(cypher, {"qn": qualified_name})
        record = result.single()
        if record is None:
            return None
        d = dict(record["d"])
        members = record["members"] or []
        return self._hydrate_interface(d, members)

    def get_enum(self, qualified_name: str) -> EnumNode | None:
        """Fetch a single enum with hydrated values."""
        cypher = """
        MATCH (d:Compound {qualified_name: $qn})
        WHERE d.kind IN ['enum', 'enum_class']
        AND d.layer = 'design'
        OPTIONAL MATCH (d)-[:COMPOSES]->(member:Member)
        RETURN d, collect(DISTINCT member) AS members
        """
        result = self._session.run(cypher, {"qn": qualified_name})
        record = result.single()
        if record is None:
            return None
        d = dict(record["d"])
        members = record["members"] or []
        return self._hydrate_enum(d, members)

    # -----------------------------------------------------------------------
    # Prompt helper queries
    # -----------------------------------------------------------------------

    def get_classes_for_component(self, component_id: int) -> list[ClassNode]:
        """Get all class-like entities for a component, with hydrated members.

        Useful for building prompt context about existing designs.
        """
        cypher = """
        MATCH (d:Compound)
        WHERE d.kind IN ['class', 'struct', 'template_class']
          AND d.component_id = $comp_id
          AND d.layer = 'design'
        OPTIONAL MATCH (d)-[:COMPOSES]->(member:Member)
        WITH d, collect(DISTINCT member) AS members
        RETURN d, members
        """
        result = self._session.run(cypher, {"comp_id": component_id})
        classes = []
        for record in result:
            d = dict(record["d"])
            members = record["members"] or []
            classes.append(self._hydrate_class(d, members))
        return classes

    def get_public_api(self, component_id: int) -> list[dict]:
        """Get public API details for intercomponent context.

        Returns list of dicts with qualified_name, kind, description, methods
        for is_intercomponent=True entities in a component.
        """
        cypher = """
        MATCH (d:Compound)
        WHERE d.is_intercomponent = true AND d.component_id = $comp_id
          AND d.kind IN ['class', 'struct', 'template_class', 'interface', 'abstract_class']
          AND d.layer = 'design'
        OPTIONAL MATCH (d)-[:COMPOSES]->(member:Member)
        WHERE member.kind = 'method' AND member.visibility = 'public'
        RETURN d, collect(DISTINCT member) AS members
        """
        result = self._session.run(cypher, {"comp_id": component_id})
        entries = []
        for record in result:
            d = dict(record["d"])
            methods = []
            for m in (record["members"] or []):
                if m is not None:
                    md = dict(m)
                    methods.append({
                        "name": md.get("name", ""),
                        "visibility": md.get("visibility", "public"),
                    })
            entries.append({
                "qualified_name": d.get("qualified_name", ""),
                "kind": d.get("kind", ""),
                "description": d.get("description", ""),
                "methods": methods,
            })
        return entries

    # -----------------------------------------------------------------------
    # Private hydration helpers
    # -----------------------------------------------------------------------

    def _hydrate_class(self, d: dict, members: list) -> ClassNode:
        """Hydrate a ClassNode from a Neo4j node dict and its member nodes."""
        attrs = []
        methods = []
        for m in members:
            if m is None:
                continue
            md = dict(m)
            kind = md.get("kind", "")
            if kind in ("attribute", "constant"):
                attrs.append(AttributeNode(
                    name=md.get("name", ""),
                    qualified_name=md.get("qualified_name", ""),
                    kind="attribute",
                    layer=_map_layer(md),
                    description=md.get("description", ""),
                    visibility=md.get("visibility", ""),
                    type_signature=md.get("type_signature", ""),
                    owner=d.get("qualified_name", ""),
                ))
            elif kind == "method":
                methods.append(MethodNode(
                    name=md.get("name", ""),
                    qualified_name=md.get("qualified_name", ""),
                    kind="method",
                    layer=_map_layer(md),
                    description=md.get("description", ""),
                    visibility=md.get("visibility", ""),
                    type_signature=md.get("type_signature", ""),
                    argsstring=md.get("argsstring", ""),
                    owner=d.get("qualified_name", ""),
                ))

        return ClassNode(
            name=d.get("name", ""),
            qualified_name=d.get("qualified_name", ""),
            kind="class",
            layer=_map_layer(d),
            description=d.get("description", ""),
            visibility=d.get("visibility", ""),
            specialization=d.get("specialization", ""),
            component_id=d.get("component_id"),
            is_intercomponent=d.get("is_intercomponent", False),
            type_signature=d.get("type_signature", ""),
            file_path=d.get("file_path", ""),
            line_number=d.get("line_number"),
            is_static=d.get("is_static", False),
            is_const=d.get("is_const", False),
            is_virtual=d.get("is_virtual", False),
            is_abstract=d.get("is_abstract", False),
            is_final=d.get("is_final", False),
            implementation_status=d.get("implementation_status", "designed"),
            source_file=d.get("source_file", ""),
            test_file=d.get("test_file", ""),
            module=_extract_module(d.get("qualified_name", "")),
            inherits_from=[],  # Populated from relationships below
            realizes=[],
            attributes=attrs,
            methods=methods,
        )

    def _hydrate_interface(self, d: dict, members: list) -> InterfaceNode:
        """Hydrate an InterfaceNode from a Neo4j node dict and its member nodes."""
        methods = []
        for m in members:
            if m is None:
                continue
            md = dict(m)
            if md.get("kind") == "method":
                methods.append(MethodNode(
                    name=md.get("name", ""),
                    qualified_name=md.get("qualified_name", ""),
                    kind="method",
                    layer=_map_layer(md),
                    description=md.get("description", ""),
                    visibility=md.get("visibility", ""),
                    type_signature=md.get("type_signature", ""),
                    argsstring=md.get("argsstring", ""),
                    owner=d.get("qualified_name", ""),
                    is_virtual=True,
                ))

        return InterfaceNode(
            name=d.get("name", ""),
            qualified_name=d.get("qualified_name", ""),
            kind="interface",
            layer=_map_layer(d),
            description=d.get("description", ""),
            visibility=d.get("visibility", ""),
            specialization=d.get("specialization", ""),
            is_intercomponent=d.get("is_intercomponent", False),
            is_abstract=d.get("is_abstract", True),
            module=_extract_module(d.get("qualified_name", "")),
            methods=methods,
        )

    def _hydrate_enum(self, d: dict, members: list) -> EnumNode:
        """Hydrate an EnumNode from a Neo4j node dict and its member nodes."""
        values = []
        for m in members:
            if m is None:
                continue
            md = dict(m)
            if md.get("kind") == "enum_value":
                values.append(EnumValueNode(
                    name=md.get("name", ""),
                    qualified_name=md.get("qualified_name", ""),
                    kind="enum_value",
                    layer=_map_layer(md),
                    owner=d.get("qualified_name", ""),
                ))

        return EnumNode(
            name=d.get("name", ""),
            qualified_name=d.get("qualified_name", ""),
            kind="enum",
            layer=_map_layer(d),
            description=d.get("description", ""),
            module=_extract_module(d.get("qualified_name", "")),
            values=values,
        )

    def _fetch_associations(self, conditions: list[str], params: dict) -> list[Association]:
        """Fetch association relationships between top-level design entities."""
        # Build WHERE for subject and object being Design nodes in our scope
        where = " AND ".join(conditions)
        # We need to find relationships between entities matching our filters
        cypher = f"""
        MATCH (s)-[r]->(o)
        WHERE {where}
          AND type(r) IN ['AGGREGATES', 'COMPOSES', 'REFERENCES', 'DEPENDS_ON', 'ASSOCIATES',
                          'INVOKES', 'RETURNS', 'REALIZES', 'INHERITS_FROM', 'IMPLEMENTS']
          AND (o:Compound OR o:Namespace)
        RETURN s.qualified_name AS subject, type(r) AS rel_type,
               o.qualified_name AS object, r.mechanism AS mechanism, r.description AS description
        """
        # Re-map conditions for o node as well
        # Actually simpler: find all relationships between Design nodes
        cypher = """
        MATCH '(s:Compound)'-[r]->(o)
        WHERE type(r) IN ['AGGREGATES', 'COMPOSES', 'REFERENCES', 'DEPENDS_ON', 'ASSOCIATES',
                          'INVOKES', 'RETURNS', 'REALIZES', 'INHERITS_FROM', 'IMPLEMENTS']
          AND (o:Compound OR o:Namespace)
        RETURN s.qualified_name AS subject, type(r) AS rel_type,
               o.qualified_name AS object, r.mechanism AS mechanism, r.description AS description
        """
        result = self._session.run(cypher, params)

        # Map Neo4j rel types back to predicates
        rel_type_to_predicate = {
            "AGGREGATES": "aggregates",
            "COMPOSES": "composes",
            "REFERENCES": "references",
            "DEPENDS_ON": "depends_on",
            "ASSOCIATES": "associates",
            "INVOKES": "invokes",
            "RETURNS": "returns",
            "REALIZES": "realizes",
            "INHERITS_FROM": "inherits_from",
            "IMPLEMENTS": "implements",
        }
        associations = []
        for record in result:
            predicate = rel_type_to_predicate.get(record["rel_type"], record["rel_type"].lower())
            associations.append(Association(
                subject=record["subject"],
                predicate=predicate,
                object=record["object"] or "",
                mechanism=record["mechanism"] or "",
                description=record.get("description", "") or "",
            ))
        return associations


def _map_layer(d: dict) -> str:
    """Map a Neo4j Design node's source_type to a layer string."""
    source_type = d.get("source_type", "")
    if source_type == "dependency":
        return "dependency"
    elif source_type == "compound":
        return "as-built"
    else:
        return "design"


def _extract_module(qualified_name: str) -> str:
    """Extract module/namespace from a qualified name like 'ns::calc::ClassName'."""
    if "::" in qualified_name:
        parts = qualified_name.rsplit("::", 1)
        return parts[0]
    return ""