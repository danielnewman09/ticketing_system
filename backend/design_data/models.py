"""Typed read models for class diagram data.

These models represent the ground-truth design data as stored in Neo4j,
unified across design, as-built, and dependency layers.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, PrivateAttr


class DiagramNode(BaseModel):
    """Common fields for every diagram node (class, method, attribute, etc.)."""

    name: str
    qualified_name: str
    kind: str  # class, interface, enum, module, attribute, method, enum_value, ...
    layer: Literal["design", "as-built", "dependency"]

    # Identity & classification
    description: str = ""
    visibility: str = ""  # public, private, protected
    specialization: str = ""  # struct, template_class, enum_class, etc.
    component_id: int | None = None
    is_intercomponent: bool = False

    # Code-level detail (empty for design-layer, populated for as-built/dependency)
    type_signature: str = ""
    argsstring: str = ""
    definition: str = ""
    source_type: str = ""  # namespace, compound, member, dependency
    source: str = ""  # dependency library name (dependency layer only)

    # Source location
    file_path: str = ""
    line_number: int | None = None

    # Flags
    is_static: bool = False
    is_const: bool = False
    is_virtual: bool = False
    is_abstract: bool = False
    is_final: bool = False

    # Implementation tracking (design layer)
    implementation_status: str = "designed"  # designed, scaffolded, tested, implemented, verified
    source_file: str = ""
    test_file: str = ""


class AttributeNode(DiagramNode):
    """Class/interface attribute."""

    kind: Literal["attribute"] = "attribute"
    owner: str = ""  # qualified name of the owning class/interface


class MethodNode(DiagramNode):
    """Class/interface method."""

    kind: Literal["method"] = "method"
    owner: str = ""  # qualified name of the owning class/interface


class EnumValueNode(DiagramNode):
    """Enum value."""

    kind: Literal["enum_value"] = "enum_value"
    owner: str = ""  # qualified name of the owning enum


class ClassNode(DiagramNode):
    """Class or struct in the class diagram."""

    kind: Literal["class"] = "class"
    module: str = ""  # enclosing namespace/module qualified name
    inherits_from: list[str] = []  # qualified names of parent classes
    realizes: list[str] = []  # qualified names of implemented interfaces
    attributes: list[AttributeNode] = []
    methods: list[MethodNode] = []


class InterfaceNode(DiagramNode):
    """Interface / abstract class in the class diagram."""

    kind: Literal["interface"] = "interface"
    module: str = ""
    methods: list[MethodNode] = []


class EnumNode(DiagramNode):
    """Enum in the class diagram."""

    kind: Literal["enum"] = "enum"
    module: str = ""
    values: list[EnumValueNode] = []


class ModuleNode(DiagramNode):
    """Module / namespace in the class diagram."""

    kind: Literal["module"] = "module"


class Association(BaseModel):
    """A relationship between two top-level entities."""

    subject: str  # qualified name
    predicate: str  # aggregates, references, depends_on, invokes, etc.
    object: str  # qualified name
    mechanism: str = ""  # "std::vector", "std::unique_ptr", etc.
    description: str = ""


class ClassDiagram(BaseModel):
    """Complete class diagram for a query scope.

    Contains all top-level entities and their cross-entity relationships.
    Members (attributes, methods, enum values) are nested inside their parents.
    """

    module_names: list[str] = []
    classes: list[ClassNode] = []
    interfaces: list[InterfaceNode] = []
    enums: list[EnumNode] = []
    associations: list[Association] = []

    _entity_index: dict[str, ClassNode | InterfaceNode | EnumNode | ModuleNode] = PrivateAttr(
        default_factory=dict
    )

    def model_post_init(self, __context) -> None:
        """Build the entity index for fast lookups."""
        self._entity_index = {}
        for cls in self.classes:
            self._entity_index[cls.qualified_name] = cls
        for iface in self.interfaces:
            self._entity_index[iface.qualified_name] = iface
        for enum in self.enums:
            self._entity_index[enum.qualified_name] = enum

    def get_entity(
        self, qualified_name: str
    ) -> ClassNode | InterfaceNode | EnumNode | ModuleNode | None:
        """Look up a top-level entity by qualified name."""
        return self._entity_index.get(qualified_name)

    def associations_for(self, qualified_name: str) -> list[Association]:
        """Return associations where the entity is the subject."""
        return [a for a in self.associations if a.subject == qualified_name]

    def associations_involving(self, qualified_name: str) -> list[Association]:
        """Return associations where the entity is subject or object."""
        return [
            a
            for a in self.associations
            if a.subject == qualified_name or a.object == qualified_name
        ]

    def classes_in_module(self, module: str) -> list[ClassNode]:
        """Return classes belonging to a specific module."""
        return [c for c in self.classes if c.module == module]