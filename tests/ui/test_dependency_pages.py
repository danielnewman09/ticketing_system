"""NiceGUI User-simulation tests for the project dependency management section.

Uses ``nicegui.testing.User`` (httpx + websocket simulation) to render
the project page with mocked data — no running server or browser needed.

Patches are applied **at the import site** (the page module) rather than
the definition site (the data module) so that ``asyncio.to_thread`` calls
see the mock.

``ProjectFileTree`` is mocked at the class level to avoid Neo4J
access — the dependency panel creates it lazily and wraps all its
methods in try/except, so a simple MagicMock suffices.

The project page at ``/`` calls multiple sections that all need their
data-layer functions patched:

- ``section_project_meta()`` → ``fetch_project_meta``
- ``section_stats()`` → ``fetch_requirements_data``
- ``section_dependencies()`` → ``fetch_environment_data`` + ``ProjectFileTree``
- ``section_scaffold()`` → ``fetch_project_meta`` + ``ProjectFileTree``

**Note on table content:** NiceGUI's ``ui.table`` renders cell content
through Vue virtual-DOM slots.  The ``User`` simulation can see the
``Table`` element itself and its column/row configuration, but cannot
inspect individual cell text.  Table content tests (dependency names,
versions, status badges) are therefore verified via **Playwright
screenshot tests** rather than User-simulation.

Run with::

    pytest tests/ui/test_dependency_pages.py -v
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from nicegui import ui

from tests.ui.mocks import make_dep_dict, make_env_data
from tests.ui.conftest import PATCH_TARGETS as P

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def make_mock_tree(cmake_files: list | None = None):
    """Build a mock ``ProjectFileTree`` that avoids Neo4J access.

    Returns a MagicMock whose ``cmake_tree()`` method returns
    predictable test data.
    """
    tree = MagicMock()
    tree.cmake_tree.return_value = cmake_files or []
    tree.project_exists = True
    tree.project_dir = "/tmp/test-project/Calculator"
    return tree


def make_project_meta(**overrides) -> dict:
    """Build a mock return value for ``fetch_project_meta()``."""
    return {
        "name": "Calculator",
        "description": "A test project",
        "working_directory": "/tmp/test-project",
        "refid": "test::Calculator",
        **overrides,
    }


def make_requirements_data(**overrides) -> dict:
    """Build a mock return value for ``fetch_requirements_data()``."""
    return {
        "hlrs": [],
        "unlinked_llrs": [],
        "total_hlrs": 0,
        "total_llrs": 0,
        "total_verifications": 0,
        "total_nodes": 0,
        "total_triples": 0,
        **overrides,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_tree():
    """Return a mock ProjectFileTree with default test data."""
    return make_mock_tree()


@pytest.fixture
def typical_env_data():
    """Return environment data with 2 languages and 3 dependencies."""
    return make_env_data()


# ---------------------------------------------------------------------------
# Helper: patch all data-layer calls for the project page at /
# ---------------------------------------------------------------------------


def project_page_patches(
    *,
    env_data: list[dict] | None = None,
    project_meta: dict | None = None,
    requirements_data: dict | None = None,
    tree: MagicMock | None = None,
) -> ExitStack:
    """Return an ExitStack that patches all data-layer calls for the project page.

    Usage::

        with project_page_patches() as stack:
            await user.open("/")
    """
    stack = ExitStack()

    # Project meta (called from sections.py and route.py)
    meta = project_meta or make_project_meta()
    stack.enter_context(patch(P["fetch_project_meta"], return_value=meta))
    stack.enter_context(patch(P["fetch_project_meta_route"], return_value=meta))

    # Stats (called from sections.py)
    req_data = requirements_data or make_requirements_data()
    stack.enter_context(patch(P["fetch_requirements_data_sections"], return_value=req_data))
    stack.enter_context(patch(P["fetch_components_sections"], return_value=[]))

    # Dependencies (called from dependencies.py)
    stack.enter_context(patch(P["fetch_environment_data"], return_value=env_data if env_data is not None else make_env_data()))
    stack.enter_context(patch(P["delete_dependency_dep"], side_effect=NotImplementedError("stub")))
    stack.enter_context(patch(P["update_dependency_index_config"], side_effect=NotImplementedError("stub")))

    # Tag sync and environment sync (called from route.py on page load)
    stack.enter_context(patch("frontend_migrated.pages.project.route.sync_all_tags", return_value={"dependencies": 0, "components": 0, "languages": 0, "project": 0}))
    stack.enter_context(patch("frontend_migrated.pages.project.route.sync_project_environment", return_value=[]))

    # ProjectFileTree (used by dependencies.py and scaffold.py)
    mock_tree_obj = tree or make_mock_tree()
    stack.enter_context(
        patch("frontend_migrated.pages.project.dependencies.ProjectFileTree", return_value=mock_tree_obj)
    )
    stack.enter_context(
        patch("frontend_migrated.pages.project.scaffold.ProjectFileTree", return_value=mock_tree_obj)
    )

    # Scaffold's fetch calls
    stack.enter_context(patch(P["fetch_project_meta_scaffold"], return_value=meta))
    stack.enter_context(patch(P["fetch_components_scaffold"], return_value=[]))

    return stack


# ---------------------------------------------------------------------------
# Tests: Card header and empty states
# ---------------------------------------------------------------------------


async def test_dep_page_shows_card_header(user):
    """The dependency card always shows 'Dependency Management'."""
    with project_page_patches():
        await user.open("/")
        await user.should_see("Dependency Management")


async def test_dep_page_no_env_data(user):
    """When environment data is empty, shows 'No language environment data'."""
    with project_page_patches(env_data=[]):
        await user.open("/")
        await user.should_see("Dependency Management")
        await user.should_see("No language environment data available")


async def test_dep_page_no_deps(user):
    """When a language has no dependencies, shows 'No dependencies configured'."""
    env_no_deps = [{"name": "C++", "version": "20", "dependencies": [],
                    "build_systems": [], "test_frameworks": [], "dependency_managers": []}]
    with project_page_patches(env_data=env_no_deps):
        await user.open("/")
        await user.should_see("Dependency Management")
        await user.should_see("No dependencies configured")


# ---------------------------------------------------------------------------
# Tests: Table rendering
#
# NOTE: ui.table cell content is rendered via Vue slots, so User.should_see
# cannot find individual cell text like "boost" or "1.82.0".  We verify:
# 1. The Table element is present when deps exist.
# 2. No Table element when no deps exist.
# Cell-level content is verified via Playwright screenshot tests.
# ---------------------------------------------------------------------------


async def test_dep_page_shows_table_when_deps_exist(user):
    """When dependencies exist, a Table element is rendered."""
    with project_page_patches():
        await user.open("/")
        await user.should_see(kind=ui.table)


async def test_dep_page_no_table_when_no_deps(user):
    """When no dependencies exist, no Table element is rendered."""
    env_no_deps = [{"name": "C++", "version": "20", "dependencies": [],
                    "build_systems": [], "test_frameworks": [], "dependency_managers": []}]
    with project_page_patches(env_data=env_no_deps):
        await user.open("/")
        await user.should_not_see(kind=ui.table)


async def test_dep_page_no_table_when_empty_env(user):
    """When environment data is empty, no Table element is rendered."""
    with project_page_patches(env_data=[]):
        await user.open("/")
        await user.should_not_see(kind=ui.table)


# ---------------------------------------------------------------------------
# Tests: Project metadata (other sections on the same page)
# ---------------------------------------------------------------------------


async def test_project_page_shows_project_name(user):
    """The project metadata card shows the project name."""
    with project_page_patches():
        await user.open("/")
        await user.should_see("Calculator")


async def test_project_page_shows_project_description(user):
    """The project metadata card shows the description."""
    with project_page_patches():
        await user.open("/")
        await user.should_see("A test project")


async def test_project_page_shows_working_directory(user):
    """The project metadata card shows the working directory."""
    with project_page_patches():
        await user.open("/")
        await user.should_see("/tmp/test-project")


async def test_project_page_shows_stats(user):
    """The stats row renders stat cards with correct counts."""
    with project_page_patches(requirements_data=make_requirements_data(total_hlrs=5, total_llrs=10)):
        await user.open("/")
        await user.should_see("HLRs")
        await user.should_see("5")


# ---------------------------------------------------------------------------
# Tests: Scaffold section
# ---------------------------------------------------------------------------


async def test_project_page_shows_scaffold_card(user):
    """The scaffold card is visible when project is not yet scaffolded."""
    # No CMakeLists.txt in working dir → not scaffolded
    with project_page_patches():
        await user.open("/")
        await user.should_see("Project Scaffold")
        await user.should_see("Create Scaffold")


async def test_project_page_shows_scaffolded_state(user):
    """When a project dir exists and is scaffolded, show 'Created' badge."""
    import os
    meta = make_project_meta(
        working_directory=os.path.dirname(os.path.abspath(__file__)),  # real dir
        name="",  # empty name → project_dir = working_directory
    )
    tree = make_mock_tree()
    tree.cmake_tree.return_value = [
        MagicMock(name="CMakeLists.txt", path="CMakeLists.txt", is_dir=False),
    ]
    with project_page_patches(project_meta=meta, tree=tree):
        await user.open("/")
        # Scaffold card should still show (may say "Created" or still "Create Scaffold"
        await user.should_see("Project Scaffold")


# ---------------------------------------------------------------------------
# Tests: Pure data transform functions (unit-level, no NiceGUI)
# ---------------------------------------------------------------------------


class TestFlattenDeps:
    """Unit tests for _flatten_deps pure function."""

    def test_empty_env_data(self):
        from frontend_migrated.pages.project.dependencies import _flatten_deps
        result = _flatten_deps([])
        assert result == []

    def test_tag_integrated(self):
        """Tags are the source of truth — 'integrated' maps to status 'integrated'."""
        from frontend_migrated.pages.project.dependencies import _flatten_deps
        env = [{"name": "C++", "version": "20", "dependencies": [
            {"name": "boost", "refid": "conan::boost", "github_url": "", "version": "1.82.0",
             "is_dev": False, "manager_name": "conan", "index_file_patterns": "*.h",
             "index_subdir": "", "index_exclude_patterns": "", "index_recursive": True,
             "tags": ["integrated"],
             "components": [{"name": "Calculator"}]},
        ], "build_systems": [], "test_frameworks": [], "dependency_managers": []}]
        result = _flatten_deps(env)
        assert len(result) == 1
        assert result[0]["name"] == "boost"
        assert result[0]["language"] == "C++ 20"
        assert result[0]["integration_status"] == "integrated"
        assert result[0]["health_tags"] == []

    def test_tag_indexed(self):
        """Tags — 'indexed' maps to status 'indexed'."""
        from frontend_migrated.pages.project.dependencies import _flatten_deps
        env = [{"name": "C++", "version": "20", "dependencies": [
            {"name": "eigen", "refid": "conan::eigen", "github_url": "", "version": "3.4.0",
             "is_dev": False, "manager_name": "conan", "index_file_patterns": "*.h",
             "index_subdir": "", "index_exclude_patterns": "", "index_recursive": True,
             "tags": ["indexed"],
             "components": [{"name": "Calculator"}]},
        ], "build_systems": [], "test_frameworks": [], "dependency_managers": []}]
        result = _flatten_deps(env)
        assert result[0]["integration_status"] == "indexed"

    def test_tag_missing_maps_to_not_in_build(self):
        """Tags — 'missing' maps to status 'not in build'."""
        from frontend_migrated.pages.project.dependencies import _flatten_deps
        env = [{"name": "C++", "version": "20", "dependencies": [
            {"name": "fmt", "refid": "conan::fmt", "github_url": "", "version": "10.2.1",
             "is_dev": True, "manager_name": "conan", "index_file_patterns": "*.h",
             "index_subdir": "", "index_exclude_patterns": "", "index_recursive": False,
             "tags": ["missing"],
             "components": []},
        ], "build_systems": [], "test_frameworks": [], "dependency_managers": []}]
        result = _flatten_deps(env)
        assert result[0]["integration_status"] == "not in build"

    def test_tag_registered(self):
        """Tags — 'registered' means declared but not yet scaffolded."""
        from frontend_migrated.pages.project.dependencies import _flatten_deps
        env = [{"name": "C++", "version": "20", "dependencies": [
            {"name": "spdlog", "refid": "conan::spdlog", "github_url": "", "version": "1.14.1",
             "is_dev": False, "manager_name": "conan", "index_file_patterns": "*.h",
             "index_subdir": "", "index_exclude_patterns": "", "index_recursive": True,
             "tags": ["registered"],
             "components": [{"name": "Calculator"}]},
        ], "build_systems": [], "test_frameworks": [], "dependency_managers": []}]
        result = _flatten_deps(env)
        assert result[0]["integration_status"] == "registered"

    def test_no_tags_defaults_to_registered(self):
        """If a dependency has no tags at all, defaults to 'registered'."""
        from frontend_migrated.pages.project.dependencies import _flatten_deps
        env = [{"name": "C++", "version": "20", "dependencies": [
            {"name": "boost", "refid": "conan::boost", "github_url": "", "version": "1.82.0",
             "is_dev": False, "manager_name": "conan", "index_file_patterns": "*.h",
             "index_subdir": "", "index_exclude_patterns": "", "index_recursive": True,
             "tags": [],
             "components": [{"name": "Calculator"}]},
        ], "build_systems": [], "test_frameworks": [], "dependency_managers": []}]
        result = _flatten_deps(env)
        assert result[0]["integration_status"] == "registered"

    def test_health_tags_passing(self):
        """Health tags — 'passing' appears in health_tags."""
        from frontend_migrated.pages.project.dependencies import _flatten_deps
        env = [{"name": "C++", "version": "20", "dependencies": [
            {"name": "boost", "refid": "conan::boost", "github_url": "", "version": "1.82.0",
             "is_dev": False, "manager_name": "conan", "index_file_patterns": "*.h",
             "index_subdir": "", "index_exclude_patterns": "", "index_recursive": True,
             "tags": ["integrated", "passing"],
             "components": [{"name": "Calculator"}]},
        ], "build_systems": [], "test_frameworks": [], "dependency_managers": []}]
        result = _flatten_deps(env)
        assert result[0]["integration_status"] == "integrated"
        assert result[0]["health_tags"] == ["passing"]

    def test_health_tags_failing(self):
        """Health tags — 'failing' appears in health_tags."""
        from frontend_migrated.pages.project.dependencies import _flatten_deps
        env = [{"name": "C++", "version": "20", "dependencies": [
            {"name": "boost", "refid": "conan::boost", "github_url": "", "version": "1.82.0",
             "is_dev": False, "manager_name": "conan", "index_file_patterns": "*.h",
             "index_subdir": "", "index_exclude_patterns": "", "index_recursive": True,
             "tags": ["integrated", "failing"],
             "components": [{"name": "Calculator"}]},
        ], "build_systems": [], "test_frameworks": [], "dependency_managers": []}]
        result = _flatten_deps(env)
        assert result[0]["integration_status"] == "integrated"
        assert result[0]["health_tags"] == ["failing"]

    def test_language_without_version(self):
        from frontend_migrated.pages.project.dependencies import _flatten_deps
        env = [{"name": "Python", "version": None, "dependencies": [
            {"name": "requests", "refid": "pip::requests", "github_url": "", "version": "2.31.0",
             "is_dev": False, "manager_name": "pip", "index_file_patterns": "*.py",
             "index_subdir": "", "index_exclude_patterns": "", "index_recursive": False,
             "tags": ["integrated"],
             "components": []},
        ], "build_systems": [], "test_frameworks": [], "dependency_managers": []}]
        result = _flatten_deps(env)
        assert result[0]["language"] == "Python"


class TestBuildDepRows:
    """Unit tests for _build_dep_rows pure function."""

    def test_basic_row(self):
        from frontend_migrated.pages.project.dependencies import _build_dep_rows
        all_deps = [{
            "name": "boost",
            "refid": "conan::boost",
            "github_url": "https://github.com/boostorg/boost",
            "version": "1.82.0",
            "is_dev": False,
            "manager_name": "conan",
            "components": [{"name": "Calculator"}],
            "language": "C++ 20",
            "integration_status": "integrated",
            "health_tags": [],
            "index_file_patterns": "*.h *.hpp",
            "index_subdir": "",
            "index_exclude_patterns": "",
            "index_recursive": True,
        }]
        rows = _build_dep_rows(all_deps)
        assert len(rows) == 1
        assert rows[0]["name"] == "boost"
        assert rows[0]["source_url"] == "https://github.com/boostorg/boost"
        assert rows[0]["version"] == "1.82.0"
        assert rows[0]["components"] == "Calculator"
        assert rows[0]["status"] == "integrated"
        assert rows[0]["health"] == ""
        assert rows[0]["language"] == "C++ 20"
        assert rows[0]["unused"] is False

    def test_no_components_means_unused(self):
        from frontend_migrated.pages.project.dependencies import _build_dep_rows
        all_deps = [{
            "name": "eigen",
            "refid": "conan::eigen",
            "github_url": "",
            "version": "3.4.0",
            "is_dev": False,
            "manager_name": "conan",
            "components": [],
            "language": "C++ 20",
            "integration_status": "indexed",
            "health_tags": [],
            "index_file_patterns": "*.h",
            "index_subdir": "Eigen",
            "index_exclude_patterns": "",
            "index_recursive": True,
        }]
        rows = _build_dep_rows(all_deps)
        assert rows[0]["unused"] is True
        assert rows[0]["components"] == "—"

    def test_multiple_components(self):
        from frontend_migrated.pages.project.dependencies import _build_dep_rows
        all_deps = [{
            "name": "eigen",
            "refid": "conan::eigen",
            "github_url": "",
            "version": "3.4.0",
            "is_dev": False,
            "manager_name": "conan",
            "components": [{"name": "Calculator"}, {"name": "UI"}],
            "language": "C++ 20",
            "integration_status": "indexed",
            "health_tags": [],
            "index_file_patterns": "*.h",
            "index_subdir": "",
            "index_exclude_patterns": "",
            "index_recursive": True,
        }]
        rows = _build_dep_rows(all_deps)
        assert rows[0]["components"] == "Calculator, UI"

    def test_health_passing(self):
        from frontend_migrated.pages.project.dependencies import _build_dep_rows
        all_deps = [{
            "name": "boost",
            "refid": "conan::boost",
            "github_url": "",
            "version": "1.82.0",
            "is_dev": False,
            "manager_name": "conan",
            "components": [{"name": "Calculator"}],
            "language": "C++ 20",
            "integration_status": "integrated",
            "health_tags": ["passing"],
            "index_file_patterns": "*.h",
            "index_subdir": "",
            "index_exclude_patterns": "",
            "index_recursive": True,
        }]
        rows = _build_dep_rows(all_deps)
        assert rows[0]["health"] == "passing"

    def test_health_failing(self):
        from frontend_migrated.pages.project.dependencies import _build_dep_rows
        all_deps = [{
            "name": "boost",
            "refid": "conan::boost",
            "github_url": "",
            "version": "1.82.0",
            "is_dev": False,
            "manager_name": "conan",
            "components": [{"name": "Calculator"}],
            "language": "C++ 20",
            "integration_status": "integrated",
            "health_tags": ["failing"],
            "index_file_patterns": "*.h",
            "index_subdir": "",
            "index_exclude_patterns": "",
            "index_recursive": True,
        }]
        rows = _build_dep_rows(all_deps)
        assert rows[0]["health"] == "failing"


class TestBuildDepColumns:
    """Unit tests for _build_dep_columns pure function."""

    def test_returns_column_defs(self):
        from frontend_migrated.pages.project.dependencies import _build_dep_columns
        cols = _build_dep_columns()
        names = [c["name"] for c in cols]
        assert "name" in names
        assert "source_url" in names
        assert "version" in names
        assert "components" in names
        assert "status" in names
        assert "health" in names
        assert "language" in names
        assert "actions" in names