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


class LLRVerification(models.Model):
    """Deprecated: replaced by VerificationMethod. Kept for data migration."""

    VERIFICATION_METHODS = ["automated", "review", "inspection"]
    VERIFICATION_CHOICES = [
        (m, m.capitalize()) for m in VERIFICATION_METHODS
    ]

    low_level_requirement = models.ForeignKey(
        LowLevelRequirement,
        on_delete=models.CASCADE,
        related_name="legacy_verifications",
    )
    method = models.CharField(max_length=20, choices=VERIFICATION_CHOICES)
    confirmation = models.TextField(blank=True)
    test_name = models.CharField(max_length=300, blank=True)

    class Meta:
        app_label = "requirements"
        db_table = "llr_verifications"

    def __str__(self):
        return f"{self.get_method_display()} - {self.test_name or self.confirmation[:60]}"


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
