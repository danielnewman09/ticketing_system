from django.db import models

from .hlr import HighLevelRequirement


class LowLevelRequirement(models.Model):
    high_level_requirement = models.ForeignKey(
        HighLevelRequirement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="low_level_requirements",
    )
    description = models.TextField()
    components = models.ManyToManyField(
        "components.Component",
        related_name="low_level_requirements",
        blank=True,
        help_text="Components that implement this requirement",
    )
    triples = models.ManyToManyField(
        "codebase.OntologyTriple",
        related_name="low_level_requirements",
        blank=True,
        help_text="Ontology triples that express this requirement",
    )

    class Meta:
        app_label = "requirements"
        db_table = "low_level_requirements"

    def __str__(self):
        return self.description[:80] if self.description else f"LLR {self.pk}"


class TicketRequirement(models.Model):
    ticket = models.ForeignKey(
        "tickets.Ticket", on_delete=models.CASCADE
    )
    low_level_requirement = models.ForeignKey(
        LowLevelRequirement, on_delete=models.CASCADE
    )

    class Meta:
        app_label = "requirements"
        db_table = "ticket_requirements"
        unique_together = [("ticket", "low_level_requirement")]

    def __str__(self):
        return f"Ticket {self.ticket_id} -> LLR {self.low_level_requirement_id}"
