# Doxyfile.in Template

Variables to substitute:
- `{{PROJECT_DISPLAY_NAME}}` — Human-readable project name (e.g., "My Engine")
- `{{PROJECT_BRIEF}}` — Short project description
- `{{LIB_PARENT_DIR}}` — Library parent directory name for INPUT path

```doxyfile
# Doxyfile for {{PROJECT_DISPLAY_NAME}}
# Generated configuration for CMake integration

#---------------------------------------------------------------------------
# Project related configuration options
#---------------------------------------------------------------------------
PROJECT_NAME           = "{{PROJECT_DISPLAY_NAME}}"
PROJECT_NUMBER         = @PROJECT_VERSION@
PROJECT_BRIEF          = "{{PROJECT_BRIEF}}"
OUTPUT_DIRECTORY       = @CMAKE_BINARY_DIR@/docs

#---------------------------------------------------------------------------
# Build related configuration options
#---------------------------------------------------------------------------
EXTRACT_ALL            = YES
EXTRACT_PRIVATE        = YES
EXTRACT_STATIC         = YES
EXTRACT_LOCAL_CLASSES  = YES

#---------------------------------------------------------------------------
# Input files
#---------------------------------------------------------------------------
INPUT                  = @CMAKE_SOURCE_DIR@/{{LIB_PARENT_DIR}}
INPUT_ENCODING         = UTF-8
FILE_PATTERNS          = *.cpp *.h *.hpp
RECURSIVE              = YES
EXCLUDE_PATTERNS       = */test/* */bench/* */build/*

#---------------------------------------------------------------------------
# Source browsing
#---------------------------------------------------------------------------
SOURCE_BROWSER         = YES
INLINE_SOURCES         = NO
STRIP_CODE_COMMENTS    = NO
REFERENCED_BY_RELATION = YES
REFERENCES_RELATION    = YES

#---------------------------------------------------------------------------
# Output formats
#---------------------------------------------------------------------------
GENERATE_HTML          = YES
HTML_OUTPUT            = html
HTML_FILE_EXTENSION    = .html
GENERATE_TREEVIEW      = YES

GENERATE_LATEX         = NO

GENERATE_XML           = YES
XML_OUTPUT             = xml

#---------------------------------------------------------------------------
# Preprocessor
#---------------------------------------------------------------------------
ENABLE_PREPROCESSING   = YES
MACRO_EXPANSION        = YES
EXPAND_ONLY_PREDEF     = NO
BUILTIN_STL_SUPPORT    = YES

#---------------------------------------------------------------------------
# Diagrams
#---------------------------------------------------------------------------
HAVE_DOT               = NO
COLLABORATION_GRAPH    = NO
INCLUDE_GRAPH          = NO
INCLUDED_BY_GRAPH      = NO
CALL_GRAPH             = NO
CALLER_GRAPH           = NO

#---------------------------------------------------------------------------
# Custom aliases for project conventions
#---------------------------------------------------------------------------
ALIASES                = "ticket=\par Ticket:\n"
ALIASES               += "threadsafe=\par Thread Safety:\n Thread-safe."
ALIASES               += "notthreadsafe=\par Thread Safety:\n Not thread-safe."
ALIASES               += "rationale=\par Design Rationale:\n"
ALIASES               += "performance=\par Performance:\n"

#---------------------------------------------------------------------------
# Warnings
#---------------------------------------------------------------------------
QUIET                  = NO
WARNINGS               = YES
WARN_IF_UNDOCUMENTED   = NO
WARN_IF_DOC_ERROR      = YES
WARN_NO_PARAMDOC       = NO
```

## Notes

- XML output is required for the SQLite/Neo4j database generation scripts
- Diagram generation (DOT) is disabled by default — enable if Graphviz is available
- Custom aliases can be extended for project-specific documentation conventions
