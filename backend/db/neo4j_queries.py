"""Read-side Neo4j queries returning plain dicts for the frontend."""

from __future__ import annotations

import logging

from backend.db.neo4j import get_neo4j_session

log = logging.getLogger(__name__)


def _make_node_data(n) -> dict:
    """Build a Cytoscape node-data dict from a Neo4j node."""
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


_VISIBILITY_PREFIX = {"private": "-", "protected": "#", "public": "+"}

# Member kinds that get collapsed into their owning class node
_COLLAPSIBLE_KINDS = {"attribute", "method", "variable", "function", "friend", "enum", "typedef"}

# Owner kinds whose members should be collapsed
_OWNER_KINDS = {"class", "interface", "enum", "struct"}


def _dedup_by_name(members: list[dict]) -> list[dict]:
    """Keep only the first member with each name (removes overloads)."""
    seen: set[str] = set()
    out: list[dict] = []
    for m in members:
        if m["name"] not in seen:
            seen.add(m["name"])
            out.append(m)
    return out


def _collapse_members(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """Collapse attributes and methods into their owning class/interface nodes.

    Members linked via COMPOSES or CONTAINS are removed as separate graph nodes
    and folded into the parent's label as a PlantUML-style compartment list
    using visibility prefixes (+ public, - private, # protected).

    For dependency-layer nodes, private members are hidden and overloaded
    methods (same name) are deduplicated.

    Handles both design-intent nodes (COMPOSES) and codebase nodes (CONTAINS).

    Returns the pruned (nodes, edges) tuple.
    """
    # Map codebase member kinds to design-intent kinds for grouping
    kind_normalize = {"variable": "attribute", "function": "method",
                      "friend": "attribute", "enum": "attribute", "typedef": "attribute"}

    node_by_id: dict[str, dict] = {n["data"]["id"]: n for n in nodes}

    # Collect members to collapse, keyed by owner node id
    collapsed: dict[str, dict[str, list[dict]]] = {}  # owner → {kind → [members]}
    remove_node_ids: set[str] = set()
    remove_edge_ids: set[str] = set()

    containment_rels = {"COMPOSES", "CONTAINS"}

    for e in edges:
        d = e["data"]
        if d["label"] not in containment_rels:
            continue
        target = node_by_id.get(d["target"])
        if target is None:
            continue
        td = target["data"]
        raw_kind = td["kind"]
        if raw_kind not in _COLLAPSIBLE_KINDS:
            continue
        owner_id = d["source"]
        owner = node_by_id.get(owner_id)
        if owner is None or owner["data"]["kind"] not in _OWNER_KINDS:
            continue

        is_dependency = td.get("layer") == "dependency"

        # For dependency nodes, only show public API
        if is_dependency and td.get("visibility") in ("private", "protected"):
            remove_node_ids.add(d["target"])
            remove_edge_ids.add(d["id"])
            continue

        norm_kind = kind_normalize.get(raw_kind, raw_kind)
        collapsed.setdefault(owner_id, {}).setdefault(norm_kind, []).append({
            "name": td["label"],
            "type_signature": td.get("type_signature", ""),
            "visibility": td.get("visibility", ""),
            "qualified_name": td.get("qualified_name", ""),
            "layer": td.get("layer", ""),
        })
        remove_node_ids.add(d["target"])
        remove_edge_ids.add(d["id"])

    if not collapsed:
        return nodes, edges

    # Also remove any other edges that reference a removed member node
    for e in edges:
        d = e["data"]
        if d["source"] in remove_node_ids or d["target"] in remove_node_ids:
            remove_edge_ids.add(d["id"])

    # Build UML-style compound labels
    for owner_id, by_kind in collapsed.items():
        owner = node_by_id[owner_id]
        od = owner["data"]
        is_dependency = od.get("layer") == "dependency"
        class_name = od["label"]
        separator = "─" * max(len(class_name), 10)
        lines = [class_name]

        # Attributes compartment
        attrs = by_kind.get("attribute", [])
        if attrs:
            if is_dependency:
                attrs = _dedup_by_name(attrs)
            lines.append(separator)
            attrs.sort(key=lambda a: a["name"])
            for a in attrs:
                vis = _VISIBILITY_PREFIX.get(a["visibility"], " ")
                sig = f": {a['type_signature']}" if a["type_signature"] else ""
                lines.append(f"{vis} {a['name']}{sig}")

        # Methods compartment
        methods = by_kind.get("method", [])
        if methods:
            if is_dependency:
                methods = _dedup_by_name(methods)
            lines.append(separator)
            methods.sort(key=lambda m: m["name"])
            for m in methods:
                vis = _VISIBILITY_PREFIX.get(m["visibility"], " ")
                sig = f": {m['type_signature']}" if m["type_signature"] else ""
                lines.append(f"{vis} {m['name']}(){sig}")

        od["label"] = "\n".join(lines)
        od["has_members"] = "true"
        member_count = len(attrs) + len(methods)
        od["member_count"] = member_count

    out_nodes = [n for n in nodes if n["data"]["id"] not in remove_node_ids]
    out_edges = [e for e in edges if e["data"]["id"] not in remove_edge_ids]
    return out_nodes, out_edges


def _fetch_component_namespaces() -> dict[str, str]:
    """Fetch Component namespace → name mapping from the database.

    Returns a dict of {namespace: component_name} for all components
    that have a namespace defined.
    """
    try:
        from backend.db import get_session
        from backend.db.models.components import Component
        with get_session() as session:
            return {
                c.namespace: c.name
                for c in session.query(Component).all()
                if c.namespace
            }
    except Exception:
        return {}


def _assign_namespace_parents(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """Group design nodes into namespace containers using Cytoscape parents.

    Uses Component namespaces as the source of truth when available.
    Falls back to qualified_name prefix inference for as-built codebase nodes.

    Works in three passes:
    1. If explicit module COMPOSES edges exist, convert them to parent fields.
    2. Use Component namespaces to create containers for design-intent nodes.
    3. For as-built nodes without a component, infer from qualified_name prefixes.

    Returns the updated (nodes, edges) tuple.
    """
    node_by_id: dict[str, dict] = {n["data"]["id"]: n for n in nodes}
    _CONTAINABLE = {"class", "interface", "enum", "module", "struct"}

    # --- Pass 1: explicit COMPOSES from module nodes ---
    remove_edge_ids: set[str] = set()
    assigned: set[str] = set()

    for e in edges:
        d = e["data"]
        if d["label"] != "COMPOSES":
            continue
        source = node_by_id.get(d["source"])
        target = node_by_id.get(d["target"])
        if source is None or target is None:
            continue
        sd = source["data"]
        td = target["data"]
        if sd["kind"] != "module" or td["kind"] not in _CONTAINABLE:
            continue
        td["parent"] = d["source"]
        sd["is_namespace"] = "true"
        remove_edge_ids.add(d["id"])
        assigned.add(d["target"])

    out_edges = [e for e in edges if e["data"]["id"] not in remove_edge_ids]

    # --- Pass 2: Component-based namespace containers ---
    component_ns = _fetch_component_namespaces()

    # Build synthetic namespace nodes from Components
    synth_ns: dict[str, str] = {}  # namespace → synthetic node id

    def _ensure_component_ns(ns: str) -> str | None:
        """Create or reuse a namespace container from a Component."""
        if ns in synth_ns:
            return synth_ns[ns]
        if ns not in component_ns:
            return None

        # Check if an existing module node already has this qualified_name
        for n in nodes:
            d = n["data"]
            if d.get("kind") == "module" and d.get("qualified_name") == ns:
                d["is_namespace"] = "true"
                d["label"] = component_ns[ns]  # Use component name as label
                synth_ns[ns] = d["id"]
                if "::" in ns:
                    parent_ns = ns.rsplit("::", 1)[0]
                    parent_id = _ensure_component_ns(parent_ns)
                    if parent_id:
                        d["parent"] = parent_id
                return d["id"]

        # No existing node — create a synthetic one
        node_id = f"ns_{ns}"
        short_name = component_ns[ns]
        new_node = {
            "data": {
                "id": node_id,
                "label": short_name,
                "qualified_name": ns,
                "kind": "module",
                "description": "",
                "visibility": "",
                "type_signature": "",
                "layer": "design",
                "is_namespace": "true",
            }
        }
        if "::" in ns:
            parent_ns = ns.rsplit("::", 1)[0]
            parent_id = _ensure_component_ns(parent_ns)
            if parent_id:
                new_node["data"]["parent"] = parent_id
        nodes.append(new_node)
        synth_ns[ns] = node_id
        return node_id

    # Assign component namespace parents to design nodes
    if component_ns:
        # Sort namespaces longest-first for most-specific matching
        sorted_ns = sorted(component_ns.keys(), key=len, reverse=True)
        for n in nodes:
            d = n["data"]
            if d["id"] in assigned or d.get("parent"):
                continue
            if d.get("layer") != "design":
                continue
            qn = d.get("qualified_name", "")
            for ns in sorted_ns:
                if qn.startswith(ns + "::") or qn == ns:
                    parent_id = _ensure_component_ns(ns)
                    if parent_id and parent_id != d["id"]:
                        d["parent"] = parent_id
                        assigned.add(d["id"])
                    break

    # --- Pass 3: fallback inference for as-built nodes only ---
    # Design-intent nodes MUST have a Component namespace; no fallback inference.
    ns_prefixes: dict[str, set[str]] = {}
    for n in nodes:
        d = n["data"]
        if d["id"] in assigned or d.get("parent"):
            continue
        if d.get("layer") != "as-built":
            continue
        qn = d.get("qualified_name", "")
        if "::" not in qn:
            continue
        ns = qn.rsplit("::", 1)[0]
        ns_prefixes.setdefault(ns, set()).add(d["id"])

    if ns_prefixes:
        def _ensure_ns(ns_qn: str) -> str:
            if ns_qn in synth_ns:
                return synth_ns[ns_qn]
            for n in nodes:
                d = n["data"]
                if d.get("kind") == "module" and d.get("qualified_name") == ns_qn:
                    d["is_namespace"] = "true"
                    synth_ns[ns_qn] = d["id"]
                    if "::" in ns_qn:
                        parent_ns = ns_qn.rsplit("::", 1)[0]
                        d["parent"] = _ensure_ns(parent_ns)
                    return d["id"]
            node_id = f"ns_{ns_qn}"
            short_name = ns_qn.rsplit("::", 1)[-1]
            new_node = {
                "data": {
                    "id": node_id,
                    "label": short_name,
                    "qualified_name": ns_qn,
                    "kind": "module",
                    "description": "",
                    "visibility": "",
                    "type_signature": "",
                    "layer": "as-built",
                    "is_namespace": "true",
                }
            }
            if "::" in ns_qn:
                parent_ns = ns_qn.rsplit("::", 1)[0]
                new_node["data"]["parent"] = _ensure_ns(parent_ns)
            nodes.append(new_node)
            synth_ns[ns_qn] = node_id
            return node_id

        for ns_qn, child_ids in ns_prefixes.items():
            parent_id = _ensure_ns(ns_qn)
            for cid in child_ids:
                node_by_id[cid]["data"]["parent"] = parent_id

    return nodes, out_edges


def fetch_design_graph(
    kind_filter: str | None = None,
    search: str | None = None,
    component_id: int | None = None,
) -> dict:
    """Fetch design-layer graph in Cytoscape.js format.

    Returns {"nodes": [...], "edges": [...]}.
    """
    conditions = ["n:Design"]
    params: dict = {}

    if kind_filter:
        conditions.append("n.kind = $kind")
        params["kind"] = kind_filter
    if component_id is not None:
        conditions.append("n.component_id = $comp_id")
        params["comp_id"] = component_id
    if search:
        conditions.append("(n.name CONTAINS $search OR n.qualified_name CONTAINS $search)")
        params["search"] = search

    where = " AND ".join(conditions)

    with get_neo4j_session() as session:
        # Nodes
        node_result = session.run(
            f"MATCH (n) WHERE {where} RETURN n",
            params,
        )
        nodes = []
        node_ids = set()
        for record in node_result:
            n = record["n"]
            node_ids.add(n.element_id)
            nodes.append({"data": _make_node_data(n)})

        # Edges between matched nodes
        edge_result = session.run(
            f"""
            MATCH (s)-[r]->(t)
            WHERE {where.replace('n:', 's:').replace('n.', 's.')}
              AND t:Design
              AND type(r) <> 'IMPLEMENTED_BY'
            RETURN s, r, t
            """,
            params,
        )
        edges = []
        for record in edge_result:
            s = record["s"]
            t = record["t"]
            r = record["r"]
            # Ensure target is in node set
            if t.element_id not in node_ids:
                node_ids.add(t.element_id)
                nodes.append({"data": _make_node_data(t)})
            edges.append({
                "data": {
                    "id": r.element_id,
                    "source": s.element_id,
                    "target": t.element_id,
                    "label": r.type,
                },
            })

        # Also fetch linked requirement nodes
        if node_ids:
            req_result = session.run("""
            MATCH (req)-[:TRACES_TO]->(d:Design)
            WHERE (req:HLR OR req:LLR)
              AND d.qualified_name IS NOT NULL
            RETURN DISTINCT req, d
            """)
            for record in req_result:
                req = record["req"]
                d = record["d"]
                if d.element_id in node_ids:
                    if req.element_id not in node_ids:
                        node_ids.add(req.element_id)
                        labels = list(req.labels)
                        req_type = "HLR" if "HLR" in labels else "LLR"
                        nodes.append({
                            "data": {
                                "id": req.element_id,
                                "label": f"{req_type} {req.get('sqlite_id', '')}",
                                "qualified_name": "",
                                "kind": req_type,
                                "description": req.get("title", ""),
                                "layer": "requirement",
                            },
                        })
                    edges.append({
                        "data": {
                            "id": f"traces_{req.element_id}_{d.element_id}",
                            "source": req.element_id,
                            "target": d.element_id,
                            "label": "TRACES_TO",
                        },
                    })

    # Collapse attributes/methods into class nodes, then group by namespace
    nodes, edges = _collapse_members(nodes, edges)
    nodes, edges = _assign_namespace_parents(nodes, edges)

    return {"nodes": nodes, "edges": edges}


def _make_codebase_node(n, kind_override: str = "") -> dict:
    """Build Cytoscape node-data dict from a codebase Neo4j node (Compound/Member)."""
    kind = kind_override or n.get("kind", "")
    return {
        "id": n.element_id,
        "label": n.get("name", ""),
        "qualified_name": n.get("qualified_name", ""),
        "kind": kind,
        "description": n.get("brief_description", "") or n.get("detailed_description", ""),
        "visibility": n.get("visibility", ""),
        "type_signature": n.get("type", ""),
        "argsstring": n.get("argsstring", ""),
        "layer": "as-built",
    }


def fetch_codebase_graph(
    search: str | None = None,
    namespace_filter: str | None = None,
) -> dict:
    """Fetch the as-built codebase graph (Compound/Member/Namespace) for Cytoscape.js.

    Returns {"nodes": [...], "edges": [...]}.
    """
    with get_neo4j_session() as session:
        nodes = []
        edges = []
        node_ids: set[str] = set()

        # Build optional filter
        conditions = []
        params: dict = {}
        if namespace_filter:
            conditions.append("c.qualified_name STARTS WITH $ns")
            params["ns"] = namespace_filter
        if search:
            conditions.append(
                "(c.name CONTAINS $search OR c.qualified_name CONTAINS $search)"
            )
            params["search"] = search

        where = " AND ".join(conditions)
        where_clause = f"WHERE {where}" if where else ""

        # Compounds + their Members (via CONTAINS)
        result = session.run(f"""
            MATCH (c:Compound) {where_clause}
            OPTIONAL MATCH (c)-[r:CONTAINS]->(m:Member)
            RETURN c, r, m
        """, params)

        for record in result:
            c = record["c"]
            if c.element_id not in node_ids:
                node_ids.add(c.element_id)
                nodes.append({"data": _make_codebase_node(c)})

            m = record["m"]
            r = record["r"]
            if m is not None and m.element_id not in node_ids:
                node_ids.add(m.element_id)
                nodes.append({"data": _make_codebase_node(m)})
            if r is not None and m is not None:
                edges.append({
                    "data": {
                        "id": r.element_id,
                        "source": c.element_id,
                        "target": m.element_id,
                        "label": "CONTAINS",
                    }
                })

        # Inter-compound relationships (INHERITS_FROM, CALLS between compounds)
        result2 = session.run(f"""
            MATCH (c1:Compound)-[r:INHERITS_FROM]->(c2:Compound)
            {where_clause.replace('c.', 'c1.')}
            RETURN c1, r, c2
        """, params)

        for record in result2:
            c1 = record["c1"]
            c2 = record["c2"]
            r = record["r"]
            for c in [c1, c2]:
                if c.element_id not in node_ids:
                    node_ids.add(c.element_id)
                    nodes.append({"data": _make_codebase_node(c)})
            edges.append({
                "data": {
                    "id": r.element_id,
                    "source": c1.element_id,
                    "target": c2.element_id,
                    "label": "INHERITS_FROM",
                }
            })

    # Collapse members into compounds, then group by namespace
    nodes, edges = _collapse_members(nodes, edges)
    nodes, edges = _assign_namespace_parents(nodes, edges)

    return {"nodes": nodes, "edges": edges}


def fetch_hlr_subgraph(hlr_id: int, component_id: int | None = None) -> dict:
    """Fetch the requirement neighbourhood of an HLR in Cytoscape.js format.

    Includes: the HLR node, its LLRs, any TRACES_TO design nodes, the
    component's design nodes and their inter-relationships.
    """
    with get_neo4j_session() as session:
        nodes = []
        edges = []
        node_ids: set[str] = set()

        def _add_node(element_id, data):
            if element_id not in node_ids:
                node_ids.add(element_id)
                nodes.append({"data": {**data, "id": element_id}})

        # 1. Verify HLR exists
        check = session.run(
            "MATCH (h:HLR {sqlite_id: $hid}) RETURN h", {"hid": hlr_id},
        ).single()
        if not check:
            return {"nodes": [], "edges": []}

        # 2. Design nodes traced from HLR/LLRs (requirements themselves excluded)
        trace_result = session.run("""
        MATCH (h:HLR {sqlite_id: $hid})
        OPTIONAL MATCH (h)-[:TRACES_TO]->(d1:Design)
        OPTIONAL MATCH (l:LLR)-[:DECOMPOSES]->(h)
        OPTIONAL MATCH (l)-[:TRACES_TO]->(d2:Design)
        WITH collect(DISTINCT d1) + collect(DISTINCT d2) AS designs
        UNWIND designs AS d
        WITH DISTINCT d WHERE d IS NOT NULL
        RETURN d
        """, {"hid": hlr_id})
        for record in trace_result:
            d = record["d"]
            _add_node(d.element_id, _make_node_data(d))

        # 3. Component design nodes + their inter-relationships
        if component_id is not None:
            comp_result = session.run("""
            MATCH (d:Design {component_id: $cid})
            OPTIONAL MATCH (d)-[r]->(d2:Design {component_id: $cid})
            WHERE type(r) <> 'IMPLEMENTED_BY'
            RETURN d, collect({rel: r, target: d2}) AS rels
            """, {"cid": component_id})
            for record in comp_result:
                d = record["d"]
                _add_node(d.element_id, _make_node_data(d))
                for item in record["rels"]:
                    r = item["rel"]
                    t = item["target"]
                    if r is None or t is None:
                        continue
                    _add_node(t.element_id, _make_node_data(t))
                    edges.append({"data": {
                        "id": r.element_id,
                        "source": d.element_id,
                        "target": t.element_id,
                        "label": r.type,
                    }})

    # Collapse members into class nodes, then group by namespace
    nodes, edges = _collapse_members(nodes, edges)
    nodes, edges = _assign_namespace_parents(nodes, edges)

    return {"nodes": nodes, "edges": edges}


def fetch_combined_graph(design_qnames: list[str]) -> dict:
    """Fetch design subgraph + linked as-built nodes via IMPLEMENTED_BY."""
    if not design_qnames:
        return {"nodes": [], "edges": []}

    with get_neo4j_session() as session:
        result = session.run("""
        UNWIND $qnames AS qn
        MATCH (d:Design {qualified_name: qn})
        OPTIONAL MATCH (d)-[impl:IMPLEMENTED_BY]->(code)
        OPTIONAL MATCH (d)-[r]->(d2:Design)
        RETURN d, impl, code, r, d2
        """, {"qnames": design_qnames})

        nodes = []
        edges = []
        seen_ids = set()

        for record in result:
            d = record["d"]
            if d.element_id not in seen_ids:
                seen_ids.add(d.element_id)
                nodes.append({
                    "data": {
                        "id": d.element_id,
                        "label": d.get("name", ""),
                        "qualified_name": d.get("qualified_name", ""),
                        "kind": d.get("kind", ""),
                        "layer": "design",
                    },
                })

            if record["code"] is not None:
                code = record["code"]
                if code.element_id not in seen_ids:
                    seen_ids.add(code.element_id)
                    labels = list(code.labels)
                    nodes.append({
                        "data": {
                            "id": code.element_id,
                            "label": code.get("name", code.get("qualified_name", "")),
                            "qualified_name": code.get("qualified_name", ""),
                            "kind": labels[0] if labels else "Unknown",
                            "layer": "as-built",
                        },
                    })
                impl = record["impl"]
                if impl is not None:
                    edges.append({
                        "data": {
                            "id": impl.element_id,
                            "source": d.element_id,
                            "target": code.element_id,
                            "label": "IMPLEMENTED_BY",
                        },
                    })

            if record["d2"] is not None:
                d2 = record["d2"]
                if d2.element_id not in seen_ids:
                    seen_ids.add(d2.element_id)
                    nodes.append({
                        "data": {
                            "id": d2.element_id,
                            "label": d2.get("name", ""),
                            "qualified_name": d2.get("qualified_name", ""),
                            "kind": d2.get("kind", ""),
                            "layer": "design",
                        },
                    })
                r = record["r"]
                if r is not None:
                    edges.append({
                        "data": {
                            "id": r.element_id,
                            "source": d.element_id,
                            "target": d2.element_id,
                            "label": r.type,
                        },
                    })

    return {"nodes": nodes, "edges": edges}


def fetch_neighbourhood_graph(qualified_name: str) -> dict:
    """Fetch the 1-hop neighbourhood of a Design node with collapsed members.

    Returns Cytoscape-format {"nodes": [...], "edges": [...]}.
    """
    with get_neo4j_session() as session:
        # Fetch center + all direct neighbours (both directions)
        result = session.run("""
        MATCH (center:Design {qualified_name: $qn})
        OPTIONAL MATCH (center)-[r_out]->(target)
        OPTIONAL MATCH (source)-[r_in]->(center)
        RETURN center,
               collect(DISTINCT {rel: r_out, target: target}) AS outs,
               collect(DISTINCT {rel: r_in, source: source}) AS ins
        """, {"qn": qualified_name})

        record = result.single()
        if not record:
            return {"nodes": [], "edges": []}

        nodes = []
        edges = []
        node_ids: set[str] = set()

        def _add(n, extra_data=None):
            if n is None or n.element_id in node_ids:
                return
            node_ids.add(n.element_id)
            d = _make_node_data(n)
            if extra_data:
                d.update(extra_data)
            nodes.append({"data": d})

        center = record["center"]
        _add(center, {"is_center": "true"})

        for item in record["outs"]:
            r = item["rel"]
            t = item["target"]
            if r is None or t is None:
                continue
            # Determine layer from labels
            labels = list(t.labels)
            layer = "design"
            if "HLR" in labels or "LLR" in labels:
                layer = "requirement"
            elif not any(l in labels for l in ("Design",)):
                layer = "as-built"
            _add(t, {"layer": layer})
            edges.append({"data": {
                "id": r.element_id,
                "source": center.element_id,
                "target": t.element_id,
                "label": r.type,
            }})

        for item in record["ins"]:
            r = item["rel"]
            s = item["source"]
            if r is None or s is None:
                continue
            labels = list(s.labels)
            layer = "design"
            if "HLR" in labels or "LLR" in labels:
                layer = "requirement"
            elif not any(l in labels for l in ("Design",)):
                layer = "as-built"
            _add(s, {"layer": layer})
            edges.append({"data": {
                "id": r.element_id,
                "source": s.element_id,
                "target": center.element_id,
                "label": r.type,
            }})

    nodes, edges = _collapse_members(nodes, edges)
    return {"nodes": nodes, "edges": edges}


def fetch_node_detail(qualified_name: str) -> dict | None:
    """Fetch full node properties + relationships + traced requirements + members."""
    with get_neo4j_session() as session:
        result = session.run("""
        MATCH (n:Design {qualified_name: $qn})
        OPTIONAL MATCH (n)-[r_out]->(target)
        OPTIONAL MATCH (source)-[r_in]->(n)
        RETURN n,
               collect(DISTINCT {rel: type(r_out), target_qn: target.qualified_name, target_name: target.name, target_labels: labels(target)}) AS outgoing,
               collect(DISTINCT {rel: type(r_in), source_qn: source.qualified_name, source_name: source.name, source_labels: labels(source)}) AS incoming
        """, {"qn": qualified_name})

        record = result.single()
        if not record:
            return None

        n = record["n"]
        props = dict(n)

        # Filter out null entries from collect
        outgoing = [
            r for r in record["outgoing"]
            if r["rel"] is not None
        ]
        incoming = [
            r for r in record["incoming"]
            if r["rel"] is not None
        ]

        # Extract traced requirements from incoming
        requirements = []
        relationships_in = []
        for r in incoming:
            labels = r.get("source_labels", [])
            if "HLR" in labels or "LLR" in labels:
                req_type = "HLR" if "HLR" in labels else "LLR"
                requirements.append({
                    "type": req_type,
                    "name": r.get("source_name", ""),
                    "relationship": r["rel"],
                })
            else:
                relationships_in.append(r)

        # Extract IMPLEMENTED_BY and COMPOSES members from outgoing
        implemented_by = []
        relationships_out = []
        member_qns = set()
        for r in outgoing:
            if r["rel"] == "IMPLEMENTED_BY":
                implemented_by.append({
                    "qualified_name": r.get("target_qn", ""),
                    "name": r.get("target_name", ""),
                    "labels": r.get("target_labels", []),
                })
            elif r["rel"] == "COMPOSES":
                member_qns.add(r.get("target_qn", ""))
            else:
                relationships_out.append(r)

        # Fetch full member details for COMPOSES targets
        members = _fetch_members(session, member_qns) if member_qns else []

        # Also try codebase CONTAINS members if this is a Compound
        codebase_members = _fetch_codebase_members(session, qualified_name)

        # Build available types from relationship targets + sibling types
        available_types = _fetch_available_types(
            session, qualified_name, relationships_out,
        )

        return {
            "properties": props,
            "outgoing": relationships_out,
            "incoming": relationships_in,
            "requirements": requirements,
            "implemented_by": implemented_by,
            "members": members,
            "codebase_members": codebase_members,
            "available_types": available_types,
        }


def _fetch_members(session, qualified_names: set[str]) -> list[dict]:
    """Fetch full properties for design-intent member nodes."""
    if not qualified_names:
        return []
    result = session.run("""
    UNWIND $qns AS qn
    MATCH (m:Design {qualified_name: qn})
    RETURN m
    """, {"qns": list(qualified_names)})
    members = []
    for record in result:
        m = record["m"]
        members.append({
            "name": m.get("name", ""),
            "qualified_name": m.get("qualified_name", ""),
            "kind": m.get("kind", ""),
            "visibility": m.get("visibility", ""),
            "type_signature": m.get("type_signature", ""),
            "argsstring": m.get("argsstring", ""),
            "description": m.get("description", ""),
        })
    return sorted(members, key=lambda m: (m["kind"], m["name"]))


def _fetch_codebase_members(session, qualified_name: str) -> list[dict]:
    """Fetch members from the codebase layer (Compound→CONTAINS→Member)."""
    result = session.run("""
    MATCH (c:Compound {qualified_name: $qn})-[:CONTAINS]->(m:Member)
    RETURN m
    """, {"qn": qualified_name})
    members = []
    for record in result:
        m = record["m"]
        members.append({
            "name": m.get("name", ""),
            "qualified_name": m.get("qualified_name", ""),
            "kind": m.get("kind", ""),
            "visibility": m.get("visibility", ""),
            "type_signature": m.get("type", ""),
            "argsstring": m.get("argsstring", ""),
            "description": m.get("brief_description", "") or m.get("detailed_description", ""),
        })
    return sorted(members, key=lambda m: (m["kind"], m["name"]))


def _fetch_available_types(
    session, qualified_name: str, outgoing_rels: list[dict],
) -> list[str]:
    """Build a list of type names available to a class for autocomplete.

    Sources (in order of priority):
    1. Direct relationship targets (ASSOCIATES, DEPENDS_ON, AGGREGATES, etc.)
       — these are types the class "knows about" (analogous to #include).
    2. Sibling types in the same namespace.
    3. Primitive/built-in types.
    """
    types: dict[str, str] = {}  # qualified_name → short_name

    # 1. Relationship targets — types this class depends on / associates with
    _DESIGN_RELS = {"ASSOCIATES", "DEPENDS_ON", "AGGREGATES", "GENERALIZES", "REALIZES"}
    for r in outgoing_rels:
        if r["rel"] in _DESIGN_RELS:
            tqn = r.get("target_qn", "")
            tname = r.get("target_name", "")
            if tqn:
                types[tqn] = tname

    # 2. Sibling types in the same namespace
    if "::" in qualified_name:
        ns = qualified_name.rsplit("::", 1)[0]
        result = session.run("""
        MATCH (d:Design)
        WHERE d.qualified_name STARTS WITH $prefix
          AND d.kind IN ['class', 'interface', 'enum', 'struct', 'type_alias']
          AND d.qualified_name <> $self
        RETURN d.qualified_name AS qn, d.name AS name
        """, {"prefix": ns + "::", "self": qualified_name})
        for record in result:
            qn = record["qn"]
            if qn not in types:
                types[qn] = record["name"]

    # 3. Built-in / primitive types
    builtins = [
        "void", "bool", "int", "double", "float", "char",
        "uint8_t", "uint16_t", "uint32_t", "uint64_t",
        "int8_t", "int16_t", "int32_t", "int64_t",
        "size_t", "std::string", "std::vector", "std::map",
        "std::optional", "std::shared_ptr", "std::unique_ptr",
    ]

    # Build completion list: qualified names + short names + builtins
    completions = set()
    for qn, name in types.items():
        completions.add(qn)
        completions.add(name)
    completions.update(builtins)

    return sorted(completions)


def _make_dependency_node(n) -> dict:
    """Build Cytoscape node-data dict from a dependency Neo4j node (Compound/Member)."""
    kind = n.get("kind", "")
    return {
        "id": n.element_id,
        "label": n.get("name", ""),
        "qualified_name": n.get("qualified_name", ""),
        "kind": kind,
        "description": n.get("brief_description", "") or n.get("detailed_description", ""),
        "visibility": n.get("protection", ""),
        "type_signature": n.get("type", ""),
        "argsstring": n.get("argsstring", ""),
        "source": n.get("source", ""),
        "layer": "dependency",
    }


def fetch_dependency_graph(
    search: str,
    source_filter: str | None = None,
    limit: int = 100,
) -> dict:
    """Fetch dependency-layer graph (external library symbols) for Cytoscape.js.

    Uses Neo4j full-text index (``doc_search``) for scored, Lucene-powered
    search across symbol names and documentation.  Requires a non-empty
    search string to prevent loading the entire dependency graph.

    Returns {"nodes": [...], "edges": [...]}.
    """
    if not search or not search.strip():
        return {"nodes": [], "edges": []}

    with get_neo4j_session() as session:
        nodes = []
        edges = []
        node_ids: set[str] = set()
        compound_ids: set[str] = set()

        # --- Step 1: full-text search to discover matching Compounds ----------
        # If a hit is a Member, resolve its owning Compound so we always
        # work with Compounds (just like the as-built layer).
        source_clause = "AND node.source CONTAINS $source_filter" if source_filter else ""
        params: dict = {"query": search.strip(), "limit": limit}
        if source_filter:
            params["source_filter"] = source_filter

        try:
            result = session.run(f"""
                CALL db.index.fulltext.queryNodes('doc_search', $query)
                YIELD node, score
                WHERE node.source IS NOT NULL AND node.source <> ''
                  {source_clause}
                WITH node, score
                ORDER BY score DESC
                LIMIT $limit
                WITH collect({{node: node, score: score}}) AS hits,
                     max(score) AS top_score
                UNWIND hits AS hit
                WITH hit.node AS node, hit.score AS score, top_score
                WHERE score >= top_score * 0.4
                WITH CASE
                    WHEN node:Compound THEN node
                    ELSE null
                END AS direct_compound, node
                OPTIONAL MATCH (owner:Compound)-[:CONTAINS]->(node)
                WHERE NOT node:Compound AND owner.source IS NOT NULL
                WITH coalesce(direct_compound, owner) AS c
                WHERE c IS NOT NULL
                RETURN DISTINCT c
            """, params)
        except Exception:
            log.warning("Full-text index 'doc_search' unavailable, falling back to CONTAINS search")
            fallback_where = "n.source IS NOT NULL AND n.source <> '' AND (n.name CONTAINS $search OR n.qualified_name CONTAINS $search)"
            if source_filter:
                fallback_where += " AND n.source CONTAINS $source_filter"
            result = session.run(f"""
                MATCH (n) WHERE ({fallback_where}) AND (n:Compound OR n:Member)
                WITH n LIMIT $limit
                WITH CASE WHEN n:Compound THEN n ELSE null END AS direct_compound, n
                OPTIONAL MATCH (owner:Compound)-[:CONTAINS]->(n)
                WHERE NOT n:Compound AND owner.source IS NOT NULL
                WITH coalesce(direct_compound, owner) AS c
                WHERE c IS NOT NULL
                RETURN DISTINCT c
            """, {"search": search.strip(), "limit": limit, "source_filter": source_filter})

        for record in result:
            c = record["c"]
            compound_ids.add(c.element_id)

        if not compound_ids:
            return {"nodes": [], "edges": []}

        # --- Step 2: direct inheritance only (1 up, 1 down) -------------------
        # Only show classes directly inheriting from/to matched compounds.
        result2 = session.run("""
            UNWIND $cids AS cid
            MATCH (c:Compound) WHERE elementId(c) = cid
            OPTIONAL MATCH (c)-[r1:INHERITS_FROM]->(base:Compound)
            OPTIONAL MATCH (derived:Compound)-[r2:INHERITS_FROM]->(c)
            RETURN c, r1, base, r2, derived
        """, {"cids": list(compound_ids)})

        edge_ids: set[str] = set()
        for record in result2:
            c = record["c"]
            compound_ids.add(c.element_id)

            base = record["base"]
            r1 = record["r1"]
            if base is not None:
                compound_ids.add(base.element_id)
                if r1 is not None and r1.element_id not in edge_ids:
                    edge_ids.add(r1.element_id)
                    edges.append({
                        "data": {
                            "id": r1.element_id,
                            "source": c.element_id,
                            "target": base.element_id,
                            "label": "INHERITS_FROM",
                        }
                    })

            derived = record["derived"]
            r2 = record["r2"]
            if derived is not None:
                compound_ids.add(derived.element_id)
                if r2 is not None and r2.element_id not in edge_ids:
                    edge_ids.add(r2.element_id)
                    edges.append({
                        "data": {
                            "id": r2.element_id,
                            "source": derived.element_id,
                            "target": c.element_id,
                            "label": "INHERITS_FROM",
                        }
                    })

        # --- Step 3: fetch all Compounds + their Members (same as as-built) ---
        result3 = session.run("""
            UNWIND $cids AS cid
            MATCH (c:Compound) WHERE elementId(c) = cid
            OPTIONAL MATCH (c)-[r:CONTAINS]->(m:Member)
            RETURN c, r, m
        """, {"cids": list(compound_ids)})

        for record in result3:
            c = record["c"]
            if c.element_id not in node_ids:
                node_ids.add(c.element_id)
                nodes.append({"data": _make_dependency_node(c)})

            m = record["m"]
            r = record["r"]
            if m is not None and m.element_id not in node_ids:
                node_ids.add(m.element_id)
                nodes.append({"data": _make_dependency_node(m)})
            if r is not None and m is not None:
                edges.append({
                    "data": {
                        "id": r.element_id,
                        "source": c.element_id,
                        "target": m.element_id,
                        "label": "CONTAINS",
                    }
                })

    # Collapse members into compounds, then group by namespace
    nodes, edges = _collapse_members(nodes, edges)
    nodes, edges = _assign_namespace_parents(nodes, edges)

    return {"nodes": nodes, "edges": edges}


def fetch_dependency_node_detail(qualified_name: str) -> dict | None:
    """Fetch full details for a dependency node (Compound/Member with source).

    Returns properties, members, inheritance, and links to Design nodes.
    """
    with get_neo4j_session() as session:
        # Try Compound first, then Member
        result = session.run("""
        MATCH (n:Compound {qualified_name: $qn})
        WHERE n.source IS NOT NULL AND n.source <> ''
        OPTIONAL MATCH (n)-[r_out]->(target)
        OPTIONAL MATCH (source)-[r_in]->(n)
        RETURN n,
               collect(DISTINCT {rel: type(r_out), target_qn: target.qualified_name, target_name: target.name, target_labels: labels(target)}) AS outgoing,
               collect(DISTINCT {rel: type(r_in), source_qn: source.qualified_name, source_name: source.name, source_labels: labels(source)}) AS incoming
        """, {"qn": qualified_name})

        record = result.single()
        if not record or record["n"] is None:
            # Try Member
            result = session.run("""
            MATCH (n:Member {qualified_name: $qn})
            WHERE n.source IS NOT NULL AND n.source <> ''
            OPTIONAL MATCH (c:Compound)-[:CONTAINS]->(n)
            RETURN n, c.qualified_name AS compound_qn, c.name AS compound_name
            """, {"qn": qualified_name})
            record = result.single()
            if not record:
                return None
            n = record["n"]
            props = dict(n)
            props["layer"] = "dependency"
            return {
                "properties": props,
                "outgoing": [],
                "incoming": [],
                "members": [],
                "design_links": [],
                "compound": {"qualified_name": record["compound_qn"], "name": record["compound_name"]} if record["compound_qn"] else None,
            }

        n = record["n"]
        props = dict(n)
        props["layer"] = "dependency"

        outgoing = [r for r in record["outgoing"] if r["rel"] is not None]
        incoming = [r for r in record["incoming"] if r["rel"] is not None]

        # Fetch members via CONTAINS
        members = _fetch_codebase_members(session, qualified_name)

        # Find Design nodes that reference this dependency (cross-layer links)
        design_result = session.run("""
        MATCH (d:Design)-[r]->(dep:Compound {qualified_name: $qn})
        WHERE dep.source IS NOT NULL AND dep.source <> ''
        RETURN d.qualified_name AS design_qn, d.name AS design_name, d.kind AS design_kind, type(r) AS rel
        """, {"qn": qualified_name})
        design_links = [dict(r) for r in design_result]

        # Also check by name match (Design nodes that DEPENDS_ON something with same qualified_name)
        if not design_links:
            design_result2 = session.run("""
            MATCH (d:Design)-[r:DEPENDS_ON]->(d2:Design)
            WHERE d2.qualified_name = $qn
            RETURN d.qualified_name AS design_qn, d.name AS design_name, d.kind AS design_kind, type(r) AS rel
            """, {"qn": qualified_name})
            design_links = [dict(r) for r in design_result2]

        return {
            "properties": props,
            "outgoing": [r for r in outgoing if r["rel"] not in ("CONTAINS",)],
            "incoming": [r for r in incoming if r["rel"] not in ("CONTAINS",)],
            "members": members,
            "design_links": design_links,
        }


def fetch_design_dependency_links(design_qnames: list[str]) -> dict:
    """Find dependency Compounds linked to given Design nodes.

    Uses query-time matching: checks if Design DEPENDS_ON targets match
    Compound nodes with a non-null source field.

    Returns Cytoscape-format {"nodes": [...], "edges": [...]}.
    """
    if not design_qnames:
        return {"nodes": [], "edges": []}

    with get_neo4j_session() as session:
        nodes = []
        edges = []
        node_ids: set[str] = set()

        # Direct relationships from Design to dependency Compounds
        result = session.run("""
        UNWIND $qnames AS qn
        MATCH (d:Design {qualified_name: qn})-[r]->(dep:Compound)
        WHERE dep.source IS NOT NULL AND dep.source <> ''
        RETURN d, r, dep
        """, {"qnames": design_qnames})

        for record in result:
            d = record["d"]
            dep = record["dep"]
            r = record["r"]

            if d.element_id not in node_ids:
                node_ids.add(d.element_id)
                nodes.append({"data": _make_node_data(d)})

            if dep.element_id not in node_ids:
                node_ids.add(dep.element_id)
                nodes.append({"data": _make_dependency_node(dep)})

            edges.append({
                "data": {
                    "id": r.element_id,
                    "source": d.element_id,
                    "target": dep.element_id,
                    "label": r.type,
                }
            })

        # Also check for Design→Design DEPENDS_ON where the target matches a dependency Compound by qualified_name
        result2 = session.run("""
        UNWIND $qnames AS qn
        MATCH (d:Design {qualified_name: qn})-[r:DEPENDS_ON]->(d2:Design)
        WITH d, r, d2
        MATCH (dep:Compound {qualified_name: d2.qualified_name})
        WHERE dep.source IS NOT NULL AND dep.source <> ''
        RETURN d, r, d2, dep
        """, {"qnames": design_qnames})

        for record in result2:
            d = record["d"]
            dep = record["dep"]

            if d.element_id not in node_ids:
                node_ids.add(d.element_id)
                nodes.append({"data": _make_node_data(d)})

            if dep.element_id not in node_ids:
                node_ids.add(dep.element_id)
                nodes.append({"data": _make_dependency_node(dep)})

            edges.append({
                "data": {
                    "id": f"dep_link_{d.element_id}_{dep.element_id}",
                    "source": d.element_id,
                    "target": dep.element_id,
                    "label": "DEPENDS_ON",
                }
            })

    return {"nodes": nodes, "edges": edges}


def fetch_design_stats() -> dict:
    """Counts for dashboard."""
    with get_neo4j_session() as session:
        result = session.run("""
        MATCH (d:Design)
        RETURN count(d) AS design_nodes,
               count(DISTINCT d.kind) AS kinds
        """)
        record = result.single()
        design_nodes = record["design_nodes"] if record else 0
        kinds = record["kinds"] if record else 0

        result2 = session.run("""
        MATCH (:Design)-[r]->(:Design)
        WHERE type(r) <> 'IMPLEMENTED_BY'
        RETURN count(r) AS design_rels
        """)
        record2 = result2.single()
        design_rels = record2["design_rels"] if record2 else 0

        result3 = session.run("""
        MATCH (:Design)-[:IMPLEMENTED_BY]->()
        RETURN count(*) AS implemented
        """)
        record3 = result3.single()
        implemented = record3["implemented"] if record3 else 0

        return {
            "design_nodes": design_nodes,
            "design_kinds": kinds,
            "design_relationships": design_rels,
            "implemented_links": implemented,
        }


def fetch_traceability(hlr_id: int) -> dict:
    """Full chain: HLR → LLRs → design nodes → as-built code."""
    with get_neo4j_session() as session:
        result = session.run("""
        MATCH (h:HLR {sqlite_id: $hid})
        OPTIONAL MATCH (l:LLR)-[:DECOMPOSES]->(h)
        OPTIONAL MATCH (h)-[:TRACES_TO]->(d:Design)
        OPTIONAL MATCH (l)-[:TRACES_TO]->(d2:Design)
        OPTIONAL MATCH (d)-[:IMPLEMENTED_BY]->(c1)
        OPTIONAL MATCH (d2)-[:IMPLEMENTED_BY]->(c2)
        RETURN h,
               collect(DISTINCT {id: l.sqlite_id, title: l.title}) AS llrs,
               collect(DISTINCT {qn: d.qualified_name, name: d.name, kind: d.kind}) AS hlr_design,
               collect(DISTINCT {qn: d2.qualified_name, name: d2.name, kind: d2.kind}) AS llr_design,
               collect(DISTINCT {qn: c1.qualified_name, name: c1.name}) AS hlr_code,
               collect(DISTINCT {qn: c2.qualified_name, name: c2.name}) AS llr_code
        """, {"hid": hlr_id})

        record = result.single()
        if not record:
            return {}

        return {
            "hlr": {"sqlite_id": record["h"].get("sqlite_id"), "title": record["h"].get("title", "")},
            "llrs": [l for l in record["llrs"] if l["id"] is not None],
            "hlr_design_nodes": [d for d in record["hlr_design"] if d["qn"] is not None],
            "llr_design_nodes": [d for d in record["llr_design"] if d["qn"] is not None],
            "hlr_code_nodes": [c for c in record["hlr_code"] if c["qn"] is not None],
            "llr_code_nodes": [c for c in record["llr_code"] if c["qn"] is not None],
        }
