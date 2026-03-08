/**
 * Alpine.js component for requirement detail page graphs (HLR/LLR).
 * Loads graph data from a URL and renders a simple Cytoscape visualization.
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
                    cytoscape({
                        container: this.$refs.cy,
                        elements: buildElements(data),
                        style: CYTOSCAPE_STYLES,
                        layout: { ...COSE_DEFAULTS, animationDuration: 400 },
                        minZoom: 0.3,
                        maxZoom: 4,
                    });
                });
        },
    };
}
