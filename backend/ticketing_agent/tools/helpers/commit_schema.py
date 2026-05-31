"""Schema builder for the commit_design_and_verifications tool."""


def commit_tool_schema() -> dict:
    """Build the JSON schema for commit_design_and_verifications.

    Manually constructs the schema because DesignAndVerificationSchema
    contains neomodel-backed types that Pydantic cannot generate JSON
    schema for.
    """
    return {
        "type": "object",
        "properties": {
            "oo_design": {
                "type": "object",
                "description": "The final OO class diagram design",
                "properties": {
                    "module_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Module/namespace names used in the design",
                    },
                    "classes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "module": {"type": "string"},
                                "brief_description": {"type": "string"},
                                "kind": {"type": "string"},
                                "requirement_ids": {"type": "array", "items": {"type": "string"}},
                                "inherits_from": {"type": "array", "items": {"type": "string"}},
                                "realizes": {"type": "array", "items": {"type": "string"}},
                                "is_intercomponent": {"type": "boolean"},
                                "specialization": {"type": "string"},
                                "attributes": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "visibility": {"type": "string"},
                                            "type_signature": {"type": "string"},
                                            "brief_description": {"type": "string"},
                                        },
                                    },
                                },
                                "methods": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "visibility": {"type": "string"},
                                            "type_signature": {"type": "string"},
                                            "argsstring": {"type": "string"},
                                            "brief_description": {"type": "string"},
                                        },
                                    },
                                },
                            },
                        },
                    },
                    "interfaces": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "module": {"type": "string"},
                                "brief_description": {"type": "string"},
                                "kind": {"type": "string"},
                                "requirement_ids": {"type": "array", "items": {"type": "string"}},
                                "is_intercomponent": {"type": "boolean"},
                                "methods": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "visibility": {"type": "string"},
                                            "type_signature": {"type": "string"},
                                            "argsstring": {"type": "string"},
                                            "brief_description": {"type": "string"},
                                        },
                                    },
                                },
                            },
                        },
                    },
                    "enums": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "module": {"type": "string"},
                                "brief_description": {"type": "string"},
                                "kind": {"type": "string"},
                                "values": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "brief_description": {"type": "string"},
                                        },
                                    },
                                },
                            },
                        },
                    },
                    "associations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "subject": {"type": "string"},
                                "predicate": {"type": "string"},
                                "object": {"type": "string"},
                                "requirement_ids": {"type": "array", "items": {"type": "string"}},
                                "mechanism": {"type": "string"},
                            },
                        },
                    },
                },
            },
            "verifications": {
                "type": "object",
                "description": (
                    "Map of LLR ID (integer string) to list of verification procedures. "
                    "Keys MUST be LLR IDs like \"1\", \"2\" — NOT test names. "
                    "Example: {\"1\": [...], \"2\": [...]}"
                ),
                "additionalProperties": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "method": {"type": "string", "description": "Verification method (e.g., 'unit_test', 'integration_test')"},
                            "test_name": {"type": "string", "description": "Name of the test (e.g., 'test_calculator_add')"},
                            "description": {"type": "string", "description": "Brief explanation of the verification"},
                            "preconditions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "operator": {"type": "string"},
                                        "expected_value": {"type": "string"},
                                        "subject_qualified_name": {"type": "string"},
                                        "object_qualified_name": {"type": "string"},
                                    },
                                },
                            },
                            "actions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "description": {"type": "string"},
                                        "caller_qualified_name": {"type": "string"},
                                        "callee_qualified_name": {"type": "string"},
                                    },
                                },
                            },
                            "postconditions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "operator": {"type": "string"},
                                        "expected_value": {"type": "string"},
                                        "subject_qualified_name": {"type": "string"},
                                        "object_qualified_name": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
        "required": ["oo_design"],
    }
