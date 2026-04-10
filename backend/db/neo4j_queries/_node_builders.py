"""Cytoscape node-data construction helpers and shared constants."""

from __future__ import annotations

_VISIBILITY_PREFIX = {"private": "-", "protected": "#", "public": "+"}

# Member kinds that get collapsed into their owning class node
_COLLAPSIBLE_KINDS = {"attribute", "method", "variable", "function", "friend", "enum", "typedef"}

# Owner kinds whose members should be collapsed
_OWNER_KINDS = {"class", "interface", "enum", "struct"}


def _build_node(n: dict, layer: str) -> dict:
    """Build Cytoscape node-data from a Neo4j element.
    
    Unified builder for all ontology graph layers (design, codebase, dependency, requirement).
    
    Args:
        n: Neo4j node element as dict
        layer: One of "design", "codebase", "dependency", or "requirement"
    
    Returns:
        dict with node data in Cytoscape.js format
    """
    # Common fields for all layers
    base = {
        "id": n.element_id,
        "label": n.get("name", ""),
        "qualified_name": n.get("qualified_name", ""),
        "kind": n.get("kind", ""),
        "layer": layer,
    }
    
    # Layer-specific field mapping
    if layer == "design":
        return _build_design_node(base, n)
    elif layer in ("codebase", "dependency"):
        return _build_compound_node(base, n, layer)
    elif layer == "requirement":
        return _build_requirement_node(base, n)
    else:
        # Unknown layer - return base fields
        return base


def _build_design_node(base: dict, n: dict) -> dict:
    """Build node data for Design layer.
    
    Unified schema: Compound/Member nodes with layer="design".
    """
    return {
        **base,
        "description": n.get("description", ""),
        "component_id": n.get("component_id"),
        "visibility": n.get("visibility", ""),
        "type_signature": n.get("type_signature", ""),
        "layer": "design",
    }


def _build_compound_node(base: dict, n: dict, layer: str) -> dict:
    """Build node data for Compound/Member nodes in codebase or dependency layers."""
    is_dep = layer == "dependency"
    
    # Description: prefer brief_description, fallback to detailed_description
    description = n.get("brief_description", "") or n.get("detailed_description", "")
    
    # Visibility: protection for dependency, visibility for codebase
    visibility = n.get("protection", "") if is_dep else n.get("visibility", "")
    
    result = {
        **base,
        "description": description,
        "visibility": visibility,
        "type_signature": n.get("type", ""),
        "argsstring": n.get("argsstring", ""),
    }
    
    # Add source field for dependency layer
    if is_dep:
        result["source"] = n.get("source", "")
    
    return result


def _build_requirement_node(base: dict, n: dict) -> dict:
    """Build node data for requirement (HLR/LLR) nodes."""
    # Determine requirement type
    labels = n.get("labels", [])
    req_type = "HLR" if "HLR" in labels else "LLR"
    
    return {
        **base,
        "label": f"{req_type} {n.get('sqlite_id', '')}",
        "description": n.get("title", ""),
        "kind": req_type,
    }


# ============================================================================
# Legacy functions (deprecated - use _build_node() instead)
# ============================================================================

def _make_node_data(n) -> dict:
    """Build a Cytoscape node-data dict from a Neo4j Design node.
    
    Deprecated: Use _build_node(n, "design") instead.
    """
    return _build_node(n, "design")


def _make_compound_node(n, layer: str) -> dict:
    """Build Cytoscape node-data from a Compound/Member Neo4j node.

    Deprecated: Use _build_node(n, layer) instead.
    
    *layer* is ``"dependency"`` or ``"as-built"``; the only behavioural
    difference is which property holds visibility.
    """
    return _build_node(n, layer)


def _make_dependency_node(n) -> dict:
    """Build Cytoscape node-data dict from a dependency Neo4j node (Compound/Member).
    
    Deprecated: Use _build_node(n, "dependency") instead.
    """
    return _build_node(n, "dependency")
