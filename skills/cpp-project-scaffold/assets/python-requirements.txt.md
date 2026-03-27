# python/requirements.txt Template

```
# Python Environment for Documentation Tooling
#
# Install with: python/setup.sh
# Or manually: pip install -r python/requirements.txt

# --- Neo4j Graph Database (for codebase graph ingestion) ---
neo4j==5.28.1
```

## Notes

- This is the minimal set needed for the codebase database scripts
- The `doxygen_to_sqlite.py` script uses only Python stdlib (no pip deps needed)
- The `doxygen_to_neo4j.py` script requires the `neo4j` driver
- Add more dependencies as the project grows (e.g., `tree-sitter` for traceability, `fastmcp` for MCP servers)
