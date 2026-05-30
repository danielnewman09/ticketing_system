# Design Data Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a `backend/design_data/` module with typed read models, a Neo4j query repository, and transforms that replace 5+ ad-hoc data reconstruction patterns with a single clean API.

**Architecture:** Read models (`ClassNode`, `InterfaceNode`, `EnumNode`, `Association`, `ClassDiagram`) represent the class diagram layer as stored in Neo4j. A `DesignDataRepository` queries Neo4j and returns hydrated typed objects. Transform functions bridge between `OODesignSchema` (LLM write shape) and `ClassDiagram` (rich read shape). Existing write path (`map_to_ontology` → `persist_design` → Neo4j) is unchanged.

**Tech Stack:** Python 3.12+, Pydantic v2, Neo4j (via existing `neo4j` driver), SQLAlchemy (for component lookups only), pytest

---

## File Structure

```
backend/design_data/
  __init__.py              # Public API exports
  models.py                # DiagramNode, ClassNode, InterfaceNode, EnumNode, etc.
  repository.py            # DesignDataRepository — Neo4j queries → typed models
  transforms.py            # class_diagram_from_oo_design(), oo_design_from_class_diagram()

tests/
  test_design_data_models.py         # Unit tests for models (no Neo4j needed)
  test_design_data_transforms.py     # Unit tests for transforms (no Neo4j needed)
  test_design_data_repository.py     # Integration tests for repository (Neo4j needed)
```

Modified files (later tasks):
- `backend/requirements/services/persistence.py` — Replace `build_verification_context()`
- `backend/ticketing_agent/design/design_per_hlr.py` — Replace `_extract_existing_classes()`, `_extract_intercomponent_context()`, `_build_class_lookup()`
- `backend/ticketing_agent/tools/helpers/draft_state.py` — Replace `build_draft_lookup()`, `draft_summary()`
- `backend/pipeline/orchestrator.py` — Replace `_get_verification_dicts()`, manual `all_oo_classes` construction
- `backend/ticketing_agent/generate_skeleton.py` — Add ClassDiagram acceptance path

---

### Task 1: Create read models

**Files:**
- Create: `backend/design_data/__init__.py`
- Create: `backend/design_data/models.py`
- Create: `tests/test_design_data_models.py`

- [ ] **Step 1: Write failing tests for DiagramNode base model**

```python
# tests/test_design_data_models.py
"""Tests for design_data read models."""

import pytest
from pydantic import ValidationError
from backend.design_data.models import (
    DiagramNode,
    ClassNode,
    InterfaceNode,
    EnumNode,
    ModuleNode,
    AttributeNode,
    MethodNode,
    EnumValueNode,
    Association,
    ClassDiagram,
)


class TestDiagramNode:
    def test_minimal_creation(self):
        node = DiagramNode(
            name="Calculator",
            qualified_name="calc::Calculator",
            kind="class",
            layer="design",
        )
        assert node.name == "Calculator"
        assert node.qualified_name == "calc::Calculator"
        assert node.kind == "class"
        assert node.layer == "design"
        assert node.description == ""
        assert node.visibility == ""
        assert node.implementation_status == "designed"

    def test_all_fields(self):
        node = DiagramNode(
            name="calculate",
            qualified_name="calc::Calculator::calculate",
            kind="method",
            layer="as-built",
            description="Adds two numbers",
            visibility="public",
            specialization="const_method",
            component_id=3,
            is_intercomponent=False,
            type_signature="double(double, double)",
            argsstring="(double x, double y)",
            definition="double Calculator::calculate(double x, double y)",
            source_type="member",
            source="",
            file_path="src/calculator.hpp",
            line_number=42,
            is_static=False,
            is_const=True,
            is_virtual=False,
            is_abstract=False,
            is_final=False,
            implementation_status="implemented",
            source_file="src/calculator.hpp",
            test_file="test/test_calculator.cpp",
        )
        assert node.is_const is True
        assert node.line_number == 42
        assert node.implementation_status == "implemented"

    def test_invalid_layer(self):
        with pytest.raises(ValidationError):
            DiagramNode(
                name="X",
                qualified_name="X",
                kind="class",
                layer="invalid",
            )

    def test_dependency_layer(self):
        node = DiagramNode(
            name="Fl_Button",
            qualified_name="Fl_Button",
            kind="class",
            layer="dependency",
            source="fltk",
        )
        assert node.layer == "dependency"
        assert node.source == "fltk"
```

- [ ] **Step 2: Implement DiagramNode and run tests to verify they pass**

```python
# backend/design_data/__init__.py
"""Design data module — typed read models and query API for class diagram data."""

from backend.design_data.models import (
    Association,
    AttributeNode,
    ClassDiagram,
    ClassNode,
    DiagramNode,
    EnumNode,
    EnumValueNode,
    InterfaceNode,
    MethodNode,
    ModuleNode,
)

__all__ = [
    "Association",
    "AttributeNode",
    "ClassDiagram",
    "ClassNode",
    "DiagramNode",
    "EnumNode",
    "EnumValueNode",
    "InterfaceNode",
    "MethodNode",
    "ModuleNode",
]
```

```python
# backend/design_data/models.py
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
```

Run: `pytest tests/test_design_data_models.py::TestDiagramNode -v`
Expected: All 4 tests PASS.

- [ ] **Step 3: Write failing tests for member and top-level entity models**

```python
# Append to tests/test_design_data_models.py

class TestAttributeNode:
    def test_creation(self):
        attr = AttributeNode(
            name="result_",
            qualified_name="calc::Calculator::result_",
            kind="attribute",
            layer="design",
            owner="calc::Calculator",
            type_signature="double",
            visibility="private",
        )
        assert attr.owner == "calc::Calculator"
        assert attr.type_signature == "double"

class TestMethodNode:
    def test_creation(self):
        method = MethodNode(
            name="add",
            qualified_name="calc::Calculator::add",
            kind="method",
            layer="design",
            owner="calc::Calculator",
            type_signature="double",
            argsstring="(double x, double y)",
            visibility="public",
        )
        assert method.owner == "calc::Calculator"
        assert method.argsstring == "(double x, double y)"

class TestEnumValueNode:
    def test_creation(self):
        val = EnumValueNode(
            name="ADD",
            qualified_name="calc::Operation::ADD",
            kind="enum_value",
            layer="design",
            owner="calc::Operation",
        )
        assert val.owner == "calc::Operation"


class TestClassNode:
    def test_minimal(self):
        cls = ClassNode(
            name="Calculator",
            qualified_name="calc::Calculator",
            kind="class",
            layer="design",
            module="calc",
        )
        assert cls.module == "calc"
        assert cls.attributes == []
        assert cls.methods == []
        assert cls.inherits_from == []
        assert cls.realizes == []

    def test_with_members(self):
        cls = ClassNode(
            name="Calculator",
            qualified_name="calc::Calculator",
            kind="class",
            layer="design",
            module="calc",
            attributes=[
                AttributeNode(
                    name="result_",
                    qualified_name="calc::Calculator::result_",
                    kind="attribute",
                    layer="design",
                    owner="calc::Calculator",
                    type_signature="double",
                    visibility="private",
                ),
            ],
            methods=[
                MethodNode(
                    name="add",
                    qualified_name="calc::Calculator::add",
                    kind="method",
                    layer="design",
                    owner="calc::Calculator",
                    visibility="public",
                ),
            ],
            inherits_from=["calc::ICalculator"],
            realizes=["calc::IProcessor"],
        )
        assert len(cls.attributes) == 1
        assert len(cls.methods) == 1
        assert "calc::ICalculator" in cls.inherits_from

    def test_as_built_class(self):
        cls = ClassNode(
            name="Calculator",
            qualified_name="calc::Calculator",
            kind="class",
            layer="as-built",
            module="calc",
            file_path="src/calculator.hpp",
            line_number=10,
            implementation_status="implemented",
        )
        assert cls.layer == "as-built"
        assert cls.line_number == 10


class TestInterfaceNode:
    def test_creation(self):
        iface = InterfaceNode(
            name="ICalculator",
            qualified_name="calc::ICalculator",
            kind="interface",
            layer="design",
            module="calc",
            is_abstract=True,
            methods=[
                MethodNode(
                    name="add",
                    qualified_name="calc::ICalculator::add",
                    kind="method",
                    layer="design",
                    owner="calc::ICalculator",
                    is_virtual=True,
                ),
            ],
        )
        assert iface.is_abstract is True
        assert len(iface.methods) == 1


class TestEnumNode:
    def test_creation(self):
        enum = EnumNode(
            name="Operation",
            qualified_name="calc::Operation",
            kind="enum",
            layer="design",
            module="calc",
            values=[
                EnumValueNode(
                    name="ADD",
                    qualified_name="calc::Operation::ADD",
                    kind="enum_value",
                    layer="design",
                    owner="calc::Operation",
                ),
            ],
        )
        assert len(enum.values) == 1


class TestModuleNode:
    def test_creation(self):
        mod = ModuleNode(
            name="calc",
            qualified_name="calc",
            kind="module",
            layer="design",
        )
```

- [ ] **Step 4: Implement member and top-level entity models**

```python
# Append to backend/design_data/models.py


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
```

Run: `pytest tests/test_design_data_models.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Write failing tests for Association and ClassDiagram**

```python
# Append to tests/test_design_data_models.py

class TestAssociation:
    def test_minimal(self):
        assoc = Association(
            subject="calc::Calculator",
            predicate="aggregates",
            object="calc::Result",
        )
        assert assoc.subject == "calc::Calculator"
        assert assoc.predicate == "aggregates"
        assert assoc.mechanism == ""
        assert assoc.description == ""

    def test_with_mechanism(self):
        assoc = Association(
            subject="calc::Calculator",
            predicate="references",
            object="calc::Result",
            mechanism="std::unique_ptr",
            description="Calculator holds a unique_ptr to Result",
        )
        assert assoc.mechanism == "std::unique_ptr"


class TestClassDiagram:
    def test_minimal(self):
        diagram = ClassDiagram()
        assert diagram.classes == []
        assert diagram.interfaces == []
        assert diagram.enums == []
        assert diagram.associations == []

    def test_with_entities(self):
        diagram = ClassDiagram(
            module_names=["calc"],
            classes=[
                ClassNode(
                    name="Calculator",
                    qualified_name="calc::Calculator",
                    kind="class",
                    layer="design",
                    module="calc",
                ),
            ],
            interfaces=[
                InterfaceNode(
                    name="ICalculator",
                    qualified_name="calc::ICalculator",
                    kind="interface",
                    layer="design",
                    module="calc",
                ),
            ],
            enums=[
                EnumNode(
                    name="Operation",
                    qualified_name="calc::Operation",
                    kind="enum",
                    layer="design",
                    module="calc",
                ),
            ],
            associations=[
                Association(
                    subject="calc::Calculator",
                    predicate="realizes",
                    object="calc::ICalculator",
                ),
            ],
        )
        assert len(diagram.classes) == 1
        assert len(diagram.interfaces) == 1
        assert len(diagram.enums) == 1
        assert len(diagram.associations) == 1

    def test_get_entity(self):
        calc = ClassNode(
            name="Calculator",
            qualified_name="calc::Calculator",
            kind="class",
            layer="design",
            module="calc",
        )
        iface = InterfaceNode(
            name="ICalculator",
            qualified_name="calc::ICalculator",
            kind="interface",
            layer="design",
            module="calc",
        )
        diagram = ClassDiagram(
            classes=[calc],
            interfaces=[iface],
        )
        assert diagram.get_entity("calc::Calculator") is calc
        assert diagram.get_entity("calc::ICalculator") is iface
        assert diagram.get_entity("nonexistent") is None

    def test_associations_for(self):
        diagram = ClassDiagram(
            classes=[
                ClassNode(name="A", qualified_name="ns::A", kind="class", layer="design", module="ns"),
                ClassNode(name="B", qualified_name="ns::B", kind="class", layer="design", module="ns"),
            ],
            associations=[
                Association(subject="ns::A", predicate="depends_on", object="ns::B"),
                Association(subject="ns::A", predicate="aggregates", object="ns::C"),
                Association(subject="ns::B", predicate="references", object="ns::A"),
            ],
        )
        a_assocs = diagram.associations_for("ns::A")
        assert len(a_assocs) == 2
        predicates = {a.predicate for a in a_assocs}
        assert predicates == {"depends_on", "aggregates"}

    def test_associations_involving(self):
        diagram = ClassDiagram(
            associations=[
                Association(subject="ns::A", predicate="depends_on", object="ns::B"),
                Association(subject="ns::B", predicate="references", object="ns::A"),
                Association(subject="ns::C", predicate="aggregates", object="ns::D"),
            ],
        )
        a_involving = diagram.associations_involving("ns::A")
        assert len(a_involving) == 2

    def test_classes_in_module(self):
        diagram = ClassDiagram(
            classes=[
                ClassNode(name="A", qualified_name="calc::A", kind="class", layer="design", module="calc"),
                ClassNode(name="B", qualified_name="calc::B", kind="class", layer="design", module="calc"),
                ClassNode(name="C", qualified_name="ui::Window", kind="class", layer="design", module="ui"),
            ],
        )
        calc_classes = diagram.classes_in_module("calc")
        assert len(calc_classes) == 2
        assert all(c.module == "calc" for c in calc_classes)
```

- [ ] **Step 6: Implement Association, ClassDiagram, and convenience methods**

```python
# Append to backend/design_data/models.py


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
```

Run: `pytest tests/test_design_data_models.py -v`
Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/design_data/__init__.py backend/design_data/models.py tests/test_design_data_models.py
git commit -m "feat: add design_data read models (ClassNode, InterfaceNode, EnumNode, ClassDiagram)"
```

---

### Task 2: Create transforms between OODesignSchema and ClassDiagram

**Files:**
- Create: `backend/design_data/transforms.py`
- Create: `tests/test_design_data_transforms.py`

- [ ] **Step 1: Write failing tests for class_diagram_from_oo_design**

```python
# tests/test_design_data_transforms.py
"""Tests for design_data transforms."""

from backend.codebase.schemas import (
    AssociationSchema,
    AttributeSchema,
    ClassSchema,
    EnumSchema,
    InterfaceSchema,
    MethodSchema,
    OODesignSchema,
)
from backend.design_data.transforms import class_diagram_from_oo_design, oo_design_from_class_diagram


def _sample_oo_design():
    return OODesignSchema(
        modules=["calc"],
        classes=[
            ClassSchema(
                name="Calculator",
                module="calc",
                description="Main calculator class",
                visibility="public",
                is_intercomponent=False,
                requirement_ids=["hlr:1"],
                attributes=[
                    AttributeSchema(
                        name="result_",
                        type_name="double",
                        visibility="private",
                        description="Last result",
                    ),
                ],
                methods=[
                    MethodSchema(
                        name="add",
                        visibility="public",
                        description="Add two numbers",
                        parameters=["double x", "double y"],
                        return_type="double",
                    ),
                ],
                inherits_from=["ICalculator"],
                realizes_interfaces=[],
            ),
        ],
        interfaces=[
            InterfaceSchema(
                name="ICalculator",
                module="calc",
                description="Calculator interface",
                is_intercomponent=False,
                methods=[
                    MethodSchema(
                        name="add",
                        visibility="public",
                        description="Add two numbers",
                        parameters=[],
                        return_type="double",
                    ),
                ],
            ),
        ],
        enums=[
            EnumSchema(
                name="Operation",
                module="calc",
                description="Supported operations",
                values=["ADD", "SUBTRACT"],
            ),
        ],
        associations=[
            AssociationSchema(
                from_class="Calculator",
                to_class="Result",
                kind="aggregates",
                description="Calculator aggregates results",
                mechanism="std::vector",
            ),
        ],
    )


class TestClassDiagramFromOODesign:
    def test_classes_preserved(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo)
        assert len(diagram.classes) == 1
        assert diagram.classes[0].name == "Calculator"
        assert diagram.classes[0].qualified_name == "calc::Calculator"

    def test_class_attributes(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo)
        assert len(diagram.classes[0].attributes) == 1
        assert diagram.classes[0].attributes[0].name == "result_"
        assert diagram.classes[0].attributes[0].type_signature == "double"

    def test_class_methods(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo)
        assert len(diagram.classes[0].methods) == 1
        assert diagram.classes[0].methods[0].name == "add"

    def test_class_inherits_from(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo)
        assert "ICalculator" in diagram.classes[0].inherits_from

    def test_interfaces_preserved(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo)
        assert len(diagram.interfaces) == 1
        assert diagram.interfaces[0].name == "ICalculator"

    def test_enums_preserved(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo)
        assert len(diagram.enums) == 1
        assert diagram.enums[0].name == "Operation"
        assert len(diagram.enums[0].values) == 2

    def test_associations_preserved(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo)
        assert len(diagram.associations) == 1
        assert diagram.associations[0].predicate == "aggregates"
        assert diagram.associations[0].mechanism == "std::vector"

    def test_layer_is_design(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo)
        assert diagram.classes[0].layer == "design"

    def test_component_id_propagated(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo, component_id=5)
        assert diagram.classes[0].component_id == 5

    def test_modules_extracted(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo)
        assert "calc" in diagram.module_names

    def test_owner_set_on_members(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo)
        assert diagram.classes[0].attributes[0].owner == "calc::Calculator"
        assert diagram.classes[0].methods[0].owner == "calc::Calculator"
```

- [ ] **Step 2: Implement class_diagram_from_oo_design**

```python
# backend/design_data/transforms.py
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
            visibility=cls.visibility or "public",
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
```

Run: `pytest tests/test_design_data_transforms.py -v`
Expected: All tests PASS.

- [ ] **Step 3: Update __init__.py with transforms**

```python
# backend/design_data/__init__.py — update to include transforms
"""Design data module — typed read models and query API for class diagram data."""

from backend.design_data.models import (
    Association,
    AttributeNode,
    ClassDiagram,
    ClassNode,
    DiagramNode,
    EnumNode,
    EnumValueNode,
    InterfaceNode,
    MethodNode,
    ModuleNode,
)
from backend.design_data.transforms import (
    class_diagram_from_oo_design,
    oo_design_from_class_diagram,
)

__all__ = [
    "Association",
    "AttributeNode",
    "ClassDiagram",
    "ClassNode",
    "DiagramNode",
    "EnumNode",
    "EnumValueNode",
    "InterfaceNode",
    "MethodNode",
    "ModuleNode",
    "class_diagram_from_oo_design",
    "oo_design_from_class_diagram",
]
```

Run: `pytest tests/test_design_data_transforms.py -v`
Expected: All tests still PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/design_data/transforms.py backend/design_data/__init__.py tests/test_design_data_transforms.py
git commit -m "feat: add design_data transforms (class_diagram_from_oo_design, oo_design_from_class_diagram)"
```

---

### Task 3: Create DesignDataRepository

**Files:**
- Create: `backend/design_data/repository.py`
- Create: `tests/test_design_data_repository.py`

This is a Neo4j integration task. The repository queries Neo4j and returns typed model objects.

- [ ] **Step 1: Write the repository module**

The full `DesignDataRepository` implementation is in `backend/design_data/repository.py`. This is a large file (see the spec for complete code). Key methods:

- `get_class_diagram(component_id, layer)` — full diagram query
- `get_hlr_subgraph(hlr_id, component_id)` — HLR-scoped diagram
- `get_class(qualified_name)` — single class with hydrated members
- `get_interface(qualified_name)` — single interface
- `get_enum(qualified_name)` — single enum
- `get_classes_for_component(component_id)` — prompt helper
- `get_public_api(component_id)` — intercomponent context helper

- [ ] **Step 2: Write integration tests for the repository**

Tests use the `RUN_NEO4J_INTEGRATION=1` pattern from `test_verification_repository.py`. Key test cases:

- `test_get_existing_class` — fetch a seeded class and verify name, qname, module
- `test_get_class_with_members` — verify hydrated attributes and methods
- `test_get_nonexistent_class` — returns None
- `test_get_class_diagram_by_component` — returns seeded classes

- [ ] **Step 3: Run unit tests (no Neo4j required)**

Run: `pytest tests/test_design_data_models.py tests/test_design_data_transforms.py -v`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/design_data/repository.py tests/test_design_data_repository.py
git commit -m "feat: add DesignDataRepository with Neo4j query methods"
```

---

### Task 4: Add to_verification_dicts and to_draft_lookup to ClassDiagram

**Files:**
- Modify: `backend/design_data/models.py`

- [ ] **Step 1: Add `to_verification_dicts()` method to ClassDiagram**

See spec for complete code. Produces a list of dicts compatible with `build_verification_context()` output format. Each dict has `qualified_name`, `kind`, `description`, `attributes`, `methods`, `relationships`.

- [ ] **Step 2: Add `to_draft_lookup()` method to ClassDiagram**

Produces `dict[str, dict]` mapping qualified_name → `{qualified_name, kind, description, source: 'draft'}` for all classes, interfaces, enums, and their members. Compatible with `build_draft_lookup()` output.

- [ ] **Step 3: Write tests for both methods**

- `TestClassDiagramToVerificationDicts` — verify class context dict structure, relationships inclusion
- `TestClassDiagramToDraftLookup` — verify lookup dict structure with classes, attributes, methods, enums

- [ ] **Step 4: Add `build_verification_context_from_diagram()` to persistence.py**

New function that uses `DesignDataRepository.get_class_diagram()` + `diagram.to_verification_dicts()`. Marks the existing `build_verification_context()` as having a replacement path without removing it yet.

- [ ] **Step 5: Commit**

```bash
git add backend/design_data/models.py backend/requirements/services/persistence.py tests/test_design_data_models.py
git commit -m "feat: add to_verification_dicts and to_draft_lookup to ClassDiagram, add build_verification_context_from_diagram"
```

---

### Task 5: Replace `_build_class_lookup` in design_per_hlr with design_data module

**Files:**
- Modify: `backend/ticketing_agent/design/design_per_hlr.py`

- [ ] **Step 1: Add import and replace `_build_class_lookup` call**

In the `design_all_hlrs()` function, replace:
```python
accumulated_class_lookup.update(_build_class_lookup(oo))
```
With:
```python
from backend.design_data import class_diagram_from_oo_design
...
prev_diagram = class_diagram_from_oo_design(oo, component_id=component_id)
for cls in prev_diagram.classes:
    accumulated_class_lookup[cls.name] = cls.qualified_name
for iface in prev_diagram.interfaces:
    accumulated_class_lookup[iface.name] = iface.qualified_name
for enum in prev_diagram.enums:
    accumulated_class_lookup[enum.name] = enum.qualified_name
```

- [ ] **Step 2: Mark `_extract_existing_classes` and `_extract_intercomponent_context` as deprecated**

Add `# TODO: Replace with design_data module once prompt builders accept ClassNode directly` comments.

- [ ] **Step 3: Run existing tests**

Run: `pytest tests/ -k "design" -v --ignore=tests/test_design_data_repository.py`
Expected: All existing tests still PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/ticketing_agent/design/design_per_hlr.py
git commit -m "refactor: replace _build_class_lookup with design_data module, mark _extract_existing_classes as deprecated"
```

---

### Task 6: Replace `build_draft_lookup` and `draft_summary` in draft_state.py

**Files:**
- Modify: `backend/ticketing_agent/tools/helpers/draft_state.py`

- [ ] **Step 1: Update `build_draft_lookup` to use `class_diagram_from_oo_design` + `diagram.to_draft_lookup()`**

```python
from backend.design_data import class_diagram_from_oo_design

def build_draft_lookup(design: OODesignSchema) -> dict[str, dict]:
    """Build a lookup dict from a draft OODesignSchema."""
    diagram = class_diagram_from_oo_design(design)
    return diagram.to_draft_lookup()
```

- [ ] **Step 2: Update `draft_summary` to use `class_diagram_from_oo_design`**

```python
def draft_summary(design: OODesignSchema) -> dict:
    """Return a summary dict of the draft design for tool responses."""
    diagram = class_diagram_from_oo_design(design)
    total_attrs = sum(len(c.attributes) for c in diagram.classes)
    total_methods = sum(len(c.methods) for c in diagram.classes)
    return {
        "classes": len(diagram.classes),
        "interfaces": len(diagram.interfaces),
        "enums": len(diagram.enums),
        "associations": len(diagram.associations),
        "attributes": total_attrs,
        "methods": total_methods,
    }
```

- [ ] **Step 3: Run existing tests**

Run: `pytest tests/test_design_oo_tools.py tests/test_combined_tools.py -v`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/ticketing_agent/tools/helpers/draft_state.py
git commit -m "refactor: replace build_draft_lookup and draft_summary with design_data module"
```

---

### Task 7: Integration and smoke testing

- [ ] **Step 1: Run the full model test suite**

Run: `pytest tests/test_design_data_models.py tests/test_design_data_transforms.py -v`
Expected: All PASS.

- [ ] **Step 2: Run existing tests to ensure no regressions**

Run: `pytest tests/ -v --ignore=tests/test_design_data_repository.py --ignore=tests/integration -x`
Expected: All existing tests still PASS.

- [ ] **Step 3: Verify imports work**

Run: `python -c "from backend.design_data import ClassDiagram, ClassNode, Association, class_diagram_from_oo_design, oo_design_from_class_diagram, DesignDataRepository; print('All imports OK')"`
Expected: "All imports OK"

- [ ] **Step 4: Commit any remaining changes**

```bash
git add -A
git commit -m "chore: verify design_data module integration, all tests passing"
```