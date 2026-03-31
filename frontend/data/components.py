"""Component CRUD, detail, options, and environment CRUD."""

from backend.db import get_session
from backend.db.models import (
    Component,
    Dependency,
    DependencyManager,
    Language,
)


def fetch_components_data():
    """Fetch all data needed for components page."""
    with get_session() as session:
        result = []
        for comp in session.query(Component).all():
            result.append({
                "id": comp.id,
                "name": comp.name,
                "namespace": comp.namespace or "",
                "language": repr(comp.language) if comp.language else None,
                "parent": comp.parent.name if comp.parent else None,
                "hlr_count": len(comp.high_level_requirements),
                "node_count": len(comp.ontology_nodes),
            })
        return result


def fetch_component_detail(component_id: int) -> dict | None:
    """Fetch full component detail including children, environment, requirements, and nodes."""
    with get_session() as session:
        comp = session.query(Component).filter_by(id=component_id).first()
        if not comp:
            return None

        # Children
        children = [
            {"id": c.id, "name": c.name, "namespace": c.namespace,
             "hlr_count": len(c.high_level_requirements),
             "node_count": len(c.ontology_nodes)}
            for c in comp.children
        ]

        # Environment (language, build systems, test frameworks, dep managers)
        env = None
        if comp.language:
            lang = comp.language
            env = {
                "language_id": lang.id,
                "language": repr(lang),
                "build_systems": [
                    {"name": bs.name, "config_file": bs.config_file, "version": bs.version}
                    for bs in lang.build_systems
                ],
                "test_frameworks": [
                    {"name": tf.name, "config_file": tf.config_file,
                     "discovery_path": tf.test_discovery_path}
                    for tf in lang.test_frameworks
                ],
                "dependency_managers": [
                    {
                        "id": dm.id,
                        "name": dm.name,
                        "manifest_file": dm.manifest_file,
                        "lock_file": dm.lock_file,
                        "dependencies": [
                            {"id": d.id, "name": d.name, "version": d.version, "is_dev": d.is_dev}
                            for d in dm.dependencies
                        ],
                    }
                    for dm in lang.dependency_managers
                ],
            }

        # HLRs in this component
        hlrs = [
            {"id": h.id, "description": h.description,
             "llr_count": len(h.low_level_requirements)}
            for h in comp.high_level_requirements
        ]

        # Ontology nodes (group by kind)
        node_kinds: dict[str, int] = {}
        nodes_sample = []
        for n in comp.ontology_nodes:
            node_kinds[n.kind] = node_kinds.get(n.kind, 0) + 1
            if len(nodes_sample) < 20:
                nodes_sample.append({
                    "id": n.id, "name": n.name,
                    "qualified_name": n.qualified_name,
                    "kind": n.kind,
                })

        # Dependencies linked to this component (via M2M)
        comp_deps = [
            {"id": d.id, "name": d.name, "version": d.version, "is_dev": d.is_dev}
            for d in comp.dependencies
        ]

        # Find default manager_id for add-dependency form
        default_manager_id = None
        if comp.language:
            for dm in comp.language.dependency_managers:
                default_manager_id = dm.id
                break

        return {
            "id": comp.id,
            "name": comp.name,
            "description": comp.description or "",
            "namespace": comp.namespace or "",
            "parent": {"id": comp.parent.id, "name": comp.parent.name} if comp.parent else None,
            "children": children,
            "environment": env,
            "hlrs": hlrs,
            "dependencies": comp_deps,
            "default_manager_id": default_manager_id,
            "node_kinds": node_kinds,
            "nodes_sample": nodes_sample,
            "node_count": len(comp.ontology_nodes),
        }


def fetch_components_options():
    """Return list of {id, name} for component dropdowns."""
    with get_session() as session:
        return [
            {"id": c.id, "name": c.name}
            for c in session.query(Component).order_by(Component.name).all()
        ]


def ensure_component_language(component_id: int, language_name: str, version: str = "") -> int:
    """Ensure a component has a language set, creating it if needed. Returns language id."""
    from backend.db import get_or_create
    with get_session() as session:
        lang, _ = get_or_create(session, Language, defaults={"version": version}, name=language_name)
        comp = session.query(Component).filter_by(id=component_id).first()
        if comp and comp.language_id != lang.id:
            comp.language_id = lang.id
        return lang.id


def create_dependency_manager(
    language_id: int, name: str, manifest_file: str, lock_file: str = "",
) -> int:
    """Create a dependency manager. Returns the new id."""
    with get_session() as session:
        dm = DependencyManager(
            language_id=language_id,
            name=name,
            manifest_file=manifest_file,
            lock_file=lock_file,
        )
        session.add(dm)
        session.flush()
        return dm.id


def add_dependency(
    manager_id: int, name: str, version: str = "", is_dev: bool = False,
    component_id: int | None = None,
) -> int:
    """Add a dependency to a manager. Returns the new id."""
    with get_session() as session:
        dep = Dependency(
            manager_id=manager_id,
            name=name,
            version=version,
            is_dev=is_dev,
        )
        session.add(dep)
        session.flush()
        if component_id:
            comp = session.query(Component).filter_by(id=component_id).first()
            if comp:
                dep.components.append(comp)
        return dep.id


def update_dependency_index_config(
    dep_id: int,
    file_patterns: str,
    subdir: str,
    exclude_patterns: str,
    recursive: bool,
) -> bool:
    """Update the Doxygen indexing config for a dependency."""
    with get_session() as session:
        dep = session.query(Dependency).filter_by(id=dep_id).first()
        if not dep:
            return False
        dep.index_file_patterns = file_patterns
        dep.index_subdir = subdir
        dep.index_exclude_patterns = exclude_patterns
        dep.index_recursive = recursive
        return True


def delete_dependency(dep_id: int) -> bool:
    """Delete a dependency. Returns True on success."""
    with get_session() as session:
        dep = session.query(Dependency).filter_by(id=dep_id).first()
        if not dep:
            return False
        session.delete(dep)
        return True


def delete_dependency_manager(manager_id: int) -> bool:
    """Delete a dependency manager and its dependencies. Returns True on success."""
    with get_session() as session:
        dm = session.query(DependencyManager).filter_by(id=manager_id).first()
        if not dm:
            return False
        session.delete(dm)
        return True
