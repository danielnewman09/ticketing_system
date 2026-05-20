"""
Stage 2: deterministic mapping from OO design to ontology nodes + triples.

No LLM call — all mappings are mechanical.
"""

import logging
import re
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

from backend.codebase.schemas import (
    DesignSchema,
    OntologyNodeSchema,
    OntologyTripleSchema,
    OODesignSchema,
    RequirementTripleLinkSchema,
)


def _qualify(module: str, name: str) -> str:
    """Build a qualified name from module and name."""
    if module:
        return f"{module}::{name}"
    return name


def _parse_req_id(tagged: str) -> tuple[str, int] | None:
    """Parse a tagged requirement ID into ('hlr'|'llr', int).

    Accepts flexible formats produced by LLMs:
      'hlr:3', 'HLR 1', 'llr:7', 'LLR 2', 'HLR:3', etc.
    """
    m = re.match(r"^(hlr|llr)[\s:]+(\d+)$", tagged.strip(), re.IGNORECASE)
    if m:
        return m.group(1).lower(), int(m.group(2))
    return None


def map_oo_to_ontology(
    oo: OODesignSchema,
    component_id: int | None = None,
    prior_class_lookup: dict[str, str] | None = None,
    component_namespace: str = "",
    dependency_lookup: dict[str, str] | None = None,
) -> DesignSchema:
    """Map an OO design to ontology nodes, triples, and requirement links.

    Args:
        oo: The OO design output from Stage 1.
        component_id: Optional component FK to set on all output nodes.
        prior_class_lookup: name -> qualified_name mapping from previously
            designed HLRs, so cross-HLR references resolve correctly.
        component_namespace: Required namespace prefix. If set, modules that
            don't match are corrected to use this namespace.
        dependency_lookup: Mapping of dependency class bare names (e.g.
            "Fl_Button") to their qualified_name in the dependency graph
            (e.g. "Fl_Button"). Used to resolve references to dependency
            classes so that triples can link to the correct target node.
    """
    nodes: list[OntologyNodeSchema] = []
    triples: list[OntologyTripleSchema] = []
    links: list[RequirementTripleLinkSchema] = []

    # Track qualified_name -> index in nodes list for dedup
    node_index: dict[str, int] = {}

    def _add_node(kind, name, qualified_name, is_intercomponent=False, **kwargs):
        if qualified_name in node_index:
            return
        node_index[qualified_name] = len(nodes)
        nodes.append(
            OntologyNodeSchema(
                kind=kind,
                name=name,
                qualified_name=qualified_name,
                component_id=component_id,
                is_intercomponent=is_intercomponent,
                **kwargs,
            )
        )

    def _add_triple(subject_qname, predicate, object_qname):
        idx = len(triples)
        triples.append(
            OntologyTripleSchema(
                subject_qualified_name=subject_qname,
                predicate=predicate,
                object_qualified_name=object_qname,
            )
        )
        return idx

    def _link_reqs(tagged_ids, triple_idx):
        for tagged in tagged_ids:
            parsed = _parse_req_id(tagged)
            if parsed:
                req_type, req_id = parsed
                links.append(
                    RequirementTripleLinkSchema(
                        requirement_type=req_type,
                        requirement_id=req_id,
                        triple_index=triple_idx,
                    )
                )

    # --- Dependency lookup (bare name -> qualified_name) ---
    dep_lookup: dict[str, str] = dict(dependency_lookup or {})
    _TYPE_EXTRACT_RE = re.compile(r"\b([A-Z]\w+)\b")

    def _resolve_ref(name: str) -> str | None:
        """Resolve a class/interface name to a qualified name.

        Checks class_lookup (design-internal) first, then dep_lookup.
        Returns None if the name is not found in either.
        Creates a dependency stub node if the name resolves via dep_lookup.
        """
        if name in class_lookup:
            return class_lookup[name]
        if name in dep_lookup:
            qname = dep_lookup[name]
            # Create a dependency stub node if not already present
            if qname not in node_index:
                _add_node(
                    "class",
                    name,
                    qname,
                    is_intercomponent=True,
                    description=f"External dependency: {qname}",
                    source_type="dependency",
                )
            return qname
        return None

    def _add_depends_from_type(type_str: str, cls_qname: str, seen: set[str]):
        """Scan a type string for dependency class names and add depends_on triples."""
        if not type_str:
            return
        for match in _TYPE_EXTRACT_RE.finditer(type_str):
            name = match.group(1)
            if name in class_lookup:
                continue  # design-internal reference, not a dependency
            if name in dep_lookup:
                qname = dep_lookup[name]
                key = f"{cls_qname}->{qname}"
                if key not in seen:
                    seen.add(key)
                    # Ensure the dependency stub node exists
                    if qname not in node_index:
                        _add_node(
                            "class",
                            name,
                            qname,
                            is_intercomponent=True,
                            description=f"External dependency: {qname}",
                            source_type="dependency",
                        )
                    _add_triple(cls_qname, "depends_on", qname)

    # --- Correct modules to match component namespace ---
    if component_namespace:
        corrected_modules = set()
        for cls in oo.classes:
            if cls.module != component_namespace:
                log.info(
                    "Correcting class %s module %r -> %r",
                    cls.name,
                    cls.module,
                    component_namespace,
                )
                cls.module = component_namespace
            corrected_modules.add(cls.module)
        for iface in oo.interfaces:
            if iface.module != component_namespace:
                log.info(
                    "Correcting interface %s module %r -> %r",
                    iface.name,
                    iface.module,
                    component_namespace,
                )
                iface.module = component_namespace
            corrected_modules.add(iface.module)
        for enum in oo.enums:
            if enum.module != component_namespace:
                log.info(
                    "Correcting enum %s module %r -> %r",
                    enum.name,
                    enum.module,
                    component_namespace,
                )
                enum.module = component_namespace
            corrected_modules.add(enum.module)
        oo.modules = sorted(corrected_modules)

        # Correct cross-references that use wrong namespace prefixes.
        def _strip_wrong_ns(val: str) -> str:
            if "::" not in val:
                return val
            ns_part = val.rsplit("::", 1)[0]
            if ns_part == component_namespace:
                return val  # Already correct
            stripped = val.rsplit("::", 1)[-1]
            log.info("Correcting ref %r -> %r", val, stripped)
            return stripped

        for assoc in oo.associations:
            assoc.from_class = _strip_wrong_ns(assoc.from_class)
            assoc.to_class = _strip_wrong_ns(assoc.to_class)
        for cls in oo.classes:
            cls.inherits_from = [_strip_wrong_ns(p) for p in cls.inherits_from]
            cls.realizes_interfaces = [_strip_wrong_ns(i) for i in cls.realizes_interfaces]

    # --- Modules (source_type="namespace") ---
    for module in oo.modules:
        parts = module.split("::")
        for i in range(len(parts)):
            prefix = "::".join(parts[: i + 1])
            _add_node("module", parts[i], prefix, source_type="namespace")
            if i > 0:
                parent_prefix = "::".join(parts[:i])
                _add_triple(parent_prefix, "composes", prefix)

    # --- Interfaces (source_type="compound") ---
    for iface in oo.interfaces:
        iface_qname = _qualify(iface.module, iface.name)
        _add_node(
            "interface",
            iface.name,
            iface_qname,
            is_intercomponent=iface.is_intercomponent,
            specialization=iface.specialization,
            description=iface.description,
            source_type="compound",
            is_abstract=True,
        )
        if iface.module:
            _add_triple(iface.module, "composes", iface_qname)
        for method in iface.methods:
            method_qname = f"{iface_qname}::{method.name}"
            argsstring = f"({', '.join(method.parameters)})" if method.parameters else ""
            _add_node(
                "method",
                method.name,
                method_qname,
                visibility=method.visibility,
                description=method.description,
                source_type="member",
                type_signature=method.return_type,
                argsstring=argsstring,
                is_virtual=True,
            )
            _add_triple(iface_qname, "composes", method_qname)

    # --- Enums (source_type="compound") ---
    for enum in oo.enums:
        enum_qname = _qualify(enum.module, enum.name)
        _add_node(
            "enum",
            enum.name,
            enum_qname,
            description=enum.description,
            source_type="compound",
        )
        if enum.module:
            _add_triple(enum.module, "composes", enum_qname)
        for value in enum.values:
            val_qname = f"{enum_qname}::{value}"
            _add_node("enum_value", value, val_qname, source_type="member")
            _add_triple(enum_qname, "composes", val_qname)

    # --- Classes ---
    # Build a name -> qualified_name lookup for resolving references.
    # Seed with prior designs so cross-HLR references resolve correctly.
    class_lookup: dict[str, str] = dict(prior_class_lookup or {})
    for cls in oo.classes:
        class_lookup[cls.name] = _qualify(cls.module, cls.name)
    for iface in oo.interfaces:
        class_lookup[iface.name] = _qualify(iface.module, iface.name)

    for cls in oo.classes:
        cls_qname = _qualify(cls.module, cls.name)
        _add_node(
            "class",
            cls.name,
            cls_qname,
            is_intercomponent=cls.is_intercomponent,
            specialization=cls.specialization,
            description=cls.description,
            source_type="compound",
        )
        # Module composes class
        if cls.module:
            _add_triple(cls.module, "composes", cls_qname)

        # Attributes -> composes triples (source_type="member")
        for attr in cls.attributes:
            attr_qname = f"{cls_qname}::{attr.name}"
            _add_node(
                "attribute",
                attr.name,
                attr_qname,
                visibility=attr.visibility,
                description=attr.description,
                source_type="member",
                type_signature=attr.type_name,
            )
            triple_idx = _add_triple(cls_qname, "composes", attr_qname)
            _link_reqs(cls.requirement_ids, triple_idx)

        # Methods -> composes triples (source_type="member")
        for method in cls.methods:
            method_qname = f"{cls_qname}::{method.name}"
            argsstring = f"({', '.join(method.parameters)})" if method.parameters else ""
            _add_node(
                "method",
                method.name,
                method_qname,
                visibility=method.visibility,
                description=method.description,
                source_type="member",
                type_signature=method.return_type,
                argsstring=argsstring,
            )
            triple_idx = _add_triple(cls_qname, "composes", method_qname)
            _link_reqs(cls.requirement_ids, triple_idx)

        # Inheritance -> generalizes triples (with dependency resolution)
        for parent_name in cls.inherits_from:
            parent_qname = _resolve_ref(parent_name) or class_lookup.get(parent_name, parent_name)
            triple_idx = _add_triple(cls_qname, "generalizes", parent_qname)
            _link_reqs(cls.requirement_ids, triple_idx)

        # Interface realization -> realizes triples (with dependency resolution)
        for iface_name in cls.realizes_interfaces:
            iface_qname = _resolve_ref(iface_name) or class_lookup.get(iface_name, iface_name)
            triple_idx = _add_triple(cls_qname, "realizes", iface_qname)
            _link_reqs(cls.requirement_ids, triple_idx)

    # --- Dependency type inference from attribute types and return types ---
    for cls in oo.classes:
        cls_qname = _qualify(cls.module, cls.name)
        seen_dep_types: set[str] = set()
        for attr in cls.attributes:
            _add_depends_from_type(attr.type_name, cls_qname, seen_dep_types)
        for method in cls.methods:
            _add_depends_from_type(method.return_type, cls_qname, seen_dep_types)
            for param in method.parameters:
                _add_depends_from_type(param, cls_qname, seen_dep_types)

    # --- Associations (with dependency resolution) ---
    for assoc in oo.associations:
        from_qname = _resolve_ref(assoc.from_class) or class_lookup.get(assoc.from_class, assoc.from_class)
        to_qname = _resolve_ref(assoc.to_class) or class_lookup.get(assoc.to_class, assoc.to_class)
        triple_idx = _add_triple(from_qname, assoc.kind, to_qname)
        _link_reqs(assoc.requirement_ids, triple_idx)

    return DesignSchema(
        nodes=nodes,
        triples=triples,
        requirement_links=links,
    )


# ---------------------------------------------------------------------------
# Coverage validation
# ---------------------------------------------------------------------------


@dataclass
class CoverageReport:
    """Report on requirement-to-ontology coverage after mapping."""

    linked_hlrs: set[int] = field(default_factory=set)
    linked_llrs: set[int] = field(default_factory=set)
    unlinked_hlrs: set[int] = field(default_factory=set)
    unlinked_llrs: set[int] = field(default_factory=set)

    @property
    def fully_covered(self) -> bool:
        return not self.unlinked_hlrs and not self.unlinked_llrs


def validate_coverage(
    oo: OODesignSchema,
    hlr_ids: set[int],
    llr_ids: set[int],
) -> CoverageReport:
    """Check which requirements are linked to at least one design element.

    Args:
        oo: The OO design output from Stage 1.
        hlr_ids: All known HLR IDs.
        llr_ids: All known LLR IDs.
    """
    tagged_hlrs: set[int] = set()
    tagged_llrs: set[int] = set()

    def _collect(tagged_ids):
        for tagged in tagged_ids:
            parsed = _parse_req_id(tagged)
            if parsed:
                req_type, req_id = parsed
                if req_type == "hlr":
                    tagged_hlrs.add(req_id)
                else:
                    tagged_llrs.add(req_id)

    for cls in oo.classes:
        _collect(cls.requirement_ids)
    for assoc in oo.associations:
        _collect(assoc.requirement_ids)

    return CoverageReport(
        linked_hlrs=tagged_hlrs & hlr_ids,
        linked_llrs=tagged_llrs & llr_ids,
        unlinked_hlrs=hlr_ids - tagged_hlrs,
        unlinked_llrs=llr_ids - tagged_llrs,
    )