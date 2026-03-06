from django.db import models


class HighLevelRequirement(models.Model):
    description = models.TextField()

    class Meta:
        db_table = "high_level_requirements"

    def __str__(self):
        return self.description[:80]


class LowLevelRequirement(models.Model):
    VERIFICATION_CHOICES = [
        ("automated", "Automated"),
        ("review", "Review"),
        ("inspection", "Inspection"),
    ]

    high_level_requirement = models.ForeignKey(
        HighLevelRequirement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="low_level_requirements",
    )
    description = models.TextField()
    verification = models.CharField(max_length=20, choices=VERIFICATION_CHOICES, default="review")

    class Meta:
        db_table = "low_level_requirements"

    def __str__(self):
        return self.description[:80]


class TicketRequirement(models.Model):
    ticket = models.ForeignKey(
        "tickets.Ticket", on_delete=models.CASCADE
    )
    low_level_requirement = models.ForeignKey(
        LowLevelRequirement, on_delete=models.CASCADE
    )

    class Meta:
        db_table = "ticket_requirements"
        unique_together = [("ticket", "low_level_requirement")]

    def __str__(self):
        return f"Ticket {self.ticket_id} -> LLR {self.low_level_requirement_id}"
