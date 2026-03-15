/**
 * Shared Cytoscape.js configuration: colors, styles, and element builders.
 * Used by both the full ontology graph page and requirement detail graphs.
 */

const KIND_COLORS = {
    "attribute": "#9c755f",
    "class": "#4e79a7",
    "constant": "#edc948",
    "enum": "#e15759",
    "enum_value": "#ff9d9a",
    "function": "#bab0ac",
    "interface": "#b07aa1",
    "method": "#59a14f",
    "module": "#76b7b2",
    "primitive": "#a0cbe8",
    "type_alias": "#d37295",
};

const DEFAULT_EDGE_COLOR = "#888";

const CLASS_KINDS = new Set(["class", "interface"]);
const MEMBER_KINDS = new Set(["method", "attribute", "function", "constant"]);

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
    // --- Compound parent: generic (namespaces, modules) ---
    {
        selector: ":parent",
        style: {
            "shape": "round-rectangle",
            "background-color": "data(color)",
            "background-opacity": 0.12,
            "border-width": 2,
            "border-color": "data(color)",
            "border-opacity": 0.5,
            "text-valign": "top",
            "text-halign": "center",
            "text-margin-y": -4,
            "font-size": "13px",
            "font-weight": "bold",
            "padding": "20px",
        },
    },
    // --- Compound parent: class/interface nodes ---
    {
        selector: ":parent[kind='class'], :parent[kind='interface']",
        style: {
            "shape": "round-rectangle",
            "background-color": "data(color)",
            "background-opacity": 0.08,
            "border-width": 3,
            "border-color": "data(color)",
            "border-opacity": 0.7,
            "border-style": "solid",
            "padding": "25px",
            "text-valign": "top",
            "text-halign": "center",
            "text-margin-y": -6,
            "font-size": "14px",
            "font-weight": "bold",
        },
    },
    // --- Private/protected members: muted with dashed border ---
    {
        selector: "node[visibility='private']",
        style: {
            "border-style": "dashed",
            "border-color": "#999",
            "opacity": 0.6,
        },
    },
    {
        selector: "node[visibility='protected']",
        style: {
            "border-style": "dashed",
            "border-color": "#e8a838",
            "opacity": 0.7,
        },
    },
    // --- Public members: solid border accent ---
    {
        selector: "node[visibility='public']",
        style: {
            "border-color": "data(color)",
            "border-width": 2,
        },
    },
    // --- Collapsed class indicator (added by expand-collapse) ---
    {
        selector: "node.cy-expand-collapse-collapsed-node",
        style: {
            "shape": "round-rectangle",
            "width": 50,
            "height": 50,
            "border-width": 3,
            "border-color": "data(color)",
            "background-color": "data(color)",
            "background-opacity": 0.2,
            "font-size": "12px",
            "font-weight": "bold",
            "text-valign": "center",
            "text-halign": "center",
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

const FCOSE_DEFAULTS = {
    name: "fcose",
    animate: true,
    animationDuration: 500,
    quality: "default",
    randomize: true,
    nodeRepulsion: () => 8000,
    idealEdgeLength: () => 120,
    nodeSeparation: 80,
    packComponents: true,
};

// Keep cose defaults for pages that don't load fcose
const COSE_DEFAULTS = {
    name: "cose",
    animate: true,
    animationDuration: 500,
    nodeRepulsion: () => 8000,
    idealEdgeLength: () => 120,
};

/**
 * Return the best available compound-aware layout defaults.
 * Prefers fcose if registered, otherwise falls back to cose.
 */
function getLayoutDefaults() {
    if (typeof cytoscape !== "undefined") {
        try {
            // Check if fcose is registered
            cytoscape("layout", "fcose");
            return FCOSE_DEFAULTS;
        } catch (e) {
            // fcose not available
        }
    }
    return COSE_DEFAULTS;
}

/**
 * Convert API graph data ({nodes, edges}) into Cytoscape elements array.
 */
function buildElements(data) {
    const elements = [];
    data.nodes.forEach(n => {
        const nodeData = {
            id: n.id,
            name: n.name,
            qualified_name: n.qualified_name || n.name,
            kind: n.kind,
            visibility: n.visibility || "",
            nodeGroup: n.group,
            compound_refid: n.compound_refid || "",
            description: n.description || "",
            url: n.url || "",
            color: KIND_COLORS[n.kind] || "#999",
            shape: "ellipse",
        };
        if (n.parent) nodeData.parent = n.parent;
        elements.push({ group: "nodes", data: nodeData });
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
