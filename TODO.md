# Dashboard Editing TODOs

## Requirements Page (`/`)
- [x] Create HLR form (dialog with description + component selector)
- [x] Delete HLR with confirmation dialog
- [x] Add LLR to HLR (dialog from card menu)
- [x] Trigger decomposition agent from UI (currently placeholder notification)

## HLR Detail Page (`/hlr/{id}`)
- [x] Edit HLR description + component (dialog)
- [x] Create LLR form (dialog)
- [x] Delete HLR with confirmation (redirects to `/`)
- [x] Delete LLR with confirmation (per-row delete button)
- [ ] Edit LLR descriptions inline
- [ ] Link/unlink ontology triples to HLR
- [x] Run decomposition agent and display results

## LLR Detail Page (`/llr/{id}`)
- [ ] Edit LLR description inline
- [ ] Add/edit/remove verification methods
- [ ] Add/edit/remove preconditions and postconditions
- [ ] Add/edit/remove actions
- [ ] Link/unlink ontology triples to LLR

## Components Page (`/components`)
- [ ] Create component form
- [ ] Edit component name, language, parent
- [ ] Delete component with confirmation
- [ ] Manage dependencies (add/remove)

## Ontology Table Page (`/ontology`)
- [ ] Create ontology node form
- [ ] Edit node properties inline (name, kind, description, visibility, etc.)
- [ ] Delete ontology node with confirmation
- [ ] Click row to navigate to node detail view

## Ontology Graph Page (`/ontology/graph`)
- [ ] Edit node properties in the detail panel
- [ ] Create new nodes from the graph view
- [ ] Create/delete triples (relationships) between nodes
- [ ] Sync edits back to both SQLite and Neo4j
