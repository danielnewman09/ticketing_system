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


class Ticket(models.Model):
    title = models.CharField(max_length=200)
    priority = models.CharField(max_length=50, blank=True, null=True)
    complexity = models.CharField(max_length=50, blank=True, null=True)
    created_date = models.CharField(max_length=50, blank=True, null=True)
    author = models.CharField(max_length=200, blank=True, null=True)
    summary = models.TextField(blank=True, null=True)
    ticket_type = models.CharField(max_length=50, default="feature")
    parent = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children"
    )
    target_components = models.CharField(max_length=500, blank=True, null=True)
    languages = models.CharField(max_length=200, default="C++")
    requires_math = models.BooleanField(default=False)
    generate_tutorial = models.BooleanField(default=False)
    last_modified = models.CharField(max_length=50, blank=True, null=True)
    high_level_requirements = models.ManyToManyField(
        HighLevelRequirement,
        through="TicketRequirement",
        related_name="tickets",
        blank=True,
    )

    class Meta:
        db_table = "tickets"

    def __str__(self):
        return self.title


class TicketRequirement(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE)
    high_level_requirement = models.ForeignKey(HighLevelRequirement, on_delete=models.CASCADE)

    class Meta:
        db_table = "ticket_requirements"
        unique_together = [("ticket", "high_level_requirement")]

    def __str__(self):
        return f"Ticket {self.ticket_id} -> HLR {self.high_level_requirement_id}"


class TicketAcceptanceCriteria(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="acceptance_criteria")
    description = models.TextField()

    class Meta:
        db_table = "ticket_acceptance_criteria"

    def __str__(self):
        return self.description[:80]


class TicketFile(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="files")
    file_path = models.CharField(max_length=500)
    change_type = models.CharField(max_length=20)
    description = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        db_table = "ticket_files"

    def __str__(self):
        return f"{self.change_type}: {self.file_path}"


class TicketReference(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="references")
    ref_type = models.CharField(max_length=50)
    ref_target = models.CharField(max_length=200)

    class Meta:
        db_table = "ticket_references"

    def __str__(self):
        return f"{self.ref_type}: {self.ref_target}"
