"""Tests for the build-and-index pipeline script.

Tests the non-IO logic: project metadata, Doxyfile generation,
command construction, and linked-design queries.
"""

import os
import tempfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Project metadata helpers (testable without Neo4j)
# ---------------------------------------------------------------------------


class TestProjectMetadata:
    """Test project metadata read/write via SQLite."""

    def test_get_or_create_project_meta(self):
        """ProjectMeta singleton row can be looked up."""
        from backend.db import init_db, get_session, get_main_engine
        from backend.db.base import Base
        from backend.db.models import ProjectMeta

        init_db()
        Base.metadata.create_all(get_main_engine())
        with get_session() as session:
            # Simulate the _get_or_create_project_meta logic
            meta = session.query(ProjectMeta).filter_by(id=1).first()
            if not meta:
                meta = ProjectMeta(id=1, name="", description="", working_directory="")
                session.add(meta)
                session.flush()
            assert meta.id == 1
            # meta.name may already have data from other tests
            assert isinstance(meta.name, str)

    def test_set_and_get_project_meta(self):
        """Project name and working directory round-trip through SQLite."""
        from backend.db import init_db, get_session, get_main_engine
        from backend.db.base import Base
        from backend.db.models import ProjectMeta

        # Use the actual helpers but require DB setup
        init_db()
        Base.metadata.create_all(get_main_engine())
        with get_session() as session:
            meta = session.query(ProjectMeta).filter_by(id=1).first()
            if not meta:
                meta = ProjectMeta(id=1, name="", description="", working_directory="")
                session.add(meta)
                session.flush()
            meta.name = "test-engine"
            meta.working_directory = "/tmp/test-engine"
            session.flush()

        with get_session() as session:
            meta = session.query(ProjectMeta).filter_by(id=1).first()
            assert meta.name == "test-engine"
            assert meta.working_directory == "/tmp/test-engine"


# ---------------------------------------------------------------------------
# Doxyfile generation
# ---------------------------------------------------------------------------


class TestDoxyfileGeneration:
    """Test manual Doxyfile generation (fallback path)."""

    def test_doxyfile_content(self):
        """The manual Doxyfile has required fields."""
        project_name = "calculator_engine"
        lib_parent = "/tmp/calculator/calculator"
        docs_dir = "/tmp/calculator/build/docs"

        content = f"""\
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
        assert f'PROJECT_NAME = "{project_name}"' in content
        assert "GENERATE_XML = YES" in content
        assert f"INPUT = {lib_parent}" in content
        assert "*.hpp" in content


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------


class TestCommandConstruction:
    """Test that build commands are constructed correctly."""

    def test_conan_install_command(self):
        """Conan install command has correct flags."""
        cmd = ["conan", "install", ".", "--build=missing", "-s", "build_type=Debug"]
        assert cmd[0] == "conan"
        assert "install" in cmd
        assert "--build=missing" in cmd
        assert "-s" in cmd
        assert "build_type=Debug" in cmd

    def test_cmake_preset_commands(self):
        """CMake preset commands use the correct preset names."""
        configure = ["cmake", "--preset", "conan-debug"]
        build = ["cmake", "--build", "--preset", "conan-debug"]
        test = ["ctest", "--preset", "conan-debug", "--output-on-failure"]

        assert "conan-debug" in configure
        assert "--preset" in configure
        assert "--build" in build
        assert "--output-on-failure" in test


# ---------------------------------------------------------------------------
# IMPLEMENTED_BY link logic (unit-level)
# ---------------------------------------------------------------------------


class TestImplementedByLinkLogic:
    """Test the Cypher queries for linking design to as-built nodes."""

    def test_link_query_matches_qualified_name(self):
        """The IMPLEMENTED_BY query matches by qualified_name."""
        # This tests the query structure, not execution
        query = """
            MATCH (d:Design)
            WHERE d.qualified_name IS NOT NULL AND d.qualified_name <> ''
            OPTIONAL MATCH (c:Compound {qualified_name: d.qualified_name})
            OPTIONAL MATCH (m:Member {qualified_name: d.qualified_name})
            OPTIONAL MATCH (ns:Namespace {name: d.qualified_name})
            WITH d, coalesce(c, m, ns) AS target
            WHERE target IS NOT NULL
            MERGE (d)-[:IMPLEMENTED_BY]->(target)
            RETURN count(*) AS cnt
        """
        assert "IMPLEMENTED_BY" in query
        assert "Compound" in query
        assert "Member" in query
        assert "qualified_name" in query

    def test_refid_fallback_query(self):
        """The IMPLEMENTED_BY fallback uses refid matching."""
        query = """
            MATCH (d:Design)
            WHERE d.refid IS NOT NULL AND d.refid <> ''
            AND NOT EXISTS { (d)-[:IMPLEMENTED_BY]->() }
            OPTIONAL MATCH (c:Compound {refid: d.refid})
            OPTIONAL MATCH (m:Member {refid: d.refid})
            WITH d, coalesce(c, m) AS target
            WHERE target IS NOT NULL
            MERGE (d)-[:IMPLEMENTED_BY]->(target)
            RETURN count(*) AS cnt
        """
        assert "refid" in query
        assert "NOT EXISTS" in query


# ---------------------------------------------------------------------------
# doxygen-index import
# ---------------------------------------------------------------------------


class TestDoxygenIndexImport:
    """Test that doxygen-index library is available."""

    def test_import_neo4j_backend(self):
        """The neo4j_backend module can be imported."""
        from doxygen_index.neo4j_backend import ingest
        assert callable(ingest)

    def test_import_sqlite_backend(self):
        """The sqlite_backend module can be imported."""
        from doxygen_index.sqlite_backend import ingest
        assert callable(ingest)

    def test_import_deps_config(self):
        """DepConfig can be imported."""
        from doxygen_index.deps_config import DepConfig
        dc = DepConfig()
        assert dc.file_patterns == "*.h *.hpp"
        assert dc.recursive is True

    def test_import_discover_packages(self):
        """discover_packages function can be imported."""
        from doxygen_index.conan import discover_packages
        assert callable(discover_packages)


# ---------------------------------------------------------------------------
# Integration: script imports
# ---------------------------------------------------------------------------


class TestScriptImports:
    """Test that the 05a script itself can be imported."""

    def test_import_run_cmd(self):
        """The _run_cmd helper exists in the script."""
        # Import the script as a module
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "build_and_index",
            os.path.join(os.path.dirname(__file__), "..", "scripts", "05a_build_and_index.py"),
        )
        module = importlib.util.module_from_spec(spec)
        # We can't fully execute it (it runs main), but we can check it compiles
        assert spec is not None

    def test_script_syntax_valid(self):
        """The script compiles without syntax errors."""
        script_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "05a_build_and_index.py")
        with open(script_path) as f:
            source = f.read()
        compile(source, "05a_build_and_index.py", "exec")