/**
 * Alpine.js component for the full ontology graph page.
 * Manages filters, layout switching, node details, and legend.
 */
function ontologyGraph(dataUrl) {
    return {
        cy: null,
        filterKind: "all",
        filterGroup: "all",
        search: "",
        layout: "cose",
        selectedNode: null,

        init() {
            this.buildLegend();
            fetch(dataUrl)
                .then(r => r.json())
                .then(data => {
                    if (data.nodes.length === 0) {
                        this.$refs.cy.innerHTML =
                            '<div class="d-flex align-items-center justify-content-center h-100 text-muted">No nodes yet. Add ontology nodes to see the graph.</div>';
                        return;
                    }
                    this.initGraph(data);
                });
        },

        initGraph(data) {
            const elements = buildElements(data);

            this.cy = cytoscape({
                container: this.$refs.cy,
                elements,
                style: CYTOSCAPE_STYLES,
                layout: { ...COSE_DEFAULTS },
                minZoom: 0.2,
                maxZoom: 5,
            });

            this.cy.on("tap", "node", evt => {
                this.selectNode(evt.target);
            });

            this.cy.on("tap", evt => {
                if (evt.target === this.cy) {
                    this.selectedNode = null;
                }
            });
        },

        selectNode(node) {
            const d = node.data();
            const incoming = node.incomers("edge");
            const outgoing = node.outgoers("edge");

            this.selectedNode = {
                qualified_name: d.qualified_name,
                kind: d.kind,
                nodeGroup: d.nodeGroup,
                description: d.description,
                compound_refid: d.compound_refid,
                outgoing: outgoing.map(e => ({
                    label: e.data("label"),
                    target: e.target().data("name"),
                })),
                incoming: incoming.map(e => ({
                    label: e.data("label"),
                    source: e.source().data("name"),
                })),
            };
        },

        applyFilters() {
            if (!this.cy) return;
            const kind = this.filterKind;
            const group = this.filterGroup;
            const search = this.search.toLowerCase().trim();

            this.cy.batch(() => {
                this.cy.elements().removeClass("faded highlighted");

                let matched = this.cy.nodes();
                if (kind !== "all") {
                    matched = matched.filter(n => n.data("kind") === kind);
                }
                if (group !== "all") {
                    matched = matched.filter(n => n.data("nodeGroup") === group);
                }
                if (search) {
                    matched = matched.filter(n =>
                        n.data("name").toLowerCase().includes(search) ||
                        n.data("qualified_name").toLowerCase().includes(search)
                    );
                }

                if (kind !== "all" || group !== "all" || search) {
                    this.cy.elements().addClass("faded");
                    const neighborhood = matched
                        .union(matched.connectedEdges())
                        .union(matched.connectedEdges().connectedNodes());
                    neighborhood.removeClass("faded");
                    matched.addClass("highlighted");
                }
            });
        },

        changeLayout() {
            if (!this.cy) return;
            const opts = { name: this.layout, animate: true, animationDuration: 500 };
            if (this.layout === "cose") {
                opts.nodeRepulsion = () => 8000;
                opts.idealEdgeLength = () => 120;
            }
            if (this.layout === "breadthfirst") opts.spacingFactor = 1.5;
            if (this.layout === "concentric") {
                opts.concentric = n => n.connectedEdges().length;
                opts.levelWidth = () => 2;
            }
            this.cy.layout(opts).run();
        },

        fit() {
            if (this.cy) this.cy.fit(null, 30);
        },

        reset() {
            this.filterKind = "all";
            this.filterGroup = "all";
            this.search = "";
            this.selectedNode = null;
            if (this.cy) {
                this.cy.elements().removeClass("faded highlighted");
                this.layout = "cose";
                this.cy.layout({ ...COSE_DEFAULTS }).run();
            }
        },

        buildLegend() {
            const el = this.$refs.legend;
            function section(title, items, shape) {
                const heading = document.createElement("div");
                heading.className = "fw-bold small mb-1" + (title !== "Ontology Nodes" ? " mt-2" : "");
                heading.textContent = title;
                el.appendChild(heading);
                items.forEach(([, label, color]) => {
                    const row = document.createElement("div");
                    row.className = "d-flex align-items-center gap-2 ms-2 small";
                    const swatch = document.createElement("span");
                    swatch.style.display = "inline-block";
                    swatch.style.width = shape === "line" ? "16px" : "12px";
                    swatch.style.height = shape === "line" ? "3px" : (shape === "rect" ? "10px" : "12px");
                    swatch.style.borderRadius = shape === "circle" ? "50%" : (shape === "rect" ? "2px" : "0");
                    swatch.style.background = color;
                    row.appendChild(swatch);
                    const text = document.createElement("span");
                    text.textContent = label;
                    row.appendChild(text);
                    el.appendChild(row);
                });
            }
            section("Ontology Nodes", [
                ["class", "Class", KIND_COLORS.class],
                ["struct", "Struct", KIND_COLORS.struct],
                ["enum", "Enum", KIND_COLORS.enum],
                ["union", "Union", KIND_COLORS.union],
                ["namespace", "Namespace", KIND_COLORS.namespace],
                ["interface", "Interface", KIND_COLORS.interface],
                ["concept", "Concept", KIND_COLORS.concept],
            ], "circle");
            section("Requirements", [
                ["hlr", "High-Level Req", KIND_COLORS.hlr],
                ["llr", "Low-Level Req", KIND_COLORS.llr],
            ], "rect");
            section("Edges", [
                ["triple", "Predicate (triple)", DEFAULT_EDGE_COLOR],
            ], "line");
        },
    };
}
