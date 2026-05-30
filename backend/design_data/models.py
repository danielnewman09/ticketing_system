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

    def to_verification_dicts(self) -> list[dict]:
        """Produce verification context dicts compatible with build_verification_context().

        Each dict has: qualified_name, kind, description, attributes, methods,
        relationships.
        """
        results = []

        for cls in self.classes:
            attrs = [
                {
                    "name": attr.name,
                    "qualified_name": attr.qualified_name,
                    "kind": "attribute",
                    "visibility": attr.visibility,
                    "type_signature": attr.type_signature,
                    "description": attr.description,
                }
                for attr in cls.attributes
            ]
            methods = [
                {
                    "name": method.name,
                    "qualified_name": method.qualified_name,
                    "kind": "method",
                    "visibility": method.visibility,
                    "type_signature": method.type_signature,
                    "argsstring": method.argsstring,
                    "description": method.description,
                }
                for method in cls.methods
            ]
            relationships = [
                {
                    "predicate": assoc.predicate,
                    "target": assoc.object,
                    "target_name": assoc.object.rsplit("::", 1)[-1],
                }
                for assoc in self.associations
                if assoc.subject == cls.qualified_name
            ]
            results.append({
                "qualified_name": cls.qualified_name,
                "kind": cls.specialization or cls.kind,
                "description": cls.description,
                "attributes": sorted(attrs, key=lambda a: a["name"]),
                "methods": sorted(methods, key=lambda m: m["name"]),
                "relationships": relationships,
            })

        for iface in self.interfaces:
            methods = [
                {
                    "name": method.name,
                    "qualified_name": method.qualified_name,
                    "kind": "method",
                    "visibility": method.visibility,
                    "type_signature": method.type_signature,
                    "argsstring": method.argsstring,
                    "description": method.description,
                }
                for method in iface.methods
            ]
            results.append({
                "qualified_name": iface.qualified_name,
                "kind": iface.kind,
                "description": iface.description,
                "attributes": [],
                "methods": sorted(methods, key=lambda m: m["name"]),
                "relationships": [],
            })

        return sorted(results, key=lambda c: c["qualified_name"])

    def to_draft_lookup(self) -> dict[str, dict]:
        """Produce a lookup dict for draft design state.

        Returns qualified_name -> {qualified_name, kind, description, source: 'draft'}
        for all classes, interfaces, enums, their attributes, and methods.
        """
        lookup: dict[str, dict] = {}

        for cls in self.classes:
            lookup[cls.qualified_name] = {
                "qualified_name": cls.qualified_name,
                "kind": "class",
                "description": cls.description,
                "source": "draft",
            }
            for attr in cls.attributes:
                lookup[attr.qualified_name] = {
                    "qualified_name": attr.qualified_name,
                    "kind": "attribute",
                    "description": attr.description,
                    "source": "draft",
                }
            for method in cls.methods:
                lookup[method.qualified_name] = {
                    "qualified_name": method.qualified_name,
                    "kind": "method",
                    "description": method.description,
                    "source": "draft",
                }

        for iface in self.interfaces:
            lookup[iface.qualified_name] = {
                "qualified_name": iface.qualified_name,
                "kind": "interface",
                "description": iface.description,
                "source": "draft",
            }
            for method in iface.methods:
                lookup[method.qualified_name] = {
                    "qualified_name": method.qualified_name,
                    "kind": "method",
                    "description": method.description,
                    "source": "draft",
                }

        for enum in self.enums:
            lookup[enum.qualified_name] = {
                "qualified_name": enum.qualified_name,
                "kind": "enum",
                "description": enum.description,
                "source": "draft",
            }

        return lookup

    def to_summary(self) -> dict:
        """Return a summary dict of this diagram for tool responses.

        Returns counts of all top-level entities, attributes, and methods.
        """
        total_attrs = sum(len(c.attributes) for c in self.classes)
        total_methods = sum(len(c.methods) for c in self.classes)
        return {
            "classes": len(self.classes),
            "interfaces": len(self.interfaces),
            "enums": len(self.enums),
            "associations": len(self.associations),
            "attributes": total_attrs,
            "methods": total_methods,
        }