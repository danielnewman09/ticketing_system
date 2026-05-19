"""
Python skeleton templates — generate class/method stubs from OO design.

Takes OODesignSchema (or dict) and produces Python source code with:
- class definitions (with inheritance, docstrings)
- method stubs with signatures and `pass` bodies
- dataclass support for attribute-only classes
- __init__.py generation for packages
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class SkeletonResult:
    """Result of skeleton generation for one source file."""
    file_path: str       # Relative path, e.g. src/calculator/engine.py
    content: str         # Python source code
    classes_generated: list[str] = ()  # Class names in this file

    def __post_init__(self):
        if not isinstance(self.classes_generated, list):
            self.classes_generated = list(self.classes_generated)


# ---------------------------------------------------------------------------
# Class skeleton
# ---------------------------------------------------------------------------

def generate_class_skeleton(cls: dict) -> str:
    """Generate a Python class definition with method stubs."""
    name = cls["name"]
    bases = ", ".join(cls.get("inherits_from", []))
    if cls.get("realizes_interfaces"):
        extra = ", ".join(cls["realizes_interfaces"])
        bases = f"{bases}, {extra}" if bases else extra

    header = f"class {name}({bases}):" if bases else f"class {name}:"
    lines = [header]

    desc = cls.get("description", "")
    if desc:
        lines.append(f'    """{desc}"""')
        lines.append("")

    # Attributes -> class-level annotations or __init__
    attrs = cls.get("attributes", [])
    methods = cls.get("methods", [])

    if attrs and not methods:
        # Attribute-only: use dataclass-like pattern
        lines = [header]
        if desc:
            lines[-1] += f'  # {desc}'
        for attr in attrs:
            type_hint = _python_type(attr.get("type_name", "Any"))
            lines.append(f"    {attr['name']}: {type_hint}")
        lines.append("    pass")
        return "\n".join(lines)

    if attrs:
        # Generate __init__ method
        lines.append("")
        sig_params = _init_params(attrs, methods)
        lines.append(f"    def __init__(self, {sig_params}):")
        for attr in attrs:
            vis = attr.get("visibility", "public")
            prefix = "_" if vis in ("private", "protected") else ""
            lines.append(f"        self.{prefix}{attr['name']} = {attr['name']}")
        lines.append("")

    for method in methods:
        method_src = generate_method_skeleton(method)
        lines.append(method_src)
        lines.append("")

    if not attrs and not methods:
        lines.append("    pass")

    return "\n".join(lines)


def generate_method_skeleton(method: dict) -> str:
    """Generate a method definition stub."""
    name = method["name"]
    params = method.get("parameters", [])
    ret = method.get("return_type", "")
    vis = method.get("visibility", "public")
    desc = method.get("description", "")

    # Add self as first parameter
    all_params = ["self"] + params

    type_hints = [p for p in all_params]
    if ret:
        type_hints_str = ", ".join(type_hints)
        ret_hint = _python_type(ret)
        sig = f"def {name}({type_hints_str}) -> {ret_hint}:"
    else:
        sig = f"def {name}({', '.join(type_hints)}):"

    lines = [sig]
    if desc:
        lines.append(f'        """{desc}"""')
        lines.append("        pass")
    else:
        lines.append("        pass")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# __init__.py generation
# ---------------------------------------------------------------------------

def generate_init_py(classes: list[dict], module_name: str) -> str:
    """Generate __init__.py with imports for the module's classes."""
    lines = [
        f'"""{module_name} module."""',
        "",
    ]

    for cls in classes:
        name = cls["name"]
        lines.append(f"from .{module_name} import {name}")

    all_names = ", ".join(repr(c["name"]) for c in classes)
    lines.append("")
    lines.append(f"__all__ = [{all_names}]")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Module skeleton (groups classes into a single file)
# ---------------------------------------------------------------------------

def generate_module_skeleton(
    classes: list[dict],
    module_name: str,
    docstring: str = "",
) -> SkeletonResult:
    """Generate a full Python module with all classes.

    Args:
        classes: List of class dicts from OODesignSchema.
        module_name: Filename without .py extension.
        docstring: Module docstring.

    Returns:
        SkeletonResult with file path and content.
    """
    file_path = f"src/{module_name}.py"
    lines = []

    if docstring:
        lines.append(f'"""{docstring}"""')
    else:
        lines.append(f'"""{module_name} module."""')
    lines.append("")

    class_names = []
    for i, cls in enumerate(classes):
        if i > 0:
            lines.append("")
            lines.append("")
        lines.append(generate_class_skeleton(cls))
        class_names.append(cls["name"])

    return SkeletonResult(
        file_path=file_path,
        content="\n".join(lines) + "\n",
        classes_generated=class_names,
    )


# ---------------------------------------------------------------------------
# Batch skeleton from OO design
# ---------------------------------------------------------------------------

def generate_skeleton_from_design(
    oo_design: dict,
    workspace_dir: str = "",
    source_root: str = "src",
) -> list[SkeletonResult]:
    """Generate complete skeleton for an OO design.

    Groups classes by module, generates one file per module.

    Args:
        oo_design: Dict from OODesignSchema.model_dump().
        workspace_dir: Root directory for generated files.
        source_root: Source directory name (default 'src').

    Returns:
        List of SkeletonResult objects.
    """
    # Group classes by module
    by_module: dict[str, list[dict]] = {}
    for cls in oo_design.get("classes", []):
        mod = cls.get("module", "default") or "default"
        by_module.setdefault(mod, []).append(cls)

    results = []
    for mod_name, classes in sorted(by_module.items()):
        # Convert module namespace to file path
        # e.g. "calc_engine" -> "src/calc_engine.py"
        # e.g. "calc.engine" -> "src/calc/engine.py"
        file_parts = mod_name.replace("::", ".").split(".")
        if len(file_parts) == 1:
            file_path = f"{source_root}/{file_parts[0]}.py"
        else:
            pkg_path = f"{source_root}/{'/'.join(file_parts[:-1])}"
            file_path = f"{pkg_path}/{file_parts[-1]}.py"

        docstring = f"{mod_name} module — auto-generated skeleton from design."
        result = generate_module_skeleton(classes, file_parts[-1], docstring)
        result.file_path = file_path
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_params(attrs: list[dict], methods: list[dict]) -> str:
    """Build __init__ parameter list from attributes."""
    parts = []
    for attr in attrs:
        name = attr["name"]
        type_hint = _python_type(attr.get("type_name", "Any"))
        parts.append(f"{name}: {type_hint}")
    return ", ".join(parts)


def _python_type(type_name: str) -> str:
    """Map a type name to a Python type hint."""
    if not type_name:
        return "Any"
    mapping = {
        "int": "int",
        "float": "float",
        "str": "str",
        "bool": "bool",
        "void": "None",
        "string": "str",
        "integer": "int",
        "double": "float",
        "list": "list",
        "dict": "dict",
        "any": "Any",
    }
    return mapping.get(type_name.lower(), type_name)
