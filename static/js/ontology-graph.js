/**
 * Alpine.js component for the full ontology graph page.
 * Manages filters, layout switching, node details, legend, and
 * expand/collapse for class compound nodes.
 */
function ontologyGraph(dataUrl) {
    return {
        cy: null,
        api: null, // expand-collapse API
        filterKind: "all",
        search: "",
        layout: "fcose",
        selectedNode: null,
        showPrivate: false,

        init() {
            this.buildLegend();
            this.loadGraph();
        },

        loadGraph() {
            const url = this.showPrivate
                ? dataUrl + "?show_private=1"
                : dataUrl;

            fetch(url)
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
            const layoutDefaults = getLayoutDefaults();

            // Destroy previous instance if reloading
            if (this.cy) {
                this.cy.destroy();
                this.cy = null;
                this.api = null;
            }

            this.cy = cytoscape({
                container: this.$refs.cy,
                elements,
                style: CYTOSCAPE_STYLES,
                layout: { ...layoutDefaults },
                minZoom: 0.2,
                maxZoom: 5,
            });

            // Initialize expand-collapse if available
            if (typeof cytoscape !== "undefined" && this.cy.expandCollapse) {
                this.api = this.cy.expandCollapse({
                    layoutBy: { ...layoutDefaults, animate: true, randomize: false },
                    fisheye: false,
                    animate: true,
                    animationDuration: 300,
                    undoable: false,
                    cueEnabled: true,
                    expandCueImage: undefined,
                    collapseCueImage: undefined,
                    expandCuePosition: "top-left",
                    collapseCuePosition: "top-left",
                });

                // Collapse all class/interface compound nodes by default
                const classParents = this.cy.nodes(":parent").filter(
                    n => CLASS_KINDS.has(n.data("kind"))
                );
                if (classParents.length > 0) {
                    this.api.collapseAll();
                }
            }

            this.cy.on("tap", "node", evt => {
                this.selectNode(evt.target);
            });

            this.cy.on("dbltap", "node", evt => {
                const node = evt.target;
                // Double-click on collapsed class: expand it
                if (this.api && node.hasClass("cy-expand-collapse-collapsed-node")) {
                    this.api.expand(node);
                    return;
                }
                // Double-click on expanded class parent: collapse it
                if (this.api && node.isParent() && CLASS_KINDS.has(node.data("kind"))) {
                    this.api.collapse(node);
                    return;
                }
                // Otherwise navigate to detail
                const url = node.data("url");
                if (url) window.location.href = url;
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

            const children = node.children().map(c => ({
                name: c.data("name"),
                kind: c.data("kind"),
                visibility: c.data("visibility"),
                url: c.data("url"),
            }));

            this.selectedNode = {
                qualified_name: d.qualified_name,
                kind: d.kind,
                visibility: d.visibility,
                nodeGroup: d.nodeGroup,
                description: d.description,
                compound_refid: d.compound_refid,
                url: d.url,
                children,
                memberCount: children.length,
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

        togglePrivate() {
            this.showPrivate = !this.showPrivate;
            this.selectedNode = null;
            this.loadGraph();
        },

        expandAll() {
            if (this.api) this.api.expandAll();
        },

        collapseAll() {
            if (this.api) this.api.collapseAll();
        },

        applyFilters() {
            if (!this.cy) return;
            const kind = this.filterKind;
            const search = this.search.toLowerCase().trim();

            this.cy.batch(() => {
                this.cy.elements().removeClass("faded highlighted");

                let matched = this.cy.nodes();
                if (kind !== "all") {
                    matched = matched.filter(n => n.data("kind") === kind);
                }
                if (search) {
                    matched = matched.filter(n =>
                        n.data("name").toLowerCase().includes(search) ||
                        n.data("qualified_name").toLowerCase().includes(search)
                    );
                }

                if (kind !== "all" || search) {
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
            if (this.layout === "fcose") {
                Object.assign(opts, {
                    quality: "default",
                    nodeRepulsion: () => 8000,
                    idealEdgeLength: () => 120,
                    nodeSeparation: 80,
                });
            }
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
            this.search = "";
            this.selectedNode = null;
            if (this.cy) {
                this.cy.elements().removeClass("faded highlighted");
                this.layout = "fcose";
                const layoutDefaults = getLayoutDefaults();
                this.cy.layout({ ...layoutDefaults }).run();
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
                ["attribute", "Attribute", KIND_COLORS.attribute],
                ["class", "Class", KIND_COLORS.class],
                ["constant", "Constant", KIND_COLORS.constant],
                ["enum", "Enum", KIND_COLORS.enum],
                ["enum_value", "Enum Value", KIND_COLORS.enum_value],
                ["function", "Function", KIND_COLORS.function],
                ["interface", "Interface", KIND_COLORS.interface],
                ["method", "Method", KIND_COLORS.method],
                ["module", "Module", KIND_COLORS.module],
                ["primitive", "Primitive", KIND_COLORS.primitive],
                ["type_alias", "Type Alias", KIND_COLORS.type_alias],
            ], "circle");
            section("Edges", [
                ["triple", "Predicate (triple)", DEFAULT_EDGE_COLOR],
            ], "line");
            section("Visibility", [
                ["public", "Public (solid)", "#4e79a7"],
                ["private", "Private (dashed)", "#999"],
                ["protected", "Protected (dashed)", "#e8a838"],
            ], "circle");
        },
    };
}
