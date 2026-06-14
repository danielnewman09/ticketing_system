"""Agent integration tests — real LLM calls with full traceability.

These tests call the LLM backend configured in ``.env`` and save all
intermediate data (prompts, tool schemas, model responses, parsed
results) to ``tests/agents/__data__/`` for offline inspection.

Mark all tests in this package with ``@pytest.mark.agent`` so they can
be selected or deselected as a group::

    # Run only agent tests
    pytest tests/agents/ -m agent

    # Skip agent tests (they hit the network)
    pytest -m "not agent"
"""

import pytest

# Convenience marker — registered in pyproject.toml [tool.pytest.ini_options].mark.
# Use ``pytest -m agent`` to run only agent tests,
# ``pytest -m "not agent"`` to skip them.
agent = pytest.mark.agent