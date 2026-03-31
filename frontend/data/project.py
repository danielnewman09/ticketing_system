"""Project metadata and environment data."""

from backend.db import get_session
from backend.db.models import Language, ProjectMeta


def fetch_project_meta() -> dict:
    """Fetch project metadata (single row), creating defaults if missing."""
    with get_session() as session:
        meta = session.query(ProjectMeta).filter_by(id=1).first()
        if not meta:
            meta = ProjectMeta(id=1, name="", description="", working_directory="")
            session.add(meta)
            session.flush()
        return {
            "name": meta.name,
            "description": meta.description,
            "working_directory": meta.working_directory,
        }


def update_project_meta(name: str, description: str, working_directory: str) -> bool:
    """Update project metadata. Returns True on success."""
    with get_session() as session:
        meta = session.query(ProjectMeta).filter_by(id=1).first()
        if not meta:
            meta = ProjectMeta(id=1)
            session.add(meta)
        meta.name = name
        meta.description = description
        meta.working_directory = working_directory
        return True


def fetch_environment_data() -> list[dict]:
    """Fetch languages with their build systems, test frameworks, and dependencies."""
    with get_session() as session:
        langs = session.query(Language).all()
        result = []
        for lang in langs:
            deps = []
            for dm in lang.dependency_managers:
                for d in dm.dependencies:
                    deps.append({
                        "id": d.id,
                        "name": d.name,
                        "version": d.version,
                        "github_url": d.github_url,
                        "manager": dm.name,
                        "is_dev": d.is_dev,
                        "index_file_patterns": d.index_file_patterns,
                        "index_subdir": d.index_subdir,
                        "index_exclude_patterns": d.index_exclude_patterns,
                        "index_recursive": d.index_recursive,
                        "components": [
                            {"id": c.id, "name": c.name} for c in d.components
                        ],
                    })
            result.append({
                "id": lang.id,
                "name": lang.name,
                "version": lang.version,
                "build_systems": [
                    {"name": bs.name, "config_file": bs.config_file}
                    for bs in lang.build_systems
                ],
                "test_frameworks": [
                    {"name": tf.name, "config_file": tf.config_file}
                    for tf in lang.test_frameworks
                ],
                "dependency_managers": [dm.name for dm in lang.dependency_managers],
                "dependencies": deps,
            })
        return result
