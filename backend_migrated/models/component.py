"""Component node model (:Component label in Neo4j).

Represents a logical subsystem or module of a project (e.g.,
"backend calculation engine", "frontend UI"). Connects to code-level
nodes via GROUPS relationships to indicate which code belongs to
which project component. Extends CodeGraphNode to share serialization,
registry, and relationship introspection infrastructure.
"""

from neomodel import (
    StructuredNode, StringProperty, RelationshipTo, RelationshipFrom,
)

from codegraph.models.tags import CodeGraphNode


class Component(StructuredNode, CodeGraphNode):
    """Project-management grouping node — :Component label in Neo4j.

    Represents a logical subsystem or module of a project (e.g.,
    "backend calculation engine", "frontend UI"). Connects to code-level
    nodes via GROUPS relationships to indicate which code belongs to
    which project component.

    Components form a self-referential hierarchy via PARENT_OF edges,
    linking to languages via WRITTEN_IN, dependencies via DEPENDS_ON,
    and code-level namespaces/classes via GROUPS.

    Attributes:
        name: Short name of the component (e.g. 'calculation_engine'),
            inherited from CodeGraphNode.
        refid: Unique identifier, inherited from CodeGraphNode. Serves
            as the primary lookup key, replacing the auto-increment
            integer id from SQLAlchemy. Convention: use a hierarchical
            path like 'backend::calculation_engine'.
        source: Project name, inherited from CodeGraphNode.
        description: Human-readable description of the component.
        namespace: Code-level namespace this component maps to
            (e.g. 'calculation_engine::').
    """

    # --- Description ---
    description = StringProperty(default="")
    namespace = StringProperty(default="",
        help_text="Code-level namespace this component maps to "
                  "(e.g. 'calculation_engine::').")

    # --- Self-referential hierarchy -------------------------------------------
    #
    #  • PARENT_OF (outgoing)  — Component(parent) → Component(child)
    #    A component can contain sub-components. The parent is the
    #    broader subsystem; the child is a more specific module within it.
    #    Example: Component('backend')-[:PARENT_OF]->Component('calculation_engine')
    #
    #  • PARENT_OF (incoming)  — Component(parent) → Component(child)
    #    Traversed via ``parent`` to find the parent component.
    # --------------------------------------------------------------------------

    children = RelationshipTo(
        'backend_migrated.models.component.Component', 'PARENT_OF')
    parent = RelationshipFrom(
        'backend_migrated.models.component.Component', 'PARENT_OF')

    # --- Language -------------------------------------------------------------
    #
    #  • WRITTEN_IN (outgoing)  — Component → Language
    #    The programming language this component is written in.
    #    Example: Component('backend')-[:WRITTEN_IN]->Language('C++')
    # --------------------------------------------------------------------------

    language = RelationshipTo(
        'backend_migrated.models.language.Language', 'WRITTEN_IN')

    # --- Dependencies ---------------------------------------------------------
    #
    #  • DEPENDS_ON (outgoing)  — Component → Dependency
    #    The third-party libraries this component requires. This is a
    #    many-to-many relationship — a component can depend on multiple
    #    libraries, and a library can be used by multiple components.
    #    Replaces the SQLAlchemy M2M junction table dependency_components.
    # --------------------------------------------------------------------------

    dependencies = RelationshipTo(
        'backend_migrated.models.dependency.Dependency', 'DEPENDS_ON')

    # --- Code-level connections -----------------------------------------------
    #
    #  • GROUPS (outgoing)  — Component → NamespaceNode | ClassNode
    #    A component groups code-level namespaces and classes, indicating
    #    which code belongs to which project component. This replaces the
    #    former component_id integer property on compound/member nodes.
    #
    #    The primary relationship is to NamespaceNode — a component groups
    #    entire namespaces. For unparented classes that don't belong to a
    #    namespace, a direct GROUPS edge to ClassNode is used.
    #
    #    Example: Component('backend')-[:GROUPS]->NamespaceNode('calculation_engine::')
    # --------------------------------------------------------------------------

    namespaces = RelationshipTo(
        'codegraph.models.namespace.NamespaceNode', 'GROUPS')
    classes = RelationshipTo(
        'codegraph.models.compound.ClassNode', 'GROUPS')

    # --- Serialization contract ---
    _llm_fields: set[str] = {
        "name", "description", "namespace",
    }