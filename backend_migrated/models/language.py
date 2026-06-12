"""Language node model (:Language label in Neo4j).

Represents a programming language (e.g., C++ 20, Python 3.12)
used by components in the project. Extends CodeGraphNode to share
serialization, registry, and relationship introspection infrastructure.

Language is a leaf node — it has no outgoing relationships. Components
reference languages via WRITTEN_IN edges.
"""

from neomodel import StructuredNode, StringProperty, ArrayProperty, RelationshipFrom

from codegraph.models.tags import CodeGraphNode


class Language(StructuredNode, CodeGraphNode):
    """Programming language node — :Language label in Neo4j.

    Represents a programming language (e.g., C++ 20, Python 3.12)
    used by components in the project.

    Attributes:
        name: Language name (e.g. 'C++', 'Python'), inherited from CodeGraphNode.
        refid: Unique identifier (e.g. 'python', 'cpp-20'), inherited from
            CodeGraphNode. Used as the primary lookup key.
        source: Project name, inherited from CodeGraphNode.
        version: Language version string (e.g. '20', '3.12'). Empty if
            unspecified.
    """

    # --- Language-specific ---
    version = StringProperty(default="",
        help_text="Language version (e.g. '20', '3.12'). Empty if unspecified.")

    # --- Workflow tags ---
    #
    #  Tags reflect deterministic state checks on the language node:
    #
    #  • "detected"   — language version was detected from project files
    #  • "configured" — language settings are present in CMakeLists.txt
    #
    tags = ArrayProperty(StringProperty(), default=list,
        help_text="Workflow tags: 'detected', 'configured'.")

    # --- Reverse relationships -------------------------------------------------
    #
    #  • WRITTEN_IN (incoming)  — Component → Language
    #    Components written in this language. Traversed via ``components``.
    # --------------------------------------------------------------------------

    components = RelationshipFrom(
        'backend_migrated.models.component.Component', 'WRITTEN_IN')

    # --- Serialization contract ---
    _llm_fields: set[str] = {"name", "version", "tags"}