from django.db import models
from django.utils import timezone
from components.models import Component, Language
from requirements.models import HighLevelRequirement, LowLevelRequirement


class Ticket(models.Model):
    PRIORITY_CHOICES = [
        ("critical", "Critical"),
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    ]
    COMPLEXITY_CHOICES = [
        ("small", "Small"),
        ("medium", "Medium"),
        ("large", "Large"),
    ]
    TYPE_CHOICES = [
        ("feature", "Feature"),
        ("bug", "Bug"),
        ("task", "Task"),
    ]

    title = models.CharField(max_length=200)
    priority = models.CharField(max_length=50, choices=PRIORITY_CHOICES, blank=True)
    complexity = models.CharField(max_length=50, choices=COMPLEXITY_CHOICES, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    author = models.CharField(max_length=200, blank=True)
    summary = models.TextField(blank=True)
    ticket_type = models.CharField(max_length=50, choices=TYPE_CHOICES, default="feature")
    parent = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children"
    )
    components = models.ManyToManyField(Component, related_name="tickets", blank=True)
    languages = models.ManyToManyField(Language, related_name="tickets", blank=True)
    requires_math = models.BooleanField(default=False)
    generate_tutorial = models.BooleanField(default=False)
    low_level_requirements = models.ManyToManyField(
        LowLevelRequirement,
        through="requirements.TicketRequirement",
        related_name="tickets",
        blank=True,
    )

    class Meta:
        db_table = "tickets"

    def __str__(self):
        return self.title

    def get_hlrs(self):
        """Derive high-level requirements transitively via linked LLRs."""
        return HighLevelRequirement.objects.filter(
            low_level_requirements__in=self.low_level_requirements.all()
        ).distinct()


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
    description = models.CharField(max_length=500, blank=True)

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
