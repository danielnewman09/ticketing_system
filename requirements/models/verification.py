from django.db import models


VERIFICATION_METHODS = ["automated", "review", "inspection"]


class VerificationMethod(models.Model):
    """A structured verification procedure for a low-level requirement.

    Groups pre-conditions, actions, and post-conditions into a coherent
    test specification that maps directly to code assertions.
    """

    VERIFICATION_CHOICES = [
        (m, m.capitalize()) for m in VERIFICATION_METHODS
    ]

    low_level_requirement = models.ForeignKey(
        "requirements.LowLevelRequirement",
        on_delete=models.CASCADE,
        related_name="verifications",
    )
    method = models.CharField(max_length=20, choices=VERIFICATION_CHOICES)
    test_name = models.CharField(
        max_length=300,
        blank=True,
        help_text="Test that verifies this (e.g., 'test_press_addition_key')",
    )
    description = models.TextField(
        blank=True,
        help_text="Free-text summary of what this verification does",
    )

    class Meta:
        app_label = "requirements"
        db_table = "verification_methods"

    def __str__(self):
        parts = [self.get_method_display()]
        if self.test_name:
            parts.append(f"[{self.test_name}]")
        return " - ".join(parts)

    def to_prompt_text(self):
        """Format this verification as text for LLM prompts."""
        parts = [self.method]
        if self.test_name:
            parts.append(self.test_name)
        if self.description:
            parts.append(self.description)
        return " — ".join(parts)

    @property
    def preconditions(self):
        return self.conditions.filter(phase="pre").order_by("order")

    @property
    def postconditions(self):
        return self.conditions.filter(phase="post").order_by("order")


CONDITION_OPERATORS = [
    ("==", "equals"),
    ("!=", "not equals"),
    ("<", "less than"),
    (">", "greater than"),
    ("<=", "less than or equal"),
    (">=", "greater than or equal"),
    ("is_true", "is true"),
    ("is_false", "is false"),
    ("contains", "contains"),
    ("not_null", "is not null"),
]


class VerificationCondition(models.Model):
    """A pre- or post-condition asserting a member variable's expected state.

    References a specific member by qualified name (e.g.,
    ``calc::core::Calculator::operation``) and an expected value.
    Optionally links to an OntologyNode for the owning class/struct.
    """

    PHASE_CHOICES = [
        ("pre", "Pre-condition"),
        ("post", "Post-condition"),
    ]

    verification = models.ForeignKey(
        VerificationMethod,
        on_delete=models.CASCADE,
        related_name="conditions",
    )
    phase = models.CharField(max_length=4, choices=PHASE_CHOICES)
    order = models.PositiveIntegerField(default=0)
    ontology_node = models.ForeignKey(
        "codebase.OntologyNode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Owning class/struct in the ontology graph",
    )
    member_qualified_name = models.CharField(
        max_length=500,
        help_text="Fully qualified member name (e.g., calc::core::Calculator::operation)",
    )
    operator = models.CharField(
        max_length=20,
        choices=CONDITION_OPERATORS,
        default="==",
    )
    expected_value = models.CharField(
        max_length=500,
        help_text="Expected value or state (e.g., Operation::Addition)",
    )

    class Meta:
        app_label = "requirements"
        db_table = "verification_conditions"
        ordering = ["phase", "order"]

    def __str__(self):
        return f"{self.member_qualified_name} {self.operator} {self.expected_value}"


class VerificationAction(models.Model):
    """An ordered step/stimulus between pre- and post-conditions.

    Represents an operation performed during the verification, such as
    pressing a button or invoking a method.
    """

    verification = models.ForeignKey(
        VerificationMethod,
        on_delete=models.CASCADE,
        related_name="actions",
    )
    order = models.PositiveIntegerField(default=0)
    description = models.TextField(
        help_text="Human-readable description (e.g., 'Press the + button')",
    )
    ontology_node = models.ForeignKey(
        "codebase.OntologyNode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Design entity being acted upon (e.g., OperatorButton)",
    )
    member_qualified_name = models.CharField(
        max_length=500,
        blank=True,
        help_text="Specific member invoked (e.g., calc::gui::OperatorButton::onClick)",
    )

    class Meta:
        app_label = "requirements"
        db_table = "verification_actions"
        ordering = ["order"]

    def __str__(self):
        return self.description[:80]
