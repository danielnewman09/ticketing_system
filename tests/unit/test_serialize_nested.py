"""Unit tests for serialize(nested=True) on requirement node models.

Verifies that calling ``serialize(fields="all", nested=True)`` on HLR, LLR,
and TestNode nodes produces properly nested dictionaries where
COMPOSES children are inlined under a ``composes`` key.

Each test persists its serialized output to ``unit_test_data/`` as a JSON
file for visual debugging.  That directory is gitignored.
"""

import json
import os
import pytest
from unittest.mock import MagicMock, patch

from codegraph_project.models import Component, Dependency, Language, ProjectMeta
from codegraph_requirements.models import HLR, LLR
from codegraph.models.test import TestNode, AssertionNode, TestStepNode
from backend_migrated.models.verification import get_typed_edge_targets


DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "unit_test_data")


def _dump(name: str, data: dict) -> None:
    """Write serialised data to ``unit_test_data/<name>.json`` for inspection."""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"{name}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


class TestHLRSerializeNested:
    """HLR.serialize(fields="all", nested=True) should include llrs under composes."""

    @patch.object(HLR, "nodes")
    def test_hlr_with_no_llrs(self, mock_nodes):
        hlr = HLR(description="Test HLR", tags=["design"])
        hlr.refid = "test-hlr-1"
        hlr.element_id_property = "123"

        hlr.llrs = MagicMock()
        hlr.llrs.all.return_value = []
        hlr.component = MagicMock()
        hlr.component.all.return_value = []

        result = hlr.serialize(fields="all", nested=True)
        _dump("hlr_no_llrs", result)

        assert result["type"] == "HLR"
        assert result["description"] == "Test HLR"
        assert result["layer"] == "design"
        assert "composes" not in result or result.get("composes") == []

    @patch.object(LLR, "nodes")
    def test_hlr_with_llrs(self, mock_llr_nodes):
        hlr = HLR(description="Test HLR", tags=["design"])
        hlr.refid = "test-hlr-1"
        hlr.element_id_property = "123"

        llr = LLR(description="Test LLR", tags=["design"])
        llr.refid = "test-llr-1"
        llr.element_id_property = "456"

        llr.verification_methods = MagicMock()
        llr.verification_methods.all.return_value = []
        llr.hlr = MagicMock()
        llr.hlr.all.return_value = []

        hlr.llrs = MagicMock()
        hlr.llrs.all.return_value = [llr]
        hlr.component = MagicMock()
        hlr.component.all.return_value = []

        result = hlr.serialize(fields="all", nested=True)
        _dump("hlr_with_llrs", result)

        assert result["type"] == "HLR"
        assert "composes" in result
        assert len(result["composes"]) == 1

        child = result["composes"][0]
        assert child["type"] == "LLR"
        assert child["description"] == "Test LLR"


class TestLLRSerializeNested:
    """LLR.serialize(fields="all", nested=True) should include verification methods under composes."""

    @patch.object(LLR, "nodes")
    def test_llr_with_verification_methods(self, mock_nodes):
        llr = LLR(description="Test LLR", tags=["design"])
        llr.refid = "test-llr-1"
        llr.element_id_property = "456"

        vm = TestNode(method="automated", test_name="test_something", description="Verify something works", tags=["design"])
        vm.uid = "test-vm-1"
        vm.element_id_property = "789"

        vm.assertions = MagicMock()
        vm.assertions.all.return_value = []
        vm.steps = MagicMock()
        vm.steps.all.return_value = []
        vm.llr = MagicMock()
        vm.llr.all.return_value = []

        llr.verification_methods = MagicMock()
        llr.verification_methods.all.return_value = [vm]
        llr.hlr = MagicMock()
        llr.hlr.all.return_value = []

        result = llr.serialize(fields="all", nested=True)
        _dump("llr_with_vm", result)

        assert result["type"] == "LLR"
        assert "composes" in result
        assert len(result["composes"]) == 1

        child = result["composes"][0]
        assert child["type"] == "TestNode"
        assert child["method"] == "automated"
        assert child["test_name"] == "test_something"

    @patch.object(LLR, "nodes")
    def test_llr_with_deeply_nested_verification(self, mock_nodes):
        """VM → Condition and VM → Action should appear in nested serialize."""
        llr = LLR(description="Test LLR", tags=["design"])
        llr.refid = "test-llr-1"
        llr.element_id_property = "456"

        vm = TestNode(method="automated", test_name="test_deep", description="Deep nested test", tags=["design"])
        vm.refid = "test-vm-1"
        vm.element_id_property = "789"

        cond = AssertionNode(phase="pre", order=0, operator="==", expected_value="null", subject_qualified_name="Engine.is_initialized", tags=["design"])
        cond.refid = "test-cond-1"
        cond.element_id_property = "100"

        act = TestStepNode(order=0, description="Invoke the add operation", callee_qualified_name="Engine.add", tags=["design"])
        act.refid = "test-act-1"
        act.element_id_property = "200"

        # Mock leaf nodes' relationship managers
        cond.left_operand = MagicMock()
        cond.left_operand.all.return_value = []
        cond.right_operand = MagicMock()
        cond.right_operand.all.return_value = []
        cond.parent_test = MagicMock()
        cond.parent_test.all.return_value = []

        act.caller = MagicMock()
        act.caller.all.return_value = []
        act.callee = MagicMock()
        act.callee.all.return_value = []
        act.parent_test = MagicMock()
        act.parent_test.all.return_value = []

        vm.assertions = MagicMock()
        vm.assertions.all.return_value = [cond]
        vm.steps = MagicMock()
        vm.steps.all.return_value = [act]
        vm.llr = MagicMock()
        vm.llr.all.return_value = []

        llr.verification_methods = MagicMock()
        llr.verification_methods.all.return_value = [vm]
        llr.hlr = MagicMock()
        llr.hlr.all.return_value = []

        result = llr.serialize(fields="all", nested=True)
        _dump("llr_deeply_nested", result)

        # LLR → VM
        assert len(result["composes"]) == 1
        vm_dict = result["composes"][0]
        assert vm_dict["type"] == "TestNode"
        assert vm_dict["method"] == "automated"

        # VM → Conditions + Actions
        assert "composes" in vm_dict
        children = vm_dict["composes"]
        child_types = [c["type"] for c in children]
        assert "Assertion" in child_types
        assert "TestStep" in child_types

        # Check Condition content
        cond_dict = next(c for c in children if c["type"] == "Assertion")
        assert cond_dict["phase"] == "pre"
        assert cond_dict["operator"] == "=="
        assert cond_dict["subject_qualified_name"] == "Engine.is_initialized"

        # Check Action content
        act_dict = next(c for c in children if c["type"] == "TestStep")
        assert act_dict["description"] == "Invoke the add operation"
        assert act_dict["callee_qualified_name"] == "Engine.add"


class TestNestedSerializeExcludesComposedEdges:
    """COMPOSES edges should be removed from the flat edges list when nested=True."""

    @patch.object(LLR, "nodes")
    def test_composes_edges_removed_from_flat_list(self, mock_nodes):
        llr = LLR(description="Test LLR", tags=["design"])
        llr.refid = "test-llr-1"
        llr.element_id_property = "456"

        vm = TestNode(method="automated", description="Verify", tags=["design"])
        vm.refid = "test-vm-1"
        vm.element_id_property = "789"
        vm.assertions = MagicMock()
        vm.assertions.all.return_value = []
        vm.steps = MagicMock()
        vm.steps.all.return_value = []
        vm.llr = MagicMock()
        vm.llr.all.return_value = []

        llr.verification_methods = MagicMock()
        llr.verification_methods.all.return_value = [vm]
        llr.hlr = MagicMock()
        llr.hlr.all.return_value = []

        result = llr.serialize(fields="all", nested=True)
        _dump("llr_edges_excluded", result)

        for edge in result.get("edges", []):
            assert edge["relation_type"] != "COMPOSES", \
                f"COMPOSES edge should be removed from flat list when nested=True, got: {edge}"


class TestLLRSerializedMethodsExtraction:
    """Verifies that methods can be extracted from the nested composes key."""

    @patch.object(LLR, "nodes")
    def test_methods_from_nested_composes(self, mock_nodes):
        llr = LLR(description="Test LLR", tags=["design"])
        llr.refid = "test-llr-1"
        llr.element_id_property = "456"

        vm1 = TestNode(method="automated", test_name="test_a", description="A", tags=["design"])
        vm1.refid = "test-vm-1"
        vm1.element_id_property = "789"
        vm1.assertions = MagicMock()
        vm1.assertions.all.return_value = []
        vm1.steps = MagicMock()
        vm1.steps.all.return_value = []
        vm1.llr = MagicMock()
        vm1.llr.all.return_value = []

        vm2 = TestNode(method="review", test_name="test_b", description="B", tags=["design"])
        vm2.refid = "test-vm-2"
        vm2.element_id_property = "790"
        vm2.assertions = MagicMock()
        vm2.assertions.all.return_value = []
        vm2.steps = MagicMock()
        vm2.steps.all.return_value = []
        vm2.llr = MagicMock()
        vm2.llr.all.return_value = []

        llr.verification_methods = MagicMock()
        llr.verification_methods.all.return_value = [vm1, vm2]
        llr.hlr = MagicMock()
        llr.hlr.all.return_value = []

        result = llr.serialize(fields="all", nested=True)
        _dump("llr_methods_extraction", result)

        methods = [
            child["method"]
            for child in result.get("composes", [])
            if child.get("type") == "TestNode" and child.get("method")
        ]
        assert methods == ["automated", "review"]

    @patch.object(LLR, "nodes")
    def test_methods_empty_when_no_vms(self, mock_nodes):
        llr = LLR(description="Empty LLR", tags=["design"])
        llr.refid = "test-llr-2"
        llr.element_id_property = "457"

        llr.verification_methods = MagicMock()
        llr.verification_methods.all.return_value = []
        llr.hlr = MagicMock()
        llr.hlr.all.return_value = []

        result = llr.serialize(fields="all", nested=True)
        _dump("llr_methods_empty", result)

        methods = [
            child["method"]
            for child in result.get("composes", [])
            if child.get("type") == "TestNode" and child.get("method")
        ]
        assert methods == []