from django.db import models


# ---------------------------------------------------------------------------
# External (unmanaged) models — populated by doxygen or similar tooling
# into the 'codebase' database. Django never migrates these.
# ---------------------------------------------------------------------------

class CodebaseFile(models.Model):
    refid = models.TextField(unique=True)
    name = models.TextField()
    path = models.TextField(null=True, blank=True)
    language = models.TextField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "files"

    def __str__(self):
        return self.name


class Namespace(models.Model):
    refid = models.TextField(unique=True)
    name = models.TextField()
    qualified_name = models.TextField()

    class Meta:
        managed = False
        db_table = "namespaces"

    def __str__(self):
        return self.qualified_name


class Compound(models.Model):
    """Classes, structs, unions, enums from the codebase."""

    refid = models.TextField(unique=True)
    kind = models.TextField()
    name = models.TextField()
    qualified_name = models.TextField()
    file = models.ForeignKey(
        CodebaseFile,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        db_column="file_id",
    )
    line_number = models.IntegerField(null=True, blank=True)
    brief_description = models.TextField(null=True, blank=True)
    detailed_description = models.TextField(null=True, blank=True)
    base_classes = models.TextField(null=True, blank=True)
    is_final = models.IntegerField(default=0)
    is_abstract = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = "compounds"

    def __str__(self):
        return self.qualified_name


class Member(models.Model):
    """Functions, variables, typedefs belonging to a compound."""

    refid = models.TextField(unique=True)
    compound = models.ForeignKey(
        Compound,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        db_column="compound_id",
    )
    kind = models.TextField()
    name = models.TextField()
    qualified_name = models.TextField()
    type = models.TextField(null=True, blank=True)
    definition = models.TextField(null=True, blank=True)
    argsstring = models.TextField(null=True, blank=True)
    file = models.ForeignKey(
        CodebaseFile,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        db_column="file_id",
    )
    line_number = models.IntegerField(null=True, blank=True)
    brief_description = models.TextField(null=True, blank=True)
    detailed_description = models.TextField(null=True, blank=True)
    protection = models.TextField(null=True, blank=True)
    is_static = models.IntegerField(default=0)
    is_const = models.IntegerField(default=0)
    is_constexpr = models.IntegerField(default=0)
    is_virtual = models.IntegerField(default=0)
    is_inline = models.IntegerField(default=0)
    is_explicit = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = "members"

    def __str__(self):
        return self.qualified_name


class Parameter(models.Model):
    member = models.ForeignKey(
        Member,
        on_delete=models.DO_NOTHING,
        db_column="member_id",
    )
    position = models.IntegerField()
    name = models.TextField(null=True, blank=True)
    type = models.TextField()
    default_value = models.TextField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "parameters"

    def __str__(self):
        return f"{self.type} {self.name or ''}"


class SymbolRef(models.Model):
    from_member = models.ForeignKey(
        Member,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        db_column="from_member_id",
    )
    to_member_refid = models.TextField()
    to_member_name = models.TextField()
    relationship = models.TextField()

    class Meta:
        managed = False
        db_table = "symbol_refs"

    def __str__(self):
        return f"{self.from_member_id} {self.relationship} {self.to_member_name}"


class Include(models.Model):
    file = models.ForeignKey(
        CodebaseFile,
        on_delete=models.DO_NOTHING,
        db_column="file_id",
    )
    included_file = models.TextField()
    included_refid = models.TextField(null=True, blank=True)
    is_local = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = "includes"

    def __str__(self):
        return self.included_file


class Metadata(models.Model):
    key = models.TextField(primary_key=True)
    value = models.TextField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "metadata"

    def __str__(self):
        return f"{self.key}={self.value}"


# ---------------------------------------------------------------------------
# Ontology graph layer (Django-managed, lives in the default database)
# Provides typed relationships and design annotations on top of the
# external codebase index.
# ---------------------------------------------------------------------------

class OntologyNode(models.Model):
    """A node in the design ontology graph.

    Each node references a compound from the external codebase DB by refid,
    or can be a free-standing design concept (when compound_refid is blank).
    """

    NODE_KINDS = [
        ("class", "Class"),
        ("struct", "Struct"),
        ("enum", "Enum"),
        ("union", "Union"),
        ("namespace", "Namespace"),
        ("interface", "Interface"),
        ("concept", "Design Concept"),
    ]

    compound_refid = models.CharField(
        max_length=200, blank=True, default="",
        help_text="Refid linking to a compound in the codebase DB",
    )
    kind = models.CharField(max_length=20, choices=NODE_KINDS)
    name = models.CharField(max_length=200)
    qualified_name = models.CharField(max_length=500, blank=True, default="")
    description = models.TextField(blank=True)

    class Meta:
        db_table = "ontology_nodes"

    def __str__(self):
        return self.qualified_name or self.name

    def get_compound(self):
        """Resolve to the external Compound, if linked."""
        if not self.compound_refid:
            return None
        return Compound.objects.using("codebase").filter(
            refid=self.compound_refid,
        ).first()


class NamespaceNodeManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(kind="namespace")


class NamespaceNode(OntologyNode):
    """Proxy model for namespace nodes with hierarchy-aware methods."""

    objects = NamespaceNodeManager()

    class Meta:
        proxy = True

    def save(self, *args, **kwargs):
        self.kind = "namespace"
        super().save(*args, **kwargs)

    def get_children(self):
        """Return direct children (one level deep) based on qualified_name."""
        prefix = self.qualified_name + "::"
        return OntologyNode.objects.filter(
            qualified_name__startswith=prefix,
        ).exclude(
            qualified_name__regex=rf"^{self.qualified_name}::[^:]+::.+",
        )

    def get_descendants(self):
        """Return all nested nodes at any depth."""
        prefix = self.qualified_name + "::"
        return OntologyNode.objects.filter(qualified_name__startswith=prefix)

    def get_child_triples(self):
        """Return all triples where at least one endpoint is a direct child."""
        child_pks = set(self.get_children().values_list("pk", flat=True))
        return OntologyTriple.objects.select_related(
            "subject", "object",
        ).filter(
            models.Q(subject_id__in=child_pks) | models.Q(object_id__in=child_pks)
        )

    @staticmethod
    def parent_lookup():
        """Return a dict mapping qualified_name -> graph node ID for all namespaces."""
        return {
            n.qualified_name: f"node-{n.pk}"
            for n in NamespaceNode.objects.all()
        }

    @staticmethod
    def resolve_parent(qualified_name, ns_lookup):
        """Given a qualified_name and namespace lookup, return the parent graph ID or None."""
        parts = qualified_name.rsplit("::", 1)
        if len(parts) == 2 and parts[0] in ns_lookup:
            return ns_lookup[parts[0]]
        return None


PREDICATE_SUGGESTIONS = [
    "inherits",
    "composes",
    "aggregates",
    "depends_on",
    "calls",
    "implements",
    "uses",
]


class OntologyTriple(models.Model):
    """A semantic triple: subject --predicate--> object.

    Unifies ontology edges and requirement-to-ontology links into a single
    structure. The predicate is free text (commonly a verb like "inherits",
    "compiles", "displays").
    """

    subject = models.ForeignKey(
        OntologyNode, on_delete=models.CASCADE, related_name="triples_as_subject",
    )
    predicate = models.CharField(max_length=200)
    object = models.ForeignKey(
        OntologyNode, on_delete=models.CASCADE, related_name="triples_as_object",
    )

    class Meta:
        db_table = "ontology_triples"
        unique_together = [("subject", "predicate", "object")]

    def __str__(self):
        return f"{self.subject} --{self.predicate}--> {self.object}"
