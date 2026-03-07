const KIND_COLORS = {
    "class": "#4e79a7", "struct": "#59a14f", "enum": "#e15759",
    "union": "#f28e2b", "namespace": "#76b7b2", "interface": "#b07aa1",
    "concept": "#edc948", "hlr": "#ff7f0e", "llr": "#9467bd",
};
const EDGE_COLORS = {
    "inherits": "#e15759", "composes": "#4e79a7", "aggregates": "#59a14f",
    "depends_on": "#999", "calls": "#f28e2b", "implements": "#b07aa1",
    "uses": "#76b7b2", "actor": "#ff7f0e", "subject": "#9467bd",
};

function loadRequirementGraph(url) {
    fetch(url)
        .then(r => r.json())
        .then(data => {
            if (data.nodes.length <= 1) {
                document.getElementById("cy").innerHTML =
                    '<div class="d-flex align-items-center justify-content-center h-100 text-muted small">No ontology connections for this requirement.</div>';
                return;
            }

            const elements = [];
            data.nodes.forEach(n => {
                elements.push({
                    group: "nodes",
                    data: {
                        id: n.id, name: n.name,
                        qualified_name: n.qualified_name || n.name,
                        kind: n.kind, nodeGroup: n.group,
                        description: n.description || "",
                        color: KIND_COLORS[n.kind] || "#999",
                        shape: n.group === "requirement" ? "round-rectangle" : "ellipse",
                    },
                });
            });
            data.edges.forEach(e => {
                elements.push({
                    group: "edges",
                    data: {
                        id: e.source + "-" + e.relationship + "-" + e.target,
                        source: e.source, target: e.target,
                        relationship: e.relationship,
                        label: e.label || e.relationship,
                        color: EDGE_COLORS[e.relationship] || "#999",
                        dashed: (e.relationship === "actor" || e.relationship === "subject"),
                    },
                });
            });

            cytoscape({
                container: document.getElementById("cy"),
                elements: elements,
                style: [
                    {
                        selector: "node",
                        style: {
                            "label": "data(name)", "background-color": "data(color)",
                            "shape": "data(shape)", "color": "#333", "font-size": "11px",
                            "text-valign": "bottom", "text-margin-y": 6,
                            "border-width": 2, "border-color": "#fff",
                            "width": 32, "height": 32,
                        },
                    },
                    {
                        selector: "edge",
                        style: {
                            "width": 2, "line-color": "data(color)",
                            "target-arrow-color": "data(color)",
                            "target-arrow-shape": "triangle",
                            "curve-style": "bezier",
                            "label": "data(label)", "font-size": "9px",
                            "color": "#666", "text-rotation": "autorotate",
                            "text-margin-y": -10,
                        },
                    },
                    {
                        selector: "edge[?dashed]",
                        style: { "line-style": "dashed", "line-dash-pattern": [6, 3] },
                    },
                ],
                layout: {
                    name: "cose", animate: true, animationDuration: 400,
                    nodeRepulsion: function() { return 6000; },
                    idealEdgeLength: function() { return 100; },
                },
                minZoom: 0.3, maxZoom: 4,
            });
        });
}
