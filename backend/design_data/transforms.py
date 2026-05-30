"""Transforms between OODesignSchema (LLM write shape) and ClassDiagram (rich read shape)."""

from backend.codebase.schemas import OODesignSchema
from backend.design_data.models import (
    Association,
    AttributeNode,
    ClassDiagram,
    ClassNode,
    EnumNode,
    EnumValueNode,
    InterfaceNode,
    MethodNode,
)


def class_diagram_from_oo_design(
    oo: OODesignSchema,
    component_id: int | None = None,
) -> ClassDiagram:
    """Convert LLM output (OODesignSchema) to the rich read shape (ClassDiagram).

    Does NOT replace map_to_ontology() — that still handles the write-to-Neo4j
    path via persist_design().

    Args:
        oo: The OO design output from the agent.
        component_id: Optional component FK to set on all entities.

    Returns:
        A ClassDiagram with all entities, members, and associations.
    """
    def _qualify(module: str, name: str) -> str:
        return f"{module}::{name}" if module else name

    classes: list[ClassNode] = []
    interfaces: list[InterfaceNode] = []
    enums: list[EnumNode] = []

    for cls in oo.classes:
        qname = _qualify(cls.module, cls.name)
        classes.append(ClassNode(
            name=cls.name,
            qualified_name=qname,
            kind="class",
            layer="design",
            description=cls.description,
            visibility=getattr(cls, 'visibility', '') or "public",
            specialization=cls.specialization,
            component_id=component_id,
            is_intercomponent=cls.is_intercomponent,
            module=cls.module,
            inherits_from=cls.inherits_from,
            realizes=cls.realizes_interfaces,
            attributes=[
                AttributeNode(
                    name=attr.name,
                    qualified_name=f"{qname}::{attr.name}",
                    kind="attribute",
                    layer="design",
                    description=attr.description,
                    visibility=attr.visibility or "public",
                    type_signature=attr.type_name,
                    owner=qname,
                    component_id=component_id,
                )
                for attr in cls.attributes
            ],
            methods=[
                MethodNode(
                    name=method.name,
                    qualified_name=f"{qname}::{method.name}",
                    kind="method",
                    layer="design",
                    description=method.description,
                    visibility=method.visibility or "public",
                    type_signature=method.return_type,
                    argsstring=f"({', '.join(method.parameters)})" if method.parameters else "",
                    owner=qname,
                    component_id=component_id,
                )
                for method in cls.methods
            ],
        ))

    for iface in oo.interfaces:
        qname = _qualify(iface.module, iface.name)
        interfaces.append(InterfaceNode(
            name=iface.name,
            qualified_name=qname,
            kind="interface",
            layer="design",
            description=iface.description,
            specialization=iface.specialization,
            is_intercomponent=iface.is_intercomponent,
            is_abstract=True,
            module=iface.module,
            methods=[
                MethodNode(
                    name=method.name,
                    qualified_name=f"{qname}::{method.name}",
                    kind="method",
                    layer="design",
                    description=method.description,
                    visibility=method.visibility or "public",
                    type_signature=method.return_type,
                    argsstring=f"({', '.join(method.parameters)})" if method.parameters else "",
                    owner=qname,
                    is_virtual=True,
                    component_id=component_id,
                )
                for method in iface.methods
            ],
        ))

    for enum in oo.enums:
        qname = _qualify(enum.module, enum.name)
        enums.append(EnumNode(
            name=enum.name,
            qualified_name=qname,
            kind="enum",
            layer="design",
            description=enum.description,
            module=enum.module,
            component_id=component_id,
            values=[
                EnumValueNode(
                    name=val,
                    qualified_name=f"{qname}::{val}",
                    kind="enum_value",
                    layer="design",
                    owner=qname,
                    component_id=component_id,
                )
                for val in enum.values
            ],
        ))

    associations = [
        Association(
            subject=assoc.from_class,
            predicate=assoc.kind,
            object=assoc.to_class,
            mechanism=assoc.mechanism,
            description=assoc.description,
        )
        for assoc in oo.associations
    ]

    return ClassDiagram(
        module_names=list(oo.modules),
        classes=classes,
        interfaces=interfaces,
        enums=enums,
        associations=associations,
    )


def oo_design_from_class_diagram(diagram: ClassDiagram) -> OODesignSchema:
    """Reconstruct the LLM-friendly shape from stored design data.

    Replaces _extract_existing_classes(), _extract_intercomponent_context(),
    and all ad-hoc dict construction for agent prompts.

    Args:
        diagram: A ClassDiagram read from Neo4j or converted from an OODesignSchema.

    Returns:
        An OODesignSchema suitable for passing to the design agent prompt
        builders or the skeleton generator.
    """
    from backend.codebase.schemas import (
        AttributeSchema,
        ClassSchema,
        EnumSchema,
        InterfaceSchema,
        MethodSchema,
        AssociationSchema,
    )

    def _strip_module(qname: str) -> str:
        """Strip module prefix from qualified name for OODesignSchema compatibility."""
        if "::" in qname:
            return qname.rsplit("::", 1)[-1]
        return qname

    classes = [
        ClassSchema(
            name=cls.name,
            module=cls.module,
            description=cls.description,
            visibility=cls.visibility,
            is_intercomponent=cls.is_intercomponent,
            requirement_ids=[],
            attributes=[
                AttributeSchema(
                    name=attr.name,
                    type_name=attr.type_signature,
                    visibility=attr.visibility,
                    description=attr.description,
                )
                for attr in cls.attributes
            ],
            methods=[
                MethodSchema(
                    name=method.name,
                    visibility=method.visibility,
                    description=method.description,
                    parameters=_parse_argsstring(method.argsstring),
                    return_type=method.type_signature,
                )
                for method in cls.methods
            ],
            inherits_from=[_strip_module(parent) for parent in cls.inherits_from],
            realizes_interfaces=[_strip_module(iface) for iface in cls.realizes],
        )
        for cls in diagram.classes
    ]

    interfaces = [
        InterfaceSchema(
            name=iface.name,
            module=iface.module,
            specialization=iface.specialization,
            description=iface.description,
            is_intercomponent=iface.is_intercomponent,
            methods=[
                MethodSchema(
                    name=method.name,
                    visibility=method.visibility,
                    description=method.description,
                    parameters=_parse_argsstring(method.argsstring),
                    return_type=method.type_signature,
                )
                for method in iface.methods
            ],
        )
        for iface in diagram.interfaces
    ]

    enums = [
        EnumSchema(
            name=enum_.name,
            module=enum_.module,
            description=enum_.description,
            values=[val.name for val in enum_.values],
        )
        for enum_ in diagram.enums
    ]

    associations = [
        AssociationSchema(
            from_class=assoc.subject,
            to_class=assoc.object,
            kind=assoc.predicate,
            description=assoc.description,
            mechanism=assoc.mechanism,
        )
        for assoc in diagram.associations
    ]

    return OODesignSchema(
        modules=list(diagram.module_names),
        classes=classes,
        interfaces=interfaces,
        enums=enums,
        associations=associations,
    )


def _parse_argsstring(argsstring: str) -> list[str]:
    """Parse a C++ argsstring like '(double x, double y)' into parameter strings."""
    if not argsstring:
        return []
    inner = argsstring.strip()
    if inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1]
    if not inner.strip():
        return []
    return [p.strip() for p in inner.split(",")]