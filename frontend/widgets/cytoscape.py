"""JavaScript template strings for Cytoscape graph rendering."""

_EMPTY_GRAPH_HTML = (
    '<div style="display:flex;align-items:center;justify-content:center;'
    'height:100%;color:#888;font-size:1rem;">No nodes found</div>'
)

_JS_CLEAR_EMPTY = """
    if (window.{cy_var}) window.{cy_var}.destroy();
    const container = document.getElementById('{container_id}');
    if (container) {{
        container.innerHTML = '{placeholder_html}';
    }}
"""

_JS_INIT_GRAPH = """
    try {{
        // --- Debug: log render parameters ---
        console.log('Cytoscape render starting:', {{
            container_id: '{container_id}',
            elements_count: {elements_count},
            layout: '{layout}'
        }});

        // --- Teardown: destroy any existing Cytoscape instance ---
        if (window.{cy_var}) window.{cy_var}.destroy();

        // --- Locate the DOM container element ---
        const KIND_COLORS = {kind_colors};
        const container = document.getElementById('{container_id}');
        if (!container) {{
            console.error('Container not found');
            return {{success: false, error: 'Container not found'}};
        }}
        container.innerHTML = '';

        // --- Create Cytoscape instance with elements, styles, and layout ---
        //     cytoscape({{ ... }}) initializes the graph and runs the layout.
        window.{cy_var} = cytoscape({{
            container: container,       // DOM element to render into
            elements: {elements_json},   // JSON array of node/edge data
            style: {styles_expr},        // CSS-like styles for node/edge types
            layout: {{ name: {layout_name}, {animation_opts} }},  // layout algorithm + animation
        }});

        // --- On ready: zoom/pan to fit all nodes in view ---
        window.{cy_var}.ready(function() {{
            console.log('Cytoscape ready, fitting graph');
            window.{cy_var}.fit();
        }});

        // --- Event: single tap on a node → emit 'node_selected' ---
        window.{cy_var}.on('tap', 'node', function(evt) {{
            const data = evt.target.data();
            if (data.qualified_name) {{
                emitEvent('node_selected', data);
            }}
        }});

        // --- Event: double-tap on a node → emit 'node_dblclick' ---
        window.{cy_var}.on('dbltap', 'node', function(evt) {{
            const data = evt.target.data();
            if (data.qualified_name) {{
                emitEvent('node_dblclick', data);
            }}
        }});

        // --- Debug: confirm init completed ---
        console.log('Cytoscape initialization complete');
        return {{success: true, elements: {elements_count}}};

    }} catch (error) {{
        console.error('Cytoscape render failed:', error);
        return {{success: false, error: error.toString(), stack: error.stack}};
    }}
"""