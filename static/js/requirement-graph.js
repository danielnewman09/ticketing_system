/**
 * Alpine.js component for requirement detail page graphs (HLR/LLR) and
 * node neighborhood graphs. Supports double-click navigation to node details.
 */
function requirementGraph(dataUrl) {
    return {
        init() {
            fetch(dataUrl)
                .then(r => r.json())
                .then(data => {
                    if (data.nodes.length === 0) {
                        this.$refs.cy.innerHTML =
                            '<div class="d-flex align-items-center justify-content-center h-100 text-muted small">No ontology triples for this requirement.</div>';
                        return;
                    }
                    const layoutDefaults = getLayoutDefaults();
                    const cy = cytoscape({
                        container: this.$refs.cy,
                        elements: buildElements(data),
                        style: CYTOSCAPE_STYLES,
                        layout: { ...layoutDefaults, animationDuration: 400 },
                        minZoom: 0.3,
                        maxZoom: 4,
                    });

                    cy.on("dbltap", "node", evt => {
                        const url = evt.target.data("url");
                        if (url) window.location.href = url;
                    });
                });
        },
    };
}
