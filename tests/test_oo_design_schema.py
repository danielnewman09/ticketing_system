"""
Test that ClassDiagram correctly represents the hlr2 calculator design.

The expected data is derived from the reasoner output in:
    logs/prompts/step3b_design_oo_hlr2_reasoner_response.md

The formatter_response.json for the same run dropped all attributes and
methods — this test documents the correct representation to prove the
schema supports it.
"""

import pytest

from codegraph.designs import (
    Association,
    AttributeNode,
    ClassDiagram,
    ClassNode,
    EnumNode,
    EnumValueNode,
    MethodNode,
)

# ---------------------------------------------------------------------------
# Fixture: the full hlr2 design as the reasoner described it
# ---------------------------------------------------------------------------


@pytest.fixture()
def hlr2_design():
    """Build the ClassDiagram that matches the hlr2 reasoner output."""
    return ClassDiagram(
        module_names=["calc::engine"],
        classes=[
            ClassNode(
                name="Calculator",
                module="calc::engine",
                specialization="class",
                description=(
                    "Core calculation engine performing arithmetic operations "
                    "with error handling and state maintenance for recovery."
                ),
                attributes=[
                    AttributeNode(
                        name="current_result",
                        type_signature="double",
                        visibility="private",
                        description="Stores the last computed result or zero if no valid operation completed.",
                    ),
                    AttributeNode(
                        name="status",
                        type_signature="Status",
                        visibility="private",
                        description="Tracks the current error state or success status of the engine.",
                    ),
                ],
                methods=[
                    MethodNode(
                        name="add",
                        visibility="public",
                        argsstring="(operand1, operand2)",
                        type_signature="CalculationResult",
                        description="Computes sum of operands; returns error indicator if inputs are invalid.",
                    ),
                    MethodNode(
                        name="subtract",
                        visibility="public",
                        argsstring="(operand1, operand2)",
                        type_signature="CalculationResult",
                        description="Computes difference of operands; returns error indicator if inputs are invalid.",
                    ),
                    MethodNode(
                        name="multiply",
                        visibility="public",
                        argsstring="(operand1, operand2)",
                        type_signature="CalculationResult",
                        description="Computes product of operands; returns error indicator if inputs are invalid.",
                    ),
                    MethodNode(
                        name="divide",
                        visibility="public",
                        argsstring="(operand1, operand2)",
                        type_signature="CalculationResult",
                        description="Computes quotient; returns error indicator for division by zero or invalid inputs.",
                    ),
                    MethodNode(
                        name="getStatus",
                        visibility="public",
                        argsstring="()",
                        type_signature="Status",
                        description="Retrieves the current internal status for error recovery verification.",
                    ),
                ],
                inherits_from=[],
                realizes=[],
                requirement_ids=[
                    "hlr:2",
                    "llr:9",
                    "llr:10",
                    "llr:11",
                    "llr:12",
                    "llr:13",
                    "llr:14",
                    "llr:15",
                ],
            ),
            ClassNode(
                name="CalculationResult",
                module="calc::engine",
                specialization="class",
                description=(
                    "Encapsulates the outcome of a calculation including the "
                    "numeric value and associated status indicator."
                ),
                attributes=[
                    AttributeNode(
                        name="value",
                        type_signature="double",
                        visibility="private",
                        description="The numeric result of the operation if successful.",
                    ),
                    AttributeNode(
                        name="status",
                        type_signature="Status",
                        visibility="private",
                        description="The error indicator or success code returned by the operation.",
                    ),
                ],
                methods=[
                    MethodNode(
                        name="getValue",
                        visibility="public",
                        argsstring="()",
                        type_signature="double",
                        description="Returns the numeric value if status is valid, otherwise returns default.",
                    ),
                    MethodNode(
                        name="getStatus",
                        visibility="public",
                        argsstring="()",
                        type_signature="Status",
                        description="Returns the status indicator.",
                    ),
                ],
                inherits_from=[],
                realizes=[],
                requirement_ids=["hlr:2", "llr:13", "llr:14"],
            ),
        ],
        interfaces=[],
        enums=[
            EnumNode(
                name="Status",
                module="calc::engine",
                description="Defines valid calculation outcomes and error indicators.",
                values=[
                    EnumValueNode(name="OK", qualified_name="calc::engine::Status::OK"),
                    EnumValueNode(name="INVALID_INPUT", qualified_name="calc::engine::Status::INVALID_INPUT"),
                    EnumValueNode(name="DIVISION_BY_ZERO", qualified_name="calc::engine::Status::DIVISION_BY_ZERO"),
                ],
            ),
            EnumNode(
                name="Operation",
                module="calc::engine",
                description="Defines supported arithmetic operations for the engine.",
                values=[
                    EnumValueNode(name="ADD", qualified_name="calc::engine::Operation::ADD"),
                    EnumValueNode(name="SUBTRACT", qualified_name="calc::engine::Operation::SUBTRACT"),
                    EnumValueNode(name="MULTIPLY", qualified_name="calc::engine::Operation::MULTIPLY"),
                    EnumValueNode(name="DIVIDE", qualified_name="calc::engine::Operation::DIVIDE"),
                ],
            ),
        ],
        associations=[
            Association(
                subject="Calculator",
                object="Status",
                predicate="depends_on",
                description="Used to maintain internal state and return error indicators",
                requirement_ids=["hlr:2", "llr:13", "llr:14", "llr:15"],
            ),
            Association(
                subject="Calculator",
                object="Operation",
                predicate="depends_on",
                description="Used internally to select arithmetic logic",
                requirement_ids=["hlr:2", "llr:9", "llr:10", "llr:11", "llr:12"],
            ),
            Association(
                subject="Calculator",
                object="CalculationResult",
                predicate="associates",
                description="Produces and returns calculation results",
                requirement_ids=["hlr:2", "llr:13", "llr:14", "llr:15"],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Tests: schema can represent the full design
# ---------------------------------------------------------------------------


class TestClassDiagramHLR2:
    """Verify ClassDiagram faithfully holds the hlr2 calculator design."""

    def test_modules(self, hlr2_design):
        assert hlr2_design.module_names == ["calc::engine"]

    def test_class_count(self, hlr2_design):
        assert len(hlr2_design.classes) == 2

    def test_calculator_attributes(self, hlr2_design):
        calc = hlr2_design.classes[0]
        assert calc.name == "Calculator"
        assert len(calc.attributes) == 2
        attr_names = {a.name for a in calc.attributes}
        assert attr_names == {"current_result", "status"}

    def test_calculator_attribute_visibility(self, hlr2_design):
        calc = hlr2_design.classes[0]
        for attr in calc.attributes:
            assert attr.visibility == "private"

    def test_calculator_methods(self, hlr2_design):
        calc = hlr2_design.classes[0]
        assert len(calc.methods) == 5
        method_names = {m.name for m in calc.methods}
        assert method_names == {"add", "subtract", "multiply", "divide", "getStatus"}

    def test_calculator_method_visibility(self, hlr2_design):
        calc = hlr2_design.classes[0]
        for method in calc.methods:
            assert method.visibility == "public"

    def test_calculator_method_parameters(self, hlr2_design):
        calc = hlr2_design.classes[0]
        add = next(m for m in calc.methods if m.name == "add")
        assert add.argsstring == "(operand1, operand2)"
        assert add.type_signature == "CalculationResult"

    def test_calculation_result_attributes(self, hlr2_design):
        result_cls = hlr2_design.classes[1]
        assert result_cls.name == "CalculationResult"
        assert len(result_cls.attributes) == 2
        attr_names = {a.name for a in result_cls.attributes}
        assert attr_names == {"value", "status"}

    def test_calculation_result_methods(self, hlr2_design):
        result_cls = hlr2_design.classes[1]
        assert len(result_cls.methods) == 2
        method_names = {m.name for m in result_cls.methods}
        assert method_names == {"getValue", "getStatus"}

    def test_enum_count(self, hlr2_design):
        assert len(hlr2_design.enums) == 2
        enum_names = {e.name for e in hlr2_design.enums}
        assert enum_names == {"Status", "Operation"}

    def test_association_count(self, hlr2_design):
        assert len(hlr2_design.associations) == 3

    def test_requirement_ids_on_calculator(self, hlr2_design):
        calc = hlr2_design.classes[0]
        assert "hlr:2" in calc.requirement_ids
        assert "llr:9" in calc.requirement_ids
        assert "llr:14" in calc.requirement_ids

    # --- Round-trip: model_dump / model_validate ---

    def test_round_trip_preserves_attributes_and_methods(self, hlr2_design):
        """Serialize to dict and back — attributes/methods must survive."""
        data = hlr2_design.model_dump()
        restored = ClassDiagram.model_validate(data)

        for orig, rest in zip(hlr2_design.classes, restored.classes):
            assert len(rest.attributes) == len(
                orig.attributes
            ), f"Class {orig.name}: attributes lost in round-trip"
            assert len(rest.methods) == len(
                orig.methods
            ), f"Class {orig.name}: methods lost in round-trip"

    def test_json_round_trip(self, hlr2_design):
        """Serialize to JSON string and back — nested arrays must survive."""
        json_str = hlr2_design.model_dump_json()
        restored = ClassDiagram.model_validate_json(json_str)

        calc = restored.classes[0]
        assert len(calc.attributes) == 2, "Attributes lost in JSON round-trip"
        assert len(calc.methods) == 5, "Methods lost in JSON round-trip"

    # --- Demonstrate the formatter bug ---

    def test_formatter_output_missing_attributes_and_methods(self):
        """Reproduce the actual formatter output from hlr2 — shows the bug.

        The formatter returned classes with no attributes or methods arrays.
        ClassDiagram accepts this (they default to []) but it represents
        a data loss compared to the reasoner output.
        """
        formatter_output = {
            "module_names": ["calc::engine"],
            "classes": [
                {
                    "name": "Calculator",
                    "module": "calc::engine",
                    "specialization": "class",
                    "description": "Core calculation engine performing arithmetic operations with error handling and state maintenance for recovery.",
                    "inherits_from": [],
                    "realizes": [],
                    "requirement_ids": [
                        "hlr:2",
                        "llr:9",
                        "llr:10",
                        "llr:11",
                        "llr:12",
                        "llr:13",
                        "llr:14",
                        "llr:15",
                    ],
                },
                {
                    "name": "CalculationResult",
                    "module": "calc::engine",
                    "specialization": "class",
                    "description": "Encapsulates the outcome of a calculation including the numeric value and associated status indicator.",
                    "inherits_from": [],
                    "realizes": [],
                    "requirement_ids": ["hlr:2", "llr:13", "llr:14"],
                },
            ],
            "interfaces": [],
            "enums": [
                {
                    "name": "Status",
                    "module": "calc::engine",
                    "description": "Defines valid calculation outcomes and error indicators.",
                    "values": [
                        {"name": "OK", "qualified_name": "calc::engine::Status::OK"},
                        {"name": "INVALID_INPUT", "qualified_name": "calc::engine::Status::INVALID_INPUT"},
                        {"name": "DIVISION_BY_ZERO", "qualified_name": "calc::engine::Status::DIVISION_BY_ZERO"},
                    ],
                },
                {
                    "name": "Operation",
                    "module": "calc::engine",
                    "description": "Defines supported arithmetic operations for the engine.",
                    "values": [
                        {"name": "ADD", "qualified_name": "calc::engine::Operation::ADD"},
                        {"name": "SUBTRACT", "qualified_name": "calc::engine::Operation::SUBTRACT"},
                        {"name": "MULTIPLY", "qualified_name": "calc::engine::Operation::MULTIPLY"},
                        {"name": "DIVIDE", "qualified_name": "calc::engine::Operation::DIVIDE"},
                    ],
                },
            ],
            "associations": [
                {
                    "from_class": "Calculator",
                    "to_class": "Status",
                    "kind": "depends_on",
                    "description": "Used to maintain internal state and return error indicators",
                    "requirement_ids": ["hlr:2", "llr:13", "llr:14", "llr:15"],
                },
                {
                    "from_class": "Calculator",
                    "to_class": "Operation",
                    "kind": "depends_on",
                    "description": "Used internally to select arithmetic logic",
                    "requirement_ids": ["hlr:2", "llr:9", "llr:10", "llr:11", "llr:12"],
                },
                {
                    "from_class": "Calculator",
                    "to_class": "CalculationResult",
                    "kind": "associates",
                    "description": "Produces and returns calculation results",
                    "requirement_ids": ["hlr:2", "llr:13", "llr:14", "llr:15"],
                },
            ],
        }

        schema = ClassDiagram.model_validate(formatter_output)

        # The formatter bug: classes have no attributes or methods
        calc = schema.classes[0]
        assert calc.attributes == [], "Formatter produced no attributes (this is the bug)"
        assert calc.methods == [], "Formatter produced no methods (this is the bug)"

        result_cls = schema.classes[1]
        assert result_cls.attributes == [], "Formatter produced no attributes (this is the bug)"
        assert result_cls.methods == [], "Formatter produced no methods (this is the bug)"
