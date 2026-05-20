"""Build Cytoscape.js node/edge dicts from raw Neo4j data."""


def build_cytoscape_node(raw: dict) -> dict:
    """Build a Cytoscape node-data dict from a raw Neo4j node dict.

    Handles design nodes, compound nodes, dependency nodes, and requirement nodes
    based on the ``layer`` key or available properties.
    """
    layer = raw.get("layer", "design")
    if layer == "dependency":
        return _build_dependency_node(raw)
    if layer == "codebase" or layer == "as-built":
        return _build_compound_node(raw, layer)
    return _build_design_node(raw)


def _build_design_node(d: dict) -> dict:
    return {
        "id": d.get("element_id", d.get("qualified_name", "")),
        "label": d.get("name", ""),
        "qualified_name": d.get("qualified_name", ""),
        "kind": d.get("kind", ""),
        "description": d.get("description", ""),
        "component_id": d.get("component_id"),
        "visibility": d.get("visibility", ""),
        "type_signature": d.get("type_signature", ""),
        "layer": "design",
        "source_type": d.get("source_type", ""),
        "requirements": d.get("requirements", []),
        "is_hlr_highlight": d.get("is_hlr_highlight", ""),
    }


def _build_compound_node(d: dict, layer: str) -> dict:
    """Build node data for codebase or dependency compound/member nodes."""
    return {
        "id": d.get("element_id", d.get("qualified_name", "")),
        "label": d.get("name", ""),
        "qualified_name": d.get("qualified_name", ""),
        "kind": d.get("kind", ""),
        "description": d.get("brief_description", "") or d.get("detailed_description", ""),
        "visibility": d.get("protection", "") if layer == "dependency" else d.get("visibility", ""),
        "type_signature": d.get("type", ""),
        "argsstring": d.get("argsstring", ""),
        "source": d.get("source", "") if layer == "dependency" else "",
        "layer": layer,
    }


def _build_dependency_node(d: dict) -> dict:
    return {
        "id": d.get("element_id", d.get("qualified_name", "")),
        "label": d.get("name", ""),
        "qualified_name": d.get("qualified_name", ""),
        "kind": d.get("kind", ""),
        "description": d.get("brief_description", "") or d.get("detailed_description", ""),
        "visibility": d.get("protection", ""),
        "type_signature": d.get("type", ""),
        "argsstring": d.get("argsstring", ""),
        "source": d.get("source", ""),
        "layer": "dependency",
    }


_edge_counter = 0


def build_cytoscape_edge(e: dict) -> dict:
    """Build a Cytoscape edge-data dict from a raw edge dict."""
    global _edge_counter
    _edge_counter += 1
    return {
        "id": f"e_{_edge_counter}_{e.get('source', '')}_{e.get('target', '')}_{e.get('type', '')}",
        "source": e.get("source", ""),
        "target": e.get("target", ""),
        "label": e.get("type", ""),
    }
