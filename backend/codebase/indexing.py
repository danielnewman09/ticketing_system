"""Index dependency headers into the Neo4j codebase graph via doxygen-index."""

import logging

log = logging.getLogger(__name__)


def _get_dep_config(dependency_name: str):
    """Load indexing config for a dependency from the database.

    Returns a DepConfig or None if the dependency isn't found.
    """
    from doxygen_index.deps_config import DepConfig
    from backend.db import get_session
    from backend.db.models import Dependency

    with get_session() as session:
        dep = session.query(Dependency).filter_by(name=dependency_name).first()
        if not dep:
            return DepConfig()
        return DepConfig(
            file_patterns=dep.index_file_patterns or "*.h *.hpp",
            recursive=dep.index_recursive,
            subdir=dep.index_subdir or None,
            exclude_patterns=dep.index_exclude_patterns or "",
        )


def index_dependency(
    project_dir: str,
    dependency_name: str,
) -> dict:
    """Discover, generate Doxygen XML, and ingest a dependency's headers
    into the Neo4j graph.

    Uses the doxygen-index Python API directly. Indexing config (file patterns,
    subdirectory, etc.) is read from the dependency record in the database.

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

        # Load config from the database
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

        indexed_names = ", ".join(sorted(xml_dirs.keys()))
        log.info("Indexed %s successfully", indexed_names)
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
