"""Index dependency headers into the Neo4j codebase graph via doxygen-index.

Migrated version: reads indexing config from the neomodel Dependency node
instead of the SQLAlchemy ``backend.db.models.Dependency``.  After
successful indexing, the Dependency node's ``tags`` are updated to
include ``"indexed"``.
"""

import logging

log = logging.getLogger(__name__)


def _get_dep_config(dependency_name: str):
    """Load indexing config for a dependency from Neo4j.

    Looks up the Dependency node by name (case-insensitive) and
    returns a DepConfig populated from its properties.  Falls back
    to defaults if the node is not found.

    Args:
        dependency_name: Conan package name (case-insensitive).

    Returns:
        A DepConfig instance (always non-None).
    """
    from doxygen_index.deps_config import DepConfig
    from backend_migrated.models import Dependency

    # Try exact refid match first (e.g. "conan::spdlog")
    # Then fall back to case-insensitive name match
    refid = f"conan::{dependency_name.lower()}"
    dep = Dependency.nodes.get_or_none(refid=refid)
    if dep is None:
        # Fall back to name-based lookup
        dep = Dependency.nodes.get_or_none(name=dependency_name)
    if dep is None:
        # Try lowercase name
        for node in Dependency.nodes.all():
            if node.name and node.name.lower() == dependency_name.lower():
                dep = node
                break

    if dep is None:
        log.warning("Dependency '%s' not found in Neo4j, using defaults", dependency_name)
        return DepConfig()

    return DepConfig(
        file_patterns=dep.index_file_patterns or "*.h *.hpp",
        recursive=dep.index_recursive,
        subdir=dep.index_subdir or None,
        exclude_patterns=dep.index_exclude_patterns or "",
    )


def _tag_dependency_indexed(dependency_name: str) -> None:
    """Tag a Dependency node as 'indexed' after successful ingestion.

    Applies the ``indexed`` presence tag to the dependency, removing
    any previous presence tag (``registered``, ``missing``, or
    ``integrated``).  Health tags (``passing``/``failing``) are
    preserved.

    Args:
        dependency_name: Conan package name (case-insensitive).
    """
    from backend_migrated.models import Dependency
    from frontend_migrated.data.tags import _DEPENDENCY_PRESENCE_TAGS, _DEPENDENCY_HEALTH_TAGS

    # Same lookup strategy as _get_dep_config
    refid = f"conan::{dependency_name.lower()}"
    dep = Dependency.nodes.get_or_none(refid=refid)
    if dep is None:
        dep = Dependency.nodes.get_or_none(name=dependency_name)
    if dep is None:
        for node in Dependency.nodes.all():
            if node.name and node.name.lower() == dependency_name.lower():
                dep = node
                break

    if dep is None:
        log.warning("Could not tag '%s' as indexed — node not found", dependency_name)
        return

    current = list(dep.tags) if dep.tags else []
    # Preserve health tags, replace presence tag with "indexed"
    health_tags = [t for t in current if t in _DEPENDENCY_HEALTH_TAGS]
    new_tags = ["indexed"] + health_tags

    if new_tags != current:
        dep.tags = new_tags
        dep.save()
        log.info("Tagged dependency '%s' as indexed (tags: %s)", dependency_name, new_tags)


def _tag_code_nodes_as_dependency(source: str) -> int:
    """Tag all code-level nodes with the given source as ``"dependency"``.

    After doxygen-index ingests a dependency's headers, every NamespaceNode,
    CompoundNode (ClassNode, etc.), and MemberNode created during that
    ingestion has ``source=dep_name``.  This function finds those nodes
    and adds the ``"dependency"`` provenance tag to distinguish them
    from the project's own code (``"as-built"`` or ``"design"``).

    Tags are additive — ``"dependency"`` is appended if not already
    present, preserving any existing tags like ``"as-built"``.

    Args:
        source: The ``source`` property value used during ingestion
            (e.g. ``"spdlog"``).

    Returns:
        Number of nodes tagged.
    """
    from neomodel import db

    # Tag all node types that have a ``tags`` property and a ``source``
    # property.  FileNode does NOT have tags, so we skip it.
    node_labels = [
        "NamespaceNode",
        "ClassNode",
        "InterfaceNode",
        "EnumNode",
        "UnionNode",
        "ConceptNode",
        "MethodNode",
        "AttributeNode",
        "EnumValueNode",
        "FunctionNode",
        "DefineNode",
        "ModuleNode",
    ]

    total_tagged = 0
    for label in node_labels:
        query = f"""
            MATCH (n:`{label}` {{source: $source}})
            WHERE NOT 'dependency' IN n.tags
            SET n.tags = CASE
                WHEN n.tags IS NULL THEN ['dependency']
                ELSE n.tags + ['dependency']
                END
            RETURN count(n) AS cnt
        """
        try:
            results, _ = db.cypher_query(query, {"source": source})
            count = results[0][0] if results else 0
            total_tagged += count
        except Exception as exc:
            log.debug("Could not tag %s nodes for source=%s: %s", label, source, exc)

    if total_tagged:
        log.info("Tagged %d code nodes as 'dependency' (source=%s)", total_tagged, source)
    return total_tagged


def index_dependency(
    project_dir: str,
    dependency_name: str,
) -> dict:
    """Discover, generate Doxygen XML, and ingest a dependency's headers
    into the Neo4j graph.

    Uses the doxygen-index Python API directly.  Indexing config (file
    patterns, subdirectory, etc.) is read from the Dependency node in
    Neo4j.

    After successful indexing, the Dependency node's ``tags`` are
    updated to include ``"indexed"`` (replacing any previous presence
    tag).

    Args:
        project_dir: Absolute path to the project root.
        dependency_name: Conan package name to index.

    Returns:
        Dict with keys: success (bool), message (str).
    """
    try:
        from doxygen_index.conan import discover_packages
        from doxygen_index.doxygen import generate_xml
        from doxygen_index.neo4j_backend import ingest as neo4j_ingest
    except ImportError:
        return {
            "success": False,
            "message": "doxygen-index is not installed. Run: pip install -e ../Doxygen-Dependency-Parser",
        }

    try:
        # Conan package names are lowercase; normalize for discovery
        conan_name = dependency_name.lower()

        # Load config from the Neo4j Dependency node
        dep_config = _get_dep_config(dependency_name)
        dep_configs = {conan_name: dep_config}

        # Phase 1: Discover the dependency's include paths from the Conan cache
        log.info("Discovering %s packages in %s", conan_name, project_dir)
        packages = discover_packages(
            project_dir=project_dir,
            dep_configs=dep_configs,
            only={conan_name},
        )
        if not packages:
            return {
                "success": False,
                "message": (
                    f"Could not find {conan_name} in the Conan cache. "
                    f"Run 'conan install . --build=missing' in the project first."
                ),
            }

        # Phase 2: Generate Doxygen XML
        output_dir = f"{project_dir}/build/docs/deps"
        log.info("Generating Doxygen XML for %s", conan_name)
        xml_dirs = generate_xml(packages, output_dir=output_dir)
        if not xml_dirs:
            return {
                "success": False,
                "message": f"Doxygen XML generation produced no output for {dependency_name}.",
            }

        # Phase 3: Ingest into Neo4j
        for dep_name, xml_dir in xml_dirs.items():
            log.info("Ingesting %s into Neo4j", dep_name)
            neo4j_ingest(xml_dir, source=dep_name)

            # Phase 3b: Tag all ingested code-level nodes with the
            # "dependency" provenance tag so they can be distinguished
            # from the project's own code ("as-built" / "design").
            _tag_code_nodes_as_dependency(dep_name)

        indexed_names = ", ".join(sorted(xml_dirs.keys()))
        log.info("Indexed %s successfully", indexed_names)

        # Phase 4: Tag the Dependency node as indexed
        _tag_dependency_indexed(dependency_name)

        return {
            "success": True,
            "message": f"Indexed {indexed_names} into documentation graph.",
        }

    except Exception as e:
        log.warning("Indexing %s failed: %s", dependency_name, e, exc_info=True)
        return {
            "success": False,
            "message": f"Indexing failed: {e}",
        }