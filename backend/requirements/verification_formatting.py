"""Constants for verification data.

Provides the VERIFICATION_METHODS and CONDITION_OPERATORS constants
previously defined on deleted models.
"""

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
