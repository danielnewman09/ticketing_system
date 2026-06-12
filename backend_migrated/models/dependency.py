"""Dependency node model (:Dependency label in Neo4j).

Represents a third-party library that components depend on
(e.g., boost::asio 1.82, requests 2.31). Extends CodeGraphNode to share
serialization, registry, and relationship introspection infrastructure.

The ``manager_name`` property replaces the former SQLAlchemy FK to
DependencyManager. When DependencyManager is migrated to neomodel in a
future phase, this can become a MANAGED_BY relationship.
"""

from neomodel import (
    StructuredNode, StringProperty, BooleanProperty, ArrayProperty,
    RelationshipFrom,
)

from codegraph.models.tags import CodeGraphNode


class Dependency(StructuredNode, CodeGraphNode):
    """External library dependency node — :Dependency label in Neo4j.

    Represents a third-party library that components depend on
    (e.g., boost::asio 1.82, requests 2.31). Linked to components
    via DEPENDS_ON relationships and to the package manager via
    a string property (DependencyManager not yet migrated).

    Attributes:
        name: Dependency name (e.g. 'boost', 'requests'), inherited from
            CodeGraphNode.
        refid: Unique identifier, inherited from CodeGraphNode. Convention:
            '{manager_name}::{name}' (e.g. 'conan::boost', 'pip::requests').
        source: Project name, inherited from CodeGraphNode.
        version: Pinned version string (e.g. '1.82.0', '2.31.0').
        github_url: Repository URL for the dependency.
        is_dev: True if this is a dev-only dependency (not shipped in
            production).
        manager_name: Name of the package manager (e.g. 'pip', 'conan',
            'npm'). Will become a relationship when DependencyManager is
            migrated.
        index_file_patterns: File glob patterns for Doxygen indexing
            (e.g. '*.h *.hpp').
        index_subdir: Subdirectory within the dependency to index.
        index_exclude_patterns: File patterns to exclude from indexing.
        index_recursive: Whether to index recursively.
    """

    # --- Dependency metadata ---
    version = StringProperty(default="",
        help_text="Pinned version string (e.g. '1.82.0', '2.31.0').")
    github_url = StringProperty(default="",
        help_text="Repository URL for the dependency.")
    is_dev = BooleanProperty(default=False,
        help_text="True if this is a dev-only dependency (not shipped in production).")

    # --- Manager linkage (replaces FK to DependencyManager) ---
    manager_name = StringProperty(default="",
        help_text="Name of the package manager (e.g. 'pip', 'conan', 'npm'). "
                  "Will become a relationship when DependencyManager is migrated.")

    # --- Doxygen indexing config ---
    index_file_patterns = StringProperty(default="*.h *.hpp",
        help_text="File glob patterns for Doxygen indexing (e.g. '*.h *.hpp').")
    index_subdir = StringProperty(default="",
        help_text="Subdirectory within the dependency to index.")
    index_exclude_patterns = StringProperty(default="",
        help_text="File patterns to exclude from indexing.")
    index_recursive = BooleanProperty(default=True,
        help_text="Whether to index recursively.")

    # --- Workflow tags ---
    #
    #  Tags reflect deterministic state checks on the dependency's lifecycle:
    #
    #  • "registered"   — declared in Neo4j, project not yet scaffolded
    #  • "missing"       — declared in Neo4j, project scaffolded, but NOT
    #                       found in conanfile.py (expected but absent)
    #  • "integrated"    — found in conanfile.py (Conan knows about it)
    #  • "indexed"       — indexed into the documentation graph (Doxygen)
    #  • "passing"       — build/integration checks pass for this dep
    #  • "failing"       — build/integration checks fail for this dep
    #
    #  Tags are mutually exclusive within a lifecycle phase.  For the
    #  *presence* phase: exactly one of registered, missing, integrated.
    #  For the *health* phase: passing or failing (or neither if not yet
    #  checked).
    #
    tags = ArrayProperty(StringProperty(), default=list,
        help_text="Workflow tags: 'registered', 'missing', 'integrated', "
                  "'indexed', 'passing', 'failing'.")

    # --- Reverse relationships -------------------------------------------------
    #
    #  • DEPENDS_ON (incoming)  — Component → Dependency
    #    Components that depend on this library. Traversed via ``components``.
    #
    #  Previously modelled as the M2M junction table dependency_components
    #  in SQLAlchemy. Now a direct relationship edge.
    # --------------------------------------------------------------------------

    components = RelationshipFrom(
        'backend_migrated.models.component.Component', 'DEPENDS_ON')

    # --- Serialization contract ---
    _llm_fields: set[str] = {
        "name", "version", "manager_name", "github_url", "is_dev", "tags",
    }