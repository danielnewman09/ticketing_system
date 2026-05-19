"""Phase 2 ORM tests — component models: Language, Component, BuildSystem,
TestFramework, DependencyManager, Dependency, DependencyRecommendation."""

import pytest
from sqlalchemy.exc import IntegrityError

from backend.db.models.components import (
    BuildSystem,
    Component,
    Dependency,
    DependencyManager,
    DependencyRecommendation,
    Language,
    TestFramework,
)


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------

class TestLanguage:
    """Tests for Language CRUD and constraints."""

    def test_create_language(self, session):
        """Create a Language with name and version."""
        lang = Language(name="Rust", version="1.75")
        session.add(lang)
        session.flush()
        assert lang.id is not None
        assert lang.name == "Rust"
        assert lang.version == "1.75"

    def test_language_default_version(self, session):
        """Language version defaults to empty string."""
        lang = Language(name="Go")
        session.add(lang)
        session.flush()
        assert lang.version == ""

    def test_language_repr_with_version(self, session):
        """Language __repr__ includes version when present."""
        lang = Language(name="C++", version="17")
        session.add(lang)
        session.flush()
        assert repr(lang) == "C++ 17"

    def test_language_repr_without_version(self, session):
        """Language __repr__ omits version when empty."""
        lang = Language(name="Go")
        session.add(lang)
        session.flush()
        assert repr(lang) == "Go"

    def test_language_name_unique(self, session):
        """Duplicate Language name raises IntegrityError."""
        lang1 = Language(name="Python", version="3.11")
        session.add(lang1)
        session.flush()

        lang2 = Language(name="Python", version="3.12")
        session.add(lang2)
        with pytest.raises(IntegrityError):
            session.flush()


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------

class TestComponent:
    """Tests for Component CRUD, constraints and relationships."""

    def test_create_component_minimal(self, session):
        """Create a Component with just name (no language, no parent)."""
        comp = Component(name="Standalone", namespace="std")
        session.add(comp)
        session.flush()
        assert comp.id is not None
        assert comp.name == "Standalone"
        assert comp.language_id is None
        assert comp.parent_id is None

    def test_create_component_with_language(self, session):
        """Component can reference a Language."""
        lang = Language(name="Java", version="21")
        session.add(lang)
        session.flush()

        comp = Component(name="Service", namespace="svc", language=lang)
        session.add(comp)
        session.flush()

        assert comp.language is lang
        assert comp in lang.environment_components

    def test_component_defaults(self, session):
        """Component fields have expected defaults."""
        comp = Component(name="Defaults")
        session.add(comp)
        session.flush()

        assert comp.description == ""
        assert comp.namespace == ""

    def test_component_repr(self, session):
        """Component __repr__ returns the name."""
        comp = Component(name="Calculator")
        session.add(comp)
        session.flush()
        assert repr(comp) == "Calculator"

    def test_component_full_namespace(self, session):
        """Component.full_namespace returns namespace when set."""
        comp = Component(name="Foo", namespace="foo::bar")
        session.add(comp)
        session.flush()
        assert comp.full_namespace == "foo::bar"

    def test_component_full_namespace_empty(self, session):
        """Component.full_namespace returns empty string when namespace unset."""
        comp = Component(name="Foo")
        session.add(comp)
        session.flush()
        assert comp.full_namespace == ""

    def test_component_to_prompt_text_minimal(self, session):
        """Component.to_prompt_text with minimal fields."""
        comp = Component(name="MyService")
        session.add(comp)
        session.flush()
        text = comp.to_prompt_text()
        assert text.startswith("Component: MyService")

    def test_component_to_prompt_text_full(self, session):
        """Component.to_prompt_text with description, language, parent."""
        lang = Language(name="C++", version="17")
        session.add(lang)
        session.flush()

        parent = Component(name="ParentMod", namespace="parent")
        session.add(parent)
        session.flush()

        child = Component(
            name="ChildMod",
            namespace="parent::child",
            description="A child module",
            language=lang,
            parent=parent,
        )
        session.add(child)
        session.flush()

        text = child.to_prompt_text()
        assert "Component: ChildMod" in text
        assert "Namespace: parent::child" in text
        assert "Description: A child module" in text
        assert "Parent: ParentMod" in text
        assert "Language: C++" in text

    def test_component_parent_child_relationship(self, session):
        """Component parent/child self-referential relationship works."""
        parent = Component(name="Parent")
        session.add(parent)
        session.flush()

        child = Component(name="Child", parent=parent)
        session.add(child)
        session.flush()

        assert child.parent is parent
        assert child in parent.children

    def test_component_unique_name_per_parent(self, session):
        """Two components with same name can coexist under different parents."""
        parent_a = Component(name="ParentA")
        parent_b = Component(name="ParentB")
        session.add_all([parent_a, parent_b])
        session.flush()

        child1 = Component(name="SharedName", parent=parent_a)
        child2 = Component(name="SharedName", parent=parent_b)
        session.add_all([child1, child2])
        session.flush()

        assert child1.id != child2.id

    def test_component_duplicate_name_same_parent(self, session):
        """Two components with same name and same parent raises IntegrityError."""
        parent = Component(name="Parent")
        session.add(parent)
        session.flush()

        child1 = Component(name="DupName", parent=parent)
        session.add(child1)
        session.flush()

        child2 = Component(name="DupName", parent=parent)
        session.add(child2)
        with pytest.raises(IntegrityError):
            session.flush()

    def test_component_delete_does_not_cascade_at_orm_level(self, session):
        """Deleting a parent via session.delete does NOT cascade at the ORM level.

        The Component.children relationship lacks ORM-level cascade
        configuration (no cascade="all, delete-orphan"), so
        session.delete(parent) only removes the parent row.  The child
        row persists with a dangling parent_id FK until the database-level
        ON DELETE CASCADE fires (which may not happen within the same
        test transaction).
        """
        parent = Component(name="ToDrop")
        session.add(parent)
        session.flush()

        child = Component(name="Orphan", parent=parent)
        session.add(child)
        session.flush()

        session.delete(parent)
        session.flush()

        # Parent is gone
        assert session.query(Component).filter_by(name="ToDrop").first() is None
        # Child still exists (no ORM cascade; DB-level CASCADE may not
        # fire within this test transaction)
        remaining = session.query(Component).filter_by(name="Orphan").first()
        assert remaining is not None


# ---------------------------------------------------------------------------
# BuildSystem
# ---------------------------------------------------------------------------

class TestBuildSystem:
    """Tests for BuildSystem CRUD and relationships."""

    def test_create_build_system(self, session):
        """Create a BuildSystem linked to a Language."""
        lang = Language(name="C++", version="17")
        session.add(lang)
        session.flush()

        bs = BuildSystem(name="CMake", config_file="CMakeLists.txt", language=lang)
        session.add(bs)
        session.flush()

        assert bs.id is not None
        assert bs.name == "CMake"
        assert bs.config_file == "CMakeLists.txt"
        assert bs.language is lang

    def test_build_system_default_version(self, session):
        """BuildSystem version defaults to empty string."""
        lang = Language(name="Go")
        session.add(lang)
        session.flush()

        bs = BuildSystem(name="Make", config_file="Makefile", language_id=lang.id)
        session.add(bs)
        session.flush()
        assert bs.version == ""

    def test_build_system_repr(self, session):
        """BuildSystem __repr__ returns the name."""
        lang = Language(name="Rust")
        session.add(lang)
        session.flush()

        bs = BuildSystem(name="Cargo", config_file="Cargo.toml", language_id=lang.id)
        session.add(bs)
        session.flush()
        assert repr(bs) == "Cargo"

    def test_language_has_build_systems(self, session):
        """Language.build_systems lists associated BuildSystems."""
        lang = Language(name="Python", version="3.12")
        session.add(lang)
        session.flush()

        bs = BuildSystem(name="setuptools", config_file="setup.py", language=lang)
        session.add(bs)
        session.flush()

        assert bs in lang.build_systems


# ---------------------------------------------------------------------------
# TestFramework
# ---------------------------------------------------------------------------

class TestTestFramework:
    """Tests for TestFramework CRUD and relationships."""

    def test_create_test_framework(self, session):
        """Create a TestFramework linked to a Language."""
        lang = Language(name="Python", version="3.12")
        session.add(lang)
        session.flush()

        tf = TestFramework(
            name="pytest",
            config_file="pytest.ini",
            test_discovery_path="tests/",
            language=lang,
        )
        session.add(tf)
        session.flush()

        assert tf.id is not None
        assert tf.name == "pytest"
        assert tf.config_file == "pytest.ini"
        assert tf.test_discovery_path == "tests/"
        assert tf.language is lang

    def test_test_framework_default_discovery(self, session):
        """TestFramework.test_discovery_path defaults to empty string."""
        lang = Language(name="C++")
        session.add(lang)
        session.flush()

        tf = TestFramework(name="GTest", config_file="CMakeLists.txt", language_id=lang.id)
        session.add(tf)
        session.flush()
        assert tf.test_discovery_path == ""

    def test_language_has_test_frameworks(self, session):
        """Language.test_frameworks lists associated TestFrameworks."""
        lang = Language(name="Java", version="21")
        session.add(lang)
        session.flush()

        tf = TestFramework(name="JUnit", config_file="pom.xml", language_id=lang.id)
        session.add(tf)
        session.flush()

        assert tf in lang.test_frameworks


# ---------------------------------------------------------------------------
# DependencyManager
# ---------------------------------------------------------------------------

class TestDependencyManager:
    """Tests for DependencyManager CRUD and relationships."""

    def test_create_dependency_manager(self, session):
        """Create a DependencyManager linked to a Language."""
        lang = Language(name="Python", version="3.12")
        session.add(lang)
        session.flush()

        dm = DependencyManager(name="pip", manifest_file="requirements.txt", language=lang)
        session.add(dm)
        session.flush()

        assert dm.id is not None
        assert dm.name == "pip"
        assert dm.manifest_file == "requirements.txt"
        assert dm.language is lang

    def test_dependency_manager_default_lock_file(self, session):
        """DependencyManager.lock_file defaults to empty string."""
        lang = Language(name="Rust")
        session.add(lang)
        session.flush()

        dm = DependencyManager(name="cargo", manifest_file="Cargo.toml", language_id=lang.id)
        session.add(dm)
        session.flush()
        assert dm.lock_file == ""

    def test_language_has_dependency_managers(self, session):
        """Language.dependency_managers lists associated DependencyManagers."""
        lang = Language(name="JavaScript")
        session.add(lang)
        session.flush()

        dm = DependencyManager(name="npm", manifest_file="package.json", language_id=lang.id)
        session.add(dm)
        session.flush()

        assert dm in lang.dependency_managers


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------

class TestDependency:
    """Tests for Dependency CRUD and relationships."""

    def _make_dep_manager(self, session):
        """Helper: create a Language + DependencyManager."""
        lang = Language(name="Python", version="3.12")
        session.add(lang)
        session.flush()
        dm = DependencyManager(name="pip", manifest_file="requirements.txt", language_id=lang.id)
        session.add(dm)
        session.flush()
        return dm

    def test_create_dependency(self, session):
        """Create a Dependency linked to a manager."""
        dm = self._make_dep_manager(session)

        dep = Dependency(name="requests", version="2.31.0", manager=dm)
        session.add(dep)
        session.flush()

        assert dep.id is not None
        assert dep.name == "requests"
        assert dep.version == "2.31.0"
        assert dep.manager is dm

    def test_dependency_defaults(self, session):
        """Dependency optional fields have expected defaults."""
        dm = self._make_dep_manager(session)

        dep = Dependency(name="flask", manager_id=dm.id)
        session.add(dep)
        session.flush()

        assert dep.version == ""
        assert dep.github_url == ""
        assert dep.is_dev is False
        assert dep.index_file_patterns == "*.h *.hpp"
        assert dep.index_subdir == ""
        assert dep.index_exclude_patterns == ""
        assert dep.index_recursive is True

    def test_dependency_repr_with_version(self, session):
        """Dependency __repr__ includes version when present."""
        dm = self._make_dep_manager(session)
        dep = Dependency(name="numpy", version="1.26", manager_id=dm.id)
        session.add(dep)
        session.flush()
        assert repr(dep) == "numpy==1.26"

    def test_dependency_repr_without_version(self, session):
        """Dependency __repr__ omits version when empty."""
        dm = self._make_dep_manager(session)
        dep = Dependency(name="pandas", manager_id=dm.id)
        session.add(dep)
        session.flush()
        assert repr(dep) == "pandas"

    def test_dependency_unique_per_manager(self, session):
        """Duplicate (manager_id, name) raises IntegrityError."""
        dm = self._make_dep_manager(session)

        dep1 = Dependency(name="boto3", version="1.34", manager_id=dm.id)
        session.add(dep1)
        session.flush()

        dep2 = Dependency(name="boto3", version="1.35", manager_id=dm.id)
        session.add(dep2)
        with pytest.raises(IntegrityError):
            session.flush()

    def test_dependency_same_name_different_manager(self, session):
        """Same dependency name under different managers is allowed."""
        lang = Language(name="Python", version="3.12")
        session.add(lang)
        session.flush()

        dm1 = DependencyManager(name="pip", manifest_file="requirements.txt", language_id=lang.id)
        dm2 = DependencyManager(name="conda", manifest_file="environment.yml", language_id=lang.id)
        session.add_all([dm1, dm2])
        session.flush()

        dep1 = Dependency(name="numpy", version="1.26", manager_id=dm1.id)
        dep2 = Dependency(name="numpy", version="1.26", manager_id=dm2.id)
        session.add_all([dep1, dep2])
        session.flush()

        assert dep1.id != dep2.id

    def test_dependency_component_m2m(self, session):
        """Dependency and Component many-to-many works."""
        dm = self._make_dep_manager(session)
        dep = Dependency(name="redis", manager_id=dm.id)
        session.add(dep)

        comp = Component(name="CacheService", namespace="cache")
        session.add(comp)
        session.flush()

        dep.components.append(comp)
        session.flush()

        assert comp in dep.components
        assert dep in comp.dependencies


# ---------------------------------------------------------------------------
# DependencyRecommendation
# ---------------------------------------------------------------------------

class TestDependencyRecommendation:
    """Tests for DependencyRecommendation CRUD and relationships."""

    def test_create_recommendation(self, session):
        """Create a DependencyRecommendation linked to a Component."""
        comp = Component(name="AuthModule", namespace="auth")
        session.add(comp)
        session.flush()

        rec = DependencyRecommendation(
            component=comp,
            name="jwt-cpp",
            github_url="https://github.com/Thalhammer/jwt-cpp",
            description="JWT library for C++",
            version="0.7.0",
            stars=950,
            license="MIT",
            last_updated="2024-01-15",
            pros=["well-maintained", "header-only"],
            cons=["no async support"],
            status="pending",
        )
        session.add(rec)
        session.flush()

        assert rec.id is not None
        assert rec.component is comp
        assert rec.name == "jwt-cpp"
        assert rec.stars == 950
        assert rec.pros == ["well-maintained", "header-only"]

    def test_recommendation_defaults(self, session):
        """DependencyRecommendation fields have expected defaults."""
        comp = Component(name="MyMod", namespace="mod")
        session.add(comp)
        session.flush()

        rec = DependencyRecommendation(component_id=comp.id, name="libxyz")
        session.add(rec)
        session.flush()

        assert rec.github_url == ""
        assert rec.description == ""
        assert rec.version == ""
        assert rec.stars == 0
        assert rec.license == ""
        assert rec.last_updated == ""
        assert rec.pros is None
        assert rec.cons is None
        assert rec.relevant_hlrs is None
        assert rec.relevant_structures is None
        assert rec.summary == ""
        assert rec.status == "pending"

    def test_recommendation_repr(self, session):
        """DependencyRecommendation __repr__ shows name and status."""
        comp = Component(name="Svc", namespace="svc")
        session.add(comp)
        session.flush()

        rec = DependencyRecommendation(component_id=comp.id, name="boost", status="approved")
        session.add(rec)
        session.flush()
        assert repr(rec) == "boost (approved)"