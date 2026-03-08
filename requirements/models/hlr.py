from django.db import models


class HighLevelRequirement(models.Model):
    description = models.TextField()
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
