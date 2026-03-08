/**
 * Shared Cytoscape.js configuration: colors, styles, and element builders.
 * Used by both the full ontology graph page and requirement detail graphs.
 */

const KIND_COLORS = {
    "class": "#4e79a7",
    "struct": "#59a14f",
    "enum": "#e15759",
    "union": "#f28e2b",
    "namespace": "#76b7b2",
    "interface": "#b07aa1",
    "concept": "#edc948",
    "hlr": "#ff7f0e",
    "llr": "#9467bd",
};

const DEFAULT_EDGE_COLOR = "#888";

const CYTOSCAPE_STYLES = [
    {
        selector: "node",
        style: {
            "label": "data(name)",
            "background-color": "data(color)",
            "shape": "data(shape)",
            "color": "#333",
            "font-size": "11px",
            "text-valign": "bottom",
            "text-margin-y": 6,
            "border-width": 2,
            "border-color": "#fff",
            "width": 28,
            "height": 28,
            "text-max-width": "100px",
            "text-wrap": "ellipsis",
        },
    },
    {
        selector: "node[url]",
        style: {
            "cursor": "pointer",
        },
    },
    {
        selector: "node:selected",
        style: {
            "border-width": 3,
            "border-color": "#333",
            "font-weight": "bold",
        },
    },
    {
        selector: "node.highlighted",
        style: {
            "border-width": 3,
            "border-color": "#ffc107",
            "font-weight": "bold",
            "z-index": 10,
        },
    },
    {
        selector: "node.faded",
        style: { "opacity": 0.15 },
    },
    {
        selector: "edge",
        style: {
            "width": 2,
            "line-color": "data(color)",
            "target-arrow-color": "data(color)",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            "label": "data(label)",
            "font-size": "9px",
            "color": "#666",
            "text-rotation": "autorotate",
            "text-margin-y": -10,
        },
    },
    {
        selector: "edge.faded",
        style: { "opacity": 0.1 },
    },
];

const COSE_DEFAULTS = {
    name: "cose",
    animate: true,
    animationDuration: 500,
    nodeRepulsion: () => 8000,
    idealEdgeLength: () => 120,
};

/**
 * Convert API graph data ({nodes, edges}) into Cytoscape elements array.
 */
function buildElements(data) {
    const elements = [];
    data.nodes.forEach(n => {
        elements.push({
            group: "nodes",
            data: {
                id: n.id,
                name: n.name,
                qualified_name: n.qualified_name || n.name,
                kind: n.kind,
                nodeGroup: n.group,
                compound_refid: n.compound_refid || "",
                description: n.description || "",
                url: n.url || "",
                color: KIND_COLORS[n.kind] || "#999",
                shape: n.group === "requirement" ? "round-rectangle" : "ellipse",
            },
        });
    });
    data.edges.forEach((e, i) => {
        elements.push({
            group: "edges",
            data: {
                id: `${e.source}-${e.predicate}-${e.target}-${i}`,
                source: e.source,
                target: e.target,
                label: e.predicate,
                color: DEFAULT_EDGE_COLOR,
            },
        });
    });
    return elements;
}
