from django.db import models


class HighLevelRequirement(models.Model):
    actor = models.CharField(max_length=200, default="", help_text="Who performs the action (e.g., 'a developer')")
    action = models.CharField(max_length=200, default="", help_text="What they do (e.g., 'compiles')")
    subject = models.CharField(max_length=200, default="", help_text="What they act on (e.g., 'the codebase')")
    description = models.TextField(blank=True)

    class Meta:
        db_table = "high_level_requirements"

    def __str__(self):
        if self.actor or self.action or self.subject:
            return f"{self.actor} {self.action} {self.subject}"
        return self.description[:80] if self.description else f"HLR {self.pk}"

    @property
    def statement(self):
        return f"{self.actor} {self.action} {self.subject}"


class LowLevelRequirement(models.Model):
    high_level_requirement = models.ForeignKey(
        HighLevelRequirement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="low_level_requirements",
    )
    actor = models.CharField(max_length=200, default="", help_text="Who performs the action (e.g., 'the end user')")
    action = models.CharField(max_length=200, default="", help_text="What they do (e.g., 'presses the + button')")
    subject = models.CharField(max_length=200, default="", help_text="What they act on (e.g., 'in the GUI')")
    description = models.TextField(blank=True)
    components = models.ManyToManyField(
        "components.Component",
        related_name="low_level_requirements",
        blank=True,
        help_text="Components that implement this requirement",
    )

    class Meta:
        db_table = "low_level_requirements"

    def __str__(self):
        if self.actor or self.action or self.subject:
            return f"{self.actor} {self.action} {self.subject}"
        return self.description[:80] if self.description else f"LLR {self.pk}"

    @property
    def statement(self):
        return f"{self.actor} {self.action} {self.subject}"


VERIFICATION_METHODS = ["automated", "review", "inspection"]


class LLRVerification(models.Model):
    VERIFICATION_CHOICES = [
        (m, m.capitalize()) for m in VERIFICATION_METHODS
    ]

    low_level_requirement = models.ForeignKey(
        LowLevelRequirement,
        on_delete=models.CASCADE,
        related_name="verifications",
    )
    method = models.CharField(max_length=20, choices=VERIFICATION_CHOICES)
    confirmation = models.TextField(
        blank=True,
        help_text="How the behavior is confirmed (e.g., 'the operator field is populated with the ADDITION enum value')",
    )
    test_name = models.CharField(
        max_length=300,
        blank=True,
        help_text="Test that verifies this (e.g., 'user_presses_addition_key')",
    )

    class Meta:
        db_table = "llr_verifications"

    def __str__(self):
        parts = [self.get_method_display()]
        if self.confirmation:
            parts.append(self.confirmation[:60])
        if self.test_name:
            parts.append(f"[{self.test_name}]")
        return " - ".join(parts)


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
