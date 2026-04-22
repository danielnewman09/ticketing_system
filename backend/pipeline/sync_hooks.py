"""
Synchronization hooks between implemented source code and the design.

Two checks:
1. Design-Code Sync Hook -- compare implemented source files against
   the OO design schema to verify classes, methods, signatures match.
2. Test Coverage Hook -- verify every VerificationMethod has a corresponding
   unit test that exercises it.

After both hooks pass, update Neo4j with implementation_status.
"""

import ast
import logging
from dataclasses import dataclass, field

from backend.pipeline.schemas import TaskSchema

log = logging.getLogger("pipeline.sync_hooks")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DesignSyncReport:
    """Report from comparing source code to the design schema."""
    missing_classes: list[str] = field(default_factory=list)
    missing_methods: dict[str, list[str]] = field(default_factory=dict)
    # class_name -> [method_name, ...]
    signature_mismatches: list[str] = field(default_factory=list)
    extra_public_methods: dict[str, list[str]] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return (
            not self.missing_classes
            and not self.missing_methods
            and not self.signature_mismatches
        )


@dataclass
class TestCoverageReport:
    """Report from comparing test files to verification methods."""
    untested_verifications: list[str] = field(default_factory=list)
    # verification test_name values with no matching test
    
    @property
    def clean(self) -> bool:
        return not self.untested_verifications


# ---------------------------------------------------------------------------
# Design-Code Sync Hook
# ---------------------------------------------------------------------------

def check_design_against_code(
    oo_design: dict,
    source_files: list[str],
) -> DesignSyncReport:
    """Compare the OO design schema against the actual source files.

    Args:
        oo_design: Dict from OODesignSchema (classes, interfaces, etc.).
        source_files: List of absolute or relative paths to source files.

    Returns:
        DesignSyncReport with any mismatches.
    """
    report = DesignSyncReport()

    # Build a set of expected class names from the design
    expected_classes = {c["name"] for c in oo_design.get("classes", [])}
    expected_interfaces = {i["name"] for i in oo_design.get("interfaces", [])}
    expected_all = expected_classes | expected_interfaces

    # Parse source files and collect actual classes
    actual_classes: dict[str, dict] = {}
    # Maps class_name -> {methods: {method_name: {params, return_type}}}
    
    for src_path in source_files:
        try:
            tree = _parse_file(src_path)
            if tree is None:
                continue
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.ClassDef,)):
                    methods = {}
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            params = [
                                a.arg for a in item.args.args
                                if a.arg != "self" and a.arg != "cls"
                            ]
                            rt = ""
                            if item.returns:
                                rt = _unparse_annotation(item.returns)
                            methods[item.name] = {
                                "params": params, "return_type": rt,
                            }
                    actual_classes[node.name] = {"methods": methods}
        except FileNotFoundError:
            log.warning("Source file not found: %s", src_path)

    # Check missing classes
    for cls_name in expected_all:
        if cls_name not in actual_classes:
            report.missing_classes.append(cls_name)

    # Check missing / mismatched methods
    for cls in oo_design.get("classes", []) + oo_design.get("interfaces", []):
        cls_name = cls["name"]
        if cls_name not in actual_classes:
            continue
        actual_methods = actual_classes[cls_name]["methods"]
        expected_methods = {m["name"] for m in cls.get("methods", [])}
        
        for method_name in expected_methods:
            if method_name not in actual_methods:
                report.missing_methods.setdefault(cls_name, []).append(method_name)
            else:
                # Check signature (parameter count -- loose check)
                actual_m = actual_methods[method_name]
                expected_m = next(
                    m for m in cls["methods"] if m["name"] == method_name
                )
                actual_params = [p for p in actual_m["params"]]
                expected_params = expected_m.get("parameters", [])
                if len(actual_params) != len(expected_params):
                    report.signature_mismatches.append(
                        f"{cls_name}.{method_name}: "
                        f"expected {len(expected_params)} params, "
                        f"got {len(actual_params)}"
                    )

    # Check extra public methods (not in design but present in code)
    for cls_name, cls_info in actual_classes.items():
        extra = [
            m for m in cls_info["methods"]
            if not m.startswith("_")  # skip private
            and m not in {
                m["name"]
                for c in (oo_design.get("classes", []) + oo_design.get("interfaces", []))
                if c["name"] == cls_name
                for m in c.get("methods", [])
            }
        ]
        if extra:
            report.extra_public_methods[cls_name] = extra

    return report


# ---------------------------------------------------------------------------
# Test Coverage Hook
# ---------------------------------------------------------------------------

def check_test_coverage(
    verification_test_names: list[str],
    test_files: list[str],
) -> TestCoverageReport:
    """Verify every verification method has a corresponding test function.

    Args:
        verification_test_names: test_name values from VerificationMethod.
        test_files: List of test file paths to scan.

    Returns:
        TestCoverageReport with any untested verifications.
    """
    report = TestCoverageReport()

    # Collect all test function names from test files
    actual_test_names: set[str] = set()
    for tf in test_files:
        try:
            tree = _parse_file(tf)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                    actual_test_names.add(node.name)
        except FileNotFoundError:
            log.warning("Test file not found: %s", tf)

    # Check each expected test
    for test_name in verification_test_names:
        if test_name not in actual_test_names:
            report.untested_verifications.append(test_name)

    return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_file(path: str) -> ast.AST | None:
    """Parse a Python file into an AST, returning None on failure."""
    try:
        with open(path, "r") as f:
            source = f.read()
        return ast.parse(source)
    except (SyntaxError, FileNotFoundError, OSError) as e:
        log.warning("Could not parse %s: %s", path, e)
        return None


def _unparse_annotation(node: ast.AST) -> str:
    """Convert an AST annotation node back to source text."""
    if hasattr(ast, "unparse"):
        return ast.unparse(node)
    return str(node)
