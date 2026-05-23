"""Formatting helpers and constants for verification data.

Replaces the SQLAlchemy model __repr__ and to_prompt_text methods
that were removed in Phase 3 along with the deleted models.

Also provides the VERIFICATION_METHODS and CONDITION_OPERATORS
constants that were previously defined on the deleted model file.
"""

from backend.db.neo4j.repositories.models.verification import (
    ActionNode,
    ConditionNode,
    VerificationMethodNode,
)

# Constants previously on backend.db.models.verification
VERIFICATION_METHODS = ["automated", "review", "inspection"]

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


def format_verification_method(vm: VerificationMethodNode) -> str:
    """Format a VerificationMethodNode for display (replaces ORM __repr__)."""
    parts = [vm.method]
    if vm.test_name:
        parts.append(f"[{vm.test_name}]")
    return " - ".join(parts)


def format_verification_method_prompt(vm: VerificationMethodNode) -> str:
    """Format a VerificationMethodNode for LLM prompts (replaces ORM to_prompt_text)."""
    parts = [vm.method]
    if vm.test_name:
        parts.append(vm.test_name)
    if vm.description:
        parts.append(vm.description)
    return " — ".join(parts)


def format_condition(c: ConditionNode) -> str:
    """Format a ConditionNode for display (replaces ORM __repr__)."""
    return f"{c.subject_qualified_name} {c.operator} {c.expected_value}"


def format_action(a: ActionNode) -> str:
    """Format an ActionNode for display (replaces ORM __repr__)."""
    return a.description[:80]
