"""OO design structural validation."""

import re

from codegraph.designs import ClassDiagram


def extract_type_refs(type_string: str, known_names: set[str], out: set[str]) -> None:
    """Extract references to known design entity names from a type string.

    Handles types like `CalculatorResult`, `const CalculatorResult&`,
    `vector<CalculatorResult>`, `std::unique_ptr<Operator>`, etc.
    Only adds names that appear in *known_names*.
    """
    for token in re.findall(r'\b([A-Z][A-Za-z0-9_]*)\b', type_string):
        if token in known_names:
            out.add(token)


def validate_oo_design(
    oo: ClassDiagram,
    prior_class_lookup: dict[str, str],
    dependency_lookup: dict[str, str] | None,
    intercomponent_classes: list[dict] | None,
) -> list[str]:
    """Validate an OO design for association target resolution and intercomponent coverage.

    Returns a list of error strings. Empty list means valid.
    """
    errors = []

    # Build set of known names
    design_class_names = {cls.name for cls in oo.classes}
    design_iface_names = {iface.name for iface in oo.interfaces}
    design_enum_names = {enum.name for enum in oo.enums}
    all_design_names = design_class_names | design_iface_names | design_enum_names

    # Set of intercomponent qualified names for lookup
    intercomp_qnames: set[str] = set()
    intercomp_bare: set[str] = set()
    if intercomponent_classes:
        intercomp_qnames = {c["qualified_name"] for c in intercomponent_classes}
        intercomp_bare = {qname.rsplit("::", 1)[-1] for qname in intercomp_qnames}

    # Build dependency lookup
    dep_lookup = dict(dependency_lookup or {})

    # Check 1: Unknown association targets
    for assoc in oo.associations:
        for ref in [assoc.subject, assoc.object]:
            if ref in all_design_names:
                continue
            if ref in prior_class_lookup.values():
                continue
            if ref in prior_class_lookup:
                continue
            if ref in dep_lookup:
                continue
            if ref in intercomp_qnames or ref in intercomp_bare:
                continue
            errors.append(
                f'Unknown class reference: "{ref}" in association '
                f'({assoc.subject} -[{assoc.predicate}]-> {assoc.object}). '
                f'"{ref}" is not defined in this design or the provided context.'
            )

    # Check 2: aggregates must have a mechanism; references recommended
    for assoc in oo.associations:
        if assoc.predicate == "aggregates" and not assoc.mechanism:
            errors.append(
                f"Association {assoc.subject} -[aggregates]-> {assoc.object} "
                f"has no mechanism. Use find_mechanism to discover the container "
                f"type (e.g., std::vector, std::map) and specify it in the mechanism field."
            )
        if assoc.predicate == "aggregates" and assoc.mechanism:
            mechanism = assoc.mechanism
            if mechanism not in all_design_names and mechanism not in prior_class_lookup and mechanism not in dep_lookup:
                errors.append(
                    f"Association {assoc.subject} -[aggregates]-> {assoc.object} "
                    f"has mechanism '{mechanism}' which is not a known class or dependency. "
                    f"Use find_mechanism to search for the correct container name."
                )

    # Check 3: Missing intercomponent associations
    if intercomponent_classes:
        for cls in oo.classes:
            referenced_intercomp: set[str] = set()
            for attr in cls.attributes:
                for ic in intercomponent_classes:
                    ic_bare = ic["qualified_name"].rsplit("::", 1)[-1]
                    if attr.type_signature and (ic_bare in attr.type_signature or ic["qualified_name"] in attr.type_signature):
                        referenced_intercomp.add(ic["qualified_name"])
            for method in cls.methods:
                if method.type_signature:
                    for ic in intercomponent_classes:
                        ic_bare = ic["qualified_name"].rsplit("::", 1)[-1]
                        if ic_bare in method.type_signature or ic["qualified_name"] in method.type_signature:
                            referenced_intercomp.add(ic["qualified_name"])

            if referenced_intercomp:
                assoc_targets = {assoc.object for assoc in oo.associations} | {assoc.subject for assoc in oo.associations}
                for ic_qname in referenced_intercomp:
                    if ic_qname not in assoc_targets:
                        ic_bare = ic_qname.rsplit("::", 1)[-1]
                        if ic_bare not in assoc_targets:
                            errors.append(
                                f"Missing intercomponent association: {cls.name} references "
                                f"{ic_qname} in attributes/methods but has no association to it."
                            )

    # Check 4: Disconnected design entities
    inbound: dict[str, set[str]] = {name: set() for name in all_design_names}
    outbound: dict[str, set[str]] = {name: set() for name in all_design_names}

    for assoc in oo.associations:
        if assoc.subject in all_design_names:
            if assoc.object in all_design_names:
                inbound[assoc.object].add(assoc.subject)
            outbound[assoc.subject].add(assoc.object)
        elif assoc.object in all_design_names:
            inbound[assoc.object].add(assoc.subject)

    for cls in oo.classes:
        for attr in cls.attributes:
            if attr.type_signature:
                extract_type_refs(attr.type_signature, all_design_names, outbound[cls.name])
        for method in cls.methods:
            if method.type_signature:
                extract_type_refs(method.type_signature, all_design_names, outbound[cls.name])
            if method.argsstring:
                inner = method.argsstring.strip("()")
                for param_text in inner.split(","):
                    param_text = param_text.strip()
                    if param_text:
                        extract_type_refs(param_text, all_design_names, outbound[cls.name])
        for parent in (cls.inherits_from or []):
            if parent in all_design_names:
                outbound[cls.name].add(parent)
                inbound[parent].add(cls.name)
        for iface in (cls.realizes or []):
            if iface in all_design_names:
                outbound[cls.name].add(iface)
                inbound[iface].add(cls.name)

    for iface in oo.interfaces:
        for method in iface.methods:
            if method.type_signature:
                extract_type_refs(method.type_signature, all_design_names, outbound[iface.name])
            if method.argsstring:
                inner = method.argsstring.strip("()")
                for param_text in inner.split(","):
                    param_text = param_text.strip()
                    if param_text:
                        extract_type_refs(param_text, all_design_names, outbound[iface.name])

    for entity_name, refs in outbound.items():
        for ref_name in refs:
            if ref_name in inbound and ref_name != entity_name:
                inbound[ref_name].add(entity_name)

    if len(all_design_names) > 1:
        disconnected = []
        for cls in oo.classes:
            if not inbound[cls.name] and not outbound[cls.name]:
                disconnected.append((cls.name, "class"))
        for iface in oo.interfaces:
            if not inbound[iface.name] and not outbound[iface.name]:
                disconnected.append((iface.name, "interface"))
        for enum in oo.enums:
            if not inbound[enum.name] and not outbound[enum.name]:
                disconnected.append((enum.name, "enum"))

        for name, kind in disconnected:
            errors.append(
                f"Disconnected {kind} \"{name}\" is not referenced by any association, "
                f"attribute type, method parameter/return type, inheritance, or interface, "
                f"and does not itself reference any other design entity. "
                f"Either remove it or connect it to the design."
            )

    return errors

def check_enum_collisions(design: ClassDiagram, prior_class_lookup: dict[str, str]) -> list[str]:
    """Warn if enum names collide with prior designs.

    Returns a list of warning strings. Empty list means no collisions.
    """
    warnings = []
    for enum in design.enums:
        enum_qname = f"{enum.module}::{enum.name}" if enum.module else enum.name
        if enum.name in prior_class_lookup:
            existing_qname = prior_class_lookup[enum.name]
            if existing_qname != enum_qname:
                warnings.append(
                    f"Enum '{enum.name}' already exists as '{existing_qname}' in a "
                    f"prior design. Consider referencing the existing enum or "
                    f"renaming yours to avoid confusion."
                )
    return warnings
