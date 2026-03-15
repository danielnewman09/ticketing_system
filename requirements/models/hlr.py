from django.db import models


class HighLevelRequirement(models.Model):
    description = models.TextField()
    component = models.ForeignKey(
        "components.Component",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="high_level_requirements",
        help_text="Architectural component this requirement belongs to",
    )
    dependency_context = models.JSONField(
        null=True,
        blank=True,
        help_text="Dependency assessment from the assess_dependencies agent",
    )
    triples = models.ManyToManyField(
        "codebase.OntologyTriple",
        related_name="high_level_requirements",
        blank=True,
        help_text="Ontology triples that express this requirement",
    )

    class Meta:
        app_label = "requirements"
        db_table = "high_level_requirements"

    def __str__(self):
        return self.description[:80] if self.description else f"HLR {self.pk}"
