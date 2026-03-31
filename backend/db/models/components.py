"""Component, Language, BuildSystem, TestFramework, DependencyManager, Dependency models."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, ForeignKey, Integer, String, Table, Text, Boolean, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

# Many-to-many: which components use which dependencies
dependency_components = Table(
    "dependency_components",
    Base.metadata,
    Column("dependency_id", Integer, ForeignKey("dependencies.id", ondelete="CASCADE"), primary_key=True),
    Column("component_id", Integer, ForeignKey("components.id", ondelete="CASCADE"), primary_key=True),
)

if TYPE_CHECKING:
    from backend.db.models.ontology import OntologyNode
    from backend.db.models.requirements import HighLevelRequirement, LowLevelRequirement
    from backend.db.models.tickets import Ticket


class Component(Base):
    __tablename__ = "components"
    __table_args__ = (
        UniqueConstraint("name", "parent_id", name="unique_component_name_per_parent"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    namespace: Mapped[str] = mapped_column(String(200), default="", server_default="")
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("components.id", ondelete="CASCADE"), nullable=True)
    language_id: Mapped[Optional[int]] = mapped_column(ForeignKey("languages.id", ondelete="CASCADE"), nullable=True)

    parent: Mapped[Optional[Component]] = relationship("Component", remote_side="Component.id", back_populates="children")
    children: Mapped[list[Component]] = relationship("Component", back_populates="parent")
    language: Mapped[Optional[Language]] = relationship("Language", back_populates="environment_components")

    # Reverse relationships
    high_level_requirements: Mapped[list[HighLevelRequirement]] = relationship("HighLevelRequirement", back_populates="component")
    ontology_nodes: Mapped[list[OntologyNode]] = relationship("OntologyNode", back_populates="component")
    dependencies: Mapped[list[Dependency]] = relationship(
        "Dependency", secondary=dependency_components, back_populates="components",
    )

    def __repr__(self):
        return self.name

    @property
    def full_namespace(self) -> str:
        """Return the namespace, falling back to parent-prefixed name."""
        if self.namespace:
            return self.namespace
        return ""

    def to_prompt_text(self):
        lines = [f"Component: {self.name}"]
        if self.namespace:
            lines.append(f"  Namespace: {self.namespace}")
        if self.description:
            lines.append(f"  Description: {self.description}")
        if self.parent_id:
            lines.append(f"  Parent: {self.parent.name}")
        if self.language_id:
            lines.append(f"  Language: {self.language.name}")
        if self.children:
            lines.append(f"  Children: {', '.join(c.name for c in self.children)}")
        return "\n".join(lines)


class Language(Base):
    __tablename__ = "languages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    version: Mapped[str] = mapped_column(String(50), default="", server_default="")

    environment_components: Mapped[list[Component]] = relationship("Component", back_populates="language")
    build_systems: Mapped[list[BuildSystem]] = relationship("BuildSystem", back_populates="language")
    test_frameworks: Mapped[list[TestFramework]] = relationship("TestFramework", back_populates="language")
    dependency_managers: Mapped[list[DependencyManager]] = relationship("DependencyManager", back_populates="language")

    def __repr__(self):
        if self.version:
            return f"{self.name} {self.version}"
        return self.name


class BuildSystem(Base):
    __tablename__ = "build_systems"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    config_file: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(50), default="", server_default="")

    language: Mapped[Language] = relationship("Language", back_populates="build_systems")

    def __repr__(self):
        return self.name


class TestFramework(Base):
    __tablename__ = "test_frameworks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    config_file: Mapped[str] = mapped_column(String(255), nullable=False)
    test_discovery_path: Mapped[str] = mapped_column(String(255), default="", server_default="")

    language: Mapped[Language] = relationship("Language", back_populates="test_frameworks")

    def __repr__(self):
        return self.name


class DependencyManager(Base):
    __tablename__ = "dependency_managers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    manifest_file: Mapped[str] = mapped_column(String(255), nullable=False)
    lock_file: Mapped[str] = mapped_column(String(255), default="", server_default="")

    language: Mapped[Language] = relationship("Language", back_populates="dependency_managers")
    dependencies: Mapped[list[Dependency]] = relationship("Dependency", back_populates="manager")

    def __repr__(self):
        return self.name


class Dependency(Base):
    __tablename__ = "dependencies"
    __table_args__ = (
        UniqueConstraint("manager_id", "name", name="unique_dependency_per_manager"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("dependency_managers.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(100), default="", server_default="")
    github_url: Mapped[str] = mapped_column(String(500), default="", server_default="")
    is_dev: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    # Doxygen indexing config — controls how doxygen-index processes this dependency
    index_file_patterns: Mapped[str] = mapped_column(String(200), default="*.h *.hpp", server_default="*.h *.hpp")
    index_subdir: Mapped[str] = mapped_column(String(200), default="", server_default="")
    index_exclude_patterns: Mapped[str] = mapped_column(String(500), default="", server_default="")
    index_recursive: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    manager: Mapped[DependencyManager] = relationship("DependencyManager", back_populates="dependencies")
    components: Mapped[list[Component]] = relationship(
        "Component", secondary=dependency_components, back_populates="dependencies",
    )

    def __repr__(self):
        if self.version:
            return f"{self.name}=={self.version}"
        return self.name


class DependencyRecommendation(Base):
    """A researched dependency recommendation awaiting human review."""
    __tablename__ = "dependency_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    component_id: Mapped[int] = mapped_column(ForeignKey("components.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    github_url: Mapped[str] = mapped_column(String(500), default="", server_default="")
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    version: Mapped[str] = mapped_column(String(100), default="", server_default="")
    stars: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    license: Mapped[str] = mapped_column(String(100), default="", server_default="")
    last_updated: Mapped[str] = mapped_column(String(50), default="", server_default="")
    pros: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    cons: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    relevant_hlrs: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    relevant_structures: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")

    component: Mapped[Component] = relationship("Component")

    def __repr__(self):
        return f"{self.name} ({self.status})"
