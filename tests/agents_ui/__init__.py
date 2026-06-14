"""Agent UI screenshot tests — renders requirements pages from LLM decomposition data.

Loads the raw LLM response from ``tests/agents/__data__/``, constructs
mock requirements data dicts, patches the NiceGUI data layer, and
captures screenshots of the rendered HLR cards and LLR tables.

Run::

    pytest tests/agents_ui/ -v -s

These tests depend on the agent integration tests having already run and
saved artifacts to ``tests/agents/__data__/``.  If the artifacts don't
exist, the tests are skipped.
"""

import pytest

# Register the screenshot marker in case it's not in pyproject.toml
pytest.mark.screenshot  # noqa: B018 — just ensure the name is valid