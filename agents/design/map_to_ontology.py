"""
Stage 2: deterministic mapping from OO design to ontology nodes + triples.

No LLM call — all mappings are mechanical.
"""

import re
from dataclasses import dataclass, field

from codebase.schemas import (
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
    """Parse a tagged requirement ID like 'hlr:3' into ('hlr', 3)."""
    m = re.match(r"^(hlr|llr):(\d+)$", tagged.strip())
    if m:
        return m.group(1), int(m.group(2))
    return None


def map_oo_to_ontology(
    oo: OODesignSchema,
    component_id: int | None = None,
    prior_class_lookup: dict[str, str] | None = None,
) -> DesignSchema:
    """Map an OO design to ontology nodes, triples, and requirement links.

    Args:
        oo: The OO design output from Stage 1.
        component_id: Optional component FK to set on all output nodes.
        prior_class_lookup: name -> qualified_name mapping from previously
            designed HLRs, so cross-HLR references resolve correctly.
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
        nodes.append(OntologyNodeSchema(
            kind=kind,
            name=name,
            qualified_name=qualified_name,
            component_id=component_id,
            is_intercomponent=is_intercomponent,
            **kwargs,
        ))

    def _add_triple(subject_qname, predicate, object_qname):
        idx = len(triples)
        triples.append(OntologyTripleSchema(
            subject_qualified_name=subject_qname,
            predicate=predicate,
            object_qualified_name=object_qname,
        ))
        return idx

    def _link_reqs(tagged_ids, triple_idx):
        for tagged in tagged_ids:
            parsed = _parse_req_id(tagged)
            if parsed:
                req_type, req_id = parsed
                links.append(RequirementTripleLinkSchema(
                    requirement_type=req_type,
                    requirement_id=req_id,
                    triple_index=triple_idx,
                ))

    # --- Modules ---
    for module in oo.modules:
        parts = module.split("::")
        for i in range(len(parts)):
            prefix = "::".join(parts[: i + 1])
            _add_node("module", parts[i], prefix)

    # --- Interfaces ---
    for iface in oo.interfaces:
        iface_qname = _qualify(iface.module, iface.name)
        _add_node(
            "interface", iface.name, iface_qname,
            is_intercomponent=iface.is_intercomponent,
            specialization=iface.specialization,
            description=iface.description,
        )
        for method in iface.methods:
            method_qname = f"{iface_qname}::{method.name}"
            _add_node(
                "method", method.name, method_qname,
                visibility=method.visibility,
                description=method.description,
            )
            _add_triple(iface_qname, "composes", method_qname)

    # --- Enums ---
    for enum in oo.enums:
        enum_qname = _qualify(enum.module, enum.name)
        _add_node("enum", enum.name, enum_qname, description=enum.description)
        for value in enum.values:
            val_qname = f"{enum_qname}::{value}"
            _add_node("enum_value", value, val_qname)
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
            "class", cls.name, cls_qname,
            is_intercomponent=cls.is_intercomponent,
            specialization=cls.specialization,
            description=cls.description,
        )

        # Attributes -> composes triples
        for attr in cls.attributes:
            attr_qname = f"{cls_qname}::{attr.name}"
            _add_node(
                "attribute", attr.name, attr_qname,
                visibility=attr.visibility,
                description=attr.description,
            )
            triple_idx = _add_triple(cls_qname, "composes", attr_qname)
            _link_reqs(cls.requirement_ids, triple_idx)

        # Methods -> composes triples
        for method in cls.methods:
            method_qname = f"{cls_qname}::{method.name}"
            _add_node(
                "method", method.name, method_qname,
                visibility=method.visibility,
                description=method.description,
            )
            triple_idx = _add_triple(cls_qname, "composes", method_qname)
            _link_reqs(cls.requirement_ids, triple_idx)

        # Inheritance -> generalizes triples
        for parent_name in cls.inherits_from:
            parent_qname = class_lookup.get(parent_name, parent_name)
            triple_idx = _add_triple(cls_qname, "generalizes", parent_qname)
            _link_reqs(cls.requirement_ids, triple_idx)

        # Interface realization -> realizes triples
        for iface_name in cls.realizes_interfaces:
            iface_qname = class_lookup.get(iface_name, iface_name)
            triple_idx = _add_triple(cls_qname, "realizes", iface_qname)
            _link_reqs(cls.requirement_ids, triple_idx)

    # --- Associations ---
    for assoc in oo.associations:
        from_qname = class_lookup.get(assoc.from_class, assoc.from_class)
        to_qname = class_lookup.get(assoc.to_class, assoc.to_class)
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
