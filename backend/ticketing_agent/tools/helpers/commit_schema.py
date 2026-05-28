"""Schema builder for the commit_design_and_verifications tool."""

from backend.codebase.schemas import DesignAndVerificationSchema


def commit_tool_schema() -> dict:
    """Build the JSON schema for commit_design_and_verifications.

    Customizes the verifications field to explicitly describe the LLR ID key
    format, which LLMs frequently get wrong.
    """
    schema = DesignAndVerificationSchema.model_json_schema()
    if "properties" in schema and "verifications" in schema["properties"]:
        schema["properties"]["verifications"]["description"] = (
            "Map of LLR ID (integer string) to list of verification procedures. "
            "Keys MUST be LLR IDs like \"1\", \"2\" — NOT test names. "
            "Example: {\"1\": [...], \"2\": [...]}"
        )
    return schema
