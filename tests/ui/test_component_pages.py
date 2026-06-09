"""NiceGUI User-simulation tests for the migrated component pages.

Uses ``nicegui.testing.User`` (httpx + websocket simulation) to render
pages in-process with mocked Neo4j data — no running server or browser
needed.

Patches are applied **at the import site** (the page module) rather than
the definition site (the data module) so that ``asyncio.to_thread`` calls
see the mock.

Run with::

    pytest tests/ui/test_component_pages.py -v
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import patch

import pytest

from tests.ui.mocks import make_component
from tests.ui.conftest import PATCH_TARGETS as P

# ---------------------------------------------------------------------------
# Preset mock data — scenario-specific compositions of make_component
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_components():
    """Return a list of mock Component nodes for the list page."""
    return [
        make_component(name="Environment", refid="test::Environment"),
        make_component(
            name="Calculator",
            refid="test::Calculator",
            namespace="calc::",
            description="Core calculation engine",
            hlr_count=2,
            node_count=10,
            language_name="C++",
            dep_names=["boost", "eigen"],
        ),
        make_component(
            name="UI",
            refid="test::UI",
            namespace="ui::",
            description="Frontend interface",
            parent_name="Calculator",
            hlr_count=1,
            node_count=6,
            language_name="Python",
        ),
    ]


@pytest.fixture
def mock_calc_detail():
    """Return a detailed mock Component for the detail page."""
    return make_component(
        name="Calculator",
        refid="test::Calculator",
        namespace="calc::",
        description="Core calculation engine with **markdown** support.",
        children_names=["MathCore", "Parser"],
        hlr_count=2,
        node_count=8,
        language_name="C++",
        dep_names=["boost", "eigen", "fmt"],
    )


# ---------------------------------------------------------------------------
# Helper: context manager for the detail page's five data-layer patches
# ---------------------------------------------------------------------------


def detail_page_patches(comp):
    """Return an ExitStack that patches all five data-layer calls.

    Usage::

        with detail_page_patches(comp):
            await user.open("/component/...")
    """
    stack = ExitStack()
    stack.enter_context(patch(P["get_component"], return_value=comp))
    stack.enter_context(patch(P["add_dependency"], side_effect=NotImplementedError("stub")))
    stack.enter_context(patch(P["delete_dependency"], side_effect=NotImplementedError("stub")))
    stack.enter_context(patch(P["fetch_ontology_graph_data"], side_effect=NotImplementedError("stub")))
    stack.enter_context(patch(P["resolve_node_id_by_qualified_name"], side_effect=NotImplementedError("stub")))
    return stack


# ---------------------------------------------------------------------------
# Tests: Components list page
# ---------------------------------------------------------------------------


async def test_components_page_lists_architectural_components(
    user, mock_components
):
    """The /components page renders non-Environment components."""
    with patch(P["fetch_components"], return_value=mock_components):
        await user.open("/components")
        await user.should_see("Components")
        await user.should_see("Calculator")
        await user.should_see("UI")
        await user.should_not_see("Environment")


async def test_components_page_shows_language_badge(user):
    """Each component card shows its programming language as a badge."""
    components = [
        make_component(name="Calc", refid="test::Calc", language_name="C++"),
    ]
    with patch(P["fetch_components"], return_value=components):
        await user.open("/components")
        await user.should_see("C++")


async def test_components_page_shows_empty_state(user):
    """When there are no components, an empty-state message is shown."""
    with patch(P["fetch_components"], return_value=[]):
        await user.open("/components")
        await user.should_see("No components defined yet")


async def test_components_page_filters_environment(user):
    """Environment-only components are filtered out of the list."""
    env_only = [
        make_component(name="Environment", refid="test::Environment"),
        make_component(name="Runtime", refid="test::Runtime", parent_name="Environment"),
    ]
    with patch(P["fetch_components"], return_value=env_only):
        await user.open("/components")
        await user.should_see("No components defined yet")


async def test_components_page_shows_node_count(user):
    """Component cards display the node count stat."""
    components = [
        make_component(name="Calc", refid="test::Calc", node_count=7),
    ]
    with patch(P["fetch_components"], return_value=components):
        await user.open("/components")
        await user.should_see("7 nodes")


async def test_components_page_shows_hlr_count(user):
    """Component cards display the HLR count stat."""
    components = [
        make_component(name="Calc", refid="test::Calc", hlr_count=3),
    ]
    with patch(P["fetch_components"], return_value=components):
        await user.open("/components")
        await user.should_see("3 HLRs")


# ---------------------------------------------------------------------------
# Tests: Component detail page
# ---------------------------------------------------------------------------


async def test_detail_page_shows_name_and_description(user, mock_calc_detail):
    """The detail page renders the component name and description."""
    with detail_page_patches(mock_calc_detail):
        await user.open("/component/test::Calculator")
        await user.should_see("Calculator")
        await user.should_see("markdown")


async def test_detail_page_shows_namespace(user, mock_calc_detail):
    """The namespace is shown below the component name."""
    with detail_page_patches(mock_calc_detail):
        await user.open("/component/test::Calculator")
        await user.should_see("calc::")


async def test_detail_page_shows_subcomponents(user, mock_calc_detail):
    """Child components appear in the Sub-Components card."""
    with detail_page_patches(mock_calc_detail):
        await user.open("/component/test::Calculator")
        await user.should_see("Sub-Components")
        await user.should_see("MathCore")
        await user.should_see("Parser")


async def test_detail_page_shows_requirements(user, mock_calc_detail):
    """HLR requirements are listed with their LLR counts."""
    with detail_page_patches(mock_calc_detail):
        await user.open("/component/test::Calculator")
        await user.should_see("Requirements")
        await user.should_see("0 LLRs")


async def test_detail_page_shows_dependencies(user, mock_calc_detail):
    """Dependencies are listed with name and version."""
    with detail_page_patches(mock_calc_detail):
        await user.open("/component/test::Calculator")
        await user.should_see("Dependencies")
        await user.should_see("boost")
        await user.should_see("1.0.0")


async def test_detail_page_not_found(user):
    """When get_component returns None, a not-found message is shown."""
    with patch(P["get_component"], return_value=None), \
         patch(P["fetch_ontology_graph_data"], side_effect=NotImplementedError("stub")), \
         patch(P["resolve_node_id_by_qualified_name"], side_effect=NotImplementedError("stub")):
        await user.open("/component/nonexistent")
        await user.should_see("Component not found")


async def test_detail_page_shows_breadcrumb(user, mock_calc_detail):
    """Breadcrumb includes Components link and current name."""
    with detail_page_patches(mock_calc_detail):
        await user.open("/component/test::Calculator")
        await user.should_see("Components")
        await user.should_see("Calculator")


async def test_detail_page_dependencies_empty(user):
    """When a component has no dependencies, an empty state message is shown."""
    comp = make_component(name="Solo", refid="test::Solo")
    with detail_page_patches(comp):
        await user.open("/component/test::Solo")
        await user.should_see("No dependencies configured")


async def test_detail_page_dev_badge(user):
    """Dev dependencies show a 'dev' badge."""
    comp = make_component(name="DevProj", refid="test::DevProj", dep_names=["pytest"])
    comp.dependencies.all.return_value[0].is_dev = True
    with detail_page_patches(comp):
        await user.open("/component/test::DevProj")
        await user.should_see("dev")