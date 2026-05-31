#!/usr/bin/env python
"""
Build the scaffolded/skeleton project and index it into Neo4j via Doxygen.

This is pipeline step 05a, run after 05_generate_skeleton.py which writes
skeleton source files. This script:

  1. Reads project metadata (name, working_directory) from SQLite
  2. Runs the C++ build pipeline (conan install → cmake configure → cmake build)
  3. Runs Doxygen to generate XML from the skeleton headers/sources
  4. Ingests the Doxygen XML into Neo4j (as-built codebase graph)
  5. Links design-intent nodes to as-built nodes via IMPLEMENTED_BY edges

The as-built graph lets downstream agents (verification, implementation)
compare design intent (from step 03) against the actual code skeleton.

If the project does not use C++/CMake, this script will detect that and
skip the build/indexing steps with a warning.

Assumes 04_scaffold_project.py and 05_generate_skeleton.py have been run.

Usage:
    source .venv/bin/activate
    python scripts/05a_build_and_index.py
    python scripts/05a_build_and_index.py --skip-build
    python scripts/05a_build_and_index.py --skip-index
    python scripts/05a_build_and_index.py --name calculator-engine --working-directory ~/dev/calculator-example
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv

load_dotenv()

from backend.db import init_db, get_session
from backend.db.models import Component, Language, ProjectMeta
from codegraph.neo4j import Neo4jConnection
from backend.db.neo4j.sync import sync_full_design
from services.dependencies import get_neo4j, init_neo4j, close_neo4j

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
LOGS_DIR = os.path.join(REPO_ROOT, "logs")


def _configure_logging():
    """Set up file logging for the build-and-index pipeline."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_file = os.path.join(LOGS_DIR, "build_index_pipeline.log")

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

    for name in ["neo4j", "neo4j.driver", "neo4j.io", "neo4j.pool"]:
        logging.getLogger(name).setLevel(logging.WARNING)

    return log_file


# ---------------------------------------------------------------------------
# Step 1: Project metadata
# ---------------------------------------------------------------------------


def _get_or_create_project_meta(session) -> ProjectMeta:
    """Get the singleton ProjectMeta row, creating it if needed."""
    meta = session.query(ProjectMeta).filter_by(id=1).first()
    if not meta:
        meta = ProjectMeta(id=1, name="", description="", working_directory="")
        session.add(meta)
        session.flush()
    return meta


def _get_project_meta() -> dict:
    """Read project metadata from SQLite."""
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


# ---------------------------------------------------------------------------
# Step 2: Build pipeline
# ---------------------------------------------------------------------------


def _run_cmd(
    cmd: list[str],
    cwd: str,
    description: str,
    timeout: int = 300,
) -> tuple[bool, str]:
    """Run a command and return (success, output).

    Args:
        cmd: Command and arguments.
        cwd: Working directory.
        description: Human-readable description for logging.
        timeout: Timeout in seconds.

    Returns:
        Tuple of (success: bool, output: str).
    """
    log = logging.getLogger("pipeline.build")
    log.info("Running: %s (cwd=%s)", " ".join(cmd), cwd)
    print(f"    {description}...")

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr

        if result.returncode != 0:
            log.error("Command failed (%d): %s\n%s", result.returncode, " ".join(cmd), output[:2000])
            print(f"    FAILED: {description}")
            # Print last 20 lines of error for visibility
            error_lines = result.stderr.strip().split("\n")[-20:]
            for line in error_lines:
                print(f"      {line}")
            return False, output

        log.info("Command succeeded: %s", " ".join(cmd))
        return True, output

    except FileNotFoundError:
        msg = f"Command not found: {cmd[0]}"
        log.error(msg)
        print(f"    ERROR: {msg}")
        return False, msg
    except subprocess.TimeoutExpired:
        msg = f"Command timed out after {timeout}s: {' '.join(cmd)}"
        log.error(msg)
        print(f"    TIMEOUT: {description}")
        return False, msg


def step_build(project_dir: str, skip_tests: bool = False) -> bool:
    """Run the C++ build pipeline.

    Steps:
      1. Python venv setup (if python/setup.sh exists)
      2. conan install
      3. cmake --preset conan-debug
      4. cmake --build --preset conan-debug
      5. ctest --preset conan-debug (optional)

    Args:
        project_dir: Absolute path to the project root.
        skip_tests: If True, skip the test step.

    Returns:
        True if build succeeded, False otherwise.
    """
    print("=" * 60)
    print("STEP 5a.1: Build project")
    print("=" * 60)
    print(f"  Project dir: {project_dir}\n")

    build_dir = os.path.join(project_dir, "build")

    # Step 1: Python venv setup
    setup_sh = os.path.join(project_dir, "python", "setup.sh")
    if os.path.isfile(setup_sh):
        ok, _ = _run_cmd(
            ["bash", setup_sh],
            cwd=project_dir,
            description="Python environment setup",
            timeout=120,
        )
        if not ok:
            print("  WARNING: Python setup failed, continuing anyway\n")

    # Step 2: Conan install
    ok, _ = _run_cmd(
        ["conan", "install", ".", "--build=missing", "-s", "build_type=Debug"],
        cwd=project_dir,
        description="Conan install dependencies",
        timeout=300,
    )
    if not ok:
        print("\n  Build FAILED at conan install step.\n")
        return False

    # Step 3: CMake configure
    ok, _ = _run_cmd(
        ["cmake", "--preset", "conan-debug"],
        cwd=project_dir,
        description="CMake configure (debug preset)",
        timeout=120,
    )
    if not ok:
        print("\n  Build FAILED at CMake configure step.\n")
        return False

    # Step 4: CMake build
    ok, build_output = _run_cmd(
        ["cmake", "--build", "--preset", "conan-debug"],
        cwd=project_dir,
        description="CMake build (debug)",
        timeout=600,
    )
    if not ok:
        print("\n  Build FAILED at CMake build step.\n")
        return False

    # Step 5: Run tests (optional)
    if not skip_tests:
        ok, _ = _run_cmd(
            ["ctest", "--preset", "conan-debug", "--output-on-failure"],
            cwd=project_dir,
            description="Run tests (ctest)",
            timeout=120,
        )
        if not ok:
            print("\n  WARNING: Some tests failed, but build succeeded.\n")
            # Don't fail the whole pipeline on test failures for skeleton code

    print("\n  Build SUCCEEDED ✓\n")
    return True


# ---------------------------------------------------------------------------
# Step 3: Doxygen XML generation
# ---------------------------------------------------------------------------


def step_doxygen(project_dir: str) -> str | None:
    """Run Doxygen to generate XML from the project source.

    Args:
        project_dir: Absolute path to the project root.

    Returns:
        Path to the XML output directory, or None if Doxygen failed.
    """
    print("=" * 60)
    print("STEP 5a.2: Generate Doxygen XML")
    print("=" * 60)

    build_dir = os.path.join(project_dir, "build")

    # Check if Doxyfile.in exists
    doxyfile_in = os.path.join(project_dir, "Doxyfile.in")
    if not os.path.isfile(doxyfile_in):
        print("  WARNING: No Doxyfile.in found in project root.")
        print("  Attempting to generate Doxygen XML directly...\n")
        return _doxygen_manual(project_dir)

    # Run cmake --build --target doxygen
    ok, output = _run_cmd(
        ["cmake", "--build", "--preset", "conan-debug", "--target", "doxygen"],
        cwd=project_dir,
        description="Generate Doxygen XML (cmake target)",
        timeout=120,
    )

    if ok:
        xml_dir = os.path.join(build_dir, "docs", "xml")
        if os.path.isdir(xml_dir):
            # Count XML files
            xml_count = len([f for f in os.listdir(xml_dir) if f.endswith(".xml")])
            print(f"  Doxygen XML generated: {xml_count} XML files in {xml_dir}\n")
            return xml_dir
        else:
            print("  WARNING: Doxygen ran but no XML output found.\n")
            return None

    # Fallback: run doxygen directly
    print("  CMake target failed, trying direct doxygen...\n")
    return _doxygen_manual(project_dir)


def _doxygen_manual(project_dir: str) -> str | None:
    """Run Doxygen manually (without CMake) as a fallback.

    Generates a minimal Doxyfile, runs doxygen, and returns the XML dir.
    """
    # Check if doxygen binary exists
    if not shutil.which("doxygen"):
        print("  ERROR: 'doxygen' not found on PATH.")
        print("  Install doxygen to enable codebase indexing.\n")
        return None

    build_dir = os.path.join(project_dir, "build")
    os.makedirs(build_dir, exist_ok=True)

    docs_dir = os.path.join(build_dir, "docs")
    xml_dir = os.path.join(docs_dir, "xml")
    os.makedirs(xml_dir, exist_ok=True)

    # Find the project name
    project_name = os.path.basename(project_dir)

    # Find the library parent directory (project_name/project_name/)
    lib_parent = os.path.join(project_dir, project_name)
    if not os.path.isdir(lib_parent):
        # Fallback: scan for directories that contain src/
        for entry in os.listdir(project_dir):
            entry_path = os.path.join(project_dir, entry)
            if os.path.isdir(entry_path) and os.path.isdir(os.path.join(entry_path, "src")):
                lib_parent = entry_path
                break

    if not os.path.isdir(lib_parent):
        print(f"  ERROR: Cannot find source directory for Doxygen.\n")
        return None

    # Generate a minimal Doxyfile
    doxyfile_content = f"""\
PROJECT_NAME = "{project_name}"
OUTPUT_DIRECTORY = {docs_dir}
GENERATE_HTML = NO
GENERATE_LATEX = NO
GENERATE_XML = YES
XML_OUTPUT = xml
INPUT = {lib_parent}
FILE_PATTERNS = *.hpp *.h *.cpp *.c
RECURSIVE = YES
EXCLUDE_PATTERNS = */build/* */test/* */.conan/*
EXTRACT_ALL = YES
EXTRACT_PRIVATE = YES
EXTRACT_STATIC = YES
QUIET = YES
"""

    doxyfile_path = os.path.join(build_dir, "Doxyfile.skeleton")
    with open(doxyfile_path, "w") as f:
        f.write(doxyfile_content)

    ok, output = _run_cmd(
        ["doxygen", doxyfile_path],
        cwd=project_dir,
        description="Run Doxygen (manual fallback)",
        timeout=120,
    )

    if ok and os.path.isdir(xml_dir):
        xml_count = len([f for f in os.listdir(xml_dir) if f.endswith(".xml")])
        print(f"  Doxygen XML generated: {xml_count} XML files\n")
        return xml_dir
    else:
        print("  Doxygen failed or produced no output.\n")
        return None


# ---------------------------------------------------------------------------
# Step 4: Ingest into Neo4j (as-built codebase)
# ---------------------------------------------------------------------------


def step_index_neo4j(xml_dir: str, project_name: str) -> bool:
    """Ingest Doxygen XML into Neo4j as as-built codebase nodes.

    Uses the doxygen-index library to parse Doxygen XML and create
    :Compound, :Member, :Namespace, etc. nodes in Neo4j.

    Args:
        xml_dir: Path to the directory containing Doxygen XML files.
        project_name: Source label for provenance tracking.

    Returns:
        True if ingestion succeeded, False otherwise.
    """
    print("=" * 60)
    print("STEP 5a.3: Index as-built codebase into Neo4j")
    print("=" * 60)

    try:
        from doxygen_index.neo4j_backend import ingest as neo4j_ingest
    except ImportError:
        print("  ERROR: doxygen-index is not installed.")
        print("  Run: pip install -e /path/to/Doxygen-Dependency-Parser\n")
        return False

    try:
        neo4j_ingest(
            xml_dir=xml_dir,
            source=project_name,
            clear=True,  # Clear previous as-built data for this source
        )
        print(f"  Successfully indexed '{project_name}' into Neo4j\n")
        return True
    except Exception as e:
        log = logging.getLogger("pipeline.index")
        log.exception("Neo4j ingestion failed: %s", e)
        print(f"  ERROR: Neo4j ingestion failed: {e}\n")
        return False


# ---------------------------------------------------------------------------
# Step 5: Ingest into SQLite (local codebase.db)
# ---------------------------------------------------------------------------


def step_index_sqlite(xml_dir: str, project_name: str, project_dir: str) -> bool:
    """Ingest Doxygen XML into a local SQLite codebase database.

    Creates a codebase.db in the build directory with parsed
    Compound, Member, and Namespace records.

    Args:
        xml_dir: Path to the directory containing Doxygen XML files.
        project_name: Source label for provenance tracking.
        project_dir: Root directory of the project (for placing the db).

    Returns:
        True if ingestion succeeded, False otherwise.
    """
    print("=" * 60)
    print("STEP 5a.4: Index as-built codebase into SQLite")
    print("=" * 60)

    try:
        from doxygen_index.sqlite_backend import ingest as sqlite_ingest
    except ImportError:
        print("  ERROR: doxygen-index is not installed.\n")
        return False

    build_dir = os.path.join(project_dir, "build")
    os.makedirs(build_dir, exist_ok=True)
    db_path = os.path.join(build_dir, "docs", "codebase.db")

    try:
        result = sqlite_ingest(
            xml_dir=xml_dir,
            db_path=db_path,
            source=project_name,
            append=False,
        )
        counts = result if result else {}
        print(f"  SQLite codebase.db created at {db_path}")
        for entity_type, count in counts.items():
            print(f"    {entity_type}: {count}")
        print()
        return True
    except Exception as e:
        log = logging.getLogger("pipeline.index")
        log.exception("SQLite ingestion failed: %s", e)
        print(f"  ERROR: SQLite ingestion failed: {e}\n")
        return False


# ---------------------------------------------------------------------------
# Step 6: Link design → as-built (IMPLEMENTED_BY edges)
# ---------------------------------------------------------------------------


def step_link_design_to_asbuilt() -> dict:
    """Create IMPLEMENTED_BY edges between Design nodes and as-built nodes.

    Matches design-intent :Design nodes to :Compound/:Member/:Namespace
    nodes by qualified_name, creating IMPLEMENTED_BY relationships.

    Returns:
        Dict with link count.
    """
    print("=" * 60)
    print("STEP 5a.5: Link design intent → as-built codebase")
    print("=" * 60)

    try:
        with get_neo4j().session() as session:
            result = session.run("""
                MATCH (d:Design)
                WHERE d.qualified_name IS NOT NULL AND d.qualified_name <> ''
                OPTIONAL MATCH (c:Compound {qualified_name: d.qualified_name})
                OPTIONAL MATCH (m:Member {qualified_name: d.qualified_name})
                OPTIONAL MATCH (ns:Namespace {name: d.qualified_name})
                WITH d, coalesce(c, m, ns) AS target
                WHERE target IS NOT NULL
                MERGE (d)-[:IMPLEMENTED_BY]->(target)
                RETURN count(*) AS cnt
            """)
            direct_count = result.single()["cnt"] if result.single() else 0

            # Also try matching by refid
            result2 = session.run("""
                MATCH (d:Design)
                WHERE d.refid IS NOT NULL AND d.refid <> ''
                AND NOT EXISTS { (d)-[:IMPLEMENTED_BY]->() }
                OPTIONAL MATCH (c:Compound {refid: d.refid})
                OPTIONAL MATCH (m:Member {refid: d.refid})
                WITH d, coalesce(c, m) AS target
                WHERE target IS NOT NULL
                MERGE (d)-[:IMPLEMENTED_BY]->(target)
                RETURN count(*) AS cnt
            """)
            refid_count = result2.single()["cnt"] if result2.single() else 0

        total = direct_count + refid_count
        print(f"  IMPLEMENTED_BY edges created: {total}")
        print(f"    By qualified_name: {direct_count}")
        print(f"    By refid:          {refid_count}\n")

        # Update implementation_status on Design nodes
        with get_neo4j().session() as session:
            result = session.run("""
                MATCH (d:Design)-[:IMPLEMENTED_BY]->()
                SET d.implementation_status = 'skeleton'
                RETURN count(d) AS cnt
            """)
            skeleton_count = result.single()["cnt"] if result.single() else 0

        print(f"  Design nodes marked 'skeleton': {skeleton_count}\n")

        return {
            "implemented_by_edges": total,
            "skeleton_nodes": skeleton_count,
        }

    except Exception as e:
        log = logging.getLogger("pipeline.link")
        log.exception("Link design → as-built failed: %s", e)
        print(f"  ERROR: Link failed: {e}\n")
        return {"implemented_by_edges": 0, "skeleton_nodes": 0}


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def step_summary(build_ok: bool, xml_dir: str | None, neo4j_ok: bool, sqlite_ok: bool, link_result: dict) -> None:
    """Print a pipeline summary."""
    print("\n" + "=" * 60)
    print("BUILD & INDEX SUMMARY")
    print("=" * 60)
    print(f"  Build:            {'PASSED ✓' if build_ok else 'FAILED ✗'}")
    print(f"  Doxygen XML:      {xml_dir or 'not generated'}")
    print(f"  Neo4j ingestion:  {'PASSED ✓' if neo4j_ok else 'FAILED ✗' if xml_dir else 'SKIPPED'}")
    print(f"  SQLite ingestion: {'PASSED ✓' if sqlite_ok else 'FAILED ✗' if xml_dir else 'SKIPPED'}")
    print(f"  Design links:     {link_result.get('implemented_by_edges', 0)} IMPLEMENTED_BY edges")
    print(f"  Skeleton nodes:   {link_result.get('skeleton_nodes', 0)} marked 'skeleton'")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def step_build_and_index(args: argparse.Namespace) -> None:
    """Run the full build + index pipeline."""
    # 0. Persist CLI-provided name/working-directory to DB
    if args.name or args.working_directory:
        _set_project_meta(name=args.name or "", working_directory=args.working_directory or "")

    # 1. Read project metadata
    meta = _get_project_meta()
    project_name = meta["name"]
    working_directory = meta["working_directory"]

    if not project_name:
        print("  ERROR: Project name not set.")
        print("  Use --name <project-name> or set it in the dashboard.\n")
        return
    if not working_directory:
        print("  ERROR: Working directory not set.")
        print("  Use --working-directory <path> or set it in the dashboard.\n")
        return

    project_dir = os.path.join(working_directory, project_name)
    if not os.path.isdir(project_dir):
        print(f"  ERROR: Project directory not found: {project_dir}")
        print(f"  Run 04_scaffold_project.py and 05_generate_skeleton.py first.\n")
        return

    print(f"  Project:  {project_name}")
    print(f"  Directory: {project_dir}\n")

    # Determine language
    language = args.language
    with get_session() as session:
        components = session.query(Component).order_by(Component.id).all()
        if components:
            comp = components[0]
            if comp.language_id:
                lang = session.query(Language).filter_by(id=comp.language_id).first()
                if lang:
                    language = lang.name.lower()
                    if "c++" in language or "cpp" in language:
                        language = "cpp"
                    elif "python" in language:
                        language = "python"

    # Only C++ projects have a build/index pipeline
    if language != "cpp":
        print(f"  Language is '{language}' — build & indexing is C++ only.")
        print("  Skipping build and Doxygen indexing.\n")
        return

    # 2. Build
    build_ok = False
    if not args.skip_build:
        build_ok = step_build(project_dir, skip_tests=args.skip_tests)
        if not build_ok and not args.force_index:
            print("  Build failed and --force-index not set. Stopping.")
            print("  Use --force-index to continue indexing despite build failure.\n")
            return
    else:
        print("  Build: SKIPPED (--skip-build)\n")
        build_ok = True  # Assume success if skipped

    # 3. Generate Doxygen XML
    xml_dir = None
    if not args.skip_index:
        xml_dir = step_doxygen(project_dir)

        if xml_dir and os.path.isdir(xml_dir):
            # 4. Index into Neo4j
            neo4j_ok = False
            if not args.skip_neo4j:
                neo4j_ok = step_index_neo4j(xml_dir, project_name)

            # 5. Index into SQLite (optional, for local analysis)
            sqlite_ok = False
            if not args.skip_sqlite:
                sqlite_ok = step_index_sqlite(xml_dir, project_name, project_dir)

            # 6. Link design → as-built
            link_result = {"implemented_by_edges": 0, "skeleton_nodes": 0}
            if neo4j_ok and not args.skip_link:
                link_result = step_link_design_to_asbuilt()
        else:
            neo4j_ok = False
            sqlite_ok = False
            link_result = {"implemented_by_edges": 0, "skeleton_nodes": 0}
            print("  No Doxygen XML available — skipping indexing and linking.\n")
    else:
        neo4j_ok = False
        sqlite_ok = False
        link_result = {"implemented_by_edges": 0, "skeleton_nodes": 0}
        print("  Indexing: SKIPPED (--skip-index)\n")

    # Summary
    step_summary(build_ok, xml_dir, neo4j_ok, sqlite_ok, link_result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build the C++ project and index into Neo4j via Doxygen.",
    )
    parser.add_argument(
        "--name", default="",
        help="Project name. Persisted to DB.",
    )
    parser.add_argument(
        "--working-directory", default="",
        help="Directory containing the project folder. Persisted to DB.",
    )
    parser.add_argument(
        "--language", default="cpp",
        choices=["cpp", "python"],
        help="Target language (default: cpp, auto-detected from DB)",
    )
    parser.add_argument(
        "--skip-build", action="store_true",
        help="Skip the build step (assume project is already built)",
    )
    parser.add_argument(
        "--skip-tests", action="store_true",
        help="Skip the test step (build only)",
    )
    parser.add_argument(
        "--skip-index", action="store_true",
        help="Skip Doxygen XML generation and indexing",
    )
    parser.add_argument(
        "--skip-neo4j", action="store_true",
        help="Skip Neo4j ingestion (only do SQLite)",
    )
    parser.add_argument(
        "--skip-sqlite", action="store_true",
        help="Skip SQLite ingestion (only do Neo4j)",
    )
    parser.add_argument(
        "--skip-link", action="store_true",
        help="Skip linking design intent to as-built nodes",
    )
    parser.add_argument(
        "--force-index", action="store_true",
        help="Continue to Doxygen indexing even if build fails",
    )

    args = parser.parse_args()

    log_file = _configure_logging()
    print(f"Pipeline log: {log_file}")

    init_neo4j()
    try:
        init_db()
        step_build_and_index(args)
    except Exception as e:
        logging.getLogger(__name__).exception("Build & index pipeline failed: %s", e)
        print(f"\nBuild & index pipeline failed: {e}")
        print(f"Check {log_file} for details.")
        raise
    finally:
        close_neo4j()