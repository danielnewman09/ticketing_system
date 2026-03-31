"""Cytoscape node-data construction helpers and shared constants."""

from __future__ import annotations

_VISIBILITY_PREFIX = {"private": "-", "protected": "#", "public": "+"}

# Member kinds that get collapsed into their owning class node
_COLLAPSIBLE_KINDS = {"attribute", "method", "variable", "function", "friend", "enum", "typedef"}

# Owner kinds whose members should be collapsed
_OWNER_KINDS = {"class", "interface", "enum", "struct"}


def _make_node_data(n) -> dict:
    """Build a Cytoscape node-data dict from a Neo4j Design node."""
    return {
        "id": n.element_id,
        "label": n.get("name", ""),
        "qualified_name": n.get("qualified_name", ""),
        "kind": n.get("kind", ""),
        "description": n.get("description", ""),
        "component_id": n.get("component_id"),
        "visibility": n.get("visibility", ""),
        "type_signature": n.get("type_signature", ""),
        "layer": "design",
    }


def _make_compound_node(n, layer: str) -> dict:
    """Build Cytoscape node-data from a Compound/Member Neo4j node.

    *layer* is ``"dependency"`` or ``"as-built"``; the only behavioural
    difference is which property holds visibility.
    """
    is_dep = layer == "dependency"
    return {
        "id": n.element_id,
        "label": n.get("name", ""),
        "qualified_name": n.get("qualified_name", ""),
        "kind": n.get("kind", ""),
        "description": (
            n.get("brief_description", "") or n.get("detailed_description", "")
        ),
        "visibility": n.get("protection", "") if is_dep else n.get("visibility", ""),
        "type_signature": n.get("type", ""),
        "argsstring": n.get("argsstring", ""),
        "source": n.get("source", "") if is_dep else "",
        "layer": "dependency" if is_dep else "as-built",
    }


def _make_dependency_node(n) -> dict:
    """Build Cytoscape node-data dict from a dependency Neo4j node (Compound/Member)."""
    return {
        "id": n.element_id,
        "label": n.get("name", ""),
        "qualified_name": n.get("qualified_name", ""),
        "kind": n.get("kind", ""),
        "description": n.get("brief_description", "") or n.get("detailed_description", ""),
        "visibility": n.get("protection", ""),
        "type_signature": n.get("type", ""),
        "argsstring": n.get("argsstring", ""),
        "source": n.get("source", ""),
        "layer": "dependency",
    }
