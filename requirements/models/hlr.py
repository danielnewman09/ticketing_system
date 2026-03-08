from django.db import models


class HighLevelRequirement(models.Model):
    actor = models.CharField(max_length=200, default="", help_text="Who performs the action (e.g., 'a developer')")
    action = models.CharField(max_length=200, default="", help_text="What they do (e.g., 'compiles')")
    subject = models.CharField(max_length=200, default="", help_text="What they act on (e.g., 'the codebase')")
    description = models.TextField(blank=True)
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
        if self.actor or self.action or self.subject:
            return f"{self.actor} {self.action} {self.subject}"
        return self.description[:80] if self.description else f"HLR {self.pk}"

    @property
    def statement(self):
        return f"{self.actor} {self.action} {self.subject}"
