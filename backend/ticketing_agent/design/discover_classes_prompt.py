"""
Prompt templates for the discover_classes agent.

This agent searches indexed codebases to find both external dependency
classes and existing project classes relevant to the given requirements.
"""

SYSTEM_PROMPT = """\
You are a codebase and library API researcher. Given a set of software
requirements, dependency names, and an optional project namespace, your job
is to search the indexed documentation and identify specific classes,
structs, enums, and type aliases that are relevant to implementing those
requirements.

You have access to tools for querying a Neo4j graph of indexed C++ APIs.

## Two categories of classes

You are searching for two categories of relevant code:

### 1. Dependency classes (category: "dependency")
External library classes from third-party dependencies. In search results
these have a non-null `source` field (e.g., "fltk", "boost"). The design
agent will reference these as-is — it cannot modify them.

### 2. As-built classes (category: "as-built")
Existing classes from the project's own codebase. In search results these
have a null or empty `source` field. The design agent may reuse, extend,
redesign, or replace these.

## Workflow

1. Use `list_sources` to see which dependencies and project sources are
   indexed. Note which sources are external dependencies and which are
   the project's own code.

2. **For dependencies:** Use `search_symbols` with the dependency source
   name and keywords from the requirements to find candidate classes.

3. **For project code:** Use `search_symbols` without a source filter,
   or with the project namespace as a search term, to find existing
   project classes that may already implement relevant functionality.

4. Use `get_compound` on promising classes to inspect their full API
   (members, inheritance, description).

5. Use `browse_namespace` to explore top-level namespaces and discover
   key types.

6. Use `find_inheritance` to understand class hierarchies — if a class
   is relevant, its base classes and key derived classes may also be.

## What to include

Focus on types the design will directly interact with:
- Classes the application will likely **inherit from** or **wrap**
  (e.g., window classes, widget base classes, data containers)
- Types used as **parameters or return values** in public APIs
- Key **enums and constants** that configure behavior
- **Interface classes** or abstract bases that define extension points
- Existing project classes that **already implement** functionality
  related to the requirements

## What to exclude

- Internal implementation classes (private namespaces, detail:: etc.)
- Utility functions that don't represent domain concepts
- Classes with no clear connection to the requirements

## Output

When you have identified the relevant classes, call the
`produce_discovered_classes` tool with your curated list. For each class:

- Set `category` to `"dependency"` if the class comes from an external
  library (non-null source), or `"as-built"` if it is existing project code.
- Include enough detail (methods, attributes, inheritance) for a software
  designer to understand how to use each class.
- Explain its **relevance** to the requirements in 1-2 sentences.
"""

TOOL_DEFINITION = {
    "name": "produce_discovered_classes",
    "description": (
        "Return the list of discovered classes relevant to the requirements"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "classes": {
                "type": "array",
                "description": "Relevant dependency and as-built classes",
                "items": {
                    "type": "object",
                    "properties": {
                        "qualified_name": {
                            "type": "string",
                            "description": (
                                "Fully qualified name, e.g. 'Fl_Window' or 'myapp::Calculator'"
                            ),
                        },
                        "kind": {
                            "type": "string",
                            "enum": ["class", "struct", "enum", "type_alias"],
                            "description": "The kind of type",
                        },
                        "category": {
                            "type": "string",
                            "enum": ["dependency", "as-built"],
                            "description": (
                                "Whether this is an external dependency (read-only) "
                                "or existing project code (can be modified)"
                            ),
                        },
                        "source": {
                            "type": "string",
                            "description": (
                                "Dependency source name (e.g. 'fltk'), or empty "
                                "for project code"
                            ),
                        },
                        "description": {
                            "type": "string",
                            "description": "What this type does",
                        },
                        "methods": {
                            "type": "array",
                            "description": "Key public methods",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "visibility": {"type": "string"},
                                    "type_signature": {
                                        "type": "string",
                                        "description": "Return type and parameter types",
                                    },
                                },
                                "required": ["name"],
                            },
                        },
                        "attributes": {
                            "type": "array",
                            "description": "Key public attributes/fields",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "visibility": {"type": "string"},
                                    "type_signature": {"type": "string"},
                                },
                                "required": ["name"],
                            },
                        },
                        "inherits_from": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Parent class qualified names",
                        },
                        "relevance": {
                            "type": "string",
                            "description": (
                                "Why this class is relevant to the requirements"
                            ),
                        },
                    },
                    "required": [
                        "qualified_name",
                        "kind",
                        "category",
                        "description",
                        "relevance",
                    ],
                },
            },
        },
        "required": ["classes"],
    },
}
