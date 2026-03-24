"""Read-side Neo4j queries returning plain dicts for the frontend."""

from __future__ import annotations

import logging

from db.neo4j import get_neo4j_session

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
_COLLAPSIBLE_KINDS = {"attribute", "method"}

# Owner kinds whose members should be collapsed
_OWNER_KINDS = {"class", "interface", "enum"}


def _collapse_members(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """Collapse attributes and methods into their owning class/interface nodes.

    Members linked via COMPOSES are removed as separate graph nodes and folded
    into the parent's label as a PlantUML-style compartment list using
    visibility prefixes (+ public, - private, # protected).

    Returns the pruned (nodes, edges) tuple.
    """
    node_by_id: dict[str, dict] = {n["data"]["id"]: n for n in nodes}

    # Collect members to collapse, keyed by owner node id
    collapsed: dict[str, dict[str, list[dict]]] = {}  # owner → {kind → [members]}
    remove_node_ids: set[str] = set()
    remove_edge_ids: set[str] = set()

    for e in edges:
        d = e["data"]
        if d["label"] != "COMPOSES":
            continue
        target = node_by_id.get(d["target"])
        if target is None:
            continue
        td = target["data"]
        if td["kind"] not in _COLLAPSIBLE_KINDS:
            continue
        owner_id = d["source"]
        owner = node_by_id.get(owner_id)
        if owner is None or owner["data"]["kind"] not in _OWNER_KINDS:
            continue
        collapsed.setdefault(owner_id, {}).setdefault(td["kind"], []).append({
            "name": td["label"],
            "type_signature": td.get("type_signature", ""),
            "visibility": td.get("visibility", ""),
            "qualified_name": td.get("qualified_name", ""),
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
        class_name = od["label"]
        separator = "─" * max(len(class_name), 10)
        lines = [class_name]

        # Attributes compartment
        attrs = by_kind.get("attribute", [])
        if attrs:
            lines.append(separator)
            attrs.sort(key=lambda a: a["name"])
            for a in attrs:
                vis = _VISIBILITY_PREFIX.get(a["visibility"], " ")
                sig = f": {a['type_signature']}" if a["type_signature"] else ""
                lines.append(f"{vis} {a['name']}{sig}")

        # Methods compartment
        methods = by_kind.get("method", [])
        if methods:
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


def _assign_namespace_parents(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """Group design nodes into namespace containers using Cytoscape parents.

    Works in two passes:
    1. If explicit module COMPOSES edges exist, convert them to parent fields.
    2. Otherwise, infer namespace grouping from qualified_name prefixes and
       synthesise lightweight namespace container nodes.

    Returns the updated (nodes, edges) tuple.
    """
    node_by_id: dict[str, dict] = {n["data"]["id"]: n for n in nodes}
    _CONTAINABLE = {"class", "interface", "enum", "module"}

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

    # --- Pass 2: infer from qualified_name for nodes without a parent ---
    # Collect all namespace prefixes from qualified names
    ns_prefixes: dict[str, set[str]] = {}  # prefix → set of child node ids
    for n in nodes:
        d = n["data"]
        if d["id"] in assigned or d.get("parent"):
            continue
        if d.get("layer") != "design":
            continue
        qn = d.get("qualified_name", "")
        if "::" not in qn:
            continue
        # The namespace is everything before the last ::
        ns = qn.rsplit("::", 1)[0]
        ns_prefixes.setdefault(ns, set()).add(d["id"])

    if not ns_prefixes:
        return nodes, out_edges

    # Build namespace hierarchy and create synthetic container nodes
    synth_ns: dict[str, str] = {}  # ns qualified_name → synthetic node id

    def _ensure_ns(ns_qn: str) -> str:
        """Ensure a synthetic namespace node exists, creating parents as needed."""
        if ns_qn in synth_ns:
            return synth_ns[ns_qn]
        # Check if an existing module node matches
        for n in nodes:
            d = n["data"]
            if d.get("kind") == "module" and d.get("qualified_name") == ns_qn:
                d["is_namespace"] = "true"
                synth_ns[ns_qn] = d["id"]
                # Recurse for parent namespace
                if "::" in ns_qn:
                    parent_ns = ns_qn.rsplit("::", 1)[0]
                    d["parent"] = _ensure_ns(parent_ns)
                return d["id"]

        # Create a synthetic namespace node
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
                "layer": "design",
                "is_namespace": "true",
            }
        }
        # Recurse for parent namespace
        if "::" in ns_qn:
            parent_ns = ns_qn.rsplit("::", 1)[0]
            new_node["data"]["parent"] = _ensure_ns(parent_ns)
        nodes.append(new_node)
        synth_ns[ns_qn] = node_id
        return node_id

    # Assign parents to all ungrouped nodes
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

        # 1. HLR + LLRs + DECOMPOSES edges
        req_result = session.run("""
        MATCH (h:HLR {sqlite_id: $hid})
        OPTIONAL MATCH (l:LLR)-[d:DECOMPOSES]->(h)
        RETURN h, collect({llr: l, rel: d}) AS decomps
        """, {"hid": hlr_id})
        record = req_result.single()
        if not record:
            return {"nodes": [], "edges": []}

        h = record["h"]
        _add_node(h.element_id, {
            "label": f"HLR {h.get('sqlite_id', '')}",
            "kind": "HLR",
            "layer": "requirement",
        })

        for item in record["decomps"]:
            llr = item["llr"]
            rel = item["rel"]
            if llr is None:
                continue
            _add_node(llr.element_id, {
                "label": f"LLR {llr.get('sqlite_id', '')}",
                "kind": "LLR",
                "layer": "requirement",
            })
            edges.append({"data": {
                "id": rel.element_id,
                "source": llr.element_id,
                "target": h.element_id,
                "label": "DECOMPOSES",
            }})

        # 2. TRACES_TO links from HLR/LLRs to Design nodes
        trace_result = session.run("""
        MATCH (h:HLR {sqlite_id: $hid})
        OPTIONAL MATCH (h)-[t1:TRACES_TO]->(d1:Design)
        OPTIONAL MATCH (l:LLR)-[:DECOMPOSES]->(h)
        OPTIONAL MATCH (l)-[t2:TRACES_TO]->(d2:Design)
        RETURN collect(DISTINCT {src: h, rel: t1, tgt: d1}) AS hlr_traces,
               collect(DISTINCT {src: l, rel: t2, tgt: d2}) AS llr_traces
        """, {"hid": hlr_id})
        tr = trace_result.single()
        for traces in [tr["hlr_traces"], tr["llr_traces"]]:
            for item in traces:
                if item["tgt"] is None:
                    continue
                d = item["tgt"]
                _add_node(d.element_id, {
                    "label": d.get("name", ""),
                    "qualified_name": d.get("qualified_name", ""),
                    "kind": d.get("kind", ""),
                    "layer": "design",
                })
                edges.append({"data": {
                    "id": item["rel"].element_id,
                    "source": item["src"].element_id,
                    "target": d.element_id,
                    "label": "TRACES_TO",
                }})

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
                _add_node(d.element_id, {
                    "label": d.get("name", ""),
                    "qualified_name": d.get("qualified_name", ""),
                    "kind": d.get("kind", ""),
                    "layer": "design",
                })
                for item in record["rels"]:
                    r = item["rel"]
                    t = item["target"]
                    if r is None or t is None:
                        continue
                    _add_node(t.element_id, {
                        "label": t.get("name", ""),
                        "qualified_name": t.get("qualified_name", ""),
                        "kind": t.get("kind", ""),
                        "layer": "design",
                    })
                    edges.append({"data": {
                        "id": r.element_id,
                        "source": d.element_id,
                        "target": t.element_id,
                        "label": r.type,
                    }})

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


def fetch_node_detail(qualified_name: str) -> dict | None:
    """Fetch full node properties + relationships + traced requirements."""
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

        # Extract IMPLEMENTED_BY from outgoing
        implemented_by = []
        relationships_out = []
        for r in outgoing:
            if r["rel"] == "IMPLEMENTED_BY":
                implemented_by.append({
                    "qualified_name": r.get("target_qn", ""),
                    "name": r.get("target_name", ""),
                    "labels": r.get("target_labels", []),
                })
            else:
                relationships_out.append(r)

        return {
            "properties": props,
            "outgoing": relationships_out,
            "incoming": relationships_in,
            "requirements": requirements,
            "implemented_by": implemented_by,
        }


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
