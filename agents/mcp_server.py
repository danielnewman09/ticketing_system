"""
MCP server that exposes the decompose_hlr agent as a tool.

Run with:
    python -m agents.mcp_server
"""

import json
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import transaction

from mcp.server.fastmcp import FastMCP

from agents.decompose_hlr import decompose
from requirements.models import HighLevelRequirement, LowLevelRequirement, VerificationMethod

mcp = FastMCP("ticketing-system")


@mcp.tool()
def decompose_requirement(
    description: str,
    model: str = "claude-sonnet-4-20250514",
    dry_run: bool = False,
) -> str:
    """Decompose a high-level requirement into low-level requirements
    with verification methods.

    Args:
        description: Human-written high-level requirement description.
        model: Claude model to use.
        dry_run: If true, return the decomposition without saving to the database.
    """
    result = decompose(description, model=model)

    if not dry_run:
        with transaction.atomic():
            hlr = HighLevelRequirement.objects.create(
                description=description,
            )
            for llr_data in result.low_level_requirements:
                llr = LowLevelRequirement.objects.create(
                    high_level_requirement=hlr,
                    description=llr_data.description,
                )
                for v_data in llr_data.verifications:
                    VerificationMethod.objects.create(
                        low_level_requirement=llr,
                        method=v_data.method,
                        test_name=v_data.test_name,
                        description=v_data.description,
                    )

    output = result.model_dump()
    if not dry_run:
        output["hlr_id"] = hlr.pk
    return json.dumps(output, indent=2)


if __name__ == "__main__":
    mcp.run()
