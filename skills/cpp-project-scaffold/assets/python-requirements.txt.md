# python/requirements.txt Template

```
# Python Environment for Documentation Tooling
#
# Install with: python/setup.sh
# Or manually: pip install -r python/requirements.txt

# --- Doxygen XML → SQLite / Neo4j indexing ---
doxygen-index
```

## Notes

- `doxygen-index` provides both SQLite and Neo4j ingestion from Doxygen XML
- It also indexes Conan dependencies via `doxygen-index full`
- Add more dependencies as the project grows (e.g., `tree-sitter` for traceability, `fastmcp` for MCP servers)
