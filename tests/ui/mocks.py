"""Mock factories for neomodel-style node objects.

Each ``make_*`` function returns a ``MagicMock`` whose relationship
managers (``.parent.all()``, ``.requirements.all()``, etc.) behave
like real neomodel relationship managers.  This lets page code call
``comp.parent.all()`` and get back a list, exactly as it would with
live Neo4j data.

These factories are the UI-test equivalent of the unit-test
``seeded_session`` fixture — predictable, fast, no database required.
"""

from __future__ import annotations

from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------


def make_component(
    *,
    name: str = "Calculator",
    refid: str = "test::Calculator",
    namespace: str = "calc::",
    description: str = "A test component",
    parent_name: str | None = None,
    children_names: list[str] | None = None,
    hlr_count: int = 0,
    node_count: int = 0,
    language_name: str | None = None,
    dep_names: list[str] | None = None,
) -> MagicMock:
    """Build a mock Component node with realistic relationship managers.

    Parameters
    ----------
    name :
        Component display name.
    refid :
        Unique identifier used in route params and URLs.
    namespace :
        Code-level namespace (shown in the UI).
    description :
        Markdown-friendly description text.
    parent_name :
        If set, ``.parent.all()`` returns a one-element list with a
        mock whose ``.name`` and ``.refid`` match.
    children_names :
        If set, ``.children.all()`` returns a list of child mocks with
        zeroed-out HLR / node counts.
    hlr_count :
        Number of mock HLR entries returned by ``.requirements.all()``.
    node_count :
        Total ontology node count (split evenly between namespaces
        and classes).
    language_name :
        If set, ``.language.all()`` returns a one-element list whose
        ``.name`` matches.
    dep_names :
        If set, ``.dependencies.all()`` returns mocks with the given
        names, ``version="1.0.0"``, and ``is_dev=False``.
    """
    comp = MagicMock()
    comp.name = name
    comp.refid = refid
    comp.namespace = namespace
    comp.description = description

    # Parent relationship
    if parent_name:
        parent = MagicMock()
        parent.name = parent_name
        parent.refid = f"test::{parent_name}"
        comp.parent.all.return_value = [parent]
    else:
        comp.parent.all.return_value = []

    # Children relationship
    children = []
    for cname in (children_names or []):
        child = MagicMock()
        child.name = cname
        child.refid = f"test::{cname}"
        child.namespace = f"{cname.lower()}::"
        child.requirements.all.return_value = []
        child.namespaces.all.return_value = []
        child.classes.all.return_value = []
        children.append(child)
    comp.children.all.return_value = children

    # Language relationship
    if language_name:
        lang = MagicMock()
        lang.name = language_name
        comp.language.all.return_value = [lang]
    else:
        comp.language.all.return_value = []

    # Requirements (HLRs)
    hlrs = []
    for i in range(hlr_count):
        hlrs.append(make_hlr(name=f"HLR-{name}-{i + 1}", description=f"Requirement {i + 1} for {name}"))
    comp.requirements.all.return_value = hlrs

    # Ontology nodes (namespaces + classes)
    ns_count = node_count // 2
    cls_count = node_count - ns_count
    comp.namespaces.all.return_value = [MagicMock() for _ in range(ns_count)]
    comp.classes.all.return_value = [MagicMock() for _ in range(cls_count)]

    # Dependencies
    deps = []
    for dname in (dep_names or []):
        deps.append(make_dependency(name=dname))
    comp.dependencies.all.return_value = deps

    return comp


# ---------------------------------------------------------------------------
# HLR (High-Level Requirement)
# ---------------------------------------------------------------------------


def make_hlr(
    *,
    name: str = "HLR-1",
    refid: str = "test::HLR-1",
    description: str = "A test requirement",
    llr_count: int = 0,
    component_name: str | None = None,
) -> MagicMock:
    """Build a mock HLR node.

    Parameters
    ----------
    name :
        Short label (shown in badges).
    refid :
        Unique identifier used in route params.
    description :
        Full requirement text.
    llr_count :
        Number of mock LLR entries returned by ``.llrs.all()``.
    component_name :
        If set, ``.component.all()`` returns a one-element list whose
        ``.name`` matches.
    """
    hlr = MagicMock()
    hlr.name = name
    hlr.refid = refid
    hlr.description = description
    hlr.llrs.all.return_value = [MagicMock() for _ in range(llr_count)]
    hlr.layer = "design"

    if component_name:
        comp = MagicMock()
        comp.name = component_name
        hlr.component.all.return_value = [comp]
    else:
        hlr.component.all.return_value = []

    return hlr


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def make_dependency(
    *,
    name: str = "boost",
    refid: str = "test::boost",
    version: str = "1.0.0",
    is_dev: bool = False,
    manager_name: str = "",
) -> MagicMock:
    """Build a mock Dependency node.

    Parameters
    ----------
    name :
        Dependency package name (e.g. "boost", "requests").
    refid :
        Unique identifier.
    version :
        Pinned version string.
    is_dev :
        Whether this is a dev-only dependency (shown as a badge).
    manager_name :
        Package manager name (e.g. "pip", "conan").
    """
    dep = MagicMock()
    dep.name = name
    dep.refid = refid
    dep.version = version
    dep.is_dev = is_dev
    dep.manager_name = manager_name
    return dep


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------


def make_language(
    *,
    name: str = "C++",
    version: str = "20",
    refid: str = "test::cpp",
) -> MagicMock:
    """Build a mock Language node.

    Parameters
    ----------
    name :
        Language display name (e.g. "C++", "Python").
    version :
        Language version string (e.g. "20", "3.12").
    refid :
        Unique identifier.
    """
    lang = MagicMock()
    lang.name = name
    lang.version = version
    lang.refid = refid
    return lang


# ---------------------------------------------------------------------------
# Serialized dict factories (for pages that consume fetch_requirements_data)
# ---------------------------------------------------------------------------


def make_llr_dict(
    *,
    refid: str = "test::LLR-1",
    description: str = "A test low-level requirement",
    verification_methods: list[dict] | None = None,
) -> dict:
    """Build a serialized LLR dict matching ``CodeGraphNode.serialize()`` output.

    Parameters
    ----------
    refid :
        Unique identifier (used as row key and navigation target).
    description :
        Full requirement text.
    verification_methods :
        List of verification method dicts added under the ``composes`` key.
        Each dict should have ``type`` (``"VerificationMethod"``) and
        ``method`` (``"automated"``, ``"review"``, etc.).
        If *None*, a single automated verification is included by default.
    """
    if verification_methods is None:
        verification_methods = [{"type": "VerificationMethod", "method": "automated"}]

    return {
        "refid": refid,
        "id": refid,
        "description": description,
        "composes": verification_methods,
    }


# ---------------------------------------------------------------------------
# Environment data factories (for dependency table)
# ---------------------------------------------------------------------------


def make_dep_dict(
    *,
    name: str = "boost",
    refid: str = "conan::boost",
    github_url: str = "https://github.com/boostorg/boost",
    version: str = "1.82.0",
    is_dev: bool = False,
    manager_name: str = "conan",
    index_file_patterns: str = "*.h *.hpp",
    index_subdir: str = "",
    index_exclude_patterns: str = "",
    index_recursive: bool = True,
    component_names: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict:
    """Build a serialized dependency dict for ``fetch_environment_data()``.

    Matches the structure returned by ``Dependency.serialize(fields='all')``
    plus the ``components`` key added by the data layer.

    The ``tags`` key contains workflow tags set by ``sync_dependency_tags``.
    Common values: ``"registered"``, ``"missing"``, ``"integrated"``,
    ``"indexed"``, ``"passing"``, ``"failing"``.
    """
    if component_names is None:
        component_names = ["Calculator"]
    if tags is None:
        # Default: infer from name for realistic test data
        tag_map = {
            "boost": ["integrated"],
            "eigen": ["indexed"],
            "fmt": ["missing"],
        }
        tags = tag_map.get(name, ["integrated"])

    return {
        "refid": refid,
        "id": refid,
        "name": name,
        "github_url": github_url,
        "version": version,
        "is_dev": is_dev,
        "manager_name": manager_name,
        "index_file_patterns": index_file_patterns,
        "index_subdir": index_subdir,
        "index_exclude_patterns": index_exclude_patterns,
        "index_recursive": index_recursive,
        "tags": tags,
        "components": [{"name": n} for n in component_names],
    }


def make_env_data(
    *,
    languages: list[dict] | None = None,
) -> list[dict]:
    """Build a mock return value for ``fetch_environment_data()``.

    If *languages* is None, returns a single C++ language with two
    dependencies (boost and eigen).  Each language dict has the
    ``dependencies`` key populated with serialized dependency dicts.
    Dependency dicts include ``tags`` from ``sync_dependency_tags``.
    """
    if languages is not None:
        return languages

    return [
        {
            "name": "C++",
            "version": "20",
            "dependencies": [
                make_dep_dict(name="boost", tags=["integrated"], component_names=["Calculator"]),
                make_dep_dict(
                    name="eigen",
                    refid="conan::eigen",
                    github_url="https://gitlab.com/libeigen/eigen",
                    version="3.4.0",
                    tags=["indexed"],
                    component_names=["Calculator", "UI"],
                ),
            ],
            "build_systems": [],
            "test_frameworks": [],
            "dependency_managers": [],
        },
    ]