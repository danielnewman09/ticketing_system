#!/usr/bin/env python
"""
Scaffold project: generate the C++ project skeleton from design data.

Uses project metadata (name, working directory) and component definitions
from the database to drive the LLM scaffolding agent, which creates
CMakeLists.txt, conanfile, library directories, and all supporting files.

Steps:
  0. (Optional) Set project name/working-directory if provided via CLI
  1. Read project metadata (name, working_directory) from SQLite
  2. Read architectural components from SQLite
  3. Build library specs from components
  4. Run the scaffold_project agent (write phase + build verification)

Project name and working directory can be set either:
  - Via CLI flags --name and --working-directory (persisted to DB)
  - Through the dashboard UI (persisted to DB)

Assumes 02_setup_project.py has been run (components exist).

Usage:
    source .venv/bin/activate
    python scripts/04_scaffold_project.py
    python scripts/04_scaffold_project.py --name my-engine --working-directory /path/to/projects

Defaults to calculator-engine in ~/dev/calculator-example.

Options:
    --name                Project name (kebab-case, e.g. calculator-engine)
    --working-directory   Directory where the project folder will be created
    --std                 C++ standard version (default: 20)
    --dep                 Extra Conan dependency (repeatable, e.g. --dep eigen/3.4.0)
    --model               LLM model override
    --max-tokens          Max tokens per LLM turn (default: 4096)
    --max-turns           Max tool-loop iterations (default: 50)
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv

load_dotenv()

from backend.db import init_db, get_session
from backend.db.models import Component, ProjectMeta
from backend.ticketing_agent.design.scaffold_project import scaffold_project
from services.dependencies import init_neo4j, close_neo4j

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
LOGS_DIR = os.path.join(REPO_ROOT, "logs")
_SCAFFOLD_SKILL = os.path.join(REPO_ROOT, "skills", "cpp-project-scaffold")


def _configure_logging():
    """Set up file logging for the scaffold run."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_file = os.path.join(LOGS_DIR, "scaffold_pipeline.log")

    file_handler = logging.FileHandler(log_file, mode="w")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)
    root_logger.setLevel(logging.DEBUG)

    # Suppress noisy neo4j logs
    for name in ["neo4j", "neo4j.driver", "neo4j.io", "neo4j.pool"]:
        logging.getLogger(name).setLevel(logging.WARNING)

    return log_file


def _get_or_create_project_meta(session) -> ProjectMeta:
    """Get the singleton ProjectMeta row, creating it if needed."""
    meta = session.query(ProjectMeta).filter_by(id=1).first()
    if not meta:
        meta = ProjectMeta(id=1, name="", description="", working_directory="")
        session.add(meta)
        session.flush()
    return meta


def _get_project_meta() -> dict:
    """Read project metadata from SQLite. Returns {name, description, working_directory}."""
    with get_session() as session:
        meta = _get_or_create_project_meta(session)
        return {
            "name": meta.name or "",
            "description": meta.description or "",
            "working_directory": meta.working_directory or "",
        }


def _set_project_meta(name: str = "", working_directory: str = "") -> None:
    """Persist project name and/or working directory to SQLite."""
    with get_session() as session:
        meta = _get_or_create_project_meta(session)
        if name:
            meta.name = name
        if working_directory:
            meta.working_directory = working_directory


def _get_libraries_from_components() -> list[dict]:
    """Build a list of library specs from architectural components in the DB.

    Excludes pseudo-components like "Environment".
    """
    libraries = []
    with get_session() as session:
        components = (
            session.query(Component)
            .order_by(Component.id)
            .all()
        )
        for comp in components:
            # Skip environment-level components
            if comp.name == "Environment" or comp.name.startswith("Environment:"):
                continue

            lib: dict = {"name": comp.name}

            # Propagate inter-component dependencies from parent linkage
            if comp.parent_id:
                parent = session.query(Component).filter_by(id=comp.parent_id).first()
                if parent and parent.name != "Environment" and not parent.name.startswith("Environment:"):
                    lib["depends_on"] = [parent.name]

            # Attach external deps that are linked to this component
            external_deps = []
            for dep in comp.dependencies:
                # Format: "name/version" for Conan
                dep_ref = dep.name
                if dep.version:
                    dep_ref = f"{dep.name}/{dep.version}"
                external_deps.append(dep_ref)

            if external_deps:
                lib["external_deps"] = external_deps

            libraries.append(lib)

    return libraries


def step_scaffold(args: argparse.Namespace):
    """Run the project scaffolding agent."""
    print("=" * 60)
    print("STEP: Scaffold project")
    print("=" * 60)

    # 0. Persist CLI-provided name/working-directory to DB
    cli_name = args.name
    cli_workdir = args.working_directory

    if cli_name or cli_workdir:
        _set_project_meta(name=cli_name, working_directory=cli_workdir)
        if cli_name:
            print(f"  Set project name: {cli_name}")
        if cli_workdir:
            print(f"  Set working directory: {cli_workdir}")
        print()

    # 1. Read project metadata
    meta = _get_project_meta()
    project_name = meta["name"]
    working_directory = meta["working_directory"]

    if not project_name:
        print("  ERROR: Project name not set.")
        print("  Use --name <project-name> or set it in the dashboard.\n")
        return None
    if not working_directory:
        print("  ERROR: Working directory not set.")
        print("  Use --working-directory <path> or set it in the dashboard.\n")
        return None

    print(f"  Project:  {project_name}")
    print(f"  Output:   {working_directory}")

    # 2. Build library specs from components
    libraries = _get_libraries_from_components()

    if not libraries:
        print("  WARNING: No components found in the database.")
        print("  Creating a single 'core' library as default.\n")
        libraries = [{"name": "core"}]

    lib_names = ", ".join(lib["name"] for lib in libraries)
    print(f"  Libraries: {lib_names}")

    # 3. Merge extra deps from CLI
    extra_dependencies = args.dep or None
    if extra_dependencies:
        print(f"  Extra Conan deps: {', '.join(extra_dependencies)}")

    print(f"  C++ standard: C++{args.std}")
    print()

    # 4. Ensure working directory exists
    os.makedirs(working_directory, exist_ok=True)

    # 5. Check if project already exists
    project_dir = os.path.join(working_directory, project_name)
    cmake_file = os.path.join(project_dir, "CMakeLists.txt")
    if os.path.isfile(cmake_file):
        print(f"  Project already exists at {project_dir}")
        print("  Skipping scaffold. Delete the directory to re-run.\n")
        return project_dir

    # 6. Run the scaffold agent
    prompt_log = os.path.join(LOGS_DIR, "scaffold_project.md")

    result = scaffold_project(
        skill_dir=_SCAFFOLD_SKILL,
        project_name=project_name,
        libraries=libraries,
        working_directory=working_directory,
        extra_dependencies=extra_dependencies,
        cpp_standard=args.std,
        model=args.model,
        max_tokens=args.max_tokens,
        max_turns=args.max_turns,
        prompt_log_file=prompt_log,
    )

    print()
    print("=" * 60)
    print("SCAFFOLD COMPLETE")
    print("=" * 60)
    print()

    summary = result.get("summary", "(no summary)")
    if summary:
        for line in summary.splitlines():
            print(f"  {line}")
    print()

    files = result.get("files_modified", [])
    if files:
        print(f"  Files ({len(files)}):")
        for f in files:
            print(f"    {f}")

    build_ok = result.get("build_success")
    if build_ok is not None:
        status = "PASSED" if build_ok else "FAILED"
        print(f"\n  Build verification: {status}")
    print()

    return project_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scaffold the C++ project using LLM agent with terminal tools.",
    )
    parser.add_argument(
        "--name", default="calculator-engine",
        help="Project name in kebab-case. Persisted to DB. (default: calculator-engine)",
    )
    parser.add_argument(
        "--working-directory", default=os.path.expanduser("~/dev/calculator-example"),
        help="Directory where the project folder will be created. Persisted to DB. "
             "(default: ~/dev/calculator-example)",
    )
    parser.add_argument(
        "--std", type=int, default=20, choices=[20, 23, 26],
        help="C++ standard version (default: 20)",
    )
    parser.add_argument(
        "--dep", action="append", default=[],
        help="Extra Conan dependency (e.g. --dep eigen/3.4.0). Repeatable.",
    )
    parser.add_argument(
        "--model", default="",
        help="LLM model override (default: LLM_MODEL env var)",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=65536,
        help="Max tokens per LLM turn (default: 4096)",
    )
    parser.add_argument(
        "--max-turns", type=int, default=100,
        help="Max tool-loop iterations for build phase (default: 50)",
    )

    args = parser.parse_args()

    log_file = _configure_logging()
    print(f"Pipeline log: {log_file}")

    init_neo4j()
    try:
        init_db()
        step_scaffold(args)
    except Exception as e:
        logging.getLogger(__name__).exception("Scaffold failed: %s", e)
        print(f"\nScaffold failed: {e}")
        print(f"Check {log_file} for details.")
        raise
    finally:
        close_neo4j()