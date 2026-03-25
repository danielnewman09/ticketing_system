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
- [x] Edit LLR descriptions inline
- [ ] Link/unlink ontology triples to HLR
- [x] Run decomposition agent and display results

## LLR Detail Page (`/llr/{id}`)
- [x] Edit LLR description inline
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


# Component TODOs
- [ ] Components have a detail view
- [ ] Components have a concept of "external dependencies"
- [ ] At the design stage, an agent determines what external dependencies to bring into the component
- [ ] Components should have a given relative path for both source and test (verification) 
- [ ] Components should have a dependency management system (e.g. conan, python virtual environment)

# Language Specific TODOs
- [ ] Create language-specific instructions for agents to determine how to format specific results. e.g. C++ can contain references, const, inline, static, etc. Python cannot. 
- [ ] Components should have a language metadata field indicating which language they use.
- [ ] Pull from the existing templates in `components/templates/components/language_edit.html` to get an idea for what this should all entail

# Ontology View TODOs
- [ ] Integration points between components should be clearly marked

# Integration TODOs
- [ ] Integration points should have their own detail view (e.g. When the calculator GUI invokes the Calculator backend)
- [ ] `INTEGRATES` should be a possible ontology relationship
- [ ] Integration tests should be their own kind of verification. 