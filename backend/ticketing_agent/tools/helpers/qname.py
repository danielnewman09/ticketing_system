"""Qualified-name resolution and suggestion helpers."""


def qname_resolves(
    qname: str,
    draft_lookup: dict[str, dict] | None = None,
    prior_class_lookup: dict[str, str] | None = None,
    dep_lookup: dict[str, str] | None = None,
    intercomponent_classes: list[dict] | None = None,
    neo4j_session=None,
) -> bool:
    """Check whether a qualified name exists in the design context.

    Checks draft lookup, prior class lookup, dependency lookup,
    intercomponent classes, and (optionally) Neo4j persistent store.
    """
    if draft_lookup and qname in draft_lookup:
        return True
    if prior_class_lookup:
        if qname in prior_class_lookup.values():
            return True
        if qname in prior_class_lookup:
            return True
    if dep_lookup:
        if qname in dep_lookup:
            return True
        if qname in dep_lookup.values():
            return True
    if intercomponent_classes:
        ic_qnames = {c["qualified_name"] for c in intercomponent_classes}
        if qname in ic_qnames:
            return True
    if neo4j_session is not None:
        from backend.db.neo4j.repositories.design import DesignRepository

        repo = DesignRepository(neo4j_session)
        nodes = repo.find_nodes(search=qname, exclude_source_types=["verification"])
        if any(n.qualified_name == qname for n in nodes):
            return True
    return False


def suggest_qname(
    unresolved: str,
    draft_lookup: dict[str, dict],
    prior_class_lookup: dict[str, str],
    dep_lookup: dict[str, str],
    intercomponent_classes: list[dict],
) -> str | None:
    """Find the closest matching qualified name for an unresolved reference.

    Searches by bare name, member name, substring matching.
    Strips common stub suffixes (.output, .result, .return_value).

    Does NOT query Neo4j — only in-memory lookups for speed.
    """
    # Strip common stub suffixes
    cleaned = unresolved
    for suffix in (".output", ".result", ".return_value"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]

    # Strategy 1: bare name match in prior/dep lookups
    bare = cleaned.rsplit("::", 1)[-1].rsplit(".", 1)[-1]
    for name, qname in {**prior_class_lookup, **dep_lookup}.items():
        if name == bare or name.lower() == bare.lower():
            return qname

    # Strategy 2: member name match in draft
    for qname, info in draft_lookup.items():
        kind = info.get("kind", "")
        if kind in ("method", "variable") and qname.endswith(f"::{bare}"):
            return qname

    # Strategy 3: class/interface/enum name match in draft
    for qname, info in draft_lookup.items():
        kind = info.get("kind", "")
        if kind in ("class", "interface", "enum"):
            class_name = qname.rsplit("::", 1)[-1]
            if class_name == bare or class_name.lower() == bare.lower():
                return qname

    # Strategy 4: substring match in draft and dep lookups
    cleaned_lower = cleaned.lower()
    for qname in draft_lookup:
        if cleaned_lower in qname.lower():
            return qname
    for qname in dep_lookup.values():
        if cleaned_lower in qname.lower():
            return qname

    return None
