"""Recursive-descent parser for C++ type signatures.

Extracts TypeRef structures from type strings like:
  "const std::vector<std::string>&"
  "std::map<std::string, double>"
  "CalculationResult"
  "(const std::string& operand1, const std::string& operand2)"

Handles qualified names, template nesting, const/ref/pointer qualifiers,
and builtin type detection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class TypeRef:
    """Structured reference to a type extracted from a type signature."""

    name: str  # "std::vector" or "Calculator"
    template_args: list[TypeRef] = field(default_factory=list)
    is_builtin: bool = False  # True for int, double, void, etc.
    original_text: str = ""  # "std::vector<const std::string&>"
    qualifiers: list[str] = field(default_factory=list)  # ["const", "&", "*"]

    @property
    def resolved_name(self) -> str:
        """The bare type name without qualifiers or template args."""
        return self.name


# C/C++ builtin types that are not dependency targets.
_BUILTIN_TYPES = frozenset({
    "void", "bool", "int", "double", "float", "char", "long", "short",
    "unsigned", "signed", "size_t", "uint8_t", "uint16_t", "uint32_t",
    "uint64_t", "int8_t", "int16_t", "int32_t", "int64_t",
    "auto", "nullptr_t",
})

# Keywords and qualifiers to skip during type extraction.
_SKIP_TOKENS = frozenset({
    "const", "volatile", "mutable", "constexpr", "static",
    "inline", "virtual", "explicit", "noexcept", "override",
    "final", "register", "extern", "typename",
})

# Regex for tokenizing C++ type strings.
_TOKEN_RE = re.compile(
    r"""(::)           # scope resolution
      | ([a-zA-Z_]\w*) # identifier
      | (<)            # template open
      | (>)            # template close
      | (,)            # comma
      | (\&)           # reference
      | (\*)           # pointer
      | (\.\.\.)       # variadic
    """,
    re.VERBOSE,
)


def _tokenize(text: str) -> list[str]:
    """Tokenize a C++ type string into meaningful tokens."""
    tokens = []
    for m in _TOKEN_RE.finditer(text):
        token = m.group(0)
        if token not in _SKIP_TOKENS:
            tokens.append(token)
    return tokens


def _parse_type_ref(tokens: list[str], pos: int) -> tuple[TypeRef | None, int]:
    """Parse a single type reference starting at position pos.

    Returns (TypeRef or None, next_position).
    Returns None if no meaningful type was found (e.g., void, bare commas).
    """
    if pos >= len(tokens):
        return None, pos

    name_parts: list[str] = []
    qualifiers: list[str] = []
    saw_qualifier = False  # Track if we've seen & or * after type name

    i = pos
    got_name = False
    while i < len(tokens):
        if tokens[i] == "::":
            # Scope resolution — this extends the qualified name
            # If we already saw qualifiers, :: can't be part of the type
            if saw_qualifier:
                break
            i += 1
            continue
        elif tokens[i] in ("&", "*"):
            qualifiers.append(tokens[i])
            saw_qualifier = True
            i += 1
            continue
        elif tokens[i] == "<":
            # Template arguments follow
            break
        elif tokens[i] == ",":
            # End of this type in a parameter list
            break
        elif tokens[i] == ">":
            # End of template args
            break
        elif tokens[i] == "...":
            i += 1
            continue
        else:
            # It's an identifier
            if saw_qualifier:
                # After qualifiers, a bare identifier is a variable name,
                # not part of the type. Skip it and stop collecting.
                i += 1
                continue
            name_parts.append(tokens[i])
            got_name = True
            i += 1

    if not name_parts:
        # If we only saw qualifiers but no name, skip past them
        if saw_qualifier:
            return None, i
        return None, i

    # Rebuild the qualified name from collected parts
    full_name = "::".join(name_parts)

    # Check for void — not a dependency
    is_void = full_name == "void"

    # Check for builtin/primitive types
    is_builtin = full_name in _BUILTIN_TYPES

    # Parse template arguments if present
    template_args: list[TypeRef] = []
    if i < len(tokens) and tokens[i] == "<":
        i += 1  # skip <
        while i < len(tokens) and tokens[i] != ">":
            arg_ref, new_i = _parse_type_ref(tokens, i)
            if arg_ref is not None:
                template_args.append(arg_ref)
            i = new_i
            # Skip commas between template args
            if i < len(tokens) and tokens[i] == ",":
                i += 1
        if i < len(tokens) and tokens[i] == ">":
            i += 1  # skip >
        # After template args, skip any trailing qualifiers or variable names
        while i < len(tokens):
            if tokens[i] in ("&", "*"):
                qualifiers.append(tokens[i])
                i += 1
            elif tokens[i] in (",", ">", "..."):
                break
            elif tokens[i] == "::":
                break
            elif tokens[i] == "<":
                break
            else:
                # Variable name after template — skip it
                i += 1

    if is_void:
        return None, i

    return TypeRef(
        name=full_name,
        template_args=template_args,
        is_builtin=is_builtin,
        original_text="",
        qualifiers=qualifiers,
    ), i


def parse_type_refs(text: str) -> list[TypeRef]:
    """Parse all type references from a C++ type signature string.

    Returns a flat list of all TypeRefs found, including nested template args.
    The first TypeRef is the outermost type; subsequent entries are inner types
    (template arguments) in depth-first order.

    Examples:
        "CalculationResult" → [TypeRef(name="CalculationResult")]
        "std::vector<std::string>" → [TypeRef(name="std::vector", template_args=[...]), TypeRef(name="std::string")]
        "const std::string&" → [TypeRef(name="std::string")]
        "(const std::string& a, double b)" → [TypeRef(name="std::string"), TypeRef(name="double")]
    """
    if not text or not text.strip():
        return []

    tokens = _tokenize(text)
    if not tokens:
        return []

    refs: list[TypeRef] = []
    i = 0
    while i < len(tokens):
        ref, new_i = _parse_type_ref(tokens, i)
        if ref is not None:
            ref.original_text = text
            refs.append(ref)
            # Also flatten template args into the result list
            for arg in ref.template_args:
                arg.original_text = text
                refs.append(arg)
                refs.extend(_flatten_template_args(arg))
        i = new_i
        # Skip commas between parameter types
        while i < len(tokens) and tokens[i] == ",":
            i += 1

    return refs


def _flatten_template_args(ref: TypeRef) -> list[TypeRef]:
    """Recursively flatten nested template args into a flat list."""
    result: list[TypeRef] = []
    for arg in ref.template_args:
        result.append(arg)
        result.extend(_flatten_template_args(arg))
    return result