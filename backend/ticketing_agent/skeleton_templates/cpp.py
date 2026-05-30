"""
C++ skeleton templates — generate header/source stubs from OO design.

Takes OODesignSchema (or dict) and produces C++ header and source files with:
- class declarations with method signatures and empty bodies
- struct declarations for attribute-only types
- enum declarations with values
- interface (abstract class) declarations with pure virtual methods
- header guards, include directives, namespace wrapping
- Separate .hpp/.cpp pairs with the .hpp holding declarations and
  .cpp holding method definitions with TODO stubs

The generated code compiles but is incomplete — method bodies contain
`// TODO: Implement` comments and return default values where needed.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkeletonResult:
    """Result of skeleton generation for one source file."""

    file_path: str  # Relative path, e.g. src/calculator/engine.hpp
    content: str  # C++ source code
    classes_generated: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not isinstance(self.classes_generated, list):
            self.classes_generated = list(self.classes_generated)


# ---------------------------------------------------------------------------
# C++ type mapping
# ---------------------------------------------------------------------------

_CPP_TYPE_MAP: dict[str, str] = {
    "int": "int",
    "float": "float",
    "double": "double",
    "bool": "bool",
    "char": "char",
    "string": "std::string",
    "void": "void",
    "auto": "auto",
    "size_t": "std::size_t",
    "vector": "std::vector",
    "list": "std::list",
    "map": "std::map",
    "set": "std::set",
    "unordered_map": "std::unordered_map",
    "unordered_set": "std::unordered_set",
    "optional": "std::optional",
    "unique_ptr": "std::unique_ptr",
    "shared_ptr": "std::shared_ptr",
    "pair": "std::pair",
    "tuple": "std::tuple",
}


def _cpp_type(type_name: str) -> str:
    """Map a type name to a C++ type.

    Handles both built-in names and qualified names like 'std::vector<int>'.
    Passes through unknown names as-is (they may be project types).
    """
    if not type_name:
        return "void"

    lower = type_name.lower()
    if lower in _CPP_TYPE_MAP:
        return _CPP_TYPE_MAP[lower]

    # If already qualified (e.g. "std::string", "Fl_Window"), pass through
    if "::" in type_name:
        return type_name

    # Capitalized names are likely project types — pass through
    if type_name[0].isupper():
        return type_name

    return type_name


def _header_guard(file_path: str) -> str:
    """Generate a header guard from a file path.

    e.g. 'src/calculator/engine.hpp' -> 'SRC_CALCULATOR_ENGINE_HPP'
    """
    guard = file_path.upper()
    for ch in ("-", ".", "/"):
        guard = guard.replace(ch, "_")
    # Remove duplicate underscores
    while "__" in guard:
        guard = guard.replace("__", "_")
    return guard


def _default_return_value(return_type: str) -> str:
    """Return a default value expression for a C++ return type."""
    rt = _cpp_type(return_type) if return_type else "void"

    if rt == "void":
        return ""
    if rt == "bool":
        return "false"
    if rt in ("int", "std::size_t", "long", "short", "unsigned int"):
        return "0"
    if rt in ("float", "double", "long double"):
        return "0.0"
    if rt == "std::string":
        return '""'
    if rt.startswith("std::unique_ptr") or rt.startswith("std::shared_ptr"):
        return "{nullptr}"
    if rt.startswith("std::optional"):
        return "{std::nullopt}"
    if rt.startswith("std::vector") or rt.startswith("std::list"):
        return "{}"
    # For project-defined types, return a default-constructed value
    return "{}"


def _includes_for_type(type_name: str) -> str | None:
    """Return the C++ include needed for a built-in type, if any."""
    mapping = {
        "std::string": "<string>",
        "std::vector": "<vector>",
        "std::list": "<list>",
        "std::map": "<map>",
        "std::set": "<set>",
        "std::unordered_map": "<unordered_map>",
        "std::unordered_set": "<unordered_set>",
        "std::optional": "<optional>",
        "std::unique_ptr": "<memory>",
        "std::shared_ptr": "<memory>",
        "std::size_t": "<cstddef>",
        "std::pair": "<utility>",
        "std::tuple": "<tuple>",
    }
    return mapping.get(_cpp_type(type_name))


# ---------------------------------------------------------------------------
# Enum skeleton
# ---------------------------------------------------------------------------


def generate_enum_skeleton(enum_def: dict, namespace: str = "") -> str:
    """Generate a C++ enum class declaration.

    Args:
        enum_def: EnumSchema dict with name, module, values, description.
        namespace: Optional enclosing namespace.

    Returns:
        C++ source code for the enum declaration.
    """
    name = enum_def["name"]
    values = enum_def.get("values", [])
    desc = enum_def.get("description", "")

    lines = []
    if desc:
        lines.append(f"/// {desc}")
    lines.append(f"enum class {name} {{")
    for i, val in enumerate(values):
        comma = "," if i < len(values) - 1 else ""
        lines.append(f"    {val}{comma}")
    if not values:
        lines.append("    // TODO: Add enum values")
    lines.append("};")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Interface (abstract class) skeleton
# ---------------------------------------------------------------------------


def generate_interface_skeleton(iface: dict, namespace: str = "") -> str:
    """Generate a C++ abstract class (interface) declaration.

    All methods are pure virtual (= 0).
    """
    name = iface["name"]
    methods = iface.get("methods", [])
    desc = iface.get("description", "")

    lines = []
    if desc:
        lines.append(f"/// {desc}")
    lines.append(f"class {name} {{")
    lines.append("public:")
    lines.append(f"    virtual ~{name}() = default;")
    lines.append("")

    for method in methods:
        method_decl = _method_declaration(method, is_pure_virtual=True)
        lines.append(f"    {method_decl}")
        lines.append("")

    if not methods:
        lines.append("    // TODO: Add pure virtual methods")
        lines.append("")

    lines.append("};")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Method declarations and definitions
# ---------------------------------------------------------------------------


def _method_declaration(method: dict, is_pure_virtual: bool = False) -> str:
    """Generate a C++ method declaration for a header file.

    Args:
        method: MethodSchema dict.
        is_pure_virtual: If True, append '= 0'.

    Returns:
        Single-line method declaration string.
    """
    name = method["name"]
    ret_type = _cpp_type(method.get("return_type", "void"))
    params = method.get("parameters", [])
    vis = method.get("visibility", "public")
    is_const = method.get("is_const", False)
    is_static = method.get("is_static", False)

    param_str = ", ".join(_format_param(p) for p in params) if params else ""
    prefix = "virtual " if is_pure_virtual else ""
    suffix = " const" if is_const else ""
    if is_pure_virtual:
        suffix += " = 0"
    elif is_static:
        suffix += "  // static"

    return f"{prefix}{ret_type} {name}({param_str}){suffix};"


def _format_param(param: dict | str) -> str:
    """Format a single method parameter for C++ declaration."""
    if isinstance(param, str):
        # Legacy format: just a name
        return param
    type_name = _cpp_type(param.get("type_name", "auto"))
    name = param.get("name", "")
    if not name:
        name = "arg"
    # Pass by value for small types, const ref for others
    if type_name in ("int", "float", "double", "bool", "char", "std::size_t"):
        return f"{type_name} {name}"
    elif type_name == "std::string" or type_name.startswith("std::vector") or type_name.startswith("std::map"):
        return f"const {type_name}& {name}"
    else:
        return f"const {type_name}& {name}"


def _method_definition(class_name: str, method: dict, namespace: str = "") -> str:
    """Generate a C++ method definition for a source file.

    Args:
        class_name: The class name (may be qualified).
        method: MethodSchema dict.
        namespace: Optional enclosing namespace.

    Returns:
        Multi-line method definition with TODO stub body.
    """
    name = method["name"]
    ret_type = _cpp_type(method.get("return_type", "void"))
    params = method.get("parameters", [])
    is_const = method.get("is_const", False)

    param_str = ", ".join(_format_param(p) for p in params) if params else ""
    qualifier = f" {class_name}::"
    ns_prefix = f"{namespace}::" if namespace else ""
    const_suffix = " const" if is_const else ""

    lines = []
    lines.append(f"{ret_type} {ns_prefix}{class_name}::{name}({param_str}){const_suffix} {{")

    default_val = _default_return_value(method.get("return_type", ""))
    if default_val:
        lines.append(f"    // TODO: Implement {name}")
        lines.append(f"    return {default_val};")
    else:
        lines.append(f"    // TODO: Implement {name}")

    lines.append("}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Class skeleton
# ---------------------------------------------------------------------------


def generate_class_skeleton(cls: dict, namespace: str = "") -> tuple[str, str]:
    """Generate C++ class declaration (header) and definitions (source).

    Args:
        cls: ClassSchema dict.
        namespace: Optional enclosing namespace.

    Returns:
        Tuple of (header_declaration, source_definitions) strings.
    """
    name = cls["name"]
    bases = cls.get("inherits_from", [])
    interfaces = cls.get("realizes_interfaces", [])
    attrs = cls.get("attributes", [])
    methods = cls.get("methods", [])
    desc = cls.get("description", "")

    # Build base class list: includes both inheritance and interface realization
    all_bases = list(bases) + list(interfaces)
    base_clause = f" : {', '.join(all_bases)}" if all_bases else ""

    # --- Header declaration ---
    h_lines = []
    if desc:
        h_lines.append(f"/// {desc}")
    h_lines.append(f"class {name}{base_clause} {{")
    h_lines.append("public:")
    h_lines.append(f"    {name}() = default;")
    h_lines.append(f"    virtual ~{name}() = default;")

    # Disable copy if the class has complex state
    # (not for simple DTOs)
    has_methods = bool(methods)
    if has_methods:
        h_lines.append("")
        h_lines.append(f"    {name}(const {name}&) = delete;")
        h_lines.append(f"    {name}& operator=(const {name}&) = delete;")
        h_lines.append(f"    {name}({name}&&) = default;")
        h_lines.append(f"    {name}& operator=({name}&&) = default;")

    # Public methods
    for method in methods:
        vis = method.get("visibility", "public")
        if vis == "public":
            h_lines.append(f"    {_method_declaration(method)}")

    # Attributes — determine visibility sectioning
    private_attrs = [a for a in attrs if a.get("visibility") in ("private", "protected")]
    public_attrs = [a for a in attrs if a.get("visibility") == "public"]

    # If class is attribute-only (no methods), treat it as a struct-like
    if not methods and attrs:
        # Regenerate as a simple struct with public members
        h_lines = []
        if desc:
            h_lines.append(f"/// {desc}")
        h_lines.append(f"struct {name}{base_clause} {{")
        for attr in attrs:
            type_hint = _cpp_type(attr.get("type_name", "int"))
            h_lines.append(f"    {type_hint} {attr['name']}{{}};")
        h_lines.append("};")
        return "\n".join(h_lines), ""

    # Protected/private sections
    protected_methods = [m for m in methods if m.get("visibility") == "protected"]
    private_methods = [m for m in methods if m.get("visibility") in ("private",)]

    if protected_methods:
        h_lines.append("")
        h_lines.append("protected:")
        for method in protected_methods:
            h_lines.append(f"    {_method_declaration(method)}")

    if private_methods:
        h_lines.append("")
        h_lines.append("private:")
        for method in private_methods:
            h_lines.append(f"    {_method_declaration(method)}")

    # Private data members
    if private_attrs or public_attrs:
        h_lines.append("")
        h_lines.append("private:")
        for attr in private_attrs:
            type_hint = _cpp_type(attr.get("type_name", "int"))
            h_lines.append(f"    {type_hint} {attr['name']}_;")

    h_lines.append("};")

    header_decl = "\n".join(h_lines)

    # --- Source definitions ---
    cpp_lines = []
    for method in methods:
        if method.get("visibility") == "private" and method.get("is_static", False):
            # Skip private static methods in source — inline in header
            continue
        cpp_lines.append(_method_definition(name, method, namespace=namespace))
        cpp_lines.append("")

    source_def = "\n".join(cpp_lines) if cpp_lines else ""

    return header_decl, source_def


# ---------------------------------------------------------------------------
# Module skeleton (groups classes/enums/interfaces into header/source pair)
# ---------------------------------------------------------------------------


def generate_module_skeleton(
    classes: list[dict],
    interfaces: list[dict],
    enums: list[dict],
    module_name: str,
    namespace: str,
    source_root: str = "src",
) -> list[SkeletonResult]:
    """Generate header and source files for one module/namespace.

    Args:
        classes: List of class dicts from OODesignSchema.
        interfaces: List of interface dicts from OODesignSchema.
        enums: List of enum dicts from OODesignSchema.
        module_name: e.g. "engine" or "calculation_engine"
        namespace: e.g. "calculation_engine"
        source_root: Source directory root (default 'src').

    Returns:
        List of SkeletonResult (one for .hpp, one for .cpp).
    """
    results = []

    # Build header content
    hpp_guard = _header_guard(f"{source_root}/{module_name}.hpp")
    hpp_lines = [
        f"#ifndef {hpp_guard}",
        f"#define {hpp_guard}",
        "",
    ]

    # Collect includes from types used in the module
    includes = set()
    for cls in classes:
        for attr in cls.get("attributes", []):
            inc = _includes_for_type(attr.get("type_name", ""))
            if inc:
                includes.add(inc)
        for m in cls.get("methods", []):
            inc = _includes_for_type(m.get("return_type", ""))
            if inc:
                includes.add(inc)
            for p in m.get("parameters", []):
                if isinstance(p, dict):
                    inc = _includes_for_type(p.get("type_name", ""))
                    if inc:
                        includes.add(inc)

    # Check for std::string, std::vector etc. in class bases too
    all_builtins = set()
    for cls in classes:
        for base in cls.get("inherits_from", []) + cls.get("realizes_interfaces", []):
            inc = _includes_for_type(base)
            if inc:
                includes.add(inc)

    # Forward declarations for cross-references within the same design
    forward_decls = set()
    for cls in classes:
        for base in cls.get("inherits_from", []) + cls.get("realizes_interfaces", []):
            # Only forward-declare if it's not a standard type
            cpp_base = _cpp_type(base)
            if cpp_base not in _CPP_TYPE_MAP.values() and "::" not in cpp_base:
                forward_decls.add(cpp_base)

    # Sort and emit includes
    # String must come before other std includes
    sorted_includes = sorted(includes)
    for inc in sorted_includes:
        hpp_lines.append(f"#include {inc}")
    hpp_lines.append("")

    # Forward declarations
    if forward_decls:
        hpp_lines.append("// Forward declarations")
        for fwd in sorted(forward_decls):
            hpp_lines.append(f"class {fwd};")
        hpp_lines.append("")

    # Namespace open
    hpp_lines.append(f"namespace {namespace} {{")
    hpp_lines.append("")

    # Enums first
    class_names = []
    for enum_def in enums:
        hpp_lines.append(generate_enum_skeleton(enum_def, namespace=namespace))
        hpp_lines.append("")

    # Interfaces
    for iface in interfaces:
        hpp_lines.append(generate_interface_skeleton(iface, namespace=namespace))
        hpp_lines.append("")
        class_names.append(iface["name"])

    # Classes — header declarations only
    cpp_body_lines = []
    for cls in classes:
        header_decl, source_def = generate_class_skeleton(cls, namespace=namespace)
        hpp_lines.append(header_decl)
        hpp_lines.append("")
        class_names.append(cls["name"])

        if source_def:
            cpp_body_lines.append(source_def)

    # Namespace close
    hpp_lines.append(f"}} // namespace {namespace}")
    hpp_lines.append("")
    hpp_lines.append(f"#endif // {hpp_guard}")
    hpp_lines.append("")

    # File paths
    # Convert module namespace to directory structure
    # e.g. "calculation_engine" -> "calculation_engine"
    # e.g. "calculation_engine::core" -> "calculation_engine/core"
    dir_parts = module_name.replace("::", "/").split("/")

    if len(dir_parts) == 1:
        hpp_path = f"{source_root}/{module_name}.hpp"
        cpp_path = f"{source_root}/{module_name}.cpp"
    else:
        pkg_dir = "/".join(dir_parts[:-1])
        hpp_path = f"{source_root}/{pkg_dir}/{dir_parts[-1]}.hpp"
        cpp_path = f"{source_root}/{pkg_dir}/{dir_parts[-1]}.cpp"

    hpp_content = "\n".join(hpp_lines)

    results.append(SkeletonResult(
        file_path=hpp_path,
        content=hpp_content,
        classes_generated=class_names,
    ))

    # Source file (only if there are method definitions)
    if cpp_body_lines:
        cpp_lines = [
            f'#include "{module_name}.hpp"',
            "",
            f"namespace {namespace} {{",
            "",
        ]
        cpp_lines.extend(cpp_body_lines)
        cpp_lines.append(f"}} // namespace {namespace}")
        cpp_lines.append("")

        results.append(SkeletonResult(
            file_path=cpp_path,
            content="\n".join(cpp_lines),
            classes_generated=class_names,
        ))

    return results


# ---------------------------------------------------------------------------
# Batch skeleton from OO design
# ---------------------------------------------------------------------------


def generate_skeleton_from_design(
    oo_design: dict,
    workspace_dir: str = "",
    source_root: str = "src",
    project_name: str = "",
) -> list[SkeletonResult]:
    """Generate complete C++ skeleton for an OO design.

    Groups classes by module, generates header/source pairs per module.

    Args:
        oo_design: Dict from OODesignSchema.model_dump().
        workspace_dir: Root directory for generated files.
        source_root: Source directory name (default 'src').
        project_name: Project name, used for the parent library directory.

    Returns:
        List of SkeletonResult objects.
    """
    # Group classes by module
    by_module: dict[str, dict] = {}
    for cls in oo_design.get("classes", []):
        mod = cls.get("module", "default") or "default"
        by_module.setdefault(mod, {"classes": [], "interfaces": [], "enums": []})
        by_module[mod]["classes"].append(cls)

    for iface in oo_design.get("interfaces", []):
        mod = iface.get("module", "default") or "default"
        by_module.setdefault(mod, {"classes": [], "interfaces": [], "enums": []})
        by_module[mod]["interfaces"].append(iface)

    for enum_def in oo_design.get("enums", []):
        mod = enum_def.get("module", "default") or "default"
        by_module.setdefault(mod, {"classes": [], "interfaces": [], "enums": []})
        by_module[mod]["enums"].append(enum_def)

    results = []
    for mod_name, mod_data in sorted(by_module.items()):
        # Determine namespace from module name
        # "calculation_engine" -> "calculation_engine"
        # "calculation_engine::core" -> "calculation_engine::core"
        namespace = mod_name.replace(".", "::").replace("/", "::")

        # If project_name is set, prefix the namespace
        if project_name:
            # Module is like "core" or "engine" — prefix with project namespace
            if "::" not in namespace:
                namespace = f"{project_name}::{namespace}"

        module_results = generate_module_skeleton(
            classes=mod_data["classes"],
            interfaces=mod_data["interfaces"],
            enums=mod_data["enums"],
            module_name=mod_name.split("::")[-1] if "::" in mod_name else mod_name,
            namespace=namespace,
            source_root=source_root,
        )
        results.extend(module_results)

    return results


# ---------------------------------------------------------------------------
# Include-gathering utility
# ---------------------------------------------------------------------------


def gather_includes_from_design(oo_design: dict) -> set[str]:
    """Collect all C++ standard library includes needed by the design.

    Scans class attributes, method return types, and parameters.
    """
    includes: set[str] = set()

    for cls in oo_design.get("classes", []):
        for attr in cls.get("attributes", []):
            inc = _includes_for_type(attr.get("type_name", ""))
            if inc:
                includes.add(inc)
        for method in cls.get("methods", []):
            inc = _includes_for_type(method.get("return_type", ""))
            if inc:
                includes.add(inc)
            for param in method.get("parameters", []):
                if isinstance(param, dict):
                    inc = _includes_for_type(param.get("type_name", ""))
                    if inc:
                        includes.add(inc)
        for base in cls.get("inherits_from", []) + cls.get("realizes_interfaces", []):
            inc = _includes_for_type(base)
            if inc:
                includes.add(inc)

    for iface in oo_design.get("interfaces", []):
        for method in iface.get("methods", []):
            inc = _includes_for_type(method.get("return_type", ""))
            if inc:
                includes.add(inc)
            for param in method.get("parameters", []):
                if isinstance(param, dict):
                    inc = _includes_for_type(param.get("type_name", ""))
                    if inc:
                        includes.add(inc)

    return includes