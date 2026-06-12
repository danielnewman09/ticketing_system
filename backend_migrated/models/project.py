"""ProjectMeta node model (:ProjectMeta label in Neo4j).

Singleton node storing project-level settings — name, description, and
working directory. Extends CodeGraphNode to share serialization,
registry, and relationship introspection infrastructure.

The singleton is identified by ``refid = "project"``.  All code that
needs the project meta should call
``ProjectMeta.nodes.get(refid="project")`` or use the helpers in
``frontend_migrated.data.project``.
"""

from neomodel import StringProperty, ArrayProperty, RelationshipTo

from codegraph.models.tags import CodeGraphNode

# Use the combined metaclass from CodeGraphNode so that StructuredNode
# machinery is initialised correctly.
from neomodel import StructuredNode


class ProjectMeta(StructuredNode, CodeGraphNode):
    """Project-level metadata node — :ProjectMeta label in Neo4j.

    Singleton node that stores project-wide settings.  The singleton
    instance is identified by ``refid = "project"``, which serves as
    the unique lookup key (replacing the SQLAlchemy auto-increment
    ``id=1`` pattern).

    ProjectMeta COMPOSES Components — the project owns its top-level
    components in the same way that a Component COMPOSES sub-components
    or HLRs.  This edge lets the project page discover all components
    directly from the ProjectMeta node without relying solely on the
    Language→Component traversal.

    Attributes:
        name: Project name (e.g. 'calculator-engine'), inherited from
            CodeGraphNode.
        refid: Fixed as ``'project'`` — unique lookup key for the
            singleton. Inherited from CodeGraphNode.
        source: Project source identifier, inherited from CodeGraphNode.
        description: Human-readable project description.
        working_directory: Filesystem path where the project lives
            (e.g. '/home/user/dev/calculator-engine').
    """

    # --- Project metadata ---
    description = StringProperty(default="",
        help_text="Human-readable project description.")
    working_directory = StringProperty(default="",
        help_text="Filesystem path where the project lives "
                  "(e.g. '/home/user/dev/calculator-engine').")

    # --- Workflow tags ---
    #
    #  Tags reflect deterministic state checks on the project's lifecycle:
    #
    #  • "scaffolded"  — CMakeLists.txt exists on disk
    #  • "passing"     — project builds successfully
    #  • "failing"     — project build fails
    #
    tags = ArrayProperty(StringProperty(), default=list,
        help_text="Workflow tags: 'scaffolded', 'passing', 'failing'.")

    # --- COMPOSES relationship to Components ---
    #
    #  • COMPOSES (outgoing)  — ProjectMeta → Component
    #    The project directly composes its top-level components.
    #    This mirrors the Component→Component COMPOSES edge used for
    #    sub-components, giving a uniform hierarchy:
    #
    #      ProjectMeta -[:COMPOSES]-> Component -[:COMPOSES]-> Component
    #                                              ↕
    #                                    HLR -[:COMPOSES]-> LLR
    #
    #    The reverse traversal (Component→ProjectMeta) is available
    #    via the ``project`` relationship.
    # --------------------------------------------------------------------------
    components = RelationshipTo(
        'backend_migrated.models.component.Component', 'COMPOSES')

    # --- Serialization contract ---
    _llm_fields: set[str] = {
        "name", "description", "working_directory", "tags",
    }

    # ------------------------------------------------------------------
    # Singleton helpers
    # ------------------------------------------------------------------

    @classmethod
    def get_singleton(cls) -> "ProjectMeta":
        """Return the singleton ProjectMeta node, creating it if absent.

        Uses ``refid = 'project'`` as the stable lookup key.

        Returns:
            The single ProjectMeta node.
        """
        try:
            node = cls.nodes.get(refid="project")
        except cls.DoesNotExist:
            node = cls(refid="project", name="", description="",
                       working_directory="").save()
        return node

    @classmethod
    def update_singleton(cls, *, name: str = "", description: str = "",
                         working_directory: str = "") -> "ProjectMeta":
        """Update the singleton ProjectMeta node, creating it if absent.

        Args:
            name: Project name.
            description: Project description.
            working_directory: Filesystem path for the project.

        Returns:
            The updated (and saved) ProjectMeta node.
        """
        node = cls.get_singleton()
        node.name = name
        node.description = description
        node.working_directory = working_directory
        return node.save()