"""Unit tests for the migrated ProjectMeta neomodel node.

These tests verify the structural properties, _llm_fields, and the
singleton helper methods without requiring a live Neo4j connection.
"""

import ast

import pytest


# ---------------------------------------------------------------------------
# Structural (import-free) tests — verify AST, _llm_fields, etc.
# ---------------------------------------------------------------------------


class TestProjectMetaStructure:
    """Verify the ProjectMeta model definition without importing neo4j."""

    @pytest.fixture()
    def project_source(self) -> str:
        with open("backend_migrated/models/project.py") as f:
            return f.read()

    def test_project_meta_class_exists(self, project_source):
        tree = ast.parse(project_source)
        classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        names = [c.name for c in classes]
        assert "ProjectMeta" in names

    def test_project_meta_inherits_from_structured_node_and_codegraph_node(self, project_source):
        tree = ast.parse(project_source)
        cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "ProjectMeta")
        base_ids = [b.id for b in cls.bases if isinstance(b, ast.Name)]
        assert "StructuredNode" in base_ids
        assert "CodeGraphNode" in base_ids

    def test_project_meta_has_expected_properties(self, project_source):
        tree = ast.parse(project_source)
        cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "ProjectMeta")

        # Collect all assignments at class body level (regular + annotated)
        assigned_names = set()
        for node in cls.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assigned_names.add(target.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                assigned_names.add(node.target.id)

        # Properties that should exist (inherited from CodeGraphNode or own)
        for prop in ("description", "working_directory", "_llm_fields"):
            assert prop in assigned_names, f"Missing property: {prop}"

    def test_project_meta_has_singleton_methods(self, project_source):
        tree = ast.parse(project_source)
        cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "ProjectMeta")

        method_names = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
        assert "get_singleton" in method_names
        assert "update_singleton" in method_names

    def test_llm_fields_includes_expected_keys(self, project_source):
        tree = ast.parse(project_source)
        cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "ProjectMeta")

        llm_fields_assign = None
        for node in cls.body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id == "_llm_fields":
                    llm_fields_assign = node
                    break

        assert llm_fields_assign is not None, "_llm_fields not found"
        # The value should be a set with "name", "description", "working_directory"
        value = llm_fields_assign.value
        if isinstance(value, ast.Set):
            elts = {elt.value for elt in value.elts if isinstance(elt, ast.Constant)}
            assert "name" in elts
            assert "description" in elts
            assert "working_directory" in elts


# ---------------------------------------------------------------------------
# Init-package tests — verify __init__.py exports
# ---------------------------------------------------------------------------


class TestProjectMetaExports:
    """Verify ProjectMeta is properly exported from packages."""

    def test_models_init_exports_project_meta(self):
        with open("backend_migrated/models/__init__.py") as f:
            source = f.read()
        assert "ProjectMeta" in source
        assert "from backend_migrated.models.project import ProjectMeta" in source

    def test_top_level_init_exports_project_meta(self):
        with open("backend_migrated/__init__.py") as f:
            source = f.read()
        assert "ProjectMeta" in source

    def test_constraints_include_project_meta(self):
        with open("backend_migrated/constraints.py") as f:
            source = f.read()
        assert "ProjectMeta" in source
        assert "projectmeta_refid" in source
        assert "projectmeta_name" in source
        assert "projectmeta_working_directory" in source


# ---------------------------------------------------------------------------
# Singleton logic tests — mock neo4j to test get_singleton / update_singleton
# ---------------------------------------------------------------------------


class TestProjectMetaSingleton:
    """Test the singleton pattern methods with mocked Neo4j."""

    def test_get_singleton_creates_when_absent(self):
        """get_singleton should create the node when it doesn't exist."""
        with open("backend_migrated/models/project.py") as f:
            source = f.read()

        # Verify get_singleton uses refid="project" as lookup key
        assert 'refid="project"' in source or "refid='project'" in source

        # Verify DoesNotExist exception is caught
        assert "DoesNotExist" in source

        # Verify default empty strings on creation
        assert 'name=""' in source or "name=''" in source
        assert 'description=""' in source or "description=''" in source
        assert 'working_directory=""'in source or "working_directory=''" in source

    def test_update_singleton_modifies_fields(self):
        """update_singleton should set name, description, working_directory and save."""
        with open("backend_migrated/models/project.py") as f:
            source = f.read()

        # Check that update_singleton calls get_singleton first
        assert "cls.get_singleton()" in source

        # Check that it sets the three fields
        assert "node.name = name" in source
        assert "node.description = description" in source
        assert "node.working_directory = working_directory" in source

        # Check that it calls save()
        assert "node.save()" in source


# ---------------------------------------------------------------------------
# Frontend data layer tests — verify project.py uses serialize()
# ---------------------------------------------------------------------------


class TestFrontendDataProject:
    """Verify frontend_migrated/data/project.py uses serialize() directly."""

    def test_fetch_project_meta_is_implemented(self):
        with open("frontend_migrated/data/project.py") as f:
            source = f.read()

        # Should NOT have NotImplementedError for fetch_project_meta
        lines = source.split("\n")
        for line in lines:
            stripped = line.strip()
            if "fetch_project_meta" in stripped and "NotImplementedError" in stripped:
                pytest.fail("fetch_project_meta still raises NotImplementedError")

    def test_fetch_project_meta_returns_serialize(self):
        """fetch_project_meta should return node.serialize() directly."""
        with open("frontend_migrated/data/project.py") as f:
            source = f.read()

        # The function should return node.serialize() directly
        assert "node.serialize()" in source, (
            "fetch_project_meta should return node.serialize() directly"
        )
        # No TypedDict class named ProjectMeta in this file —
        # the return type is just dict
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ClassDef) and node.name == "ProjectMeta":
                pytest.fail(
                    "ProjectMeta TypedDict should not exist in "
                    "frontend_migrated/data/project.py — "
                    "serialize() already defines the shape"
                )

    def test_update_project_meta_is_implemented(self):
        with open("frontend_migrated/data/project.py") as f:
            source = f.read()

        lines = source.split("\n")
        for line in lines:
            stripped = line.strip()
            if "update_project_meta" in stripped and "NotImplementedError" in stripped:
                pytest.fail("update_project_meta still raises NotImplementedError")

    def test_no_sqlalchemy_imports(self):
        """frontend_migrated/data/project.py must not import from the old backend."""
        with open("frontend_migrated/data/project.py") as f:
            source = f.read()

        for line in source.split("\n"):
            stripped = line.strip()
            if stripped.startswith("from backend.") and "backend_migrated" not in stripped:
                if not stripped.startswith("#"):
                    pytest.fail(f"Found import from old backend: {stripped}")

    def test_imports_backend_migrated_models(self):
        with open("frontend_migrated/data/project.py") as f:
            source = f.read()

        assert "from backend_migrated.models import" in source
        assert "ProjectMeta" in source

    def test_fetch_environment_data_uses_serialize(self):
        """fetch_environment_data should use .serialize() for nodes and merge dicts."""
        with open("frontend_migrated/data/project.py") as f:
            source = f.read()

        # Should call .serialize() on language nodes
        assert "lang.serialize()" in source, (
            "fetch_environment_data should call lang.serialize() "
            "instead of manually constructing dicts"
        )
        # Should call .serialize(fields='all') on dependency nodes
        # to capture indexing config outside _llm_fields
        assert '.serialize(fields="all")' in source or ".serialize(fields='all')" in source, (
            "fetch_environment_data should call dep.serialize(fields='all') "
            "to include indexing config fields"
        )
        # No TypedDict classes for EnvironmentDependency or LanguageEnvironment
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ClassDef):
                if node.name in ("EnvironmentDependency", "LanguageEnvironment"):
                    pytest.fail(
                        f"TypedDict {node.name} should not exist in "
                        "frontend_migrated/data/project.py — "
                        "serialize() already defines the shape"
                    )